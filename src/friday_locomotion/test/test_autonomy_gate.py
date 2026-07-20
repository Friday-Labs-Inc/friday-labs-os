"""Unit tests for the pure autonomy-gate logic (no ROS runtime)."""

from friday_locomotion.autonomy import motion_allowed


def test_l0_manual_blocks_autonomy_motion():
    assert motion_allowed(0) is False


def test_l1_assisted_allows_motion():
    assert motion_allowed(1) is True


def test_l2_supervised_allows_motion():
    # L2 per-waypoint approval round-trip is a later stage; gate is OPEN for now.
    assert motion_allowed(2) is True


def test_l3_autonomous_allows_motion():
    assert motion_allowed(3) is True


def test_unknown_high_level_treated_as_allowed():
    # Defensive: any level other than 0 passes (telemetry validates 0..3 at the
    # source; the adapter uses the cached value which was already validated).
    assert motion_allowed(99) is True


def test_negative_level_not_manual():
    # Sanity: negative values are not L0, so they pass.  The source validator
    # rejects them before they reach the adapter, but the helper must not crash.
    assert motion_allowed(-1) is True
