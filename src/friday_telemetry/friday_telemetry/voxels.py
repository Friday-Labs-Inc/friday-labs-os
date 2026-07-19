"""Pure voxel-grid fusion for 3D environment reconstruction (no ROS).

Both 3D sensors (lidar + depth camera) dump points; this reduces the flood
into a bounded set of occupied VOXELS in the map frame, and packs the set for
the radio. A voxel is 'the world has structure in this ~10 cm cube' — the unit
the Command Center rebuilds the 3D surroundings from.

Kept ROS-free so the packing/eviction is unit-testable without a sim.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib

VOXEL_SIZE = 0.10          # metres per cube
MAX_VOXELS = 24_000        # hard cap so an unbounded world can't flood the radio
MAX_COMPRESSED = 256_000


def add_points(occupied: dict, points, voxel_size: float, frame_idx: int,
               z_min: float = -0.1, z_max: float = 1.5) -> int:
    """Fold Nx3 map-frame points into `occupied` {(i,j,k): last_frame}.

    Floor/ceiling clip (z_min..z_max) drops the ground plane and anything above
    the rover's world of interest. Returns how many NEW voxels were added.
    """
    before = len(occupied)
    inv = 1.0 / voxel_size
    for x, y, z in points:
        # depth sensors emit NaN/inf for invalid returns; int(NaN) crashes
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        if z < z_min or z > z_max:
            continue
        key = (int(x * inv) if x >= 0 else int(x * inv) - 1,
               int(y * inv) if y >= 0 else int(y * inv) - 1,
               int(z * inv) if z >= 0 else int(z * inv) - 1)
        occupied[key] = frame_idx
    return len(occupied) - before


def evict_to_cap(occupied: dict, cap: int = MAX_VOXELS) -> None:
    """If over cap, drop the least-recently-seen voxels (oldest frame_idx)."""
    if len(occupied) <= cap:
        return
    ordered = sorted(occupied.items(), key=lambda kv: kv[1])
    for key, _ in ordered[:len(occupied) - cap]:
        del occupied[key]


def build_voxel_payload(occupied: dict, voxel_size: float, stamp_s: float) -> dict | None:
    """Occupied-voxel set -> tlm/voxel payload, or None when empty/oversize.

    Coords are re-based to the set's min corner and packed as int16 triplets so
    the whole 3D world is a few KB. base64 keeps every hop JSON-clean.
    """
    if not occupied:
        return None
    keys = list(occupied.keys())
    imin = min(k[0] for k in keys); jmin = min(k[1] for k in keys)
    kmin = min(k[2] for k in keys)
    buf = bytearray()
    for i, j, k in keys:
        di, dj, dk = i - imin, j - jmin, k - kmin
        if not (0 <= di < 32768 and 0 <= dj < 32768 and 0 <= dk < 32768):
            continue                    # a stray outlier past int16: skip, don't crash
        buf += struct.pack('<hhh', di, dj, dk)
    compressed = zlib.compress(bytes(buf), 6)
    if len(compressed) > MAX_COMPRESSED:
        return None
    return {'class': 'voxel', 'vs': voxel_size,
            'ox': imin * voxel_size, 'oy': jmin * voxel_size, 'oz': kmin * voxel_size,
            'n': len(buf) // 6, 'enc': 'i16-zlib-b64',
            'data': base64.b64encode(compressed).decode('ascii'),
            'stamp': stamp_s}
