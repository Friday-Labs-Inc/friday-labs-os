"""Sim-only data driver: wander Mark 1 around a Gazebo world for recording.

Publishes Twist on /cmd_vel_nav, the same input Nav2 uses, so every move
still goes through nav_motion_adapter -> authority lease -> locomotion
watchdog. Nothing here can bypass safety.

Behaviour (deliberately varied, so the dataset holds turns, slopes,
near-misses and recoveries, not just straight lines):
  - cruise at ~0.3 m/s with slowly wandering curvature
  - if friday_terrain reports high cost in the corridor ahead, or the rover
    is stuck (true pose barely moved), back up while turning, then go on
  - stay within RADIUS_M of the start; steer home when outside

Also publishes autonomy level L1 (ASSISTED), which the telemetry agent
normally provides; data sessions run without telemetry.

Run (inside the sim container, workspace sourced):
  python3 tools/sim_data/data_driver.py --minutes 10 --seed 1
"""

import argparse
import math
import random

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int8

CRUISE_MPS, MAX_TURN_RPS = 0.3, 0.6
DANGER_COST, AHEAD_M, HALF_WIDTH_M = 90, 1.2, 0.35
STUCK_WINDOW_S, STUCK_MOVE_M = 3.0, 0.05
BACKUP_S, RADIUS_M = 1.5, 25.0


class DataDriver(Node):

    def __init__(self, minutes: float, seed: int) -> None:
        super().__init__('data_driver')
        self.rng = random.Random(seed)
        self.end_ns = self.get_clock().now().nanoseconds + int(minutes * 60e9)
        self.turn, self.backup_until, self.pose, self.start = 0.0, 0, None, None
        self.history: list[tuple[int, float, float]] = []
        self.grid: OccupancyGrid | None = None

        self.cmd = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_publisher(Int8, '/mark1/system/autonomy_mode', latched).publish(Int8(data=1))
        self.create_subscription(OccupancyGrid, '/terrain/costmap', self.on_grid, 1)
        self.create_subscription(PoseStamped, '/model/mark1/pose', self.on_pose, 10)
        self.create_timer(0.1, self.tick)

    def on_grid(self, msg: OccupancyGrid) -> None:
        self.grid = msg

    def on_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.pose = (p.x, p.y, yaw)
        self.start = self.start or (p.x, p.y)

    def danger_ahead(self) -> bool:
        """Highest cost in a corridor in front of the rover (grid is in base_link)."""
        g = self.grid
        if g is None:
            return False
        res, ox, oy, w = g.info.resolution, g.info.origin.position.x, g.info.origin.position.y, g.info.width
        for i, cost in enumerate(g.data):
            x, y = ox + (i % w + 0.5) * res, oy + (i // w + 0.5) * res
            if 0.2 < x < AHEAD_M and abs(y) < HALF_WIDTH_M and cost >= DANGER_COST:
                return True
        return False

    def stuck(self, now: int) -> bool:
        if self.pose is None:
            return False
        self.history.append((now, self.pose[0], self.pose[1]))
        self.history = [h for h in self.history if now - h[0] < STUCK_WINDOW_S * 1e9]
        t0, x0, y0 = self.history[0]
        return now - t0 > (STUCK_WINDOW_S - 0.2) * 1e9 and math.hypot(self.pose[0] - x0, self.pose[1] - y0) < STUCK_MOVE_M

    def tick(self) -> None:
        now = self.get_clock().now().nanoseconds
        twist = Twist()
        if now > self.end_ns:
            self.cmd.publish(twist)
            raise SystemExit
        if now < self.backup_until:
            twist.linear.x, twist.angular.z = -0.2, self.turn
        elif self.danger_ahead() or self.stuck(now):
            self.backup_until = now + int(BACKUP_S * 1e9)
            self.turn = self.rng.choice([-1, 1]) * MAX_TURN_RPS
            self.history.clear()
        else:
            # slow random walk in curvature: varied but smooth paths
            self.turn = max(-MAX_TURN_RPS, min(MAX_TURN_RPS, 0.95 * self.turn + self.rng.gauss(0, 0.08)))
            if self.pose and self.start and math.dist(self.pose[:2], self.start) > RADIUS_M:
                home = math.atan2(self.start[1] - self.pose[1], self.start[0] - self.pose[0])
                err = (home - self.pose[2] + math.pi) % (2 * math.pi) - math.pi
                self.turn = max(-MAX_TURN_RPS, min(MAX_TURN_RPS, 1.5 * err))
            twist.linear.x, twist.angular.z = CRUISE_MPS, self.turn
        self.cmd.publish(twist)


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument('--minutes', type=float, default=10.0)
    args.add_argument('--seed', type=int, default=0)
    a = args.parse_args()
    rclpy.init()
    node = DataDriver(a.minutes, a.seed)
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == '__main__':
    main()
