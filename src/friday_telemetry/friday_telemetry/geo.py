"""WGS84 lat/lon <-> ENU (East-North-Up) map-frame conversion.

Flat-earth approximation: accurate to within ~1 m over 10 km at mid-latitudes.
The datum (origin of the ENU frame) corresponds to the map frame origin — in the
Baylands sim this is the SDF world's spherical_coordinates origin (spawn point).

Usage::
    east, north = latlon_to_enu(lat, lon, datum_lat, datum_lon)
    lat2, lon2  = enu_to_latlon(east, north, datum_lat, datum_lon)
"""

from __future__ import annotations

import math

_DEG_TO_M = 111_139.0  # metres per degree of latitude (WGS84 mean)

# Baylands SDF world origin — used as the default datum when the caller
# does not supply one (matches spherical_coordinates in baylands.sdf).
BAYLANDS_LAT = 37.412173
BAYLANDS_LON = -121.998878


def latlon_to_enu(lat: float, lon: float,
                  datum_lat: float, datum_lon: float) -> tuple[float, float]:
    """WGS84 (lat, lon) -> ENU (east_m, north_m) relative to datum."""
    north = (lat - datum_lat) * _DEG_TO_M
    east = (lon - datum_lon) * _DEG_TO_M * math.cos(math.radians(datum_lat))
    return east, north


def enu_to_latlon(east_m: float, north_m: float,
                  datum_lat: float, datum_lon: float) -> tuple[float, float]:
    """ENU (east_m, north_m) relative to datum -> WGS84 (lat, lon)."""
    dlat = north_m / _DEG_TO_M
    dlon = east_m / (_DEG_TO_M * math.cos(math.radians(datum_lat)))
    return datum_lat + dlat, datum_lon + dlon


def zone_gps_to_map(zone_gps: list[float],
                    datum_lat: float = BAYLANDS_LAT,
                    datum_lon: float = BAYLANDS_LON) -> list[float]:
    """[lat0, lon0, lat1, lon1] GPS zone -> [x0, y0, x1, y1] map-frame metres.

    The ENU east axis maps to +X (forward/right) and north maps to +Y (left)
    in the ROS ENU convention used by navsat_transform and the sim world.
    """
    lat0, lon0, lat1, lon1 = zone_gps
    x0, y0 = latlon_to_enu(lat0, lon0, datum_lat, datum_lon)
    x1, y1 = latlon_to_enu(lat1, lon1, datum_lat, datum_lon)
    return [x0, y0, x1, y1]
