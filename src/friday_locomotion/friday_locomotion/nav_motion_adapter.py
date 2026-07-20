"""Nav2 -> authority chain adapter — Phase 4's keystone.

Nav2's controller speaks geometry_msgs/Twist on /cmd_vel_nav. Mark 1's
locomotion agent obeys ONLY an authorized MotionCommand on
/mark1/locomotion/cmd_motion (source == current lease holder, monotonic
nonce, unexpired). This node is the bridge — and deliberately the ONLY
path autonomy has to the wheels:

    Nav2 plan -> Twist -> [this adapter] -> MotionCommand(authority fields)
        -> locomotion agent (authority check + safe-stop watchdogs) -> wheels

No bypass: if the Core Hub dies, its safety pulse stops and the locomotion
agent safe-stops on its own watchdog (<=0.6 s) no matter what Nav2 wants.
The adapter follows the CURRENT authority lease (it does not assume a
holder), so a failover to the Telemetry node keeps autonomy working under
the new holder — same rule as every other commander.
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int8

from friday_module_agent import qos
from friday_locomotion.autonomy import motion_allowed
from friday_msgs.msg import AuthorityLease, Mark1Header, MotionCommand

CMD_TOPIC = '/mark1/locomotion/cmd_motion'
AUTHORITY_TOPIC = '/mark1/system/authority'
CMD_EXPIRY_S = 0.5          # each command is only briefly valid (replay window)
IDLE_STOP_S = 0.5           # no Twist this long -> send one explicit STOP


class NavMotionAdapter(Node):

    def __init__(self):
        super().__init__('nav_motion_adapter')
        self._holder = ''
        self._nonce = 0
        self._last_twist_ns = None
        self._stopped = True
        self._autonomy = 0          # safe default: gated until /mark1/system/autonomy_mode arrives
        self._pub = self.create_publisher(
            MotionCommand, CMD_TOPIC, qos.critical_reliable())
        self.create_subscription(
            AuthorityLease, AUTHORITY_TOPIC, self._on_lease,
            qos.critical_reliable())
        self.create_subscription(Twist, '/cmd_vel_nav', self._on_twist, 10)
        # Transient_local so a late-joining adapter still gets the last published level.
        _autonomy_qos = QoSProfile(depth=1,
                                   reliability=ReliabilityPolicy.RELIABLE,
                                   durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(Int8, '/mark1/system/autonomy_mode',
                                 self._on_autonomy_mode, _autonomy_qos)
        self.create_timer(0.1, self._idle_check)
        self.get_logger().info('nav motion adapter up — Nav2 rides the authority chain')

    def _on_lease(self, msg: AuthorityLease) -> None:
        if msg.holder_module_id != self._holder:
            self.get_logger().info(f'authority holder -> {msg.holder_module_id}')
        self._holder = msg.holder_module_id

    def _on_autonomy_mode(self, msg: Int8) -> None:
        level = int(msg.data)
        if level != self._autonomy:
            self.get_logger().info(f'autonomy level -> {level}')
        self._autonomy = level

    def _on_twist(self, msg: Twist) -> None:
        if not motion_allowed(self._autonomy):
            # L0 (Manual): drop all Nav2-sourced velocity; emit one clean STOP.
            # L2 (Supervised): per-waypoint approval is a later stage — currently
            #   passes through here exactly like L1/L3.  TODO(feat/l2-approval):
            #   add a per-waypoint operator-approval round-trip before forwarding.
            if not self._stopped:
                self._stopped = True
                self._send(MotionCommand.TYPE_STOP, 0.0, 0.0)
            return
        self._last_twist_ns = self.get_clock().now().nanoseconds
        self._stopped = False
        self._send(MotionCommand.TYPE_VELOCITY,
                   float(msg.linear.x), float(msg.angular.z))

    def _idle_check(self) -> None:
        # Nav2 went quiet (goal reached/aborted): command an explicit stop once.
        # Belt only — the loco agent's own safety watchdogs are the suspenders.
        if self._stopped or self._last_twist_ns is None:
            return
        age_s = (self.get_clock().now().nanoseconds - self._last_twist_ns) / 1e9
        if age_s > IDLE_STOP_S:
            self._stopped = True
            self._send(MotionCommand.TYPE_STOP, 0.0, 0.0)

    def _send(self, cmd_type: int, v: float, w: float) -> None:
        if not self._holder:
            return                       # no authority lease seen yet: stay silent
        self._nonce += 1
        cmd = MotionCommand()
        cmd.header = Mark1Header()
        cmd.header.module_id = 'nav2-adapter'
        cmd.header.stamp = self.get_clock().now().to_msg()
        cmd.type = cmd_type
        cmd.linear_velocity = v
        cmd.angular_velocity = w
        cmd.source = self._holder        # command under the CURRENT lease
        cmd.token_id = 'nav2'
        cmd.nonce = self._nonce
        cmd.expires_at = (self.get_clock().now()
                          + Duration(seconds=CMD_EXPIRY_S)).to_msg()
        self._pub.publish(cmd)


def main(args=None):
    rclpy.init(args=args)
    node = NavMotionAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
