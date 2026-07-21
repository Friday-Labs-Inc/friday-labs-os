"""Terrain map accumulator — the operator's "sense of mission terrain".

The terrain classifier (/terrain/costmap) is robot-CENTERED and instantaneous: it
shows the ground right around the rover, and moves with it. That's right for Nav2's
local costmap, but an operator wants the OPPOSITE — a persistent, map-frame ribbon of
"what terrain has been sensed, and where, along the mission path so far".

This node stamps each instantaneous terrain reading into a persistent world grid
(map frame), keeping the worst-case class per cell (a cliff seen once stays a cliff).
It republishes the accumulated ribbon as /terrain/map_grid (OccupancyGrid, map frame)
for RViz + for the telemetry agent to forward to the Command Center.

    subscribes  /terrain/costmap   (nav_msgs/OccupancyGrid, base_link, instantaneous)
    publishes   /terrain/map_grid  (nav_msgs/OccupancyGrid, map frame, persistent)
"""
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy,
                       QoSHistoryPolicy)
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import Header
from tf2_ros import Buffer, TransformListener, TransformException

# cost sentinels mirror friday_terrain.terrain_analysis_node
COST_UNKNOWN = -1
COST_LETHAL = 100

WORLD_SIZE_M = 48.0     # covers a patrol area; fixed origin at world centre
CELL_M = 0.20           # coarser than the 10 cm local grid — an operator overview
PUBLISH_HZ = 2.0


class TerrainMap(Node):
    def __init__(self) -> None:
        super().__init__('terrain_map')
        self.declare_parameter('world_size_m', WORLD_SIZE_M)
        self.declare_parameter('cell_m', CELL_M)
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('fallback_frame', 'odom')
        self.declare_parameter('publish_hz', PUBLISH_HZ)

        self._world_m = float(self.get_parameter('world_size_m').value)
        self._cell_m = float(self.get_parameter('cell_m').value)
        self._w = int(self._world_m / self._cell_m)
        self._map_frame = str(self.get_parameter('map_frame').value)
        self._fallback = str(self.get_parameter('fallback_frame').value)
        self._half = self._world_m * 0.5
        self._ox = None  # world grid origin (map frame), anchored on first fix
        self._oy = None

        # persistent world grid, worst-case cost per cell (-1 = never sensed)
        self._world = np.full((self._w, self._w), COST_UNKNOWN, dtype=np.int16)
        self._dirty = False
        self._active_frame = None  # resolved once TF is available

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        latched = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                             durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                             history=QoSHistoryPolicy.KEEP_LAST)
        self._pub = self.create_publisher(OccupancyGrid, '/terrain/map_grid', latched)
        self._sub = self.create_subscription(OccupancyGrid, '/terrain/costmap',
                                              self._on_costmap, 5)
        hz = float(self.get_parameter('publish_hz').value)
        self._timer = self.create_timer(1.0 / hz, self._publish)
        self.get_logger().info(
            f'terrain_map up: {self._w}x{self._w} @ {self._cell_m*100:.0f} cm, '
            f'frame {self._map_frame} (fallback {self._fallback})')

    def _resolve_frame(self, src_frame, stamp):
        """Pick map frame if TF exists, else fall back to odom, else None."""
        for frame in (self._map_frame, self._fallback):
            try:
                tf = self._tf_buffer.lookup_transform(
                    frame, src_frame, stamp, rclpy.duration.Duration(seconds=0.05))
                self._active_frame = frame
                return tf
            except TransformException:
                try:
                    tf = self._tf_buffer.lookup_transform(frame, src_frame, rclpy.time.Time())
                    self._active_frame = frame
                    return tf
                except TransformException:
                    continue
        self.get_logger().warn(f'no tf {src_frame} -> {self._map_frame}/{self._fallback}',
                               throttle_duration_sec=5.0)
        return None

    def _on_costmap(self, msg: OccupancyGrid) -> None:
        tf = self._resolve_frame(msg.header.frame_id, msg.header.stamp)
        if tf is None:
            return
        w, h, res = msg.info.width, msg.info.height, msg.info.resolution
        ox, oy = msg.info.origin.position.x, msg.info.origin.position.y
        cost = np.asarray(msg.data, dtype=np.int16).reshape(h, w)
        sensed = cost != COST_UNKNOWN
        if not sensed.any():
            return
        iy, ix = np.nonzero(sensed)
        # source-frame cell centres
        sx = ox + (ix + 0.5) * res
        sy = oy + (iy + 0.5) * res
        sz = np.zeros_like(sx)
        pts = np.stack([sx, sy, sz], axis=1)
        # rotate+translate into the resolved world frame
        t = tf.transform.translation
        q = tf.transform.rotation
        x, y, z, wq = q.x, q.y, q.z, q.w
        R = np.array([
            [1 - 2*(y*y+z*z), 2*(x*y-z*wq),   2*(x*z+y*wq)],
            [2*(x*y+z*wq),    1 - 2*(x*x+z*z), 2*(y*z-x*wq)],
            [2*(x*z-y*wq),    2*(y*z+x*wq),   1 - 2*(x*x+y*y)],
        ])
        wpts = pts @ R.T + np.array([t.x, t.y, t.z])
        if self._ox is None:
            # centre the world grid on the rover's first sensed position
            self._ox = float(t.x) - self._half
            self._oy = float(t.y) - self._half
        wx = ((wpts[:, 0] - self._ox) / self._cell_m).astype(np.int32)
        wy = ((wpts[:, 1] - self._oy) / self._cell_m).astype(np.int32)
        keep = (wx >= 0) & (wx < self._w) & (wy >= 0) & (wy < self._w)
        if not keep.any():
            return
        wx, wy, c = wx[keep], wy[keep], cost[iy, ix][keep]
        # worst-case sticky: keep the max cost ever seen at each world cell
        np.maximum.at(self._world, (wy, wx), c)
        self._dirty = True

    def _publish(self) -> None:
        if not self._dirty or self._active_frame is None:
            return
        og = OccupancyGrid()
        og.header = Header()
        og.header.stamp = self.get_clock().now().to_msg()
        og.header.frame_id = self._active_frame
        og.info.resolution = self._cell_m
        og.info.width = self._w
        og.info.height = self._w
        og.info.origin.position.x = self._ox
        og.info.origin.position.y = self._oy
        og.info.origin.orientation.w = 1.0
        og.data = self._world.flatten().astype(np.int8).tolist()
        self._pub.publish(og)
        self._dirty = False


def main() -> None:
    rclpy.init()
    node = TerrainMap()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
