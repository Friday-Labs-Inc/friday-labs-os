"""spin_agent survives a raising handler (the invalid-transition crash class)."""

import threading

import rclpy
from rclpy.node import Node

from friday_module_agent.runner import spin_agent


class _FaultyNode(Node):
    """Timer handler raises once, then requests shutdown."""

    def __init__(self):
        super().__init__('faulty_test_node')
        self.calls = 0
        self.create_timer(0.05, self._tick)

    def _tick(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError('boom')          # must NOT kill the spin loop
        rclpy.shutdown()                        # second call: end the test


def test_spin_agent_survives_handler_exception():
    rclpy.init()
    node = _FaultyNode()
    t = threading.Thread(target=spin_agent, args=(node,), daemon=True)
    t.start()
    t.join(timeout=10.0)
    assert not t.is_alive(), 'spin_agent did not exit after shutdown'
    assert node.calls >= 2, 'spin loop died on the first exception'
