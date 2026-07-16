"""Pure 6-wheel corner-steer (Ackermann) kinematics for the Locomotion Control Unit.

Converts a unicycle MotionCommand (linear v, angular w) into per-wheel drive
speeds and corner steer angles — the real LCU job (6 drive motors + 4 corner
steering servos, per the Mark 1 architecture). ROS-free so it is unit-testable.

Frame: ROS REP-103 (+x forward, +y left). Geometry measured from
mark1_sim_spec.md. The 4 corner wheels steer; the 2 middle wheels are drive-only.
On a turn the rover follows a circle about the ICR at (0, R=v/w); each wheel is
pointed tangent to its own circle and driven at that circle's speed (true
coordinated steering — inner wheels turn sharper and roll slower than outer).
"""

import math

WHEEL_RADIUS = 0.065       # 130 mm DIY-replica wheel (in production); was 0.070 (140 mm).
STEER_LIMIT = 0.6          # rad, matches the URDF steer joint limit
# NOTE: wheel POSITIONS below are the sim model's own geometry, not yet derived from the
# in-production DIY CAD — re-measure off Mechanics/reference-models/howtomechatronics-replica
# and reconcile with the URDF when tightening sim↔hardware fidelity.
_EPS = 1e-5

# drive wheels in controller order: LF, LM, LR, RF, RM, RR  (x fwd, y left)
DRIVE_WHEELS = (
    ('left_front',   0.302,  0.291),
    ('left_mid',     0.015,  0.323),
    ('left_rear',   -0.302,  0.291),
    ('right_front',  0.302, -0.291),
    ('right_mid',    0.015, -0.323),
    ('right_rear',  -0.302, -0.291),
)
# steer wheels in controller order: LF, LR, RF, RR
STEER_WHEELS = (
    ('left_front',   0.302,  0.291),
    ('left_rear',   -0.302,  0.291),
    ('right_front',  0.302, -0.291),
    ('right_rear',  -0.302, -0.291),
)


def drive_and_steer(v, w):
    """(v m/s, w rad/s) -> (wheel_velocities[6] rad/s, steer_angles[4] rad).

    wheel_velocities in DRIVE_WHEELS order, steer_angles in STEER_WHEELS order.
    Each wheel's ground velocity in the body frame is (v - w*y, w*x):
      * a CORNER wheel points along that vector and rolls at its magnitude;
      * a MIDDLE (fixed) wheel rolls only the forward component (lateral scrubs).
    Steer angles are normalised to (-pi/2, pi/2) and clamped to the joint limit,
    so a tight/zero-radius request degrades gracefully instead of flipping sign."""
    if abs(w) < _EPS:                                      # straight line
        return ([v / WHEEL_RADIUS] * len(DRIVE_WHEELS),
                [0.0] * len(STEER_WHEELS))

    wheel_velocities = []
    for _, x, y in DRIVE_WHEELS:
        vx, vy = v - w * y, w * x
        if abs(x) < 0.1:                                  # middle: fixed forward
            wheel_velocities.append(vx / WHEEL_RADIUS)
        else:                                             # corner: along its heading
            wheel_velocities.append(math.copysign(math.hypot(vx, vy), vx) / WHEEL_RADIUS)

    steer_angles = []
    for _, x, y in STEER_WHEELS:
        vx, vy = v - w * y, w * x
        ang = math.atan2(vy, vx) if vx >= 0 else math.atan2(-vy, -vx)
        steer_angles.append(max(-STEER_LIMIT, min(STEER_LIMIT, ang)))

    return wheel_velocities, steer_angles


# ---- inverse: wheels -> body twist (odometry) ------------------------------
# The two MIDDLE wheels are fixed (no steer), so they form a clean differential
# pair whatever the corner wheels are doing:  v_mid = v - w*y_mid. Solving the
# left/right pair gives body (v, w) exactly -- no steer angles needed.
_Y_MID_LEFT = DRIVE_WHEELS[1][2]     # +0.323 (left_mid y)
_Y_MID_RIGHT = DRIVE_WHEELS[4][2]    # -0.323 (right_mid y)


def body_twist_from_wheels(wheel_velocities):
    """wheel_velocities[6] (rad/s, DRIVE_WHEELS order) -> (v m/s, w rad/s).

    Uses the middle differential pair (indices 1 and 4). Middle wheels only
    roll their forward component, so this is exact for the fixed pair.
    """
    v_left = wheel_velocities[1] * WHEEL_RADIUS
    v_right = wheel_velocities[4] * WHEEL_RADIUS
    v = (v_left + v_right) / 2.0
    w = (v_right - v_left) / (_Y_MID_LEFT - _Y_MID_RIGHT)
    return v, w


def integrate_pose(x, y, yaw, v, w, dt):
    """Dead-reckon one step (unicycle model, exact arc when turning)."""
    if abs(w) < _EPS:
        return (x + v * dt * math.cos(yaw),
                y + v * dt * math.sin(yaw),
                yaw)
    new_yaw = yaw + w * dt
    radius = v / w
    return (x + radius * (math.sin(new_yaw) - math.sin(yaw)),
            y - radius * (math.cos(new_yaw) - math.cos(yaw)),
            new_yaw)
