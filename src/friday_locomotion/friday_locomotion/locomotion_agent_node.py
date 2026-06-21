"""Locomotion Control Unit agent — Phase 3 (closed-loop motion).

Builds on the Phase 2 stub: still registers, heartbeats, and reports health via
the ModuleAgent base — and now also closes the motion loop:

  * subscribes MotionCommand on /mark1/locomotion/cmd_motion (critical_reliable),
  * runs a simple unicycle motion model, and
  * publishes nav_msgs/Odometry on /mark1/locomotion/odometry (state_default).

It is still a *software* model — real motor/steer drivers (via micro-ROS to the
ESP32) and the firmware 100 ms safe-stop arrive with the hardware. In Gazebo this
node is swapped for gz_ros2_control publishing the *same* Odometry, so the rest
of the OS can't tell the difference (sim/hardware parity).
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import MultiThreadedExecutor

from friday_msgs.msg import MotionCommand
from friday_module_agent import qos
from friday_module_agent.module_agent import ModuleAgent

CONTROL_PERIOD_S = 0.05   # 20 Hz odometry update
CMD_TOPIC = '/mark1/locomotion/cmd_motion'
ODOM_TOPIC = '/mark1/locomotion/odometry'


class LocomotionAgent(ModuleAgent):
    """Lifecycle agent for the Locomotion Control Unit with a motion model."""

    def __init__(self):
        super().__init__(
            node_name='locomotion',
            module_id='MARK1-LOCO-001',
            module_ns='locomotion',
            hardware_type='locomotion',
            capabilities=['drive', 'steer', 'safe_stop'],
            sw_version='0.2.0',
        )
        # Pose (in the odom frame) and the current commanded velocities.
        self._x = 0.0
        self._y = 0.0
        self._theta = 0.0
        self._v = 0.0          # commanded linear velocity (m/s)
        self._w = 0.0          # commanded angular velocity (rad/s)
        self._last_ns = 0
        self._odom_pub = None
        self._cmd_sub = None
        self._motion_timer = None

    # ---- ModuleAgent hardware hooks ---------------------------------------
    def configure_hardware(self) -> None:
        self._odom_pub = self.create_lifecycle_publisher(
            Odometry, ODOM_TOPIC, qos.state_default())
        self._cmd_sub = self.create_subscription(
            MotionCommand, CMD_TOPIC, self._on_command, qos.critical_reliable())

    def activate_hardware(self) -> None:
        self._x = self._y = self._theta = 0.0
        self._v = self._w = 0.0
        self._last_ns = self.get_clock().now().nanoseconds
        self._motion_timer = self.create_timer(CONTROL_PERIOD_S, self._step)

    def enter_safe_state(self) -> None:
        # Power-to-release behavior: stop integrating and zero the command.
        if self._motion_timer is not None:
            self.destroy_timer(self._motion_timer)
            self._motion_timer = None
        self._v = self._w = 0.0
        self.get_logger().info('locomotion safe-state: motion stopped, motors commanded off (stub)')

    # ---- motion ------------------------------------------------------------
    def _on_command(self, msg: MotionCommand) -> None:
        if msg.type == MotionCommand.TYPE_VELOCITY:
            self._v = msg.linear_velocity
            self._w = msg.angular_velocity
        else:  # TYPE_STOP or TYPE_SAFE_STOP
            self._v = self._w = 0.0
        self.get_logger().info(
            f'cmd_motion type={msg.type} v={self._v:.2f} w={self._w:.2f} '
            f'src={msg.source or "(none)"}')

    def _step(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        dt = (now_ns - self._last_ns) / 1e9
        self._last_ns = now_ns
        # Unicycle integration.
        self._theta += self._w * dt
        self._x += self._v * math.cos(self._theta) * dt
        self._y += self._v * math.sin(self._theta) * dt
        self._publish_odometry(now_ns)

    def _publish_odometry(self, now_ns: int) -> None:
        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = 'odom'          # Locomotion owns the odom frame
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self._x
        odom.pose.pose.position.y = self._y
        odom.pose.pose.orientation.z = math.sin(self._theta / 2.0)
        odom.pose.pose.orientation.w = math.cos(self._theta / 2.0)
        odom.twist.twist.linear.x = self._v
        odom.twist.twist.angular.z = self._w
        self._odom_pub.publish(odom)


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
