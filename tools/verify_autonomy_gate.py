"""Live gate integration test for the autonomy enforcement harness.

Runs entirely in-process: two rclpy nodes (adapter under test + test harness),
no Gazebo / Nav2 / SLAM required.  Uses ROS_DOMAIN_ID=99 (set in env before
running) to stay isolated from every other rover on the DDS fabric.

Pass/fail printed to stdout for the docker-logs capture.
"""

import threading
import time

import rclpy
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from friday_locomotion.nav_motion_adapter import NavMotionAdapter
from friday_msgs.msg import AuthorityLease, Mark1Header, MotionCommand
from geometry_msgs.msg import Twist
from std_msgs.msg import Int8


AUTHORITY_TOPIC = '/mark1/system/authority'
AUTONOMY_TOPIC  = '/mark1/system/autonomy_mode'
CMD_TOPIC       = '/mark1/locomotion/cmd_motion'
HOLDER          = 'MARK1-CORE-001'

_latched_qos = QoSProfile(depth=1,
                           reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.TRANSIENT_LOCAL)


class Harness(Node):
    def __init__(self):
        super().__init__('autonomy_gate_harness')
        self._commands = []

        self._auth_pub = self.create_publisher(AuthorityLease, AUTHORITY_TOPIC,
                                               _latched_qos)
        self._autonomy_pub = self.create_publisher(Int8, AUTONOMY_TOPIC,
                                                   _latched_qos)
        self._twist_pub = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        self.create_subscription(MotionCommand, CMD_TOPIC,
                                 self._on_cmd, _latched_qos)

    def _on_cmd(self, msg):
        self._commands.append(msg)

    def publish_authority(self):
        msg = AuthorityLease()
        msg.header = Mark1Header()
        msg.header.module_id = HOLDER
        msg.holder_module_id = HOLDER
        msg.epoch = 1
        msg.expires_at = (self.get_clock().now() + Duration(seconds=60.0)).to_msg()
        self._auth_pub.publish(msg)

    def publish_autonomy(self, level: int):
        msg = Int8()
        msg.data = level
        self._autonomy_pub.publish(msg)
        self.get_logger().info(f'[harness] published autonomy_mode = {level}')

    def publish_twist(self, v=0.3, w=0.0):
        msg = Twist()
        msg.linear.x = v
        msg.angular.z = w
        self._twist_pub.publish(msg)

    def last_cmd(self):
        return self._commands[-1] if self._commands else None

    def clear(self):
        self._commands.clear()


def spin_until(executor, condition_fn, timeout_s=5.0, poll_s=0.05):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        executor.spin_once(timeout_sec=poll_s)
        if condition_fn():
            return True
    return False


def main():
    rclpy.init()
    adapter  = NavMotionAdapter()
    harness  = Harness()
    executor = MultiThreadedExecutor()
    executor.add_node(adapter)
    executor.add_node(harness)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    time.sleep(0.3)   # let subscriptions settle

    # --- Phase 1: establish authority so the adapter will send commands -------
    harness.publish_authority()
    time.sleep(0.2)   # authority lease propagates

    # --- Phase 2: Publish L3 + Twists → expect VELOCITY -------------------
    print('\n[TEST] Phase 2: L3 (Autonomous) — adapter should PASS Twists as VELOCITY')
    harness.publish_autonomy(3)
    time.sleep(0.1)
    harness.clear()
    harness.publish_twist(v=0.4)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        cmd = harness.last_cmd()
        if cmd and cmd.type == MotionCommand.TYPE_VELOCITY:
            break
        time.sleep(0.05)

    cmd = harness.last_cmd()
    if cmd and cmd.type == MotionCommand.TYPE_VELOCITY:
        print(f'  [PASS] L3: VELOCITY command received (v={cmd.linear_velocity:.2f})')
    else:
        print(f'  [FAIL] L3: expected VELOCITY, got {cmd.type if cmd else "nothing"}')
        rclpy.shutdown()
        return

    # --- Phase 3: Publish L0 → expect STOP -------------------------------
    print('\n[TEST] Phase 3: L0 (Manual) — adapter should STOP and drop Twists')
    harness.clear()
    harness.publish_autonomy(0)
    # Keep sending Twists (as Nav2 would): adapter should STOP and then stay stopped
    for _ in range(5):
        time.sleep(0.1)
        harness.publish_twist(v=0.4)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        cmd = harness.last_cmd()
        if cmd and cmd.type == MotionCommand.TYPE_STOP:
            break
        time.sleep(0.05)

    cmd = harness.last_cmd()
    if cmd and cmd.type == MotionCommand.TYPE_STOP:
        print(f'  [PASS] L0: STOP command received')
        # Verify NO subsequent VELOCITY was emitted (adapter should stay gated)
        stop_count = sum(1 for c in harness._commands if c.type == MotionCommand.TYPE_STOP)
        vel_count  = sum(1 for c in harness._commands if c.type == MotionCommand.TYPE_VELOCITY)
        print(f'  [INFO] Commands during L0: STOP={stop_count}, VELOCITY={vel_count}')
        if vel_count == 0:
            print('  [PASS] No spurious VELOCITY commands during L0 gate')
        else:
            print(f'  [FAIL] {vel_count} VELOCITY commands leaked through L0 gate')
    else:
        print(f'  [FAIL] L0: expected STOP, got {cmd.type if cmd else "nothing"}')
        rclpy.shutdown()
        return

    # --- Phase 4: Publish L3 again → adapter should drive again -----------
    print('\n[TEST] Phase 4: L3 restored — adapter should PASS Twists again')
    harness.clear()
    harness.publish_autonomy(3)
    time.sleep(0.2)
    harness.publish_twist(v=0.5)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        cmd = harness.last_cmd()
        if cmd and cmd.type == MotionCommand.TYPE_VELOCITY:
            break
        time.sleep(0.05)

    cmd = harness.last_cmd()
    if cmd and cmd.type == MotionCommand.TYPE_VELOCITY:
        print(f'  [PASS] L3 restored: VELOCITY command received (v={cmd.linear_velocity:.2f})')
    else:
        print(f'  [FAIL] L3 restored: expected VELOCITY, got {cmd.type if cmd else "nothing"}')

    # --- Phase 5: latched topic check ------------------------------------
    print('\n[TEST] Phase 5: /mark1/system/autonomy_mode is latched (transient_local)')
    received = []

    def _latch_cb(m):
        received.append(m.data)

    test_node = rclpy.create_node('latch_checker')
    executor.add_node(test_node)
    test_node.create_subscription(Int8, AUTONOMY_TOPIC, _latch_cb, _latched_qos)
    deadline = time.time() + 2.0
    while time.time() < deadline and not received:
        time.sleep(0.05)
    if received:
        print(f'  [PASS] Late subscriber got latched value: {received[0]}')
    else:
        print('  [FAIL] Late subscriber got no latched value')
    executor.remove_node(test_node)
    test_node.destroy_node()

    print('\n=== autonomy gate verification complete ===')
    rclpy.shutdown()


if __name__ == '__main__':
    main()
