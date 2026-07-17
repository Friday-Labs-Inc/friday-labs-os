"""Pure payload builders for the world-sense egress (tlm/env + tlm/gps)."""
from types import SimpleNamespace

from friday_telemetry.telemetry_agent_node import (build_attitude_payload,
                                                   build_env_payload,
                                                   build_gps_payload)

S = 1_000_000_000  # ns per second


def test_env_payload_includes_only_fresh_fields():
    entries = {
        'temperature_c': (28.4, 100 * S),
        'humidity_pct': (71.0, 100 * S),
        'presence': (False, 50 * S),        # stale (55 s old)
    }
    p = build_env_payload(entries, now_ns=105 * S, fresh_ns=30 * S)
    assert p == {'class': 'env', 'temperature_c': 28.4, 'humidity_pct': 71.0,
                 'stamp': 100.0}


def test_env_payload_none_when_pod_silent():
    assert build_env_payload({}, now_ns=10 * S, fresh_ns=30 * S) is None
    stale = {'temperature_c': (28.4, 0)}
    assert build_env_payload(stale, now_ns=100 * S, fresh_ns=30 * S) is None


def _fix(status, lat=11.98901, lon=79.83312, alt=14.0):
    return SimpleNamespace(
        status=SimpleNamespace(status=status),
        latitude=lat, longitude=lon, altitude=alt,
        header=SimpleNamespace(stamp=SimpleNamespace(sec=1000, nanosec=500000000)))


def test_gps_payload_maps_navsatfix():
    p = build_gps_payload(_fix(status=0))
    assert p['class'] == 'gps' and p['fix'] == 'FIX'
    assert p['lat'] == 11.98901 and p['lon'] == 79.83312 and p['alt_m'] == 14.0
    assert p['stamp'] == 1000.5


def test_gps_payload_none_without_fix():
    assert build_gps_payload(_fix(status=-1)) is None


def test_attitude_payload_maps_all_three():
    p = build_attitude_payload([9.76, 131.0, 0.03], stamp_s=1000.0)
    assert p == {'class': 'imu', 'tilt_deg': 9.76, 'heading_deg': 131.0,
                 'vibration_rms': 0.03, 'stamp': 1000.0}


def test_attitude_payload_omits_unknown_fields_never_fakes_them():
    nan = float('nan')
    p = build_attitude_payload([9.76, nan, 0.03], stamp_s=1.0)   # no magnetometer
    assert 'heading_deg' not in p          # omitted, NOT sent as 0 or NaN
    assert p['tilt_deg'] == 9.76 and p['vibration_rms'] == 0.03


def test_attitude_payload_none_when_nothing_known():
    nan = float('nan')
    assert build_attitude_payload([nan, nan, nan], stamp_s=1.0) is None
    assert build_attitude_payload([1.0], stamp_s=1.0) is None
