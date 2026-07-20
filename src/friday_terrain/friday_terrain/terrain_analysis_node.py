"""Terrain analysis: turn the bumper-height ground-scan cloud into a
traversability grid the rover can plan on.

The mast lidar sees the top of a slope and Nav2's flat costmap can't tell
the difference between "climbable ramp" and "vertical wall" — every raised
cell is a wall. The bumper-height RGB-D sensor sees the surface directly
ahead of the wheels. This node builds a rolling 2D grid in the base_link
frame, aggregates every incoming cloud into per-cell height statistics,
computes slope from the height field, and classifies each cell:

    FLAT (< 10 deg, step < 3 cm)       -> cost   0
    GENTLE (10-20 deg)                 -> cost  40
    STEEP (20-30 deg)                  -> cost 100
    ROUGH (step > 3 cm, < wheel_r)     -> cost 150
    LETHAL_STEP (step > wheel_r)       -> cost 254
    LETHAL_SLOPE (> 30 deg)            -> cost 254
    LETHAL_CLIFF (below base - wheel_r)-> cost 254

Publishes:
    /terrain/costmap             (nav_msgs/OccupancyGrid, Nav2-compatible)
    /terrain/classified_points   (sensor_msgs/PointCloud2, XYZ + class)
    /terrain/summary             (std_msgs/String, JSON summary for tlm)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import PointCloud2, PointField
from sensor_msgs_py import point_cloud2 as pc2
from std_msgs.msg import Header, String
from tf2_ros import Buffer, TransformException, TransformListener

# ---- classifier constants --------------------------
WHEEL_RADIUS_M = 0.0668
GRID_SIZE_M = 6.0
CELL_M = 0.10
GRID_W = int(GRID_SIZE_M / CELL_M)

STEP_ROUGH_M = 0.03
STEP_LETHAL_M = WHEEL_RADIUS_M
CLIFF_M = -0.50                    # true precipice: chassis-bottom drops > 50 cm (slopes classified by SLOPE_ rules)

SLOPE_GENTLE = math.radians(10)
SLOPE_STEEP = math.radians(20)
SLOPE_LETHAL = math.radians(30)

COST_FREE = 0
COST_GENTLE = 40
COST_STEEP = 70
COST_ROUGH = 60
COST_LETHAL = 100
COST_UNKNOWN = -1

CLS_UNKNOWN = 0
CLS_FLAT = 1
CLS_GENTLE = 2
CLS_STEEP = 3
CLS_ROUGH = 4
CLS_LETHAL_STEP = 5
CLS_LETHAL_SLOPE = 6
CLS_LETHAL_CLIFF = 7


@dataclass
class TerrainGrid:
    """One frame's traversability grid centred on the rover."""
    min_z: np.ndarray
    max_z: np.ndarray
    count: np.ndarray
    classes: np.ndarray
    cost: np.ndarray

    @property
    def summary(self) -> dict:
        seen = int((self.count > 0).sum())
        total = int(self.count.size)
        by_class = {int(k): int(v) for k, v in zip(*np.unique(self.classes, return_counts=True))}
        return {
            'cells_total': total,
            'cells_seen': seen,
            'coverage_pct': round(100.0 * seen / total, 1),
            'flat': by_class.get(CLS_FLAT, 0),
            'gentle': by_class.get(CLS_GENTLE, 0),
            'steep': by_class.get(CLS_STEEP, 0),
            'rough': by_class.get(CLS_ROUGH, 0),
            'lethal_step': by_class.get(CLS_LETHAL_STEP, 0),
            'lethal_slope': by_class.get(CLS_LETHAL_SLOPE, 0),
            'lethal_cliff': by_class.get(CLS_LETHAL_CLIFF, 0),
        }


def classify_grid(min_z: np.ndarray, max_z: np.ndarray, count: np.ndarray,
                  cell_m: float = CELL_M) -> TerrainGrid:
    """Pure classifier — pass per-cell height stats, get classes + costs."""
    seen = count > 0
    mean_z = np.where(seen, (min_z + max_z) * 0.5, 0.0)
    step = np.where(seen, max_z - min_z, 0.0)

    dz_dy, dz_dx = np.gradient(mean_z, cell_m, cell_m)
    slope = np.arctan(np.hypot(dz_dx, dz_dy))
    slope = np.where(seen, slope, 0.0)

    classes = np.full(min_z.shape, CLS_UNKNOWN, dtype=np.uint8)
    cost = np.full(min_z.shape, COST_UNKNOWN, dtype=np.int16)

    lethal_step = seen & (step >= STEP_LETHAL_M)
    lethal_slope = seen & (slope >= SLOPE_LETHAL)
    lethal_cliff = seen & (min_z <= CLIFF_M)
    lethal = lethal_step | lethal_slope | lethal_cliff
    classes[lethal_step] = CLS_LETHAL_STEP
    classes[lethal_slope & ~lethal_step] = CLS_LETHAL_SLOPE
    classes[lethal_cliff & ~(lethal_step | lethal_slope)] = CLS_LETHAL_CLIFF
    cost[lethal] = COST_LETHAL

    non_lethal = seen & ~lethal
    steep = non_lethal & (slope >= SLOPE_STEEP)
    gentle = non_lethal & (slope >= SLOPE_GENTLE) & ~steep
    rough = non_lethal & (step >= STEP_ROUGH_M) & ~steep & ~gentle
    flat = non_lethal & ~steep & ~gentle & ~rough

    classes[steep] = CLS_STEEP
    classes[gentle] = CLS_GENTLE
    classes[rough] = CLS_ROUGH
    classes[flat] = CLS_FLAT
    cost[steep] = COST_STEEP
    cost[gentle] = COST_GENTLE
    cost[rough] = COST_ROUGH
    cost[flat] = COST_FREE

    return TerrainGrid(min_z=min_z, max_z=max_z, count=count,
                       classes=classes, cost=cost.astype(np.int8))


class TerrainAnalysisNode(Node):
    def __init__(self) -> None:
        super().__init__('terrain_analysis')

        self.declare_parameter('grid_size_m', GRID_SIZE_M)
        self.declare_parameter('cell_m', CELL_M)
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('cloud_topic', '/ground_scan/points')
        self.declare_parameter('publish_classified_cloud', True)

        self._grid_m = float(self.get_parameter('grid_size_m').value)
        self._cell_m = float(self.get_parameter('cell_m').value)
        self._grid_w = int(self._grid_m / self._cell_m)
        self._base = str(self.get_parameter('base_frame').value)
        self._pub_cloud = bool(self.get_parameter('publish_classified_cloud').value)

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        cost_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
        )
        self._cost_pub = self.create_publisher(OccupancyGrid, '/terrain/costmap', cost_qos)
        self._cloud_pub = self.create_publisher(PointCloud2, '/terrain/classified_points', 1)
        self._summary_pub = self.create_publisher(String, '/terrain/summary', 1)

        self._sub = self.create_subscription(
            PointCloud2, str(self.get_parameter('cloud_topic').value),
            self._on_cloud, 5)

        self.get_logger().info(
            f'terrain_analysis up: {self._grid_w}x{self._grid_w} @ '
            f'{self._cell_m*100:.0f} cm in {self._base}')

    def _lookup_transform(self, src_frame: str, stamp):
        try:
            return self._tf_buffer.lookup_transform(
                self._base, src_frame, stamp, rclpy.duration.Duration(seconds=0.05))
        except TransformException:
            try:
                return self._tf_buffer.lookup_transform(
                    self._base, src_frame, rclpy.time.Time())
            except TransformException as exc:
                self.get_logger().warn(
                    f'no tf {src_frame} -> {self._base}: {exc}',
                    throttle_duration_sec=5.0)
                return None

    def _on_cloud(self, msg: PointCloud2) -> None:
        tf = self._lookup_transform(msg.header.frame_id, msg.header.stamp)
        if tf is None:
            return

        pts = pc2.read_points_numpy(msg, field_names=('x', 'y', 'z'), skip_nans=True)
        if pts.shape[0] == 0:
            return

        t = tf.transform.translation
        q = tf.transform.rotation
        x, y, z, w = q.x, q.y, q.z, q.w
        R = np.array([
            [1 - 2*(y*y+z*z), 2*(x*y-z*w),     2*(x*z+y*w)],
            [2*(x*y+z*w),     1 - 2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w),     2*(y*z+x*w),     1 - 2*(x*x+y*y)],
        ])
        pts_base = pts @ R.T + np.array([t.x, t.y, t.z])

        half = self._grid_m * 0.5
        xs = pts_base[:, 0]
        ys = pts_base[:, 1]
        zs = pts_base[:, 2]
        in_box = (np.abs(xs) < half) & (np.abs(ys) < half)
        if not in_box.any():
            return
        xs, ys, zs = xs[in_box], ys[in_box], zs[in_box]

        ix = ((xs + half) / self._cell_m).astype(np.int32)
        iy = ((ys + half) / self._cell_m).astype(np.int32)
        ix = np.clip(ix, 0, self._grid_w - 1)
        iy = np.clip(iy, 0, self._grid_w - 1)

        min_z = np.full((self._grid_w, self._grid_w), np.inf, dtype=np.float32)
        max_z = np.full((self._grid_w, self._grid_w), -np.inf, dtype=np.float32)
        count = np.zeros((self._grid_w, self._grid_w), dtype=np.int32)
        np.minimum.at(min_z, (iy, ix), zs)
        np.maximum.at(max_z, (iy, ix), zs)
        np.add.at(count, (iy, ix), 1)
        min_z[count == 0] = 0.0
        max_z[count == 0] = 0.0

        grid = classify_grid(min_z, max_z, count, self._cell_m)

        og = OccupancyGrid()
        og.header = Header()
        og.header.stamp = msg.header.stamp
        og.header.frame_id = self._base
        og.info.resolution = self._cell_m
        og.info.width = self._grid_w
        og.info.height = self._grid_w
        og.info.origin.position.x = -half
        og.info.origin.position.y = -half
        og.info.origin.orientation.w = 1.0
        og.data = grid.cost.flatten().tolist()
        self._cost_pub.publish(og)

        summary = grid.summary
        summary['stamp'] = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self._summary_pub.publish(String(data=json.dumps(summary)))

        if self._pub_cloud:
            self._publish_classified_cloud(msg.header.stamp, grid)

    def _publish_classified_cloud(self, stamp, grid: TerrainGrid) -> None:
        seen_iy, seen_ix = np.where(grid.count > 0)
        if seen_iy.size == 0:
            return
        half = self._grid_m * 0.5
        xs = -half + (seen_ix + 0.5) * self._cell_m
        ys = -half + (seen_iy + 0.5) * self._cell_m
        zs = (grid.min_z[seen_iy, seen_ix] + grid.max_z[seen_iy, seen_ix]) * 0.5
        classes = grid.classes[seen_iy, seen_ix].astype(np.float32)

        buf = np.zeros((xs.size,),
                       dtype=[('x', np.float32), ('y', np.float32),
                              ('z', np.float32), ('intensity', np.float32)])
        buf['x'] = xs; buf['y'] = ys; buf['z'] = zs; buf['intensity'] = classes

        fields = [
            PointField(name='x',         offset=0,  datatype=PointField.FLOAT32, count=1),
            PointField(name='y',         offset=4,  datatype=PointField.FLOAT32, count=1),
            PointField(name='z',         offset=8,  datatype=PointField.FLOAT32, count=1),
            PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1),
        ]
        header = Header()
        header.stamp = stamp
        header.frame_id = self._base
        cloud = PointCloud2()
        cloud.header = header
        cloud.height = 1
        cloud.width = xs.size
        cloud.fields = fields
        cloud.is_bigendian = False
        cloud.point_step = 16
        cloud.row_step = 16 * xs.size
        cloud.is_dense = True
        cloud.data = buf.tobytes()
        self._cloud_pub.publish(cloud)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TerrainAnalysisNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
