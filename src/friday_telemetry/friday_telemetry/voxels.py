"""Pure voxel-grid fusion for 3D environment reconstruction (no ROS).

Both 3D sensors dump points; this reduces the flood into a bounded set of
occupied VOXELS in the map frame, each carrying a colour, and packs the set
for the radio. A voxel is 'the world has coloured structure in this ~10 cm
cube' — the unit the Command Center rebuilds the 3D surroundings from.

Colour is RGB332 (1 byte). The 3D lidar has no colour -> its voxels carry
sentinel 0 ('unknown', the deck height-tints them); the RGB-D camera paints
real colour where it looks, and a real colour never gets overwritten by a
later colourless lidar hit.

Kept ROS-free so packing/eviction/colour-merge is unit-testable without a sim.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib

VOXEL_SIZE = 0.10
MAX_VOXELS = 60_000
MAX_COMPRESSED = 256_000


def rgb332(r: int, g: int, b: int) -> int:
    """8-bit r,g,b -> 1-byte RGB332. 0 is reserved for 'no colour', so a pure
    black sample is bumped to 1."""
    c = ((r & 0xE0)) | ((g & 0xE0) >> 3) | ((b & 0xC0) >> 6)
    return c or 1


def add_points(occupied: dict, points, voxel_size: float, frame_idx: int,
               colors=None, z_min: float = -0.1, z_max: float = 1.5) -> int:
    """Fold Nx3 map-frame points into `occupied` {(i,j,k): (frame, colour)}.

    colors: optional per-point RGB332 (0 = none). A real colour is sticky —
    a colourless hit refreshes recency but keeps the colour. Returns NEW count.
    """
    before = len(occupied)
    inv = 1.0 / voxel_size
    for idx, (x, y, z) in enumerate(points):
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        if z < z_min or z > z_max:
            continue
        key = (int(x * inv) if x >= 0 else int(x * inv) - 1,
               int(y * inv) if y >= 0 else int(y * inv) - 1,
               int(z * inv) if z >= 0 else int(z * inv) - 1)
        c = colors[idx] if colors is not None else 0
        prev = occupied.get(key)
        if prev is not None and c == 0:
            occupied[key] = (frame_idx, prev[1])      # keep known colour
        else:
            occupied[key] = (frame_idx, c)
    return len(occupied) - before


def evict_to_cap(occupied: dict, cap: int = MAX_VOXELS) -> None:
    """If over cap, drop the least-recently-seen voxels (oldest frame)."""
    if len(occupied) <= cap:
        return
    ordered = sorted(occupied.items(), key=lambda kv: kv[1][0])
    for key, _ in ordered[:len(occupied) - cap]:
        del occupied[key]


def build_voxel_payload(occupied: dict, voxel_size: float, stamp_s: float) -> dict | None:
    """Occupied set -> tlm/voxel payload (coords int16*3 ++ colours uint8),
    or None when empty/oversize. Re-based to the min corner so coords stay small."""
    if not occupied:
        return None
    keys = list(occupied.keys())
    imin = min(k[0] for k in keys); jmin = min(k[1] for k in keys)
    kmin = min(k[2] for k in keys)
    coords = bytearray()
    cols = bytearray()
    for key in keys:
        di, dj, dk = key[0] - imin, key[1] - jmin, key[2] - kmin
        if not (0 <= di < 32768 and 0 <= dj < 32768 and 0 <= dk < 32768):
            continue
        coords += struct.pack('<hhh', di, dj, dk)
        cols.append(occupied[key][1] & 0xFF)
    payload_raw = bytes(coords) + bytes(cols)     # deck splits at n*6
    compressed = zlib.compress(payload_raw, 6)
    if len(compressed) > MAX_COMPRESSED:
        return None
    return {'class': 'voxel', 'vs': voxel_size,
            'ox': imin * voxel_size, 'oy': jmin * voxel_size, 'oz': kmin * voxel_size,
            'n': len(cols), 'enc': 'i16rgb332-zlib-b64', 'color': True,
            'data': base64.b64encode(compressed).decode('ascii'),
            'stamp': stamp_s}
