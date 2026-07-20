"""Unit tests for friday_telemetry.geo — lat/lon <-> ENU round-trip."""

import math

from friday_telemetry.geo import (
    BAYLANDS_LAT,
    BAYLANDS_LON,
    enu_to_latlon,
    latlon_to_enu,
    zone_gps_to_map,
)

_DATUM = (BAYLANDS_LAT, BAYLANDS_LON)


def test_origin_round_trip():
    """Datum point itself maps to (0, 0) and back."""
    e, n = latlon_to_enu(BAYLANDS_LAT, BAYLANDS_LON, *_DATUM)
    assert abs(e) < 1e-6
    assert abs(n) < 1e-6
    lat2, lon2 = enu_to_latlon(e, n, *_DATUM)
    assert abs(lat2 - BAYLANDS_LAT) < 1e-9
    assert abs(lon2 - BAYLANDS_LON) < 1e-9


def test_east_100m_round_trip():
    """100 m east, 0 m north -> lat/lon -> back within 1 cm."""
    e0, n0 = 100.0, 0.0
    lat, lon = enu_to_latlon(e0, n0, *_DATUM)
    e1, n1 = latlon_to_enu(lat, lon, *_DATUM)
    assert abs(e1 - e0) < 0.01, f"east error {abs(e1 - e0):.4f} m"
    assert abs(n1 - n0) < 0.01, f"north error {abs(n1 - n0):.4f} m"


def test_northeast_round_trip():
    """50 m east, 80 m north -> round-trip within 1 cm."""
    e0, n0 = 50.0, 80.0
    lat, lon = enu_to_latlon(e0, n0, *_DATUM)
    e1, n1 = latlon_to_enu(lat, lon, *_DATUM)
    assert abs(e1 - e0) < 0.01
    assert abs(n1 - n0) < 0.01


def test_direction_signs():
    """East (+x) increases longitude; North (+y) increases latitude."""
    e_pos, _ = latlon_to_enu(BAYLANDS_LAT, BAYLANDS_LON + 0.001, *_DATUM)
    assert e_pos > 0, "east should be positive for larger longitude"
    _, n_pos = latlon_to_enu(BAYLANDS_LAT + 0.001, BAYLANDS_LON, *_DATUM)
    assert n_pos > 0, "north should be positive for larger latitude"


def test_scale_at_baylands_lat():
    """1 degree at Baylands lat: longitude scale < latitude scale (cos effect)."""
    e_1deg, _ = latlon_to_enu(BAYLANDS_LAT, BAYLANDS_LON + 1.0, *_DATUM)
    _, n_1deg = latlon_to_enu(BAYLANDS_LAT + 1.0, BAYLANDS_LON, *_DATUM)
    # At ~37° lat, cos(37°) ≈ 0.8; east scale ≈ 88.7 km/deg
    assert e_1deg < n_1deg, "longitude degree shorter than latitude degree at 37° N"
    cos_expected = math.cos(math.radians(BAYLANDS_LAT))
    assert abs(e_1deg / n_1deg - cos_expected) < 0.001


def test_zone_gps_to_map_shape():
    """zone_gps_to_map returns a 4-element list of floats."""
    zone = zone_gps_to_map([BAYLANDS_LAT - 0.0001, BAYLANDS_LON - 0.0001,
                             BAYLANDS_LAT + 0.0001, BAYLANDS_LON + 0.0001])
    assert len(zone) == 4
    # Both corners near origin (within ~25 m)
    for v in zone:
        assert abs(v) < 50.0, f"unexpected large value {v}"


def test_zone_gps_to_map_round_trip():
    """A GPS zone converted to map then back gives the original corners."""
    lat0, lon0 = BAYLANDS_LAT - 0.0002, BAYLANDS_LON - 0.0002
    lat1, lon1 = BAYLANDS_LAT + 0.0002, BAYLANDS_LON + 0.0002
    x0, y0, x1, y1 = zone_gps_to_map([lat0, lon0, lat1, lon1])
    lat0r, lon0r = enu_to_latlon(x0, y0, *_DATUM)
    lat1r, lon1r = enu_to_latlon(x1, y1, *_DATUM)
    assert abs(lat0r - lat0) < 1e-7
    assert abs(lon0r - lon0) < 1e-7
    assert abs(lat1r - lat1) < 1e-7
    assert abs(lon1r - lon1) < 1e-7
