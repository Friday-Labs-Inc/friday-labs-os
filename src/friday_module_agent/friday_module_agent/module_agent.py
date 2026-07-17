"""ModuleAgent — the reusable lifecycle-node base for every Mark 1 module.

Implements the module-agent contract from
docs/architecture/ROS 2 Interface and Message Contract.md: a standard ROS 2
managed (lifecycle) node that

  * registers with the Core Hub's module-registry on `configure`,
  * heartbeats at 5 Hz and publishes health while `active`, and
  * holds a defined safe state on `deactivate`.

Concrete modules subclass this, set their identity, and override the hardware
hooks. The state machine is the standard ROS 2 one — never a custom one.
"""

from lifecycle_msgs.msg import State as LCState
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn

from friday_msgs.msg import Heartbeat, HealthStatus, Mark1Header
from friday_msgs.srv import RegisterModule

from friday_module_agent import protocol, qos

REG_KEEPALIVE_PERIOD_S = 60.0   # firmware parity: registered upsert period
REGISTER_SERVICE = '/mark1/system/register_module'


class ModuleAgent(LifecycleNode):
    """Standard managed node implementing the Friday Labs OS module-agent contract."""

    def __init__(self, *, node_name, module_id, module_ns, hardware_type,
                 capabilities, sw_version='0.1.0', fw_version='none',
                 registry_timeout_s=5.0):
        super().__init__(node_name)
        self._module_id = module_id
        self._module_ns = module_ns          # topic namespace segment, e.g. 'locomotion'
        self._hardware_type = hardware_type
        self._capabilities = list(capabilities)
        self._sw_version = sw_version
        self._fw_version = fw_version
        self._registry_timeout_s = registry_timeout_s

        self._seq = 0
        self._activated_at_ns = 0
        self._hb_pub = None
        self._health_pub = None
        self._hb_timer = None
        self._health_timer = None
        self._reg_client = None
        self._primary_state = LCState.PRIMARY_STATE_UNCONFIGURED

    # ---- helpers ----------------------------------------------------------
    def _header(self) -> Mark1Header:
        h = Mark1Header()
        h.protocol_major = protocol.PROTOCOL_MAJOR
        h.protocol_minor = protocol.PROTOCOL_MINOR
        h.protocol_patch = protocol.PROTOCOL_PATCH
        h.module_id = self._module_id
        h.stamp = self.get_clock().now().to_msg()
        return h

    def _topic(self, leaf: str) -> str:
        return f'/mark1/{self._module_ns}/{leaf}'

    # ---- lifecycle transitions --------------------------------------------
    def on_configure(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info(f'[{self._module_id}] configuring')
        self._hb_pub = self.create_lifecycle_publisher(
            Heartbeat, self._topic('heartbeat'), qos.heartbeat())
        self._health_pub = self.create_lifecycle_publisher(
            HealthStatus, self._topic('health'), qos.state_default())
        # Services use the default (reliable, volatile) services QoS on both
        # sides; the critical_reliable profile is for command/estop TOPICS, and
        # its TRANSIENT_LOCAL durability would prevent the service from matching.
        self._reg_client = self.create_client(RegisterModule, REGISTER_SERVICE)
        try:
            self.configure_hardware()
        except Exception as exc:  # noqa: BLE001 - report, never crash the transition
            self.get_logger().error(f'[{self._module_id}] hardware configure failed: {exc}')
            return TransitionCallbackReturn.FAILURE
        self._register_async()
        # Registration keep-alive (mirrors the ESP32 firmware's 60 s upsert):
        # a restarted Core Hub boots with an empty registry and only monitors
        # heartbeat/health for modules it knows — without this re-send it
        # would never see us again, so its supervisor could never heal us.
        self._reg_keepalive_timer = self.create_timer(
            REG_KEEPALIVE_PERIOD_S, self._register_keepalive)
        self._primary_state = LCState.PRIMARY_STATE_INACTIVE
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info(f'[{self._module_id}] activating')
        super().on_activate(state)
        try:
            self.activate_hardware()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'[{self._module_id}] hardware activate failed: {exc}')
            return TransitionCallbackReturn.FAILURE
        self._seq = 0
        self._activated_at_ns = self.get_clock().now().nanoseconds
        self._primary_state = LCState.PRIMARY_STATE_ACTIVE
        self._hb_timer = self.create_timer(qos.HEARTBEAT_PERIOD_S, self._publish_heartbeat)
        self._health_timer = self.create_timer(qos.HEALTH_PERIOD_S, self._publish_health)
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info(f'[{self._module_id}] deactivating -> safe state')
        self._destroy_timers()
        try:
            self.enter_safe_state()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'[{self._module_id}] safe-state hook failed: {exc}')
        super().on_deactivate(state)
        self._primary_state = LCState.PRIMARY_STATE_INACTIVE
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info(f'[{self._module_id}] cleaning up')
        self._teardown()
        self._primary_state = LCState.PRIMARY_STATE_UNCONFIGURED
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        self.get_logger().info(f'[{self._module_id}] shutting down')
        self._teardown()
        self._primary_state = LCState.PRIMARY_STATE_FINALIZED
        return TransitionCallbackReturn.SUCCESS

    # ---- subclass hooks (override as needed) ------------------------------
    def configure_hardware(self) -> None:
        """Initialize hardware/interfaces. Raise to fail the configure transition."""

    def activate_hardware(self) -> None:
        """Bring actuators/sensors online. Raise to fail the activate transition."""

    def enter_safe_state(self) -> None:
        """Hold the module's defined safe behavior (e.g. Locomotion locks motors)."""

    def health_overall(self) -> int:
        """Return HEALTH_OK / HEALTH_DEGRADED / HEALTH_FAULT for the health topic."""
        return protocol.HEALTH_OK

    def health_detail(self) -> str:
        """Human-readable cause when health_overall() is not OK ('' otherwise)."""
        return ''

    # ---- internals --------------------------------------------------------
    def _register_keepalive(self) -> None:
        if not self._reg_client.service_is_ready():
            return                       # registry down; try again next period
        self._reg_client.call_async(self._registration_request()).add_done_callback(
            self._on_register_response)

    def _registration_request(self) -> RegisterModule.Request:
        req = RegisterModule.Request()
        req.header = self._header()
        req.hardware_type = self._hardware_type
        req.sw_version = self._sw_version
        req.fw_version = self._fw_version
        req.capabilities = self._capabilities
        return req

    def _register_async(self) -> None:
        if not self._reg_client.wait_for_service(timeout_sec=self._registry_timeout_s):
            self.get_logger().warning(
                f'[{self._module_id}] module-registry unavailable after '
                f'{self._registry_timeout_s}s; continuing unregistered')
            return
        self._reg_client.call_async(self._registration_request()).add_done_callback(
            self._on_register_response)

    def _on_register_response(self, future) -> None:
        try:
            resp = future.result()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'[{self._module_id}] registration call failed: {exc}')
            return
        if resp.accepted:
            self.get_logger().info(
                f'[{self._module_id}] registered -> namespace {resp.assigned_namespace}')
        else:
            self.get_logger().error(
                f'[{self._module_id}] registration REJECTED: {resp.reason}')

    def _publish_heartbeat(self) -> None:
        msg = Heartbeat()
        msg.header = self._header()
        msg.sequence = self._seq
        msg.lifecycle_state = self._primary_state
        self._hb_pub.publish(msg)
        self._seq += 1

    def _publish_health(self) -> None:
        msg = HealthStatus()
        msg.header = self._header()
        msg.overall = self.health_overall()
        now_ns = self.get_clock().now().nanoseconds
        msg.uptime_s = max(0, int((now_ns - self._activated_at_ns) / 1e9))
        msg.detail = self.health_detail()
        self._health_pub.publish(msg)

    def _destroy_timers(self) -> None:
        for attr in ('_hb_timer', '_health_timer'):
            timer = getattr(self, attr)
            if timer is not None:
                self.destroy_timer(timer)
                setattr(self, attr, None)

    def _teardown(self) -> None:
        self._destroy_timers()
        if getattr(self, '_reg_keepalive_timer', None) is not None:
            self.destroy_timer(self._reg_keepalive_timer)
            self._reg_keepalive_timer = None
        for attr in ('_hb_pub', '_health_pub'):
            pub = getattr(self, attr)
            if pub is not None:
                try:
                    self.destroy_publisher(pub)
                except Exception:  # noqa: BLE001 - best-effort teardown
                    pass
                setattr(self, attr, None)
        if self._reg_client is not None:
            try:
                self.destroy_client(self._reg_client)
            except Exception:  # noqa: BLE001
                pass
            self._reg_client = None
