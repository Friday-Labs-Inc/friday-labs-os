"""Unit tests for the envpod pure-ingest logic (no ROS)."""

import json

from friday_envpod_bridge import ingest


def _dg(**kw):
    base = {'temp_c': 22.5, 'rh_pct': 48.0, 'press_pa': 101325, 'lux': 300,
            'human': 0}
    base.update(kw)
    return json.dumps(base).encode('utf-8')


def test_valid_sample_parses():
    s = ingest.parse_datagram(_dg())
    assert s is not None
    assert s.temp_c == 22.5 and s.rh_pct == 48.0
    assert s.press_pa == 101325 and s.lux == 300
    assert s.human is False


def test_human_flag_truthy():
    assert ingest.parse_datagram(_dg(human=1)).human is True


def test_rejects_bad_json():
    assert ingest.parse_datagram(b'not json') is None
    assert ingest.parse_datagram(b'[1,2,3]') is None


def test_rejects_missing_field():
    d = json.dumps({'temp_c': 22.0, 'rh_pct': 40.0, 'lux': 10}).encode()
    assert ingest.parse_datagram(d) is None


def test_rejects_out_of_range():
    assert ingest.parse_datagram(_dg(temp_c=999)) is None     # temp too high
    assert ingest.parse_datagram(_dg(rh_pct=150)) is None      # humidity > 100
    assert ingest.parse_datagram(_dg(press_pa=5)) is None       # pressure too low
    assert ingest.parse_datagram(_dg(lux=-3)) is None           # negative light


def test_rejects_non_finite():
    assert ingest.parse_datagram(b'{"temp_c": NaN, "rh_pct": 40, '
                                 b'"press_pa": 101325, "lux": 10}') is None


def test_health_ok_when_fresh():
    assert ingest.health_from_age(1.0, 5.0)[0] == ingest.HEALTH_OK


def test_health_degraded_when_stale_or_never():
    assert ingest.health_from_age(9.0, 5.0)[0] == ingest.HEALTH_DEGRADED
    assert ingest.health_from_age(None, 5.0)[0] == ingest.HEALTH_DEGRADED


def test_rate_limiter_caps_per_second():
    w = ingest.RateWindow(window_start_s=0.0, count=0)
    allowed = 0
    for _ in range(10):
        w, ok = ingest.rate_allow(w, 0.5, 3)
        allowed += ok
    assert allowed == 3            # only 3 in the same 1 s window
    w, ok = ingest.rate_allow(w, 1.6, 3)
    assert ok is True              # new window reopens
