"""Backup-attitude math for the phone pod — pure, no ROS.

The phone is NOT a redundant IMU: 10 Hz over WiFi with arrival timestamps can
never replace the wired 100 Hz BNO085 in the localization filter. What it CAN
do is answer the questions that survive low rate and jitter:

  * tilt  — "is the rover level, or is it about to roll?" (develops over
    hundreds of ms; 10 Hz sees it fine)
  * vibration — "are the motors shaking abnormally?" (a magnitude statistic)
  * heading — an INDEPENDENT compass reference (the BNO085 has its own; two
    disagreeing compasses is information, one silent compass is not)

So this is a FALLBACK, not a failover: if the real IMU dies the rover
safe-stops (a dead sensor on the safety path is a fault, full stop) and these
values tell the operator what state it stopped in — level or tipped, moving or
still, facing where. Everything here is advisory and labelled as such.
"""

import math

# Gravity magnitude sanity band. Outside it the phone is accelerating hard (or
# in free fall) and a gravity-derived tilt angle would be nonsense.
G_MIN = 8.0
G_MAX = 11.5
G_NOMINAL = 9.80665


def tilt_deg(ax, ay, az):
    """Angle between the phone's -Z axis and gravity, in degrees (0 = flat).

    None when the accel vector is not dominated by gravity (hard acceleration
    or free fall) — an honest 'unknown' beats a confident wrong angle.
    """
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    if not (G_MIN <= norm <= G_MAX):
        return None
    cos_t = max(-1.0, min(1.0, az / norm))
    return math.degrees(math.acos(cos_t))


def vibration_rms(samples):
    """RMS deviation of |accel| from gravity across samples, in m/s^2.

    samples: iterable of (ax, ay, az). ~0 at rest; grows with shaking. Uses the
    magnitude (not per-axis) so it is orientation-independent.
    """
    devs = []
    for ax, ay, az in samples:
        norm = math.sqrt(ax * ax + ay * ay + az * az)
        devs.append(norm - G_NOMINAL)
    if not devs:
        return None
    return math.sqrt(sum(d * d for d in devs) / len(devs))


def heading_deg(ax, ay, az, mx, my, mz):
    """Tilt-compensated magnetic heading in degrees (0-360, magnetic north).

    Standard tilt compensation: derive roll/pitch from gravity, de-rotate the
    magnetometer into the horizontal plane, then atan2. None when the inputs
    can't support an answer (no mag, or gravity unusable).

    NOTE: magnetic, not true north (no declination applied — that needs the GPS
    position and a WMM model). Uncalibrated: hard/soft-iron distortion from the
    rover's own motors is NOT compensated. Advisory only.
    """
    if mx is None or my is None or mz is None:
        return None
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    if not (G_MIN <= norm <= G_MAX):
        return None
    roll = math.atan2(ay, az)
    pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
    mxh = (mx * math.cos(pitch)
           + my * math.sin(roll) * math.sin(pitch)
           + mz * math.cos(roll) * math.sin(pitch))
    myh = my * math.cos(roll) - mz * math.sin(roll)
    return math.degrees(math.atan2(-myh, mxh)) % 360.0
