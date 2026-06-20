"""Locomotion Control Unit agent — Phase 2 walking-skeleton stub.

Proves a real module slots into the lifecycle spine: it subclasses ModuleAgent,
so it registers with the Core Hub on configure, heartbeats at 5 Hz, and reports
health while active — with zero module-specific glue.

NOT yet implemented (later phases, see docs/modules/Locomotion Control Unit.md
and docs/build/Locomotion Deck - Pin-Level Schematic.md):
  * MotionCommand subscription -> motor/steer drivers (via micro-ROS to ESP32),
  * nav_msgs/Odometry publication from wheel encoders,
  * the 100 ms firmware-watchdog safe-stop wired into enter_safe_state().
"""

import rclpy
from rclpy.executors import MultiThreadedExecutor

from friday_module_agent.module_agent import ModuleAgent


class LocomotionAgent(ModuleAgent):
    """Lifecycle agent for the Locomotion Control Unit (stub)."""

    def __init__(self):
        super().__init__(
            node_name='locomotion',
            module_id='MARK1-LOCO-001',
            module_ns='locomotion',
            hardware_type='locomotion',
            capabilities=['drive', 'steer', 'safe_stop'],
            sw_version='0.1.0',
        )

    def enter_safe_state(self) -> None:
        # TODO(phase2): command the ESP32 to drop pawls + zero motor PWM.
        self.get_logger().info('locomotion safe-state: motors commanded off (stub)')


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
