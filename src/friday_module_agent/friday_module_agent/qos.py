"""The locked Friday Labs OS QoS policy.

Four named profiles, defined once and referenced by name on both sides of every
topic. Audited by the qos-audit skill. Source of truth:
docs/architecture/ROS 2 Interface and Message Contract.md.
"""

from rclpy.duration import Duration
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSLivelinessPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

# Heartbeat/fault-detection defaults (tune in field testing).
HEARTBEAT_PERIOD_S = 0.2     # 5 Hz publish rate
HEARTBEAT_DEADLINE_S = 0.5   # QoS deadline
HEARTBEAT_LEASE_S = 1.0      # liveliness lease
HEALTH_PERIOD_S = 1.0        # health publish rate


def critical_reliable() -> QoSProfile:
    """Commands, emergency stop, recovery, registration."""
    return QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=10,
    )


def state_default() -> QoSProfile:
    """Health, mission status, odometry."""
    return QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.VOLATILE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=10,
    )


def sensor_stream() -> QoSProfile:
    """LiDAR, camera, raw sensor streams."""
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        durability=QoSDurabilityPolicy.VOLATILE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=5,
    )


def heartbeat_monitor() -> QoSProfile:
    """Health-monitor SUBSCRIPTION to module heartbeats.

    Same wire QoS as heartbeat() but with NO deadline/liveliness REQUEST:
    hardware module agents publish through the micro-ROS (XRCE) agent, whose
    binary entity creation cannot offer finite deadline/liveliness -- a
    requesting subscriber would refuse the writer outright (incompatible QoS)
    and hear nothing. Liveness is enforced in software by the registry age
    check (DEGRADED/DEAD budgets), which is the contract mechanism; Pi-side
    agents may still OFFER deadline+liveliness on their publishers.
    """
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        durability=QoSDurabilityPolicy.VOLATILE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=1,
    )


def heartbeat() -> QoSProfile:
    """Heartbeats: BEST_EFFORT, KEEP_LAST 1, with Deadline + Liveliness."""
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        durability=QoSDurabilityPolicy.VOLATILE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=1,
        deadline=Duration(seconds=HEARTBEAT_DEADLINE_S),
        liveliness=QoSLivelinessPolicy.AUTOMATIC,
        liveliness_lease_duration=Duration(seconds=HEARTBEAT_LEASE_S),
    )
