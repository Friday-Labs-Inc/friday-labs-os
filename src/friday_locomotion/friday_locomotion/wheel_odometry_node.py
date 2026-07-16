"""Wheel odometry -- dead-reckoning from /joint_states, for the EKF to fuse.

Reads the six drive-wheel joint velocities, recovers body (v, w) via the
middle differential pair (kinematics.body_twist_from_wheels), integrates a
pose, and publishes nav_msgs/Odometry on /odom (child base_link).

Deliberately does NOT broadcast TF: the robot_localization EKF owns the
odom->base_link transform (REP-105) -- two writers of one frame is chaos.
Works identically in sim (gz joint states) and on hardware (encoder-fed
joint states from the Drive board) -- that is the whole point.
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import JointState

from friday_locomotion import kinematics

WHEEL_JOINTS = ('wheel_left_front_joint', 'wheel_left_mid_joint',
                'wheel_left_rear_joint', 'wheel_right_front_joint',
                'wheel_right_mid_joint', 'wheel_right_rear_joint')


class WheelOdometry(Node):

    def __init__(self):
        super().__init__('wheel_odometry')
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._last_stamp = None
        self._pub = self.create_publisher(Odometry, '/odom', 10)
        self.create_subscription(JointState, '/joint_states', self._on_joints, 10)
        self.get_logger().info('wheel odometry up (middle differential pair)')

    def _on_joints(self, msg: JointState) -> None:
        try:
            idx = [msg.name.index(j) for j in WHEEL_JOINTS]
        except ValueError:
            return                                  # not our joints (yet)
        if len(msg.velocity) <= max(idx):
            return
        stamp_s = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self._last_stamp is None:
            self._last_stamp = stamp_s
            return
        dt = stamp_s - self._last_stamp
        self._last_stamp = stamp_s
        if not 0.0 < dt < 1.0:                      # rewind/jump: skip honestly
            return
        wheel_vel = [msg.velocity[i] for i in idx]
        v, w = kinematics.body_twist_from_wheels(wheel_vel)
        self._x, self._y, self._yaw = kinematics.integrate_pose(
            self._x, self._y, self._yaw, v, w, dt)

        odom = Odometry()
        odom.header.stamp = msg.header.stamp
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self._x
        odom.pose.pose.position.y = self._y
        odom.pose.pose.orientation.z = math.sin(self._yaw / 2.0)
        odom.pose.pose.orientation.w = math.cos(self._yaw / 2.0)
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w
        # honest covariances: wheels slip; trust velocities more than pose
        odom.pose.covariance[0] = odom.pose.covariance[7] = 0.05
        odom.pose.covariance[35] = 0.10
        odom.twist.covariance[0] = 0.02
        odom.twist.covariance[35] = 0.05
        self._pub.publish(odom)


def main(args=None):
    rclpy.init(args=args)
    node = WheelOdometry()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
