"""Pure ingest logic for the phone sensor pod — no ROS dependencies.

Parses, validates, and gates the two streams the OnePlus phone sends:

  * IMU: HyperIMU datagrams over UDP -- CSV (the app's actual wire format,
    confirmed by live capture 2026-07-16: comma-separated floats, CRLF) or
    JSON (older assumption, kept for compatibility). SI units.
  * GPS: gpsd TPV reports (newline-delimited JSON over gpsd's TCP socket)

The phone is an untrusted advisory sensor, so everything here rejects rather
than repairs: malformed JSON, missing fields, non-finite values, out-of-range
readings, and teleporting fixes are all dropped. NaN policy is per field —
IMU fields must be finite; NavSatFix altitude may legitimately be NaN (2D fix).
"""

import json
import math
from dataclasses import dataclass

# Sanity gates for an advisory phone IMU. Readings outside these are sensor
# glitches or spoofed packets, never real rover motion.
ACCEL_ABS_MAX = 80.0    # m/s^2 (~8 g)
GYRO_ABS_MAX = 35.0     # rad/s (~2000 deg/s)
# Earth's field is ~25-65 uT. Anything far outside is a magnet, a motor, or a
# glitch — reject rather than report a confidently wrong heading.
MAG_NORM_MIN_UT = 15.0
MAG_NORM_MAX_UT = 90.0

# A fix that moves more than this from the previous fresh fix is rejected as a
# teleport (0.5 deg of latitude is ~55 km — no rover does that between fixes).
MAX_FIX_JUMP_DEG = 0.5

# sensor_msgs/NavSatFix position_covariance_type values.
COVARIANCE_TYPE_UNKNOWN = 0
COVARIANCE_TYPE_APPROXIMATED = 2

# Health "overall" codes (mirror friday_module_agent.protocol / HealthStatus).
HEALTH_OK = 0
HEALTH_DEGRADED = 1


@dataclass(frozen=True)
class ImuSample:
    """One validated IMU reading, SI units, all fields finite.

    mx/my/mz (microtesla) are the magnetometer when the phone streams one and
    the reading passes the field-strength gate; None otherwise. They feed the
    ADVISORY backup-attitude heading only — never localization.
    """

    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    mx: float = None
    my: float = None
    mz: float = None


@dataclass(frozen=True)
class FixSample:
    """One validated GPS fix. altitude may be NaN (2D fix)."""

    latitude: float
    longitude: float
    altitude: float
    position_covariance: tuple      # 9 floats, row-major 3x3
    covariance_type: int


@dataclass(frozen=True)
class RateWindow:
    """State of a fixed one-second rate-limit window."""

    window_start_s: float
    count: int


def _finite_triplet(value):
    """Return (x, y, z) floats if value is a list of >=3 finite numbers, else None."""
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    out = []
    for v in value[:3]:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        f = float(v)
        if not math.isfinite(f):
            return None
        out.append(f)
    return tuple(out)


def _find_triplet(data: dict, substring: str):
    """First value in data whose key contains substring (case-insensitive).

    HyperIMU keys carry the device's chip names (e.g. 'LSM6DSO Accelerometer'),
    so matching is by sensor kind, not exact key.
    """
    for key, value in data.items():
        if substring in str(key).lower():
            return _finite_triplet(value)
    return None


def mag_is_plausible(mx, my, mz) -> bool:
    """True iff the vector's magnitude looks like Earth's field."""
    norm = math.sqrt(mx * mx + my * my + mz * mz)
    return MAG_NORM_MIN_UT <= norm <= MAG_NORM_MAX_UT


def _parse_csv(text: str, accel_i: int, gyro_i: int, mag_i: int = -1):
    """HyperIMU CSV line -> (accel, gyro, mag) triplets, or None. mag may be None.

    The stream is the phone's TICKED sensors in list order, 3 floats each.
    With only Accelerometer + Gyroscope ticked (the documented setup) the
    defaults accel_i=0, gyro_i=3 are correct; other layouts remap via the
    csv_accel_index / csv_gyro_index parameters.
    """
    parts = text.strip().split(',')
    indices = [accel_i, gyro_i] + ([mag_i] if mag_i >= 0 else [])
    need = max(indices) + 3
    if len(parts) < need:
        return None
    try:
        vals = [float(p) for p in parts[:need]]
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in vals):
        return None
    mag = tuple(vals[mag_i:mag_i + 3]) if mag_i >= 0 else None
    if mag is not None and not mag_is_plausible(*mag):
        mag = None                      # drop the mag, keep the accel/gyro sample
    return tuple(vals[accel_i:accel_i + 3]), tuple(vals[gyro_i:gyro_i + 3]), mag


def parse_imu_datagram(raw: bytes, accel_i: int = 0, gyro_i: int = 3, mag_i: int = -1):
    """bytes -> ImuSample, or None if the datagram fails any check."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        csv = _parse_csv(text, accel_i, gyro_i, mag_i)
        if csv is None:
            return None
        accel, gyro, mag = csv
        if any(abs(a) > ACCEL_ABS_MAX for a in accel):
            return None
        if any(abs(g) > GYRO_ABS_MAX for g in gyro):
            return None
        mag = mag or (None, None, None)
        return ImuSample(ax=accel[0], ay=accel[1], az=accel[2],
                         gx=gyro[0], gy=gyro[1], gz=gyro[2],
                         mx=mag[0], my=mag[1], mz=mag[2])
    if not isinstance(data, dict):
        return None
    accel = _find_triplet(data, 'acc')
    gyro = _find_triplet(data, 'gyr')
    if accel is None or gyro is None:
        return None
    if any(abs(a) > ACCEL_ABS_MAX for a in accel):
        return None
    if any(abs(g) > GYRO_ABS_MAX for g in gyro):
        return None
    return ImuSample(ax=accel[0], ay=accel[1], az=accel[2],
                     gx=gyro[0], gy=gyro[1], gz=gyro[2])


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def parse_gpsd_line(line: str):
    """One gpsd JSON line -> FixSample, or None if it is not a usable fix."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get('class') != 'TPV':
        return None
    if not isinstance(data.get('mode'), int) or data['mode'] < 2:
        return None                              # no 2D/3D fix yet
    lat, lon = data.get('lat'), data.get('lon')
    if not _finite(lat) or not _finite(lon):
        return None
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    alt = data.get('altHAE', data.get('alt'))
    altitude = float(alt) if _finite(alt) else math.nan
    epx, epy, epv = data.get('epx'), data.get('epy'), data.get('epv')
    if _finite(epx) and _finite(epy):
        vert_var = float(epv) ** 2 if _finite(epv) else 10000.0
        covariance = (float(epx) ** 2, 0.0, 0.0,
                      0.0, float(epy) ** 2, 0.0,
                      0.0, 0.0, vert_var)
        cov_type = COVARIANCE_TYPE_APPROXIMATED
    else:
        covariance = (0.0,) * 9
        cov_type = COVARIANCE_TYPE_UNKNOWN
    return FixSample(latitude=float(lat), longitude=float(lon),
                     altitude=altitude, position_covariance=covariance,
                     covariance_type=cov_type)


def jump_suspicious(prev: FixSample, new: FixSample) -> bool:
    """True if new teleports relative to prev (apply only while prev is fresh)."""
    return (abs(new.latitude - prev.latitude) > MAX_FIX_JUMP_DEG
            or abs(new.longitude - prev.longitude) > MAX_FIX_JUMP_DEG)


def rate_allow(window: RateWindow, now_s: float, limit_per_s: int):
    """Fixed-window rate limiter. Returns (new_window, allowed)."""
    if now_s - window.window_start_s >= 1.0:
        return RateWindow(window_start_s=now_s, count=1), True
    if window.count >= limit_per_s:
        return window, False
    return RateWindow(window_start_s=window.window_start_s,
                      count=window.count + 1), True


def health_from_ages(fix_age_s, imu_age_s, fix_timeout_s, imu_timeout_s):
    """(overall, detail) for HealthStatus. age None = never received.

    Advisory sensor: a silent phone is DEGRADED, never FAULT — the bridge node
    itself stays alive and heartbeating (node liveness != sensor health).
    """
    stale = []
    if fix_age_s is None or fix_age_s > fix_timeout_s:
        stale.append('gps')
    if imu_age_s is None or imu_age_s > imu_timeout_s:
        stale.append('imu')
    if not stale:
        return HEALTH_OK, ''
    return HEALTH_DEGRADED, 'phone stream stale: ' + ', '.join(stale)
