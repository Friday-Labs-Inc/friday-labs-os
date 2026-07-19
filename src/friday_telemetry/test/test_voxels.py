"""Pure voxel fusion: packing, floor-clip, eviction, round-trip."""
import base64
import struct
import zlib

from friday_telemetry import voxels


def test_add_points_clips_floor_and_ceiling():
    occ = {}
    pts = [(1.0, 0.0, 0.5),       # kept
           (1.0, 0.0, -0.5),      # below z_min -> dropped
           (1.0, 0.0, 3.0)]       # above z_max -> dropped
    added = voxels.add_points(occ, pts, 0.10, frame_idx=1)
    assert added == 1 and len(occ) == 1


def test_add_points_dedups_and_negatives_floor_correctly():
    occ = {}
    voxels.add_points(occ, [(-0.05, -0.05, 0.05), (-0.02, -0.02, 0.02)], 0.10, 1)
    assert list(occ.keys()) == [(-1, -1, 0)]        # both in the same negative voxel


def test_eviction_drops_oldest():
    occ = {}
    for f in range(5):
        voxels.add_points(occ, [(f * 1.0, 0.0, 0.5)], 0.10, frame_idx=f)
    voxels.evict_to_cap(occ, cap=3)
    assert len(occ) == 3
    # the three most-recently-seen frames survive
    assert min(occ.values()) == 2


def test_payload_round_trips_int16_triplets():
    occ = {}
    voxels.add_points(occ, [(1.0, 2.0, 0.5), (1.1, 2.0, 0.5), (1.0, 2.1, 0.6)], 0.10, 1)
    p = voxels.build_voxel_payload(occ, 0.10, 99.0)
    assert p['class'] == 'voxel' and p['enc'] == 'i16-zlib-b64'
    raw = zlib.decompress(base64.b64decode(p['data']))
    trip = [struct.unpack('<hhh', raw[i:i+6]) for i in range(0, len(raw), 6)]
    assert len(trip) == p['n'] == len(occ)
    assert all(v >= 0 for t in trip for v in t)     # re-based to min corner


def test_non_finite_points_are_skipped_not_crash():
    occ = {}
    inf = float('inf'); nan = float('nan')
    pts = [(1.0, 1.0, 0.5), (inf, 0.0, 0.5), (0.0, nan, 0.5), (0.0, 0.0, inf)]
    added = voxels.add_points(occ, pts, 0.10, frame_idx=1)   # must not raise
    assert added == 1 and len(occ) == 1


def test_payload_none_when_empty():
    assert voxels.build_voxel_payload({}, 0.10, 1.0) is None
