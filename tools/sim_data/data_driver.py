"""Sim-only data driver: wander Mark 1 around a Gazebo world for recording.

Publishes Twist on /cmd_vel_nav, the same input Nav2 uses, so every move
still goes through nav_motion_adapter -> authority lease -> locomotion
watchdog. Nothing here can bypass safety.

Behaviour (deliberately varied, so the dataset holds turns, slopes,
near-misses and recoveries, not just straight lines):
  - explore: head for a random goal up to RADIUS_M from the start, with a
    little steering noise; pick a new goal on arrival, after GOAL_TIMEOUT_S,
    or after backing away from something. Pure random wandering kept circling
    one patch of the world and filled the dataset with near-duplicate views.
  - if friday_terrain reports lethal ground in the corridor ahead, or
    the rover is blocked (real progress ALONG ITS HEADING far below what was
    commanded, e.g. pinned against a wall and scraping sideways), back up
    while turning, then choose a new goal

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
# lethal only: reacting to STEEP (70) made the rover back up every ~1.6 s on Baylands
# hills (385 back-ups in 10 min). Unclimbable walls are caught by the blocked check.
DANGER_COST, AHEAD_M, HALF_WIDTH_M = 90, 1.2, 0.35
STUCK_WINDOW_S, MIN_PROGRESS = 1.5, 0.3   # blocked if <30% of commanded distance made good
BACKUP_S, RADIUS_M = 1.5, 40.0
# gentle heading control: a gain of 1.2 pinned steering at full lock 55% of the time
GOAL_REACHED_M, GOAL_TIMEOUT_S, HEADING_GAIN, GOAL_TURN_RPS = 2.0, 90.0, 0.5, 0.35


class DataDriver(Node):

    def __init__(self, minutes: float, seed: int) -> None:
        super().__init__('data_driver')
        self.rng = random.Random(seed)
        self.end_ns = self.get_clock().now().nanoseconds + int(minutes * 60e9)
        self.turn, self.backup_until, self.pose, self.start = 0.0, 0, None, None
        self.goal, self.goal_since = None, 0
        self.history: list[tuple[int, float, float, float]] = []  # (t, x, y, commanded v)
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
        """Blocked = progress along the heading is far below what was commanded.
        Plain distance moved is not enough: sliding sideways along a curb moves
        the rover but makes no progress, and the wheels just spin."""
        if self.pose is None:
            return False
        self.history.append((now, self.pose[0], self.pose[1], CRUISE_MPS))
        self.history = [h for h in self.history if now - h[0] < STUCK_WINDOW_S * 1e9]
        t0, x0, y0, _ = self.history[0]
        if now - t0 < (STUCK_WINDOW_S - 0.2) * 1e9:
            return False
        yaw = self.pose[2]
        progress = math.cos(yaw) * (self.pose[0] - x0) + math.sin(yaw) * (self.pose[1] - y0)
        expected = sum(h[3] for h in self.history) * 0.1  # one history entry per 0.1 s tick
        return progress < MIN_PROGRESS * expected

    def steer_to_goal(self, now: int) -> float:
        """Head for a random goal near the start, with a little noise for variety."""
        if self.pose is None or self.start is None:
            return 0.0
        if (self.goal is None or math.dist(self.pose[:2], self.goal) < GOAL_REACHED_M
                or now - self.goal_since > GOAL_TIMEOUT_S * 1e9):
            r, a = RADIUS_M * math.sqrt(self.rng.random()), self.rng.uniform(-math.pi, math.pi)
            self.goal, self.goal_since = (self.start[0] + r * math.cos(a), self.start[1] + r * math.sin(a)), now
        bearing = math.atan2(self.goal[1] - self.pose[1], self.goal[0] - self.pose[0])
        err = (bearing - self.pose[2] + math.pi) % (2 * math.pi) - math.pi
        noisy = HEADING_GAIN * err + self.rng.gauss(0, 0.1)
        return max(-GOAL_TURN_RPS, min(GOAL_TURN_RPS, noisy))

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
            self.goal = None                       # whatever blocked us, go somewhere else
        else:
            self.turn = self.steer_to_goal(now)
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
