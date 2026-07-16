"""Unit tests for the pure 6-wheel corner-steer kinematics (no ROS)."""

from friday_locomotion import kinematics as k


def test_straight_all_equal_no_steer():
    wv, sa = k.drive_and_steer(0.35, 0.0)
    assert len(wv) == 6 and len(sa) == 4
    assert all(abs(w - 0.35 / k.WHEEL_RADIUS) < 1e-9 for w in wv)   # all v/r
    assert all(abs(a) < 1e-9 for a in sa)                          # no steer


def test_reverse_negative_speeds():
    wv, _ = k.drive_and_steer(-0.35, 0.0)
    assert all(w < 0 for w in wv)


def test_left_turn_outer_faster_and_ackermann_signs():
    # forward + left (w>0): right side is outer -> faster; fronts steer +, rears -
    wv, sa = k.drive_and_steer(0.3, 0.5)
    lf, lm, lr, rf, rm, rr = wv
    assert rf > lf and rm > lm and rr > lr                # right (outer) faster
    sa_lf, sa_lr, sa_rf, sa_rr = sa
    assert sa_lf > 0 and sa_rf > 0                        # front wheels steer left
    assert sa_lr < 0 and sa_rr < 0                        # rear wheels steer right
    assert sa_lf > sa_rf                                  # inner front steers sharper


def test_right_turn_mirrors():
    wv, sa = k.drive_and_steer(0.3, -0.5)
    lf, lm, lr, rf, rm, rr = wv
    assert lf > rf                                        # left now outer -> faster
    assert sa[0] < 0 and sa[2] < 0                        # fronts steer right


def test_steer_clamped_to_limit():
    # a near-zero-radius (tight) request must clamp, never exceed the joint limit
    wv, sa = k.drive_and_steer(0.05, 3.0)
    assert all(abs(a) <= k.STEER_LIMIT + 1e-9 for a in sa)


# ---- inverse kinematics (odometry) -----------------------------------------
def test_inverse_straight_line():
    wheels, _ = k.drive_and_steer(0.5, 0.0)
    v, w = k.body_twist_from_wheels(wheels)
    assert abs(v - 0.5) < 1e-9 and abs(w) < 1e-9


def test_inverse_roundtrip_turn():
    # forward then inverse must recover the commanded twist exactly for the
    # fixed middle pair (their equations are linear and steer-free)
    for v_cmd, w_cmd in [(0.4, 0.3), (0.2, -0.8), (0.0, 0.5), (-0.3, 0.2)]:
        wheels, _ = k.drive_and_steer(v_cmd, w_cmd)
        v, w = k.body_twist_from_wheels(wheels)
        assert abs(v - v_cmd) < 1e-6, (v_cmd, w_cmd)
        assert abs(w - w_cmd) < 1e-6, (v_cmd, w_cmd)


def test_integrate_pose_straight_and_arc():
    import math
    x, y, yaw = k.integrate_pose(0, 0, 0, 1.0, 0.0, 2.0)
    assert (x, y, yaw) == (2.0, 0.0, 0.0)
    # quarter circle left at r=1: v=w -> ends at (1,1) facing +y
    x, y, yaw = k.integrate_pose(0, 0, 0, 1.0, 1.0, math.pi / 2)
    assert abs(x - 1.0) < 1e-9 and abs(y - 1.0) < 1e-9
    assert abs(yaw - math.pi / 2) < 1e-9
