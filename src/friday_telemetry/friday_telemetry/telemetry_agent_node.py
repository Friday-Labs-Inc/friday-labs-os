"""Telemetry Node Agent — the Command Center boundary (Phase 3).

The single translator between the rover's internal ROS 2 world (friday_msgs over
DDS, LAN-only) and the external Command Center (signed CBOR envelopes over an
MQTT-class link). It is a normal module agent (registers, heartbeats via the
ModuleAgent base) that additionally:

  * subscribes the external command topic mark1/<rover>/cmd/<class>,
  * VALIDATES every envelope (Ed25519 signature, allowlist, nonce, expiry,
    rover_id, protocol major) — see protocol.py,
  * on accept: maps the payload to the internal friday_msgs and republishes it on
    DDS (carrying the authority provenance), and ACKs,
  * on reject: publishes a friday_msgs/FaultReport and ACKs the rejection.
    Rejected commands are never executed, never queued (per the security spec).

Inbound MQTT callbacks run on the paho network thread; they only validate and
enqueue. A ROS timer drains the queue and does all ROS publishing, so DDS is only
ever touched from the executor thread.
"""

from __future__ import annotations

import json
import queue
import time

import cbor2
import rclpy
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from lifecycle_msgs.msg import State as LCState
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor

from friday_msgs.msg import (
    AuthorityLease,
    FaultReport,
    Heartbeat,
    MotionCommand,
    ReleaseAuthority,
)
from friday_msgs.srv import RequestAuthority
from friday_module_agent import authority, qos
from friday_module_agent.module_agent import ModuleAgent
from friday_module_agent.nonce_store import NonceStore

from friday_telemetry import protocol
from friday_telemetry.transport import MqttTransport

AUTHORITY_TOPIC = '/mark1/system/authority'
SAFETY_PULSE_TOPIC = '/mark1/system/safety_pulse'
AUTHORITY_RELEASE_TOPIC = '/mark1/system/authority_release'
REQUEST_AUTHORITY_SERVICE = '/mark1/system/request_authority'

LOCOMOTION_CMD_TOPIC = '/mark1/locomotion/cmd_motion'
FAULT_TOPIC = '/mark1/telemetry/fault'
LOCO_ODOM_TOPIC = '/mark1/locomotion/odometry'
LOCO_FAULT_TOPIC = '/mark1/locomotion/fault'

# Authority state (Authority Lease Protocol — "Failover" / "Authority Return").
TLM_MONITORING = 'MONITORING'   # default: Core holds; Telemetry only watches it
TLM_HOLDING = 'HOLDING'         # Telemetry self-promoted and now holds the lease

FAILOVER_CHECK_S = 0.1          # 10 Hz check of Core's two liveness signals
LEASE_RENEW_S = 0.5            # 2 s lease, renewed every 500 ms while holding
PULSE_PERIOD_S = 0.05         # 20 Hz safety pulse while holding
PULSE_LOST_S = 1.5           # Core's safety pulse missing >= 1.5 s = pulse_lost
STABLE_QUIET_S = 1.0         # "no motion" = no nonzero command issued for >= 1 s


def _t2s(t) -> float:
    """builtin_interfaces/Time -> unix seconds (0 if unset)."""
    return t.sec + t.nanosec * 1e-9


class TelemetryAgent(ModuleAgent):
    """Command Center boundary as a lifecycle module agent."""

    def __init__(self):
        super().__init__(
            node_name='telemetry',
            module_id='MARK1-TLM-001',
            module_ns='telemetry',
            hardware_type='telemetry',
            capabilities=['command_bridge', 'recovery', 'gateway'],
            sw_version='0.3.0',
        )
        self.declare_parameter('rover_id', 'MARK1-001')
        self.declare_parameter('mqtt_host', '127.0.0.1')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('operators_file', '')
        self.declare_parameter('nonce_store', '')
        # Production link is MQTT 5 over mutual-TLS (EMQX). Off by default so the
        # node-sim + unit tests use a plain local broker; the live broker sets these.
        self.declare_parameter('mqtt_tls', False)
        self.declare_parameter('mqtt_ca', '')
        self.declare_parameter('mqtt_cert', '')
        self.declare_parameter('mqtt_key', '')
        self.declare_parameter('mqtt_client_id', '')   # '' -> '<module_id>-bridge'
        # Rover telemetry signing: sign odom/fault/ack out to the broker so the
        # operator can trust they came from THIS rover. No key -> no egress (the
        # node-sim + unit tests stay unchanged).
        self.declare_parameter('rover_key_file', '')
        self.declare_parameter('telemetry_rate_hz', 2.0)   # odom downsample to the broker

        self._rover_id = self.get_parameter('rover_id').value
        self._inbound = queue.Queue()
        self._transport = None
        self._validator = None
        self._nonce_store = None
        self._authority_holder = ''       # tracked from /mark1/system/authority
        self._motion_pub = None
        self._fault_pub = None
        self._drain_timer = None
        # --- outbound telemetry signing ---
        self._rover_priv = None            # rover signing key (None = egress off)
        self._odom_sub = None
        self._loco_fault_sub = None
        self._tlm_fault_sub = None
        self._last_odom_pub_ns = 0
        self._odom_min_period_ns = 0
        # --- split-brain failover state (Authority Lease Protocol) ---
        self._auth_state = TLM_MONITORING
        self._epoch = 0                   # highest epoch seen / held
        self._safety_seq = 0
        self._core_seen = False           # don't fail over until Core was present
        self._core_lease_expiry_s = 0.0   # Core's last lease's own 2 s expiry
        self._last_pulse_ns = 0           # last safety pulse from Core
        self._last_motion_ns = 0          # last nonzero motion command issued (stability)
        self._authority_sub = None
        self._pulse_sub = None
        self._authority_pub = None
        self._safety_pulse_pub = None
        self._release_pub = None
        self._request_srv = None
        self._failover_timer = None
        self._lease_timer = None
        self._pulse_timer = None

    # ---- ModuleAgent hooks -------------------------------------------------
    def configure_hardware(self) -> None:
        self._motion_pub = self.create_lifecycle_publisher(
            MotionCommand, LOCOMOTION_CMD_TOPIC, qos.critical_reliable())
        self._fault_pub = self.create_lifecycle_publisher(
            FaultReport, FAULT_TOPIC, qos.state_default())
        self._nonce_store = NonceStore(self.get_parameter('nonce_store').value or None)
        self._validator = protocol.CommandValidator(
            rover_id=self._rover_id,
            operator_keys=self._load_operator_allowlist(),
            now=time.time, nonce_store=self._nonce_store)
        self._authority_sub = self.create_subscription(
            AuthorityLease, AUTHORITY_TOPIC, self._on_authority, qos.critical_reliable())
        # failover: watch Core's safety pulse; on promotion, publish lease + pulse
        # as the holder and announce a clean hand-back via ReleaseAuthority.
        self._pulse_sub = self.create_subscription(
            Heartbeat, SAFETY_PULSE_TOPIC, self._on_safety_pulse, qos.sensor_stream())
        self._authority_pub = self.create_lifecycle_publisher(
            AuthorityLease, AUTHORITY_TOPIC, qos.critical_reliable())
        self._safety_pulse_pub = self.create_lifecycle_publisher(
            Heartbeat, SAFETY_PULSE_TOPIC, qos.sensor_stream())
        self._release_pub = self.create_lifecycle_publisher(
            ReleaseAuthority, AUTHORITY_RELEASE_TOPIC, qos.critical_reliable())
        self._request_srv = self.create_service(
            RequestAuthority, REQUEST_AUTHORITY_SERVICE, self._on_request_authority)
        tls = None
        if bool(self.get_parameter('mqtt_tls').value):
            tls = {'ca_certs': self.get_parameter('mqtt_ca').value or None,
                   'certfile': self.get_parameter('mqtt_cert').value or None,
                   'keyfile': self.get_parameter('mqtt_key').value or None}
        # mTLS ties authorization to the cert CN, so the client id must be the
        # rover_id the broker ACL expects (not the internal module id).
        client_id = self.get_parameter('mqtt_client_id').value or f'{self._module_id}-bridge'
        self._transport = MqttTransport(
            host=self.get_parameter('mqtt_host').value,
            port=int(self.get_parameter('mqtt_port').value),
            client_id=client_id, tls=tls)
        # outbound telemetry: sign odom (downsampled) + fault out to the operator
        self._rover_priv = self._load_rover_key()
        rate = float(self.get_parameter('telemetry_rate_hz').value)
        self._odom_min_period_ns = int(1e9 / rate) if rate > 0 else 0
        if self._rover_priv is not None:
            self._odom_sub = self.create_subscription(
                Odometry, LOCO_ODOM_TOPIC, self._on_odom, qos.state_default())
            self._loco_fault_sub = self.create_subscription(
                FaultReport, LOCO_FAULT_TOPIC, self._on_fault, qos.state_default())
            self._tlm_fault_sub = self.create_subscription(
                FaultReport, FAULT_TOPIC, self._on_fault, qos.state_default())

    def activate_hardware(self) -> None:
        try:
            self._transport.connect()
            self._transport.subscribe(f'mark1/{self._rover_id}/cmd/+', self._on_cc_message)
        except Exception as exc:  # noqa: BLE001 - link down must not crash the node
            self.get_logger().error(f'Command Center link failed: {exc}')
        self._drain_timer = self.create_timer(0.02, self._drain_inbound)
        now_ns = self.get_clock().now().nanoseconds
        self._last_pulse_ns = now_ns
        self._core_lease_expiry_s = 0.0
        self._core_seen = False
        self._failover_timer = self.create_timer(FAILOVER_CHECK_S, self._check_failover)
        self.get_logger().info(
            f'Command Center boundary up for rover {self._rover_id} '
            f'(operators allowlisted: {len(self._validator._keys)}) — monitoring Core authority')

    def enter_safe_state(self) -> None:
        if self._drain_timer is not None:
            self.destroy_timer(self._drain_timer)
            self._drain_timer = None
        if self._failover_timer is not None:
            self.destroy_timer(self._failover_timer)
            self._failover_timer = None
        if self._auth_state == TLM_HOLDING:
            self._stand_down()
        if self._transport is not None:
            self._transport.disconnect()
        self.get_logger().info('telemetry safe-state: external link closed')

    # ---- allowlist ---------------------------------------------------------
    def _load_operator_allowlist(self) -> dict:
        path = self.get_parameter('operators_file').value
        if not path:
            self.get_logger().warning('no operators_file set; allowlist empty (all commands rejected)')
            return {}
        try:
            data = json.loads(open(path).read())
        except OSError as exc:
            self.get_logger().error(f'cannot read operators_file {path}: {exc}')
            return {}
        keys = {}
        for sender_id, hex_pub in data.items():
            keys[sender_id] = Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_pub))
        return keys

    def _load_rover_key(self):
        """Load the rover's Ed25519 private key for signing outbound telemetry."""
        path = self.get_parameter('rover_key_file').value
        if not path:
            self.get_logger().info(
                'no rover_key_file; outbound telemetry will not be signed or bridged')
            return None
        try:
            return Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(open(path).read().strip()))
        except (OSError, ValueError) as exc:
            self.get_logger().error(f'cannot load rover_key_file {path}: {exc}')
            return None

    # ---- outbound telemetry (sign odom/fault out to the operator) ----------
    def _on_odom(self, msg: Odometry) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self._last_odom_pub_ns < self._odom_min_period_ns:
            return                                     # downsample the full-rate DDS odom
        self._last_odom_pub_ns = now_ns
        p, t = msg.pose.pose, msg.twist.twist
        self._publish_signed_telemetry('tlm/odom', {
            'class': 'odom',
            'x': p.position.x, 'y': p.position.y, 'z': p.position.z,
            'qx': p.orientation.x, 'qy': p.orientation.y,
            'qz': p.orientation.z, 'qw': p.orientation.w,
            'vx': t.linear.x, 'vy': t.linear.y, 'wz': t.angular.z,
            'stamp': _t2s(msg.header.stamp)})

    def _on_fault(self, msg: FaultReport) -> None:
        self._publish_signed_telemetry('tlm/fault', {
            'class': 'fault',
            'severity': int(msg.severity), 'category': int(msg.category),
            'description': msg.description,
            'recommended_action': msg.recommended_action,
            'module_id': msg.header.module_id, 'stamp': _t2s(msg.header.stamp)})

    def _publish_signed_telemetry(self, suffix: str, payload: dict) -> None:
        if self._rover_priv is None or self._transport is None:
            return
        now = time.time()
        # Dedicated nonce namespace so telemetry nonces never collide with the
        # command-router's issued-as-holder nonces.
        nonce = self._next_issued_nonce(f'{self._rover_id}/tlm')
        env = protocol.sign_telemetry(
            rover_id=self._rover_id, msg_id=nonce, nonce=nonce, issued_at=now,
            expires_at=now + protocol.DEFAULT_EXPIRY_S, payload=payload,
            private_key=self._rover_priv)
        self._transport.publish(f'mark1/{self._rover_id}/{suffix}', protocol.encode(env))

    # ---- inbound (MQTT thread: validate + enqueue only) --------------------
    def _on_cc_message(self, topic: str, payload: bytes) -> None:
        cmd_class = topic.rsplit('/', 1)[-1]
        try:
            envelope = protocol.decode(payload)
        except Exception:  # noqa: BLE001 - malformed wire data
            self._inbound.put(('reject', protocol.SECURITY_AUTH, 'undecodable envelope', None, 0))
            return
        result = self._validator.validate(envelope)
        msg_id = envelope.get('msg_id', 0)
        if result.accepted:
            self._inbound.put(('accept', cmd_class, '', envelope, msg_id))
        else:
            self._inbound.put(('reject', result.category, result.reason, envelope, msg_id))

    # ---- drain (ROS thread: all DDS publishing) ----------------------------
    def _drain_inbound(self) -> None:
        while True:
            try:
                kind, a, b, envelope, msg_id = self._inbound.get_nowait()
            except queue.Empty:
                return
            if kind == 'accept':
                self._dispatch_command(a, envelope)
                self._ack(msg_id, True, 'OK')
            else:
                self._report_rejection(a, b, envelope)
                self._ack(msg_id, False, a)

    def _dispatch_command(self, cmd_class: str, envelope: dict) -> None:
        if cmd_class != 'motion':
            self.get_logger().warning(f'unknown command class "{cmd_class}"; dropping')
            return
        p = envelope['payload']
        cmd = MotionCommand()
        cmd.header = self._header()
        cmd.type = int(p.get('type', MotionCommand.TYPE_STOP))
        cmd.linear_velocity = float(p.get('linear_velocity', 0.0))
        cmd.angular_velocity = float(p.get('angular_velocity', 0.0))
        cmd.steer_angle_rad = float(p.get('steer_angle_rad', 0.0))
        # COMMAND-ROUTER: re-issue the operator's command AS the current authority
        # lease holder (Locomotion only obeys the holder). The operator id is kept
        # for the audit log, not as the command source. Carry the operator's expiry.
        operator = envelope.get('sender_id', '?')
        if not self._authority_holder:
            self.get_logger().warning('no authority holder known yet; command dropped')
            return
        cmd.source = self._authority_holder
        cmd.nonce = self._next_issued_nonce(self._authority_holder)
        exp = float(envelope.get('expires_at', 0.0))
        cmd.expires_at.sec = int(exp)
        cmd.expires_at.nanosec = int((exp - int(exp)) * 1e9)
        self._motion_pub.publish(cmd)
        if cmd.type == MotionCommand.TYPE_VELOCITY and \
                (cmd.linear_velocity or cmd.angular_velocity):
            self._last_motion_ns = self.get_clock().now().nanoseconds   # stability gate
        self.get_logger().info(
            f'ACCEPTED motion from operator {operator} -> re-issued as '
            f'{cmd.source} (nonce {cmd.nonce}) v={cmd.linear_velocity:.2f} '
            f'w={cmd.angular_velocity:.2f}')

    def _on_authority(self, msg: AuthorityLease) -> None:
        # Track Core's lease for failover detection. Ignore our own echo while
        # holding, and ignore a stale lower-epoch lease (epoch-monotonic).
        if msg.holder_module_id == self._module_id:
            return
        if not authority.accept_lease(incoming_epoch=msg.epoch,
                                      current_epoch=self._epoch):
            return
        self._authority_holder = msg.holder_module_id
        self._epoch = msg.epoch
        self._core_lease_expiry_s = _t2s(msg.expires_at)
        self._core_seen = True

    def _on_safety_pulse(self, msg: Heartbeat) -> None:
        self._last_pulse_ns = self.get_clock().now().nanoseconds

    # ---- failover (self-promote on Core loss) ------------------------------
    def _check_failover(self) -> None:
        # Self-promote only when BOTH of Core's independent signals have failed:
        # its lease has expired AND its safety pulse has gone silent.
        if self._auth_state != TLM_MONITORING or not self._core_seen:
            return
        now_ns = self.get_clock().now().nanoseconds
        lease_expired = (now_ns * 1e-9) >= self._core_lease_expiry_s
        pulse_lost = (now_ns - self._last_pulse_ns) / 1e9 >= PULSE_LOST_S
        if authority.should_failover(lease_expired=lease_expired, pulse_lost=pulse_lost):
            self._promote()

    def _promote(self) -> None:
        self._epoch += 1                       # last epoch + 1
        self._authority_holder = self._module_id
        self._auth_state = TLM_HOLDING
        self._lease_timer = self.create_timer(LEASE_RENEW_S, self._publish_authority_lease)
        self._pulse_timer = self.create_timer(PULSE_PERIOD_S, self._publish_safety_pulse)
        self._publish_authority_lease()        # assert authority immediately
        self.get_logger().warning(
            f'CORE LOST (lease expired + safety pulse silent) — Telemetry '
            f'self-promoting to authority at epoch {self._epoch}')

    def _publish_authority_lease(self) -> None:
        if self._auth_state != TLM_HOLDING:
            return
        msg = AuthorityLease()
        msg.header = self._header()
        msg.holder_module_id = self._module_id
        msg.epoch = self._epoch
        msg.expires_at = (self.get_clock().now() + Duration(seconds=2.0)).to_msg()
        self._authority_pub.publish(msg)

    def _publish_safety_pulse(self) -> None:
        if self._auth_state != TLM_HOLDING:
            return
        msg = Heartbeat()
        msg.header = self._header()
        msg.sequence = self._safety_seq
        msg.lifecycle_state = LCState.PRIMARY_STATE_ACTIVE
        self._safety_pulse_pub.publish(msg)
        self._safety_seq += 1

    # ---- authority return (clean hand-back to a recovering Core) -----------
    def _on_request_authority(self, request, response):
        if self._auth_state != TLM_HOLDING:
            response.granted = False
            response.new_epoch = self._epoch
            response.reason = 'telemetry does not hold authority'
            return response
        stable = self._is_stable()
        if not authority.may_grant_return(
                requester_epoch=request.last_known_epoch,
                holder_epoch=self._epoch, stable=stable):
            response.granted = False
            response.new_epoch = self._epoch
            response.reason = ('rover not stable (recent motion)' if not stable
                               else f'requester epoch {request.last_known_epoch} '
                                    f'behind holder {self._epoch}')
            self.get_logger().info(
                f'RequestAuthority from {request.requester_module_id} denied: '
                f'{response.reason}')
            return response
        new_epoch = self._epoch + 1
        response.granted = True
        response.new_epoch = new_epoch
        response.reason = 'granted'
        self.get_logger().info(
            f'RequestAuthority from {request.requester_module_id} granted at epoch '
            f'{new_epoch} — releasing and standing down')
        self._release_authority(new_epoch, request.requester_module_id)
        return response

    def _release_authority(self, new_epoch: int, requester: str) -> None:
        rel = ReleaseAuthority()
        rel.header = self._header()
        rel.releasing_module_id = self._module_id
        rel.epoch = self._epoch
        rel.reason = f'authority returned to {requester} at epoch {new_epoch}'
        self._release_pub.publish(rel)
        self._stand_down()

    def _stand_down(self) -> None:
        for attr in ('_lease_timer', '_pulse_timer'):
            timer = getattr(self, attr)
            if timer is not None:
                self.destroy_timer(timer)
                setattr(self, attr, None)
        self._auth_state = TLM_MONITORING
        # grace: Core keeps pulsing through the quiet window and its fresh lease
        # arrives just after — don't re-failover in that gap.
        now_ns = self.get_clock().now().nanoseconds
        self._last_pulse_ns = now_ns
        self._core_lease_expiry_s = now_ns * 1e-9 + 2.0
        self.get_logger().info('stood down — monitoring; Core resumes authority')

    def _is_stable(self) -> bool:
        quiet_s = (self.get_clock().now().nanoseconds - self._last_motion_ns) / 1e9
        return quiet_s >= STABLE_QUIET_S

    def _next_issued_nonce(self, holder: str) -> int:
        # Durable monotonic nonce for commands issued as the holder, so a Telemetry
        # restart can't replay-collide with Locomotion's persisted nonce floor.
        n = (self._nonce_store.last(holder) or 0) + 1
        self._nonce_store.commit(holder, n)
        return n

    def _report_rejection(self, category: str, reason: str, envelope) -> None:
        sender = envelope.get('sender_id', '?') if envelope else '?'
        cat_map = {
            protocol.SECURITY_AUTH: FaultReport.CATEGORY_SECURITY_AUTH,
            protocol.SECURITY_REPLAY: FaultReport.CATEGORY_SECURITY_REPLAY,
        }
        fr = FaultReport()
        fr.header = self._header()
        fr.severity = FaultReport.SEVERITY_ERROR
        fr.category = cat_map.get(category, FaultReport.CATEGORY_GENERAL)
        fr.description = f'command from "{sender}" rejected: {category} ({reason})'
        fr.recommended_action = 'alert operator; audit Command Center link'
        self._fault_pub.publish(fr)
        self.get_logger().warning(f'REJECTED {category}: {reason}')

    def _ack(self, msg_id, accepted: bool, category: str) -> None:
        if self._transport is None:
            return
        ack = {'msg_id': msg_id, 'accepted': accepted, 'category': category}
        if self._rover_priv is not None:                  # signed ack (operator-verifiable)
            now = time.time()
            nonce = self._next_issued_nonce(f'{self._rover_id}/tlm')
            env = protocol.sign_telemetry(
                rover_id=self._rover_id, msg_id=nonce, nonce=nonce, issued_at=now,
                expires_at=now + protocol.DEFAULT_EXPIRY_S,
                payload={'class': 'ack', **ack}, private_key=self._rover_priv)
            body = protocol.encode(env)
        else:
            body = cbor2.dumps(ack)                        # plain ack (no rover key)
        self._transport.publish(f'mark1/{self._rover_id}/ack/{msg_id}', body)

    def _header(self):
        from friday_msgs.msg import Mark1Header
        h = Mark1Header()
        h.protocol_major = protocol.PROTOCOL_MAJOR
        h.protocol_minor = protocol.PROTOCOL_MINOR
        h.protocol_patch = protocol.PROTOCOL_PATCH
        h.module_id = self._module_id
        h.stamp = self.get_clock().now().to_msg()
        return h


def main(args=None):
    rclpy.init(args=args)
    node = TelemetryAgent()
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
