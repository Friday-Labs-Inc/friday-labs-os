"""Unit tests for protocol constants (no ROS runtime needed)."""

from friday_module_agent.protocol import (
    HEALTH_DEGRADED,
    HEALTH_FAULT,
    HEALTH_OK,
    PROTOCOL_MAJOR,
    major_compatible,
)


def test_major_compatible_matches():
    assert major_compatible(PROTOCOL_MAJOR) is True


def test_major_incompatible_rejected():
    assert major_compatible(PROTOCOL_MAJOR + 1) is False


def test_health_codes_distinct():
    assert len({HEALTH_OK, HEALTH_DEGRADED, HEALTH_FAULT}) == 3
