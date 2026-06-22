"""Locomotion Control Unit agent — Phase 4 (safety: authority + safe-stop).

Builds on Phase 3 closed-loop motion and adds the two safety behaviors:

  * AUTHORITY ENFORCEMENT (Authority Lease Protocol): obeys a MotionCommand only
    if a valid `authority` lease exists, the command's `source` is the current
    lease holder, the command has not expired, and its nonce strictly increases
    per source. Rejections publish a FaultReport and are dropped.

  * SAFE-STOP (Safe-Stop Latency Budget): a watchdog modelling the firmware path
    — a fast safety pulse from the owning node; if it's lost > 100 ms, or an
    EmergencyStop arrives, or authority is lost, the rover enters SAFE-STATE
    (motors -> 0, steering frozen, FaultReport category WATCHDOG). Re-activation
    via the lifecycle (inactive -> active) is required to leave safe-state.

Honest scope: in pure sim this models the watchdog *logic* and validates the DDS
EmergencyStop path; the true 100 ms p99 is the ESP32 hardware watchdog over a
dedicated serial link, validated on hardware-in-the-loop (see the budget doc).
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import Float64MultiArray

from friday_msgs.msg import (
    AuthorityLease,
    EmergencyStop,
    FaultReport,
    Heartbeat,
    MotionCommand,
)
from friday_module_agent import authority, qos
from friday_module_agent.module_agent import ModuleAgent
from friday_module_agent.nonce_store import NonceStore

from friday_locomotion import kinematics, safety

CONTROL_PERIOD_S = 0.05         # 20 Hz odometry
SAFE_CHECK_PERIOD_S = 0.025     # 40 Hz safety watchdog
SAFE_STOP_TIMEOUT_S = 0.1       # 100 ms safety-pulse loss -> safe-stop
WATCHDOG_GRACE_S = 1.0          # arm the watchdog ~1 s after activate so the
                                # best-effort safety-pulse subscription can connect
                                # first (avoids a startup false-trip; rover isn't
                                # moving yet). Runtime safe-stop latency is unchanged.

CMD_TOPIC = '/mark1/locomotion/cmd_motion'
ODOM_TOPIC = '/mark1/locomotion/odometry'
FAULT_TOPIC = '/mark1/locomotion/fault'
AUTHORITY_TOPIC = '/mark1/system/authority'
SAFETY_PULSE_TOPIC = '/mark1/system/safety_pulse'
ESTOP_TOPIC = '/mark1/locomotion/emergency_stop'


def _t2s(t) -> float:
    """builtin_interfaces/Time -> unix seconds (0 if unset)."""
    return t.sec + t.nanosec * 1e-9


class LocomotionAgent(ModuleAgent):
    """Lifecycle agent for the Locomotion Control Unit with authority + safe-stop."""

    def __init__(self):
        super().__init__(
            node_name='locomotion',
            module_id='MARK1-LOCO-001',
            module_ns='locomotion',
            hardware_type='locomotion',
            capabilities=['drive', 'steer', 'safe_stop'],
            sw_version='0.4.0',
        )
        # motion state
        self._x = self._y = self._theta = 0.0
        self._v = self._w = 0.0
        self._last_ns = 0
        # authority state
        self._holder = ''
        self._lease_expiry_s = 0.0
        self._epoch = 0
        self.declare_parameter('nonce_store', '')
        self._nonce_store = NonceStore(self.get_parameter('nonce_store').value or None)
        # sim drive-out: if both topics are set, the authority-gated, safe-stop-gated
        # (v, w) is converted (kinematics.drive_and_steer) to 6 wheel velocities + 4
        # corner steer angles and published to the gz_ros2_control command topics —
        # the real OS driving the corner-steer Gazebo rover. Empty -> pure node-sim.
        self.declare_parameter('wheel_cmd_topic', '')
        self.declare_parameter('steer_cmd_topic', '')
        # safe-stop pulse-loss timeout. 0.1 s is the HARDWARE (HIL firmware-watchdog
        # over dedicated serial) spec; the sim loosens it via this param because the
        # DDS pulse on a shared, physics-loaded CPU jitters (not a real safety event).
        self.declare_parameter('safe_stop_timeout_s', SAFE_STOP_TIMEOUT_S)
        self._safe_stop_timeout = float(self.get_parameter('safe_stop_timeout_s').value)
        # safety state
        self._safe_state = False
        self._last_safety_pulse_ns = 0
        self._activate_ns = 0
        # handles
        self._odom_pub = None
        self._fault_pub = None
        self._cmd_sub = None
        self._authority_sub = None
        self._pulse_sub = None
        self._estop_sub = None
        self._wheel_cmd_pub = None
        self._steer_cmd_pub = None
        self._motion_timer = None
        self._watchdog_timer = None

    # ---- ModuleAgent hardware hooks ---------------------------------------
    def configure_hardware(self) -> None:
        self._odom_pub = self.create_lifecycle_publisher(
            Odometry, ODOM_TOPIC, qos.state_default())
        self._fault_pub = self.create_lifecycle_publisher(
            FaultReport, FAULT_TOPIC, qos.state_default())
        self._cmd_sub = self.create_subscription(
            MotionCommand, CMD_TOPIC, self._on_command, qos.critical_reliable())
        self._authority_sub = self.create_subscription(
            AuthorityLease, AUTHORITY_TOPIC, self._on_authority, qos.critical_reliable())
        self._pulse_sub = self.create_subscription(
            Heartbeat, SAFETY_PULSE_TOPIC, self._on_safety_pulse, qos.sensor_stream())
        self._estop_sub = self.create_subscription(
            EmergencyStop, ESTOP_TOPIC, self._on_emergency_stop, qos.critical_reliable())
        wheel_topic = self.get_parameter('wheel_cmd_topic').value
        steer_topic = self.get_parameter('steer_cmd_topic').value
        if wheel_topic and steer_topic:
            self._wheel_cmd_pub = self.create_lifecycle_publisher(
                Float64MultiArray, wheel_topic, qos.state_default())
            self._steer_cmd_pub = self.create_lifecycle_publisher(
                Float64MultiArray, steer_topic, qos.state_default())
            self.get_logger().info(
                f'sim corner-steer drive-out -> {wheel_topic} + {steer_topic}')

    def activate_hardware(self) -> None:
        self._x = self._y = self._theta = 0.0
        self._v = self._w = 0.0
        self._safe_state = False            # re-activation clears safe-state
        now_ns = self.get_clock().now().nanoseconds
        self._last_ns = now_ns
        self._last_safety_pulse_ns = now_ns
        self._activate_ns = now_ns
        self._motion_timer = self.create_timer(CONTROL_PERIOD_S, self._step)
        self._watchdog_timer = self.create_timer(SAFE_CHECK_PERIOD_S, self._check_safety)

    def enter_safe_state(self) -> None:
        # Lifecycle deactivate: full stop, tear down the active timers.
        for attr in ('_motion_timer', '_watchdog_timer'):
            timer = getattr(self, attr)
            if timer is not None:
                self.destroy_timer(timer)
                setattr(self, attr, None)
        self._safe_state = True
        self._v = self._w = 0.0
        self.get_logger().info('locomotion safe-state (deactivate): motion stopped')

    # ---- authority + safety inputs ----------------------------------------
    def _on_authority(self, msg: AuthorityLease) -> None:
        # Epoch-monotonic gate (split-brain S3): honour a lease only if its epoch
        # is not behind the highest we've accepted. After a failover bumps the
        # epoch, a stale lower-epoch lease from a rejoining Core is ignored here —
        # so the consumer can never act on two holders, whoever is publishing.
        if not authority.accept_lease(incoming_epoch=msg.epoch,
                                      current_epoch=self._epoch):
            self.get_logger().warning(
                f'ignoring stale authority lease: epoch {msg.epoch} < {self._epoch} '
                f'(from {msg.holder_module_id})')
            return
        self._holder = msg.holder_module_id
        self._lease_expiry_s = _t2s(msg.expires_at)
        self._epoch = msg.epoch

    def _on_safety_pulse(self, msg: Heartbeat) -> None:
        self._last_safety_pulse_ns = self.get_clock().now().nanoseconds

    def _on_emergency_stop(self, msg: EmergencyStop) -> None:
        sent_s = _t2s(msg.header.stamp)
        now_s = self.get_clock().now().nanoseconds * 1e-9
        latency_ms = (now_s - sent_s) * 1e3 if sent_s > 0 else None
        self._trip_safe_stop(f'EmergencyStop (cat {msg.category}: {msg.reason})', latency_ms)

    # ---- command path (authority enforcement) -----------------------------
    def _on_command(self, msg: MotionCommand) -> None:
        now_s = self.get_clock().now().nanoseconds * 1e-9
        decision = safety.authorize(
            source=msg.source, nonce=msg.nonce, cmd_expires_s=_t2s(msg.expires_at),
            holder=self._holder, lease_expires_s=self._lease_expiry_s,
            last_nonce=self._nonce_store.last(msg.source),
            now_s=now_s, in_safe_state=self._safe_state)
        if not decision.accepted:
            self._publish_fault(
                FaultReport.CATEGORY_SECURITY_AUTH if decision.reason in
                (safety.WRONG_SOURCE, safety.NO_AUTHORITY) else FaultReport.CATEGORY_GENERAL,
                FaultReport.SEVERITY_WARN,
                f'MotionCommand rejected: {decision.reason} (src={msg.source} nonce={msg.nonce})')
            self.get_logger().warning(
                f'REJECT motion: {decision.reason} (src={msg.source} nonce={msg.nonce})')
            return
        self._nonce_store.commit(msg.source, msg.nonce)
        if msg.type == MotionCommand.TYPE_VELOCITY:
            self._v, self._w = msg.linear_velocity, msg.angular_velocity
        else:
            self._v = self._w = 0.0
        self.get_logger().info(
            f'ACCEPT motion src={msg.source} nonce={msg.nonce} '
            f'v={self._v:.2f} w={self._w:.2f}')

    # ---- safety watchdog --------------------------------------------------
    def _check_safety(self) -> None:
        if self._safe_state:
            return
        now_ns = self.get_clock().now().nanoseconds
        if (now_ns - self._activate_ns) / 1e9 < WATCHDOG_GRACE_S:
            return                      # startup grace: subscriptions still establishing
        pulse_age = (now_ns - self._last_safety_pulse_ns) / 1e9
        if pulse_age > self._safe_stop_timeout:
            self._trip_safe_stop(
                f'safety pulse lost ({pulse_age * 1e3:.0f} ms)', pulse_age * 1e3)
        elif self._holder and (now_ns * 1e-9) >= self._lease_expiry_s:
            self._trip_safe_stop('authority lease lost', None)

    def _trip_safe_stop(self, cause: str, latency_ms) -> None:
        if self._safe_state:
            return
        self._safe_state = True
        self._v = self._w = 0.0              # motors to zero; steering frozen (theta unchanged)
        self._publish_fault(FaultReport.CATEGORY_WATCHDOG, FaultReport.SEVERITY_CRITICAL,
                            f'SAFE-STOP: {cause}')
        tail = f' (latency {latency_ms:.0f} ms)' if latency_ms is not None else ''
        self.get_logger().warning(f'SAFE-STOP entered: {cause}{tail}')

    # ---- motion model -----------------------------------------------------
    def _step(self) -> None:
        if self._safe_state:
            self._v = self._w = 0.0
        now_ns = self.get_clock().now().nanoseconds
        dt = (now_ns - self._last_ns) / 1e9
        self._last_ns = now_ns
        self._theta += self._w * dt
        self._x += self._v * math.cos(self._theta) * dt
        self._y += self._v * math.sin(self._theta) * dt
        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self._x
        odom.pose.pose.position.y = self._y
        odom.pose.pose.orientation.z = math.sin(self._theta / 2.0)
        odom.pose.pose.orientation.w = math.cos(self._theta / 2.0)
        odom.twist.twist.linear.x = self._v
        odom.twist.twist.angular.z = self._w
        self._odom_pub.publish(odom)
        # sim: convert (v, w) -> 6 wheel speeds + 4 corner steer angles and drive the
        # gz_ros2_control controllers. Safe-stop forces v=w=0 above -> all zero.
        if self._wheel_cmd_pub is not None:
            wheel_vel, steer_ang = kinematics.drive_and_steer(self._v, self._w)
            self._wheel_cmd_pub.publish(Float64MultiArray(data=wheel_vel))
            self._steer_cmd_pub.publish(Float64MultiArray(data=steer_ang))

    def _publish_fault(self, category, severity, description) -> None:
        fr = FaultReport()
        fr.header = self._header()
        fr.severity = severity
        fr.category = category
        fr.description = description
        fr.recommended_action = 're-activate via safety-supervisor (inactive -> active)'
        self._fault_pub.publish(fr)


def main(args=None):
    rclpy.init(args=args)
    node = LocomotionAgent()
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
