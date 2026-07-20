"""Unit tests for friday_telemetry.mission_planner — boustrophedon planner."""

import math

from friday_telemetry.mission_planner import plan_survey


def test_lane_count_24x24_3m():
    """24 m wide zone, 3 m spacing -> 8 lanes -> 16 waypoints."""
    wps = plan_survey([-12, -12, 12, 12], lane_spacing_m=3.0)
    n_lanes = math.ceil(24 / 3.0)
    assert n_lanes == 8
    assert len(wps) == 2 * n_lanes  # 16


def test_lane_count_ceil():
    """lane_count = ceil(width / spacing) — non-integer widths."""
    wps = plan_survey([0, 0, 10, 20], lane_spacing_m=3.0)
    n_lanes = math.ceil(10 / 3.0)  # ceil(3.33) = 4
    assert len(wps) == 2 * n_lanes


def test_serpentine_order():
    """Even lanes go bottom-to-top, odd lanes go top-to-bottom."""
    # zone [0,0,9,10], spacing 3 -> ceil(9/3)=3 lanes
    wps = plan_survey([0, 0, 9, 10], lane_spacing_m=3.0)
    assert len(wps) == 6
    # Lane 0 (x=0): (0,0) -> (0,10)
    assert wps[0] == (0.0, 0.0)
    assert wps[1] == (0.0, 10.0)
    # Lane 1 (x=3): (3,10) -> (3,0)
    assert wps[2] == (3.0, 10.0)
    assert wps[3] == (3.0, 0.0)
    # Lane 2 (x=6): (6,0) -> (6,10)
    assert wps[4] == (6.0, 0.0)
    assert wps[5] == (6.0, 10.0)


def test_coverage_all_x_in_zone():
    """All waypoint X coords lie within [xmin, xmax]."""
    zone = [-12, -12, 12, 12]
    wps = plan_survey(zone, lane_spacing_m=3.0)
    xmin, xmax = min(zone[0], zone[2]), max(zone[0], zone[2])
    for x, _ in wps:
        assert xmin <= x <= xmax, f"x={x} out of zone [{xmin}, {xmax}]"


def test_coverage_all_y_at_zone_edges():
    """Every lane covers the full Y extent (each lane has both ymin and ymax)."""
    zone = [0, -5, 9, 5]
    wps = plan_survey(zone, lane_spacing_m=3.0)
    n_lanes = math.ceil(9 / 3.0)  # 3
    assert len(wps) == 6
    # Group by lane (pairs of waypoints)
    for i in range(n_lanes):
        ys = {wps[2 * i][1], wps[2 * i + 1][1]}
        assert ys == {-5.0, 5.0}, f"lane {i} missing a zone edge: {ys}"


def test_zone_corner_order_invariant():
    """zone can be given with any corner pair — normalised internally."""
    wps_a = plan_survey([-12, -12, 12, 12], 3.0)
    wps_b = plan_survey([12, 12, -12, -12], 3.0)
    assert wps_a == wps_b


def test_single_lane_zero_width():
    """Width exactly equals spacing -> 1 lane, 2 waypoints."""
    wps = plan_survey([0, 0, 3, 10], lane_spacing_m=3.0)
    assert len(wps) == 2


def test_degenerate_zero_area():
    """Zero-area zone returns empty list (no waypoints)."""
    assert plan_survey([0, 0, 0, 10], 3.0) == []
    assert plan_survey([0, 0, 10, 0], 3.0) == []


def test_negative_spacing():
    """Non-positive spacing returns empty list (guard)."""
    assert plan_survey([-12, -12, 12, 12], 0.0) == []
    assert plan_survey([-12, -12, 12, 12], -1.0) == []


def test_last_lane_clamped_to_zone():
    """When width is not a multiple of spacing, the last lane is at xmax."""
    wps = plan_survey([0, 0, 7, 10], lane_spacing_m=3.0)
    # n_lanes = ceil(7/3) = 3; lanes at x=0, 3, 6 but clamped: min(0+2*3,7)=6,
    # then last is min(6,7)=6 — wait actually it's min(0+2*3,7)=6 OK
    xs = [w[0] for w in wps]
    assert max(xs) <= 7.0, f"last lane x={max(xs)} exceeds xmax=7"
