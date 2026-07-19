"""Pure voxel fusion: colour merge, clip, eviction, round-trip."""
import base64
import struct
import zlib

from friday_telemetry import voxels


def test_rgb332_reserves_zero_for_unknown():
    assert voxels.rgb332(0, 0, 0) == 1            # black bumped off the sentinel
    assert voxels.rgb332(255, 0, 0) == 0xE0
    assert voxels.rgb332(0, 255, 0) == 0x1C
    assert voxels.rgb332(0, 0, 255) == 0x03


def test_add_points_clips_and_carries_colour():
    occ = {}
    added = voxels.add_points(occ, [(1.0, 0.0, 0.5), (1.0, 0.0, -0.5)],
                              0.10, frame_idx=1, colors=[0xE0, 0x1C])
    assert added == 1                              # floor point clipped
    assert next(iter(occ.values()))[1] == 0xE0     # red kept


def test_real_colour_is_sticky_over_colourless_lidar():
    occ = {}
    voxels.add_points(occ, [(1.0, 1.0, 0.5)], 0.10, 1, colors=[0xE0])   # camera: red
    voxels.add_points(occ, [(1.0, 1.0, 0.5)], 0.10, 2, colors=None)     # lidar: none
    (frame, colour), = occ.values()
    assert colour == 0xE0 and frame == 2           # colour kept, recency refreshed


def test_colourless_then_camera_paints():
    occ = {}
    voxels.add_points(occ, [(1.0, 1.0, 0.5)], 0.10, 1, colors=None)     # lidar first
    assert next(iter(occ.values()))[1] == 0
    voxels.add_points(occ, [(1.0, 1.0, 0.5)], 0.10, 2, colors=[0x1C])   # camera paints
    assert next(iter(occ.values()))[1] == 0x1C


def test_eviction_drops_oldest():
    occ = {}
    for fr in range(5):
        voxels.add_points(occ, [(fr * 1.0, 0.0, 0.5)], 0.10, frame_idx=fr, colors=None)
    voxels.evict_to_cap(occ, cap=3)
    assert len(occ) == 3 and min(f for f, _ in occ.values()) == 2


def test_non_finite_points_skipped():
    occ = {}
    inf, nan = float('inf'), float('nan')
    added = voxels.add_points(occ, [(1.0, 1.0, 0.5), (inf, 0.0, 0.5), (0.0, nan, 0.5)],
                              0.10, 1, colors=[0xE0, 0xE0, 0xE0])
    assert added == 1


def test_payload_round_trips_coords_and_colours():
    occ = {}
    voxels.add_points(occ, [(1.0, 2.0, 0.5), (1.1, 2.0, 0.6)], 0.10, 1, colors=[0xE0, 0x03])
    p = voxels.build_voxel_payload(occ, 0.10, 9.0)
    assert p['color'] is True and p['enc'] == 'i16rgb332-zlib-b64'
    raw = zlib.decompress(base64.b64decode(p['data']))
    n = p['n']
    coords = [struct.unpack('<hhh', raw[i:i+6]) for i in range(0, n*6, 6)]
    cols = list(raw[n*6:n*6+n])
    assert len(coords) == n == 2
    assert set(cols) == {0xE0, 0x03}
    assert all(v >= 0 for t in coords for v in t)


def test_payload_none_when_empty():
    assert voxels.build_voxel_payload({}, 0.10, 1.0) is None
