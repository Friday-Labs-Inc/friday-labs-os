"""Core Hub node — Phase 2 walking-skeleton spine.

Three jobs, faithful to the interface contract and the Nav2 reference:

  1. module-registry      — serves RegisterModule, broadcasts ModulePresence.
  2. system-health-manager (lite) — subscribes each module's heartbeat and
     classifies OK / DEGRADED / DEAD against the locked deadlines.
  3. safety-supervisor (lite) — a lifecycle_manager that brings the managed
     module nodes up (configure -> activate) deterministically on startup.

Real fault recovery, authority-lease, and full health live in later phases.
"""

import collections

import rclpy
from lifecycle_msgs.msg import State as LCState
from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from friday_msgs.msg import AuthorityLease, Heartbeat, Mark1Header, ModulePresence
from friday_msgs.srv import RegisterModule, RequestAuthority
from friday_module_agent import authority, protocol, qos

from friday_core_hub.registry import ModuleRegistry

PRESENCE_TOPIC = '/mark1/system/presence'
REGISTER_SERVICE = '/mark1/system/register_module'

DEGRADED_AGE_S = 1.0      # ~3 missed 200 ms heartbeats / 500 ms deadlines
DEAD_AGE_S = 1.5          # liveliness lease + margin
LIVENESS_OK = 'OK'
LIVENESS_DEGRADED = 'DEGRADED'
LIVENESS_DEAD = 'DEAD'

# Authority-lease state machine (Authority Lease Protocol — "Authority Return").
AUTH_OBSERVING = 'OBSERVING'     # boot: listen for an existing holder before taking the lease
AUTH_REQUESTING = 'REQUESTING'   # rejoin: asking the current holder for a clean hand-back
AUTH_HOLDING = 'HOLDING'         # this node holds the lease and publishes it
OBSERVE_WINDOW_S = 2.5           # how long to watch /authority before deciding clean-boot vs rejoin
QUIET_WINDOW_S = 0.5             # release -> acquire gap during a hand-back (neither side commands)
REQUEST_RETRY_S = 1.0            # re-ask if a return isn't granted yet (rover not stable)


def _t2s(t) -> float:
    """builtin_interfaces/Time -> unix seconds (0 if unset)."""
    return t.sec + t.nanosec * 1e-9


class CoreHub(Node):
    """The orchestration spine all module agents register to."""

    def __init__(self):
        super().__init__('core_hub')
        self.declare_parameter('managed_nodes', [''])
        self.declare_parameter('autostart_delay_s', 3.0)
        self.declare_parameter('authority_holder', 'MARK1-CORE-001')

        self._cb_group = ReentrantCallbackGroup()
        self._registry = ModuleRegistry()
        self._hb_subs = {}            # module_id -> Subscription
        self._last_seen_ns = {}       # module_id -> int
        self._liveness = {}           # module_id -> LIVENESS_*

        self._presence_pub = self.create_publisher(
            ModulePresence, PRESENCE_TOPIC, qos.state_default())
        self._register_srv = self.create_service(
            RegisterModule, REGISTER_SERVICE, self._on_register,
            callback_group=self._cb_group)

        self.create_timer(0.5, self._check_liveness)

        # --- safety-supervisor: authority lease + safety pulse (Phase 4) ---
        # Authority is *earned through a boot observe-window*, not assumed: a clean
        # boot (nobody else holding) takes the lease at epoch 1; a rejoin (Telemetry
        # already holds after a failover) requests a clean hand-back instead of
        # publishing a competing lease. The safety pulse runs whenever Core is up.
        self._authority_holder = self.get_parameter('authority_holder').value
        self._auth_state = AUTH_OBSERVING
        self._rejoined = False
        self._epoch = 0
        self._pending_epoch = 0
        self._safety_seq = 0
        self._observed_holder = ''
        self._observed_epoch = 0
        self._observed_expiry_s = 0.0
        self._quiet_timer = None
        self._retry_timer = None

        self._authority_pub = self.create_publisher(
            AuthorityLease, '/mark1/system/authority', qos.critical_reliable())
        self._safety_pub = self.create_publisher(
            Heartbeat, '/mark1/system/safety_pulse', qos.sensor_stream())
        self._authority_sub = self.create_subscription(
            AuthorityLease, '/mark1/system/authority', self._on_authority_observed,
            qos.critical_reliable(), callback_group=self._cb_group)
        self._request_client = self.create_client(
            RequestAuthority, '/mark1/system/request_authority',
            callback_group=self._cb_group)

        self.create_timer(0.5, self._publish_authority)       # 2 s lease, renew 500 ms (only while HOLDING)
        self.create_timer(0.05, self._publish_safety_pulse)   # 20 Hz owning-node pulse (always)
        self._observe_timer = self.create_timer(OBSERVE_WINDOW_S, self._end_observe_window)

        self._change_clients = {}     # node_name -> Client
        self._steps = collections.deque()
        delay = self.get_parameter('autostart_delay_s').value
        self._autostart_timer = self.create_timer(float(delay), self._begin_bringup)

        self.get_logger().info('Core Hub up — registry + health monitor + supervisor')

    # ---- helpers ----------------------------------------------------------
    def _header(self, module_id: str) -> Mark1Header:
        h = Mark1Header()
        h.protocol_major = protocol.PROTOCOL_MAJOR
        h.protocol_minor = protocol.PROTOCOL_MINOR
        h.protocol_patch = protocol.PROTOCOL_PATCH
        h.module_id = module_id
        h.stamp = self.get_clock().now().to_msg()
        return h

    # ---- registry ---------------------------------------------------------
    def _on_register(self, request, response):
        h = request.header
        result = self._registry.register(
            module_id=h.module_id, hardware_type=request.hardware_type,
            sw_version=request.sw_version, fw_version=request.fw_version,
            capabilities=list(request.capabilities),
            protocol_major=h.protocol_major, protocol_minor=h.protocol_minor,
            protocol_patch=h.protocol_patch)
        response.accepted = result.accepted
        response.assigned_namespace = result.assigned_namespace
        response.reason = result.reason
        if result.accepted:
            self.get_logger().info(
                f'registered {h.module_id} ({request.hardware_type}) '
                f'-> {result.assigned_namespace} '
                f'caps={list(request.capabilities)}')
            self._subscribe_heartbeat(h.module_id, result.assigned_namespace)
            self._publish_presence(h.module_id, True)
        else:
            self.get_logger().warning(
                f'rejected {h.module_id}: {result.reason}')
        return response

    def _publish_presence(self, module_id: str, online: bool) -> None:
        msg = ModulePresence()
        msg.header = self._header(module_id)
        msg.online = online
        self._presence_pub.publish(msg)

    # ---- safety-supervisor (authority lease + safety pulse) ---------------
    def _publish_authority(self) -> None:
        # Only the holder publishes a lease; while OBSERVING/REQUESTING, Core stays
        # silent so it never competes with a node that took over during a failover.
        if self._auth_state != AUTH_HOLDING:
            return
        msg = AuthorityLease()
        msg.header = self._header(self._authority_holder)
        msg.holder_module_id = self._authority_holder
        msg.epoch = self._epoch
        msg.expires_at = (self.get_clock().now() + Duration(seconds=2.0)).to_msg()
        self._authority_pub.publish(msg)

    def _on_authority_observed(self, msg: AuthorityLease) -> None:
        # Before we hold, note any *other* node's live lease (a failover took over).
        if self._auth_state == AUTH_HOLDING or \
                msg.holder_module_id == self._authority_holder:
            return
        self._observed_holder = msg.holder_module_id
        self._observed_epoch = msg.epoch
        self._observed_expiry_s = _t2s(msg.expires_at)

    def _end_observe_window(self) -> None:
        self._observe_timer.cancel()
        now_s = self.get_clock().now().nanoseconds * 1e-9
        holder_live = bool(self._observed_holder) and now_s < self._observed_expiry_s
        if holder_live:
            # rejoin: another node took authority while Core was down — request it
            # back cleanly rather than publish a competing lease.
            self._rejoined = True
            self._auth_state = AUTH_REQUESTING
            self.get_logger().info(
                f'observe window: {self._observed_holder} holds authority '
                f'(epoch {self._observed_epoch}) — requesting clean hand-back')
            self._request_authority_return()
        else:
            # clean boot: nobody else holds — take the lease at epoch 1.
            self._epoch = 1
            self._auth_state = AUTH_HOLDING
            self.get_logger().info(
                'observe window: clean boot — Core takes authority at epoch 1')

    def _request_authority_return(self) -> None:
        if not self._request_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warning(
                'request_authority service unavailable; will retry')
            self._schedule_request_retry()
            return
        req = RequestAuthority.Request()
        req.header = self._header(self._authority_holder)
        req.requester_module_id = self._authority_holder
        req.last_known_epoch = self._observed_epoch   # epoch we observed: not behind
        future = self._request_client.call_async(req)
        future.add_done_callback(self._on_request_response)

    def _on_request_response(self, future) -> None:
        try:
            resp = future.result()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'RequestAuthority call failed: {exc}; retrying')
            self._schedule_request_retry()
            return
        if not resp.granted:
            self.get_logger().info(
                f'authority return not granted ({resp.reason}); retrying')
            self._schedule_request_retry()
            return
        # Granted: wait out the 500 ms quiet window before publishing, so neither
        # node commands during the hand-off (Locomotion holds its previous state).
        self._pending_epoch = resp.new_epoch
        self.get_logger().info(
            f'authority granted at epoch {resp.new_epoch}; '
            f'{QUIET_WINDOW_S * 1e3:.0f} ms quiet window before commanding')
        self._quiet_timer = self.create_timer(QUIET_WINDOW_S, self._take_after_quiet)

    def _take_after_quiet(self) -> None:
        if self._quiet_timer is not None:
            self._quiet_timer.cancel()
            self._quiet_timer = None
        self._epoch = self._pending_epoch
        self._auth_state = AUTH_HOLDING
        self.get_logger().info(
            f'quiet window elapsed — Core resumes authority at epoch {self._epoch}')

    def _schedule_request_retry(self) -> None:
        self._auth_state = AUTH_REQUESTING
        if self._retry_timer is not None:
            self._retry_timer.cancel()
        self._retry_timer = self.create_timer(REQUEST_RETRY_S, self._fire_request_retry)

    def _fire_request_retry(self) -> None:
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None
        self._request_authority_return()

    def _publish_safety_pulse(self) -> None:
        # Models the owning-Pi heartbeat the Locomotion firmware watchdog watches.
        # (Real path is a dedicated serial/USB link, not DDS — validated on HIL.)
        msg = Heartbeat()
        msg.header = self._header(self._authority_holder)
        msg.sequence = self._safety_seq
        msg.lifecycle_state = LCState.PRIMARY_STATE_ACTIVE
        self._safety_pub.publish(msg)
        self._safety_seq += 1

    # ---- health monitor ---------------------------------------------------
    def _subscribe_heartbeat(self, module_id: str, namespace: str) -> None:
        if module_id in self._hb_subs:
            return
        topic = f'{namespace}/heartbeat'
        self._hb_subs[module_id] = self.create_subscription(
            Heartbeat, topic, self._on_heartbeat, qos.heartbeat(),
            callback_group=self._cb_group)
        self._last_seen_ns[module_id] = self.get_clock().now().nanoseconds
        self._liveness[module_id] = LIVENESS_OK
        self.get_logger().info(f'monitoring heartbeat on {topic}')

    def _on_heartbeat(self, msg: Heartbeat) -> None:
        self._last_seen_ns[msg.header.module_id] = self.get_clock().now().nanoseconds

    def _check_liveness(self) -> None:
        now = self.get_clock().now().nanoseconds
        for module_id, last in self._last_seen_ns.items():
            age = (now - last) / 1e9
            if age > DEAD_AGE_S:
                new = LIVENESS_DEAD
            elif age > DEGRADED_AGE_S:
                new = LIVENESS_DEGRADED
            else:
                new = LIVENESS_OK
            if new != self._liveness.get(module_id):
                self._liveness[module_id] = new
                level = self.get_logger().info if new == LIVENESS_OK \
                    else self.get_logger().warning
                level(f'{module_id} liveness -> {new} (age {age:.2f}s)')
                if new == LIVENESS_DEAD:
                    self._publish_presence(module_id, False)

    # ---- supervisor (lifecycle_manager) -----------------------------------
    def _begin_bringup(self) -> None:
        self._autostart_timer.cancel()
        if self._rejoined:
            self.get_logger().info(
                'rejoin: managed nodes already running; supervisor stays hands-off')
            return
        managed = [n for n in self.get_parameter('managed_nodes').value if n]
        if not managed:
            self.get_logger().info('no managed_nodes configured; supervisor idle')
            return
        self.get_logger().info(f'supervisor bringing up: {managed}')
        for node_name in managed:
            self._steps.append((node_name, Transition.TRANSITION_CONFIGURE))
            self._steps.append((node_name, Transition.TRANSITION_ACTIVATE))
        self._next_step()

    def _next_step(self) -> None:
        if not self._steps:
            self.get_logger().info('supervisor: managed nodes ACTIVE — bring-up complete')
            return
        node_name, transition_id = self._steps.popleft()
        client = self._change_clients.get(node_name)
        if client is None:
            client = self.create_client(
                ChangeState, f'/{node_name}/change_state',
                callback_group=self._cb_group)
            self._change_clients[node_name] = client
        if not client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(
                f'supervisor: /{node_name}/change_state unavailable; skipping')
            self._next_step()
            return
        req = ChangeState.Request()
        req.transition = Transition(id=transition_id)
        name = self._transition_name(transition_id)
        self.get_logger().info(f'supervisor: {node_name} -> {name}')
        future = client.call_async(req)
        future.add_done_callback(
            lambda f, n=node_name, t=name: self._on_step_done(f, n, t))

    def _on_step_done(self, future, node_name, transition_name) -> None:
        try:
            ok = future.result().success
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(
                f'supervisor: {node_name} {transition_name} call failed: {exc}')
            ok = False
        if ok:
            self.get_logger().info(f'supervisor: {node_name} {transition_name} OK')
        else:
            self.get_logger().error(
                f'supervisor: {node_name} {transition_name} FAILED')
        self._next_step()

    @staticmethod
    def _transition_name(transition_id: int) -> str:
        return {
            Transition.TRANSITION_CONFIGURE: 'configure',
            Transition.TRANSITION_ACTIVATE: 'activate',
            Transition.TRANSITION_DEACTIVATE: 'deactivate',
            Transition.TRANSITION_CLEANUP: 'cleanup',
        }.get(transition_id, str(transition_id))


def main(args=None):
    rclpy.init(args=args)
    node = CoreHub()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
