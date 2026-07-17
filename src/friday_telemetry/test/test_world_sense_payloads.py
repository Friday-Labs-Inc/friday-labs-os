"""Pure payload builders for the world-sense egress (tlm/env + tlm/gps)."""
from types import SimpleNamespace

from friday_telemetry.telemetry_agent_node import build_env_payload, build_gps_payload

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
