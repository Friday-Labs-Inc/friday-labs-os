import numpy as np, rclpy
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import TransformStamped
from friday_terrain.terrain_map_node import TerrainMap, COST_UNKNOWN, COST_LETHAL

rclpy.init()
n = TerrainMap()

# fake TF: base_link is at map (5, 3), no rotation
tf = TransformStamped()
tf.transform.translation.x = 5.0; tf.transform.translation.y = 3.0; tf.transform.translation.z = 0.0
tf.transform.rotation.w = 1.0
n._resolve_frame = lambda *a, **k: (setattr(n, "_active_frame", "map") or tf)

# synthetic instantaneous costmap: 60x60 @ 0.1, centred on base_link (origin -3,-3)
w = 60; grid = np.full((w, w), COST_UNKNOWN, dtype=np.int16)
grid[20:40, 20:40] = 0          # a 2m x 2m FREE patch around the rover
grid[45:50, 45:50] = COST_LETHAL  # a lethal patch off to +x/+y
msg = OccupancyGrid()
msg.header.frame_id = "base_link"
msg.info.width = w; msg.info.height = w; msg.info.resolution = 0.1
msg.info.origin.position.x = -3.0; msg.info.origin.position.y = -3.0
msg.data = grid.flatten().astype(np.int8).tolist()

n._on_costmap(msg)

# --- assertions ---
sensed = (n._world != COST_UNKNOWN)
n_free = int((n._world == 0).sum()); n_lethal = int((n._world == COST_LETHAL).sum())
print(f"origin anchored at map ({n._ox:.1f}, {n._oy:.1f})  [expect (5-24, 3-24)=(-19,-19)]")
print(f"sensed cells: {int(sensed.sum())}  free: {n_free}  lethal: {n_lethal}")
# FREE patch is 20 src cells wide @0.1 = 2m -> at 0.2 world res = ~10x10=100 cells; lethal 5@0.1=0.5m -> ~2-3^2
assert n._ox == 5.0 - 24.0 and n._oy == 3.0 - 24.0, "origin not anchored on rover"
assert n_free > 50, f"free patch too small: {n_free}"
assert n_lethal >= 1, f"lethal not captured: {n_lethal}"

# world location of the FREE patch centre should sit at map ~ (5,3) -> world cell ((5-ox)/.2,(3-oy)/.2)=(120,120)
wy, wx = np.nonzero(n._world == 0)
cx, cy = wx.mean(), wy.mean()
print(f"free-patch centre world cell (~120,120 expected): ({cx:.0f},{cy:.0f})")
assert 110 < cx < 130 and 110 < cy < 130, "free patch not at rover position"

# publish + verify emitted grid
captured = {}
n._pub.publish = lambda og: captured.update(dict(frame=og.header.frame_id, ox=og.info.origin.position.x,
                                                 res=og.info.resolution, w=og.info.width,
                                                 nonunknown=int((np.asarray(og.data)!=-1).sum())))
n._publish()
print(f"published: frame={captured['frame']} origin_x={captured['ox']:.1f} res={captured['res']} "
      f"w={captured['w']} sensed={captured['nonunknown']}")
assert captured['frame'] == 'map' and captured['ox'] == -19.0 and captured['nonunknown'] == int(sensed.sum())
print("\nALL ASSERTIONS PASSED ✅")
rclpy.shutdown()
