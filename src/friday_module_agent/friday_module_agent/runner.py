"""Crash-proof spin loop shared by every Python module agent.

rclpy's LifecycleNode RAISES (rather than rejecting) when its change_state
service receives an invalid transition -- e.g. activate while unconfigured.
With a bare executor.spin() that exception unwinds main() and kills the
process (seen live: the envpod bridge crash-looped under systemd during
bring-up). The ESP32 rclc agents reject invalid transitions gracefully;
this gives the Python agents the same resilience: a handler exception is
logged loudly and the executor re-enters spin. A rover daemon must degrade,
not die -- systemd would restart it, but a restart wipes lifecycle state
and drops the module off the registry.
"""

import rclpy
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor


def spin_agent(node) -> None:
    """Spin a module agent until shutdown, surviving handler exceptions."""
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        while rclpy.ok():
            try:
                executor.spin()
                break                          # clean spin exit
            except (KeyboardInterrupt, ExternalShutdownException):
                break
            except Exception as exc:  # noqa: BLE001 -- deliberate: stay alive
                node.get_logger().error(
                    f'recovered from handler exception: {exc!r}')
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
