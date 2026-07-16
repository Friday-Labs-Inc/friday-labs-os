"""Pure ingest logic for the environmental sensor pod -- no ROS dependencies.

Parses and validates the JSON datagram the Zero W SensorHub streamer sends over
UDP (one per ~second):

    {"temp_c": 37.0, "rh_pct": 55.0, "press_pa": 100116, "lux": 36, "human": 0}

The pod is an untrusted advisory sensor, so this rejects rather than repairs:
malformed JSON, missing fields, non-finite values, and out-of-range readings
are all dropped. A silent pod is DEGRADED, never FAULT (it is outside the
safety path; the bridge node keeps heartbeating regardless).
"""

import json
import math
from dataclasses import dataclass

# Plausible physical ranges -- readings outside these are glitches or spoofed.
TEMP_MIN_C, TEMP_MAX_C = -40.0, 85.0        # SensorHub onboard sensor range
RH_MIN_PCT, RH_MAX_PCT = 0.0, 100.0
PRESS_MIN_PA, PRESS_MAX_PA = 30000.0, 120000.0   # ~9 km altitude .. dense sea level
LUX_MIN, LUX_MAX = 0.0, 200000.0            # dark .. direct sunlight

# Health "overall" codes (mirror friday_module_agent.protocol / HealthStatus).
HEALTH_OK = 0
HEALTH_DEGRADED = 1


@dataclass(frozen=True)
class EnvSample:
    """One validated environmental reading. All fields finite and in range."""

    temp_c: float       # onboard temperature, Celsius
    rh_pct: float       # onboard relative humidity, percent (0..100)
    press_pa: float     # barometric pressure, Pascals
    lux: float          # ambient light, lux
    human: bool         # motion detected in the pod's recent window


@dataclass(frozen=True)
class RateWindow:
    """State of a fixed one-second rate-limit window."""

    window_start_s: float
    count: int


def _num(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def parse_datagram(raw: bytes):
    """bytes -> EnvSample, or None if the datagram fails any check."""
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    temp, rh = data.get('temp_c'), data.get('rh_pct')
    press, lux = data.get('press_pa'), data.get('lux')
    if not (_num(temp) and _num(rh) and _num(press) and _num(lux)):
        return None
    temp, rh, press, lux = float(temp), float(rh), float(press), float(lux)
    if not TEMP_MIN_C <= temp <= TEMP_MAX_C:
        return None
    if not RH_MIN_PCT <= rh <= RH_MAX_PCT:
        return None
    if not PRESS_MIN_PA <= press <= PRESS_MAX_PA:
        return None
    if not LUX_MIN <= lux <= LUX_MAX:
        return None
    return EnvSample(temp_c=temp, rh_pct=rh, press_pa=press, lux=lux,
                     human=bool(data.get('human')))


def rate_allow(window: RateWindow, now_s: float, limit_per_s: int):
    """Fixed-window rate limiter. Returns (new_window, allowed)."""
    if now_s - window.window_start_s >= 1.0:
        return RateWindow(window_start_s=now_s, count=1), True
    if window.count >= limit_per_s:
        return window, False
    return RateWindow(window_start_s=window.window_start_s,
                      count=window.count + 1), True


def health_from_age(age_s, timeout_s):
    """(overall, detail) for HealthStatus. age None = never received.

    Advisory sensor: a silent pod is DEGRADED, never FAULT -- the bridge node
    itself stays alive and heartbeating (node liveness != sensor health).
    """
    if age_s is None or age_s > timeout_s:
        return HEALTH_DEGRADED, 'envpod stream stale'
    return HEALTH_OK, ''
