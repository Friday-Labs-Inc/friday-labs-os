"""Telemetry Node Agent — the Command Center boundary (Phase 3).

The single translator between the rover's internal ROS 2 world (friday_msgs over
DDS, LAN-only) and the external Command Center (signed CBOR envelopes over an
MQTT-class link). It is a normal module agent (registers, heartbeats via the
ModuleAgent base) that additionally:

  * subscribes the external command topic mark1/<rover>/cmd/<class>,
  * VALIDATES every envelope (Ed25519 signature, allowlist, nonce, expiry,
    rover_id, protocol major) — see protocol.py,
  * on accept: maps the payload to the internal friday_msgs and republishes it on
    DDS (carrying the authority provenance), and ACKs,
  * on reject: publishes a friday_msgs/FaultReport and ACKs the rejection.
    Rejected commands are never executed, never queued (per the security spec).

Inbound MQTT callbacks run on the paho network thread; they only validate and
enqueue. A ROS timer drains the queue and does all ROS publishing, so DDS is only
ever touched from the executor thread.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import queue
import time
import zlib

import cbor2
import numpy as np
import rclpy
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from lifecycle_msgs.msg import State as LCState
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import Image, PointCloud2
from sensor_msgs.msg import FluidPressure, Illuminance, NavSatFix, RelativeHumidity, Temperature
from std_msgs.msg import Bool, Float32MultiArray, Int8, String
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
import rclpy.time
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node as _RclNode
from rclpy.parameter import Parameter as _Param
# Heavy deps import at PROCESS start on purpose: importing them inside
# configure/callbacks once cost minutes under the bring-up I/O storm,
# starving the heartbeat and faking a CORE LOST (2026-07-19 incident).
try:
    from tf2_ros import Buffer, TransformListener
except ImportError:                     # bench without tf2: dead-reckoned odom
    Buffer = TransformListener = None
try:
    from sensor_msgs_py import point_cloud2
except ImportError:                     # clouds skipped when helper is absent
    point_cloud2 = None

from friday_msgs.msg import (
    AuthorityLease,
    FaultReport,
    Heartbeat,
    MotionCommand,
    ReleaseAuthority,
)
from friday_msgs.srv import RequestAuthority
from friday_module_agent import authority, qos
from friday_module_agent.module_agent import ModuleAgent
from friday_module_agent.nonce_store import NonceStore

from friday_telemetry import protocol, voxels
from friday_telemetry.geo import zone_gps_to_map
from friday_telemetry.mission_planner import plan_survey
from friday_telemetry.transport import MqttTransport

# Nav2 action imports (optional — rover can run without nav2_msgs installed)
try:
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose
    from geometry_msgs.msg import PoseStamped
    from action_msgs.msg import GoalStatus as _GoalStatus
    _NAV2_AVAILABLE = True
except ImportError:
    _NAV2_AVAILABLE = False

AUTHORITY_TOPIC = '/mark1/system/authority'
SAFETY_PULSE_TOPIC = '/mark1/system/safety_pulse'
AUTHORITY_RELEASE_TOPIC = '/mark1/system/authority_release'
REQUEST_AUTHORITY_SERVICE = '/mark1/system/request_authority'

LOCOMOTION_CMD_TOPIC = '/mark1/locomotion/cmd_motion'
FAULT_TOPIC = '/mark1/telemetry/fault'
LOCO_ODOM_TOPIC = '/mark1/locomotion/odometry'
ENVPOD_NS = '/mark1/envpod'          # world-sense pod (SensorHub on the Zero W)
PHONE_FIX_TOPIC = '/mark1/phone/fix'
PHONE_ATTITUDE_TOPIC = '/mark1/phone/attitude'   # [tilt_deg, heading_deg, vib_rms]
ATT_TLM_PERIOD_S = 5.0               # operator cadence; the bus stays 10 Hz
MAP_TOPIC = '/map'                   # slam_toolbox occupancy grid (sim today)
MAP_TLM_PERIOD_S = 10.0              # full snapshot, only when the map changed
MAP_MAX_COMPRESSED = 256_000         # refuse to radio a monster (broker limit safety)
TERRAIN_GRID_TOPIC = '/terrain/map_grid'   # persistent map-frame terrain ribbon
TERRAIN_GRID_TLM_PERIOD_S = 2.0            # operator overview; 0.5 Hz, digest-gated
KEYFRAME_TOPIC = '/ground_scan/image'      # bumper cam — the ground the wheels cross
KEYFRAME_TLM_PERIOD_S = 8.0                # a visual postcard every 8 s
KEYFRAME_MAX_PX = 160                      # thumbnail; a few KB on the 4G link
CLOUD_TOPICS = ('/lidar3d/points', '/depthcam/points')   # the two 3D sensors
CLOUD_MIN_PERIOD_S = 0.5             # process each sensor at most 2 Hz (CPU guard)
CLOUD_SUBSAMPLE = 3                  # keep 1 in N points before transform (CPU guard)
VOXEL_TLM_PERIOD_S = 5.0             # stream the fused world every 5 s (on change)
ENV_TLM_PERIOD_S = 5.0               # env snapshot cadence to the broker
TERRAIN_TLM_PERIOD_S = 1.0           # terrain classifier summary cadence (1 Hz)
ENV_FRESH_S = 30.0                   # cached value older than this is left out
GPS_TLM_MIN_PERIOD_S = 5.0           # gpsd is 1 Hz; the operator needs far less
LOCO_FAULT_TOPIC = '/mark1/locomotion/fault'

# Authority state (Authority Lease Protocol — "Failover" / "Authority Return").
TLM_MONITORING = 'MONITORING'   # default: Core holds; Telemetry only watches it
TLM_HOLDING = 'HOLDING'         # Telemetry self-promoted and now holds the lease

FAILOVER_CHECK_S = 0.1          # 10 Hz check of Core's two liveness signals
LEASE_RENEW_S = 0.5            # 2 s lease, renewed every 500 ms while holding
PULSE_PERIOD_S = 0.05         # 20 Hz safety pulse while holding
PULSE_LOST_S = 1.5           # Core's safety pulse missing >= 1.5 s = pulse_lost
STABLE_QUIET_S = 1.0         # "no motion" = no nonzero command issued for >= 1 s


def build_env_payload(entries: dict, now_ns: int, fresh_ns: int) -> dict | None:
    """entries: field -> (value, stamp_ns). Returns the tlm/env payload with only
    the fields fresher than fresh_ns, or None when nothing fresh (pod silent —
    publishing nothing keeps the operator view honestly stale)."""
    payload = {}
    newest_ns = 0
    for field, (value, stamp_ns) in entries.items():
        if now_ns - stamp_ns <= fresh_ns:
            payload[field] = value
            newest_ns = max(newest_ns, stamp_ns)
    if not payload:
        return None
    return {'class': 'env', **payload, 'stamp': newest_ns / 1e9}


def build_map_payload(grid: 'OccupancyGrid', prev_digest: str, cls: str = 'map') -> tuple:
    """OccupancyGrid -> (tlm/map payload, digest), or (None, prev_digest).

    The whole known world in one envelope: zlib over the raw occupancy cells
    (int8: -1 unknown / 0 free / 100 wall), base64 so every hop stays
    JSON-clean. Publishes ONLY when the map actually changed (digest gate) —
    a parked rover radios nothing. Oversized maps are refused, not truncated.
    """
    raw = bytes(b & 0xFF for b in grid.data)
    digest = hashlib.sha256(raw).hexdigest()
    if digest == prev_digest:
        return None, prev_digest
    compressed = zlib.compress(raw, 6)
    if len(compressed) > MAP_MAX_COMPRESSED:
        return None, prev_digest
    q = grid.info.origin.orientation
    return ({'class': cls,
             'w': int(grid.info.width), 'h': int(grid.info.height),
             'res': float(grid.info.resolution),
             'ox': float(grid.info.origin.position.x),
             'oy': float(grid.info.origin.position.y),
             'oyaw': 2.0 * math.atan2(q.z, q.w),
             'enc': 'zlib-b64',
             'data': base64.b64encode(compressed).decode('ascii'),
             'stamp': _t2s(grid.header.stamp)}, digest)


def build_keyframe_payload(msg: 'Image', prev_digest: str, max_px: int = KEYFRAME_MAX_PX) -> tuple:
    """sensor_msgs/Image -> (tlm/terrain_keyframe payload, digest), or (None, prev_digest).

    A downsized JPEG postcard of the ground the rover is on — visual grounding for the
    terrain ribbon. The field rover has no on-board semantic seg yet, so this is the raw
    camera view; the drive/caution/block overlay grafts on when perception hardware lands.
    Digest-gated on the raw bytes so a parked rover does not re-radio the same frame.
    """
    if msg.encoding not in ('rgb8', 'bgr8'):
        return None, prev_digest
    raw = bytes(msg.data)
    digest = hashlib.sha256(raw).hexdigest()
    if digest == prev_digest:
        return None, prev_digest
    try:
        from PIL import Image as PImage
    except ImportError:
        return None, prev_digest
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(msg.height, msg.width, 3)
    if msg.encoding == 'bgr8':
        arr = arr[:, :, ::-1]
    im = PImage.fromarray(arr)
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=70)
    return ({'class': 'keyframe', 'w': im.width, 'h': im.height,
             'enc': 'jpeg-b64', 'data': base64.b64encode(buf.getvalue()).decode('ascii'),
             'stamp': _t2s(msg.header.stamp)}, digest)


def build_attitude_payload(values, stamp_s: float) -> dict | None:
    """[tilt_deg, heading_deg, vib_rms] -> tlm/imu payload.

    NaN means the rover-side math said "unknown" (no magnetometer, gravity
    unusable) — those fields are OMITTED rather than sent as NaN, so the
    operator view shows a blank, not a fake zero. All None -> no message.
    """
    if len(values) < 3:
        return None
    names = ('tilt_deg', 'heading_deg', 'vibration_rms')
    payload = {n: float(v) for n, v in zip(names, values[:3])
               if v is not None and math.isfinite(v)}
    if not payload:
        return None
    return {'class': 'imu', **payload, 'stamp': stamp_s}


def build_gps_payload(msg: 'NavSatFix') -> dict | None:
    """NavSatFix -> tlm/gps payload; None when there is no fix (no fabricated
    zero-island coordinates on the operator map)."""
    if msg.status.status < 0:            # NavSatStatus.STATUS_NO_FIX
        return None
    return {'class': 'gps', 'lat': msg.latitude, 'lon': msg.longitude,
            'alt_m': msg.altitude, 'fix': 'FIX', 'stamp': _t2s(msg.header.stamp)}


def _tf_matrix(tf):
    """TransformStamped -> 4x4 homogeneous transform (numpy)."""
    t = tf.transform.translation
    q = tf.transform.rotation
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2*(y*y+z*z), 2*(x*y-z*w),     2*(x*z+y*w),     t.x],
        [2*(x*y+z*w),     1 - 2*(x*x+z*z), 2*(y*z-x*w),     t.y],
        [2*(x*z-y*w),     2*(y*z+x*w),     1 - 2*(x*x+y*y), t.z],
        [0, 0, 0, 1]])


def _t2s(t) -> float:
    """builtin_interfaces/Time -> unix seconds (0 if unset)."""
    return t.sec + t.nanosec * 1e-9


class TelemetryAgent(ModuleAgent):
    """Command Center boundary as a lifecycle module agent."""

    def __init__(self):
        super().__init__(
            node_name='telemetry',
            module_id='MARK1-TLM-001',
            module_ns='telemetry',
            hardware_type='telemetry',
            capabilities=['command_bridge', 'recovery', 'gateway'],
            sw_version='0.3.0',
        )
        self.declare_parameter('rover_id', 'MARK1-001')
        self.declare_parameter('mqtt_host', '127.0.0.1')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('operators_file', '')
        self.declare_parameter('nonce_store', '')
        # Production link is MQTT 5 over mutual-TLS (EMQX). Off by default so the
        # node-sim + unit tests use a plain local broker; the live broker sets these.
        self.declare_parameter('mqtt_tls', False)
        self.declare_parameter('mqtt_ca', '')
        self.declare_parameter('mqtt_cert', '')
        self.declare_parameter('mqtt_key', '')
        self.declare_parameter('mqtt_client_id', '')   # '' -> '<module_id>-bridge'
        # Rover telemetry signing: sign odom/fault/ack out to the broker so the
        # operator can trust they came from THIS rover. No key -> no egress (the
        # node-sim + unit tests stay unchanged).
        self.declare_parameter('rover_key_file', '')
        self.declare_parameter('telemetry_rate_hz', 2.0)   # odom downsample to the broker

        self._rover_id = self.get_parameter('rover_id').value
        self._inbound = queue.Queue()
        self._transport = None
        self._validator = None
        self._nonce_store = None
        self._authority_holder = ''       # tracked from /mark1/system/authority
        self._motion_pub = None
        self._fault_pub = None
        self._drain_timer = None
        # --- outbound telemetry signing ---
        self._rover_priv = None            # rover signing key (None = egress off)
        self._odom_sub = None
        self._loco_fault_sub = None
        self._tlm_fault_sub = None
        self._last_odom_pub_ns = 0
        self._odom_min_period_ns = 0
        # world senses: cached latest env-pod values + phone GPS egress state
        self._env_entries = {}             # field -> (value, stamp_ns)
        self._env_subs = []
        self._env_timer = None
        # Terrain intelligence relay: /terrain/summary -> tlm/terrain (1 Hz)
        self._terrain_timer = None
        self._terrain_latest_json = None
        self.create_subscription(String, '/terrain/summary',
                                 self._on_terrain_summary, 1)
        self._fix_sub = None
        self._last_gps_pub_ns = 0
        self._attitude_sub = None
        self._last_att_pub_ns = 0
        self._map_sub = None
        self._map_msg = None
        self._map_digest = ''
        self._map_timer = None
        self._terrain_grid_sub = None
        self._terrain_grid_msg = None
        self._terrain_grid_digest = ''
        self._terrain_grid_timer = None
        self._keyframe_sub = None
        self._keyframe_msg = None
        self._keyframe_digest = ''
        self._keyframe_timer = None
        # TF runs on its OWN node/clock: in sim the transforms are stamped in
        # sim time, but this agent keeps WALL clock (envelope expiry). A
        # wall-clock buffer evicts sim-time TF as ancient -> map frame vanishes.
        # tf_use_sim_time:=true (sim launch) aligns the TF node with the sim.
        self.declare_parameter('tf_use_sim_time', False)
        self._tf_node = _RclNode(
            'telemetry_tf',
            parameter_overrides=[_Param('use_sim_time', _Param.Type.BOOL,
                                        bool(self.get_parameter('tf_use_sim_time').value))])
        self._tf_buffer = None
        self._tf_listener = None
        self._cloud_cbg = MutuallyExclusiveCallbackGroup()  # clouds serialize on ONE thread, never saturate the pool nor block the heartbeat/lifecycle
        self._cloud_subs = []
        self._voxels = {}               # {(i,j,k): last_frame_idx} in map frame
        self._voxel_frame = 0
        self._voxel_timer = None
        self._voxel_digest = 0
        self._last_cloud_ns = {}
        # --- split-brain failover state (Authority Lease Protocol) ---
        # Authority evidence must never share a callback group with app work:
        # a stalled configure once starved the pulse sub long enough to fake
        # a CORE LOST and self-promote against a healthy Core (2026-07-19).
        self._auth_cbg = MutuallyExclusiveCallbackGroup()
        self._last_failover_check_ns = 0
        self._auth_state = TLM_MONITORING
        self._epoch = 0                   # highest epoch seen / held
        self._safety_seq = 0
        self._core_seen = False           # don't fail over until Core was present
        self._core_lease_expiry_s = 0.0   # Core's last lease's own 2 s expiry
        self._last_pulse_ns = 0           # last safety pulse from Core
        self._last_motion_ns = 0          # last nonzero motion command issued (stability)
        self._authority_sub = None
        self._pulse_sub = None
        self._authority_pub = None
        self._safety_pulse_pub = None
        self._release_pub = None
        self._request_srv = None
        self._failover_timer = None
        self._lease_timer = None
        self._pulse_timer = None
        # --- autonomy mode state (enforced via /mark1/system/autonomy_mode) ---
        self._autonomy_level = 0           # default: L0 Manual (safest / most restrictive)
        self._mission_profile = 'Bench'
        self._brain = 'Rules'
        self._autonomy_mode_pub = None
        self._autonomy_timer = None
        # --- mission executor (dedicated callback group — never shares vitals) ---
        # Respects the same isolation rules as the authority groups (2308629):
        # mission work in its own MECE group so it cannot starve the heartbeat.
        self._mission_cbg = MutuallyExclusiveCallbackGroup()
        self._mission_inbound: queue.Queue = queue.Queue()
        self._mission_state: dict | None = None   # None = IDLE
        self._mission_goal_sent = False
        self._mission_current_goal_handle = None
        self._mission_nav_client = None
        self._mission_timer = None
        self._mission_retry_count = 0          # retries on current waypoint
        self._mission_next_retry_ns = 0        # wall-ns: earliest time to retry

    # ---- ModuleAgent hooks -------------------------------------------------
    def configure_hardware(self) -> None:
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        self._motion_pub = self.create_lifecycle_publisher(
            MotionCommand, LOCOMOTION_CMD_TOPIC, qos.critical_reliable())
        self._fault_pub = self.create_lifecycle_publisher(
            FaultReport, FAULT_TOPIC, qos.state_default())
        # Latched autonomy-level topic: reliable + transient_local + keep_last 1.
        # Any node that joins late (e.g. nav_motion_adapter restart) still gets
        # the current level immediately — safe default 0 is published on activate.
        _autonomy_qos = QoSProfile(depth=1,
                                   reliability=ReliabilityPolicy.RELIABLE,
                                   durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self._autonomy_mode_pub = self.create_lifecycle_publisher(
            Int8, '/mark1/system/autonomy_mode', _autonomy_qos)
        self._nonce_store = NonceStore(self.get_parameter('nonce_store').value or None)
        self._validator = protocol.CommandValidator(
            rover_id=self._rover_id,
            operator_keys=self._load_operator_allowlist(),
            now=time.time, nonce_store=self._nonce_store)
        self._authority_sub = self.create_subscription(
            AuthorityLease, AUTHORITY_TOPIC, self._on_authority, qos.critical_reliable(),
            callback_group=self._auth_cbg)
        # failover: watch Core's safety pulse; on promotion, publish lease + pulse
        # as the holder and announce a clean hand-back via ReleaseAuthority.
        self._pulse_sub = self.create_subscription(
            Heartbeat, SAFETY_PULSE_TOPIC, self._on_safety_pulse, qos.sensor_stream(),
            callback_group=self._auth_cbg)
        self._authority_pub = self.create_lifecycle_publisher(
            AuthorityLease, AUTHORITY_TOPIC, qos.critical_reliable())
        self._safety_pulse_pub = self.create_lifecycle_publisher(
            Heartbeat, SAFETY_PULSE_TOPIC, qos.sensor_stream())
        self._release_pub = self.create_lifecycle_publisher(
            ReleaseAuthority, AUTHORITY_RELEASE_TOPIC, qos.critical_reliable())
        self._request_srv = self.create_service(
            RequestAuthority, REQUEST_AUTHORITY_SERVICE, self._on_request_authority)
        tls = None
        if bool(self.get_parameter('mqtt_tls').value):
            tls = {'ca_certs': self.get_parameter('mqtt_ca').value or None,
                   'certfile': self.get_parameter('mqtt_cert').value or None,
                   'keyfile': self.get_parameter('mqtt_key').value or None}
        # mTLS ties authorization to the cert CN, so the client id must be the
        # rover_id the broker ACL expects (not the internal module id).
        client_id = self.get_parameter('mqtt_client_id').value or f'{self._module_id}-bridge'
        self._transport = MqttTransport(
            host=self.get_parameter('mqtt_host').value,
            port=int(self.get_parameter('mqtt_port').value),
            client_id=client_id, tls=tls)
        # outbound telemetry: sign odom (downsampled) + fault out to the operator
        self._rover_priv = self._load_rover_key()
        rate = float(self.get_parameter('telemetry_rate_hz').value)
        self._odom_min_period_ns = int(1e9 / rate) if rate > 0 else 0
        if self._rover_priv is not None:
            self._odom_sub = self.create_subscription(
                Odometry, LOCO_ODOM_TOPIC, self._on_odom, qos.state_default())
            self._loco_fault_sub = self.create_subscription(
                FaultReport, LOCO_FAULT_TOPIC, self._on_fault, qos.state_default())
            self._tlm_fault_sub = self.create_subscription(
                FaultReport, FAULT_TOPIC, self._on_fault, qos.state_default())
            # world senses (advisory pods): cache latest, snapshot on a timer
            def _cache(field, extract):
                def cb(msg):
                    self._env_entries[field] = (
                        extract(msg), self.get_clock().now().nanoseconds)
                return cb
            self._env_subs = [
                self.create_subscription(
                    Temperature, f'{ENVPOD_NS}/temperature',
                    _cache('temperature_c', lambda m: m.temperature), qos.sensor_stream()),
                self.create_subscription(
                    RelativeHumidity, f'{ENVPOD_NS}/humidity',
                    _cache('humidity_pct', lambda m: m.relative_humidity * 100.0),
                    qos.sensor_stream()),
                self.create_subscription(
                    FluidPressure, f'{ENVPOD_NS}/pressure',
                    _cache('pressure_hpa', lambda m: m.fluid_pressure / 100.0),
                    qos.sensor_stream()),
                self.create_subscription(
                    Illuminance, f'{ENVPOD_NS}/illuminance',
                    _cache('light_lux', lambda m: m.illuminance), qos.sensor_stream()),
                self.create_subscription(
                    Bool, f'{ENVPOD_NS}/presence',
                    _cache('presence', lambda m: bool(m.data)), qos.sensor_stream()),
            ]
            self._fix_sub = self.create_subscription(
                NavSatFix, PHONE_FIX_TOPIC, self._on_fix, qos.sensor_stream())
            self._attitude_sub = self.create_subscription(
                Float32MultiArray, PHONE_ATTITUDE_TOPIC, self._on_attitude,
                qos.sensor_stream())
            # slam publishes the grid latched (transient_local) at low rate
            from rclpy.qos import (DurabilityPolicy, QoSProfile,
                                   ReliabilityPolicy)
            map_qos = QoSProfile(depth=1,
                                 reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self._map_sub = self.create_subscription(
                OccupancyGrid, MAP_TOPIC, self._on_map, map_qos)
            self._terrain_grid_sub = self.create_subscription(
                OccupancyGrid, TERRAIN_GRID_TOPIC, self._on_terrain_grid, map_qos)
            self._keyframe_sub = self.create_subscription(
                Image, KEYFRAME_TOPIC, self._on_keyframe, qos.sensor_stream())
            # 3D perception: both point clouds -> fused map-frame voxel world
            for topic in CLOUD_TOPICS:
                self._cloud_subs.append(self.create_subscription(
                    PointCloud2, topic,
                    lambda msg, t=topic: self._on_cloud(msg, t), qos.sensor_stream(),
                    callback_group=self._cloud_cbg))
            # map-frame pose: the locomotion odom is DEAD-RECKONED (integrated
            # commanded velocities, no feedback) and drifts unboundedly — fine
            # as a heartbeat of motion, wrong as a position on the SLAM map.
            # When TF carries map->base_link (SLAM running), radio THAT pose.
            if Buffer is None:
                self.get_logger().warning('tf2_ros unavailable — odom egress stays dead-reckoned')
            else:
                self._tf_buffer = Buffer()
                self._tf_listener = TransformListener(self._tf_buffer, self._tf_node)
        # Mission executor: Nav2 action client in dedicated callback group so
        # goal-response callbacks never run on the vitals or auth threads.
        if _NAV2_AVAILABLE:
            self._mission_nav_client = ActionClient(
                self, NavigateToPose, '/navigate_to_pose',
                callback_group=self._mission_cbg)
        else:
            self.get_logger().warning(
                'nav2_msgs not available — mission executor disabled')

    def activate_hardware(self) -> None:
        try:
            self._transport.connect()
            self._transport.subscribe(f'mark1/{self._rover_id}/cmd/+', self._on_cc_message)
        except Exception as exc:  # noqa: BLE001 - link down must not crash the node
            self.get_logger().error(f'Command Center link failed: {exc}')
        self._drain_timer = self.create_timer(0.02, self._drain_inbound)
        now_ns = self.get_clock().now().nanoseconds
        self._last_pulse_ns = now_ns
        self._core_lease_expiry_s = 0.0
        self._core_seen = False
        self._last_failover_check_ns = 0
        self._failover_timer = self.create_timer(
            FAILOVER_CHECK_S, self._check_failover, callback_group=self._auth_cbg)
        # Publish default L0 so the gate has a value before any cmd/mode arrives.
        _init_mode = Int8()
        _init_mode.data = 0
        self._autonomy_mode_pub.publish(_init_mode)
        if self._rover_priv is not None:
            self._env_timer = self.create_timer(ENV_TLM_PERIOD_S, self._publish_env)
            self._terrain_timer = self.create_timer(TERRAIN_TLM_PERIOD_S, self._publish_terrain)
            self._autonomy_timer = self.create_timer(1.0, self._publish_autonomy)
            self._map_timer = self.create_timer(MAP_TLM_PERIOD_S, self._publish_map)
            self._terrain_grid_timer = self.create_timer(
                TERRAIN_GRID_TLM_PERIOD_S, self._publish_terrain_grid)
            self._keyframe_timer = self.create_timer(
                KEYFRAME_TLM_PERIOD_S, self._publish_keyframe)
            self._voxel_timer = self.create_timer(
                VOXEL_TLM_PERIOD_S, self._publish_voxels, callback_group=self._cloud_cbg)
        # Mission executor timer — always active (missions arrive whether or not
        # signing is configured, though progress telemetry needs _rover_priv).
        self._mission_timer = self.create_timer(
            0.5, self._mission_advance, callback_group=self._mission_cbg)
        self.get_logger().info(
            f'Command Center boundary up for rover {self._rover_id} '
            f'(operators allowlisted: {len(self._validator._keys)}) — monitoring Core authority')

    def enter_safe_state(self) -> None:
        if self._drain_timer is not None:
            self.destroy_timer(self._drain_timer)
            self._drain_timer = None
        if self._failover_timer is not None:
            self.destroy_timer(self._failover_timer)
            self._failover_timer = None
        if self._env_timer is not None:
            self.destroy_timer(self._env_timer)
            self._env_timer = None
        if self._terrain_timer is not None:
            self.destroy_timer(self._terrain_timer)
            self._terrain_timer = None
        if self._autonomy_timer is not None:
            self.destroy_timer(self._autonomy_timer)
            self._autonomy_timer = None
        if self._map_timer is not None:
            self.destroy_timer(self._map_timer)
            self._map_timer = None
        if self._terrain_grid_timer is not None:
            self.destroy_timer(self._terrain_grid_timer)
            self._terrain_grid_timer = None
        if self._keyframe_timer is not None:
            self.destroy_timer(self._keyframe_timer)
            self._keyframe_timer = None
        self._keyframe_sub = None
        self._keyframe_msg = None
        self._keyframe_digest = ''
        self._keyframe_timer = None
        if self._voxel_timer is not None:
            self.destroy_timer(self._voxel_timer)
            self._voxel_timer = None
        if self._mission_timer is not None:
            self.destroy_timer(self._mission_timer)
            self._mission_timer = None
        if self._mission_state is not None:
            self._mission_state['state'] = 'aborted'
            self._publish_mission_progress()
            self._mission_cancel_nav_goal()
            self._mission_state = None
        if self._auth_state == TLM_HOLDING:
            self._announce_release('telemetry deactivated while holding')
            self._stand_down()
        if self._transport is not None:
            self._transport.disconnect()
        self.get_logger().info('telemetry safe-state: external link closed')

    # ---- allowlist ---------------------------------------------------------
    def _load_operator_allowlist(self) -> dict:
        path = self.get_parameter('operators_file').value
        if not path:
            self.get_logger().warning('no operators_file set; allowlist empty (all commands rejected)')
            return {}
        try:
            data = json.loads(open(path).read())
        except OSError as exc:
            self.get_logger().error(f'cannot read operators_file {path}: {exc}')
            return {}
        keys = {}
        for sender_id, hex_pub in data.items():
            keys[sender_id] = Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_pub))
        return keys

    def _load_rover_key(self):
        """Load the rover's Ed25519 private key for signing outbound telemetry."""
        path = self.get_parameter('rover_key_file').value
        if not path:
            self.get_logger().info(
                'no rover_key_file; outbound telemetry will not be signed or bridged')
            return None
        try:
            return Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(open(path).read().strip()))
        except (OSError, ValueError) as exc:
            # Log the error TYPE only — the message can echo key-material fragments.
            self.get_logger().error(
                f'cannot load rover_key_file {path}: {type(exc).__name__}')
            return None

    # ---- autonomy mode enforcement ----------------------------------------
    def _apply_mode(self, envelope: dict) -> None:
        """Apply a validated cmd/mode envelope: update state, publish Int8, emit tlm."""
        p = envelope['payload']
        level = p.get('autonomy_level', 0)
        try:
            level = int(level)
        except (TypeError, ValueError):
            self.get_logger().warning(f'cmd/mode: autonomy_level not an int ({level!r}); dropping')
            return
        if level not in (0, 1, 2, 3):
            self.get_logger().warning(f'cmd/mode: autonomy_level {level} not in 0..3; dropping')
            return
        self._autonomy_level = level
        self._mission_profile = str(p.get('mission_profile', self._mission_profile))
        self._brain = str(p.get('brain', self._brain))
        msg = Int8()
        msg.data = level
        self._autonomy_mode_pub.publish(msg)
        self.get_logger().info(
            f'autonomy mode SET: level={level} profile={self._mission_profile} '
            f'brain={self._brain}')
        self._publish_signed_telemetry('tlm/autonomy', self._autonomy_payload())

    def _publish_autonomy(self) -> None:
        """1 Hz timer: sign and emit the enforced autonomy state to the FCC."""
        self._publish_signed_telemetry('tlm/autonomy', self._autonomy_payload())

    def _autonomy_payload(self) -> dict:
        return {
            'class': 'autonomy',
            'autonomy_level': self._autonomy_level,
            'mission_profile': self._mission_profile,
            'brain': self._brain,
            'enforced': True,
            'stamp': time.time(),
        }

    # ---- terrain intelligence relay ---------------------------------------
    def _on_terrain_summary(self, msg) -> None:
        self._terrain_latest_json = msg.data

    def _publish_terrain(self) -> None:
        """Sign + emit tlm/terrain with the latest terrain classifier summary.

        The classifier already produces a compact JSON on /terrain/summary
        (~200 bytes: class histogram + coverage). We just forward it through
        the signed envelope so the FCC can trust and record it.
        """
        raw = self._terrain_latest_json
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        payload['class'] = 'terrain'
        self._publish_signed_telemetry('tlm/terrain', payload)

    def _publish_env(self) -> None:
        payload = build_env_payload(
            self._env_entries, self.get_clock().now().nanoseconds,
            int(ENV_FRESH_S * 1e9))
        if payload is not None:
            self._publish_signed_telemetry('tlm/env', payload)

    def _on_map(self, msg: 'OccupancyGrid') -> None:
        self._map_msg = msg                 # keep latest; the timer does the work

    def _on_terrain_grid(self, msg: 'OccupancyGrid') -> None:
        self._terrain_grid_msg = msg        # keep latest; the timer does the work

    def _on_cloud(self, msg: 'PointCloud2', topic: str) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self._last_cloud_ns.get(topic, 0) < int(CLOUD_MIN_PERIOD_S * 1e9):
            return                          # rate-limit per sensor (CPU guard)
        self._last_cloud_ns[topic] = now_ns
        if self._tf_buffer is None:
            return
        try:
            tf = self._tf_buffer.lookup_transform(
                'map', msg.header.frame_id, rclpy.time.Time())
        except Exception:  # noqa: BLE001 - no TF yet / deps: skip this cloud
            return
        has_rgb = any(fld.name == 'rgb' for fld in msg.fields)
        fields = ('x', 'y', 'z', 'rgb') if has_rgb else ('x', 'y', 'z')
        try:
            data = point_cloud2.read_points(
                msg, field_names=fields, skip_nans=True)
        except Exception:  # noqa: BLE001
            return
        data = data[::CLOUD_SUBSAMPLE]
        if len(data) == 0:
            return
        arr = np.column_stack([data['x'], data['y'], data['z']]).astype(float)
        finite = np.isfinite(arr).all(axis=1)
        if not finite.any():
            return
        arr = arr[finite]
        mat = _tf_matrix(tf)
        if not np.all(np.isfinite(mat)):
            return                          # bad TF during startup: skip, don't churn
        world = (np.hstack([arr, np.ones((arr.shape[0], 1))]) @ mat.T)[:, :3]
        colors = None
        if has_rgb:
            rgb_i = np.asarray(data['rgb'], dtype=np.float32)[finite].view(np.uint32)
            r = (rgb_i >> 16) & 0xFF; g = (rgb_i >> 8) & 0xFF; b = rgb_i & 0xFF
            c = ((r & 0xE0) | ((g & 0xE0) >> 3) | ((b & 0xC0) >> 6)).astype(np.uint8)
            colors = np.where(c == 0, 1, c)
        self._voxel_frame += 1
        voxels.add_points(self._voxels, world, voxels.VOXEL_SIZE,
                          self._voxel_frame, colors=colors)
        voxels.evict_to_cap(self._voxels)

    def _publish_voxels(self) -> None:
        if not self._voxels:
            return
        if self._voxel_frame == self._voxel_digest:
            return                          # no new frames since last send
        self._voxel_digest = self._voxel_frame
        payload = voxels.build_voxel_payload(
            self._voxels, voxels.VOXEL_SIZE, time.time())
        if payload is not None:
            self._publish_signed_telemetry('tlm/voxel', payload)

    def _publish_map(self) -> None:
        if self._map_msg is None:
            return
        payload, self._map_digest = build_map_payload(self._map_msg, self._map_digest)
        if payload is not None:
            self._publish_signed_telemetry('tlm/map', payload)

    def _publish_terrain_grid(self) -> None:
        """Sign + emit the accumulated map-frame terrain ribbon as tlm/terrain_grid.
        The operator's persistent 'terrain sensed along the mission' overlay. Digest-
        gated (radios only on change) + zlib over the sparse grid, so a 44 m world of
        mostly-unsensed cells stays a few hundred bytes on the 4G link."""
        if self._terrain_grid_msg is None:
            return
        payload, self._terrain_grid_digest = build_map_payload(
            self._terrain_grid_msg, self._terrain_grid_digest, cls='terrain_grid')
        if payload is not None:
            self._publish_signed_telemetry('tlm/terrain_grid', payload)

    def _on_keyframe(self, msg: 'Image') -> None:
        self._keyframe_msg = msg

    def _publish_keyframe(self) -> None:
        """Sign + emit a JPEG postcard of the ground as tlm/terrain_keyframe."""
        if self._keyframe_msg is None:
            return
        payload, self._keyframe_digest = build_keyframe_payload(
            self._keyframe_msg, self._keyframe_digest)
        if payload is not None:
            self._publish_signed_telemetry('tlm/terrain_keyframe', payload)

    def _on_attitude(self, msg: Float32MultiArray) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self._last_att_pub_ns < int(ATT_TLM_PERIOD_S * 1e9):
            return                        # summarise: the bus runs 10 Hz, the radio needs 0.2
        payload = build_attitude_payload(list(msg.data), now_ns / 1e9)
        if payload is not None:
            self._last_att_pub_ns = now_ns
            self._publish_signed_telemetry('tlm/imu', payload)

    def _on_fix(self, msg: NavSatFix) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self._last_gps_pub_ns < int(GPS_TLM_MIN_PERIOD_S * 1e9):
            return
        payload = build_gps_payload(msg)
        if payload is not None:
            self._last_gps_pub_ns = now_ns
            self._publish_signed_telemetry('tlm/gps', payload)

    # ---- outbound telemetry (sign odom/fault out to the operator) ----------
    def _map_frame_pose(self):
        """(x, y, qz, qw) of base_link in the MAP frame, or None."""
        if self._tf_buffer is None:
            return None
        try:
            tf = self._tf_buffer.lookup_transform(
                'map', 'base_link', rclpy.time.Time())
        except Exception:  # noqa: BLE001 - no SLAM / TF not up yet
            return None
        tr, q = tf.transform.translation, tf.transform.rotation
        return tr.x, tr.y, q.z, q.w

    def _on_odom(self, msg: Odometry) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self._last_odom_pub_ns < self._odom_min_period_ns:
            return                                     # downsample the full-rate DDS odom
        self._last_odom_pub_ns = now_ns
        p, t = msg.pose.pose, msg.twist.twist
        payload = {
            'class': 'odom', 'frame': 'dead-reckon',
            'x': p.position.x, 'y': p.position.y, 'z': p.position.z,
            'qx': p.orientation.x, 'qy': p.orientation.y,
            'qz': p.orientation.z, 'qw': p.orientation.w,
            'vx': t.linear.x, 'vy': t.linear.y, 'wz': t.angular.z,
            'stamp': _t2s(msg.header.stamp)}
        pose = self._map_frame_pose()
        if pose is not None:
            payload['frame'] = 'map'
            payload['x'], payload['y'] = pose[0], pose[1]
            payload['qx'] = payload['qy'] = 0.0
            payload['qz'], payload['qw'] = pose[2], pose[3]
        self._publish_signed_telemetry('tlm/odom', payload)

    def _on_fault(self, msg: FaultReport) -> None:
        self._publish_signed_telemetry('tlm/fault', {
            'class': 'fault',
            'severity': int(msg.severity), 'category': int(msg.category),
            'description': msg.description,
            'recommended_action': msg.recommended_action,
            'module_id': msg.header.module_id, 'stamp': _t2s(msg.header.stamp)})

    def _publish_signed_telemetry(self, suffix: str, payload: dict) -> None:
        if self._rover_priv is None or self._transport is None:
            return
        now = time.time()
        # Dedicated nonce namespace so telemetry nonces never collide with the
        # command-router's issued-as-holder nonces.
        nonce = self._next_issued_nonce(f'{self._rover_id}/tlm')
        env = protocol.sign_telemetry(
            rover_id=self._rover_id, msg_id=nonce, nonce=nonce, issued_at=now,
            expires_at=now + protocol.DEFAULT_EXPIRY_S, payload=payload,
            private_key=self._rover_priv)
        self._transport.publish(f'mark1/{self._rover_id}/{suffix}', protocol.encode(env))

    # ---- inbound (MQTT thread: validate + enqueue only) --------------------
    def _on_cc_message(self, topic: str, payload: bytes) -> None:
        cmd_class = topic.rsplit('/', 1)[-1]
        try:
            envelope = protocol.decode(payload)
        except Exception:  # noqa: BLE001 - malformed wire data
            self._inbound.put(('reject', protocol.SECURITY_AUTH, 'undecodable envelope', None, 0))
            return
        result = self._validator.validate(envelope)
        msg_id = envelope.get('msg_id', 0)
        if result.accepted:
            self._inbound.put(('accept', cmd_class, '', envelope, msg_id))
        else:
            self._inbound.put(('reject', result.category, result.reason, envelope, msg_id))

    # ---- drain (ROS thread: all DDS publishing) ----------------------------
    def _drain_inbound(self) -> None:
        while True:
            try:
                kind, a, b, envelope, msg_id = self._inbound.get_nowait()
            except queue.Empty:
                return
            if kind == 'accept':
                self._dispatch_command(a, envelope)
                self._ack(msg_id, True, 'OK')
            else:
                self._report_rejection(a, b, envelope)
                self._ack(msg_id, False, a)

    def _dispatch_command(self, cmd_class: str, envelope: dict) -> None:
        if cmd_class == 'mission':
            self._dispatch_mission(envelope)
            return
        if cmd_class == 'mode':
            self._apply_mode(envelope)
            return
        if cmd_class != 'motion':
            self.get_logger().warning(f'unknown command class "{cmd_class}"; dropping')
            return
        p = envelope['payload']
        cmd = MotionCommand()
        cmd.header = self._header()
        cmd.type = int(p.get('type', MotionCommand.TYPE_STOP))
        cmd.linear_velocity = float(p.get('linear_velocity', 0.0))
        cmd.angular_velocity = float(p.get('angular_velocity', 0.0))
        cmd.steer_angle_rad = float(p.get('steer_angle_rad', 0.0))
        # COMMAND-ROUTER: re-issue the operator's command AS the current authority
        # lease holder (Locomotion only obeys the holder). The operator id is kept
        # for the audit log, not as the command source. Carry the operator's expiry.
        operator = envelope.get('sender_id', '?')
        if not self._authority_holder:
            self.get_logger().warning('no authority holder known yet; command dropped')
            return
        cmd.source = self._authority_holder
        cmd.nonce = self._next_issued_nonce(self._authority_holder)
        exp = float(envelope.get('expires_at', 0.0))
        cmd.expires_at.sec = int(exp)
        cmd.expires_at.nanosec = int((exp - int(exp)) * 1e9)
        self._motion_pub.publish(cmd)
        if cmd.type == MotionCommand.TYPE_VELOCITY and \
                (cmd.linear_velocity or cmd.angular_velocity):
            self._last_motion_ns = self.get_clock().now().nanoseconds   # stability gate
        self.get_logger().info(
            f'ACCEPTED motion from operator {operator} -> re-issued as '
            f'{cmd.source} (nonce {cmd.nonce}) v={cmd.linear_velocity:.2f} '
            f'w={cmd.angular_velocity:.2f}')

    # ---- mission dispatch (MQTT drain thread: enqueue only) ----------------
    def _dispatch_mission(self, envelope: dict) -> None:
        """Called from the MQTT drain timer — just enqueue for the mission thread."""
        p = envelope.get('payload', {})
        op = p.get('op')
        self._mission_inbound.put(p)
        self.get_logger().info(
            f'mission received: op={op} id={p.get("mission_id", "?")} — queued')

    # ---- mission executor (runs in _mission_cbg) ---------------------------
    def _mission_advance(self) -> None:
        """State-machine tick for the mission executor (0.5 Hz timer, mission_cbg)."""
        # Drain inbound mission commands (enqueued by MQTT drain timer)
        try:
            while True:
                cmd = self._mission_inbound.get_nowait()
                self._handle_mission_cmd(cmd)
        except queue.Empty:
            pass

        ms = self._mission_state
        if ms is None:
            return

        # Authority health check: if neither Core nor Telemetry holds a valid
        # lease the rover's wheels are frozen — pause the mission rather than
        # keep issuing Nav2 goals that go nowhere.
        now_s = self.get_clock().now().nanoseconds * 1e-9
        authority_ok = (now_s < self._core_lease_expiry_s or
                        self._auth_state == TLM_HOLDING)

        if ms['state'] == 'active' and not authority_ok:
            self.get_logger().warning(
                f'mission {ms["mission_id"]}: authority lost — pausing')
            self._mission_cancel_nav_goal()
            ms['state'] = 'paused'
            self._publish_mission_progress()
            return

        if ms['state'] == 'paused' and authority_ok:
            self.get_logger().info(
                f'mission {ms["mission_id"]}: authority restored — resuming')
            ms['state'] = 'active'
            self._mission_goal_sent = False    # re-send current waypoint
            self._publish_mission_progress()

        if ms['state'] != 'active':
            return

        if self._mission_goal_sent:
            return    # waiting for Nav2 result callback

        # Honour retry backoff (costmap expanding, SLAM building)
        if self._mission_next_retry_ns > 0:
            if self.get_clock().now().nanoseconds < self._mission_next_retry_ns:
                return
            self._mission_next_retry_ns = 0

        i = ms['waypoint_i']
        waypoints = ms['waypoints']
        if i >= len(waypoints):
            ms['state'] = 'complete'
            ms['coverage_pct'] = 100.0
            self.get_logger().info(
                f'mission {ms["mission_id"]}: COMPLETE ({len(waypoints)} waypoints)')
            self._publish_mission_progress()
            self._mission_state = None
            return

        if self._mission_nav_client is None:
            self.get_logger().error('Nav2 action client not available; mission failed')
            ms['state'] = 'failed'
            self._publish_mission_progress()
            self._mission_state = None
            return

        if not self._mission_nav_client.server_is_ready():
            return    # Nav2 not up yet — retry next tick

        # L2 Supervised: pause for operator approval before EACH waypoint goal.
        # The rover plans + executes, but the operator approves key decisions.
        # motion_allowed(2) is True at the wheel gate, so approval controls the
        # GOAL, not low-level motion. Approve/deny arrives as a signed command.
        if self._autonomy_level == 2 and ms.get('approved_wp', -1) < i:
            if not ms.get('awaiting_approval'):
                ms['awaiting_approval'] = True
                ms['pending_wp'] = i
                self.get_logger().info(
                    f'mission {ms["mission_id"]}: wp {i} AWAITING OPERATOR '
                    f'APPROVAL (L2 Supervised)')
                self._publish_mission_progress()
            return    # hold until an approve/deny command arrives

        x, y = waypoints[i]
        self._mission_send_nav_goal(x, y)
        self._mission_goal_sent = True
        self.get_logger().info(
            f'mission {ms["mission_id"]}: wp {i}/{len(waypoints)-1} -> ({x:.2f}, {y:.2f})')

    def _handle_mission_cmd(self, cmd: dict) -> None:
        op = cmd.get('op')
        mission_id = cmd.get('mission_id', '?')

        if op == 'survey_start':
            if self._mission_state is not None:
                # Preempt any existing mission
                self.get_logger().warning(
                    f'preempting mission {self._mission_state["mission_id"]} '
                    f'for new mission {mission_id}')
                self._mission_cancel_nav_goal()
                self._mission_state['state'] = 'aborted'
                self._publish_mission_progress()

            zone = cmd.get('zone')
            zone_gps = cmd.get('zone_gps')
            if zone_gps is not None and zone is None:
                zone = zone_gps_to_map(zone_gps)
            if zone is None:
                self.get_logger().error(f'mission {mission_id}: no zone in payload')
                return

            spacing = float(cmd.get('lane_spacing_m', 3.0))
            waypoints = plan_survey(zone, spacing)
            if not waypoints:
                self.get_logger().error(
                    f'mission {mission_id}: degenerate zone {zone} produced no waypoints')
                return

            self._mission_state = {
                'mission_id': mission_id,
                'waypoints': waypoints,
                'waypoint_i': 0,
                'waypoint_n': len(waypoints),
                'state': 'active',
                'coverage_pct': 0.0,
            }
            self._mission_goal_sent = False
            self._mission_retry_count = 0
            self._mission_current_goal_handle = None
            self.get_logger().info(
                f'mission {mission_id}: survey_start zone={zone} '
                f'spacing={spacing} waypoints={len(waypoints)}')
            self._publish_mission_progress()

        elif op == 'abort':
            if (self._mission_state is not None and
                    self._mission_state['mission_id'] == mission_id):
                self.get_logger().info(f'mission {mission_id}: ABORT received')
                self._mission_cancel_nav_goal()
                self._mission_state['state'] = 'aborted'
                self._publish_mission_progress()
                self._mission_state = None
            else:
                self.get_logger().warning(
                    f'abort for {mission_id} but active mission is '
                    f'{self._mission_state["mission_id"] if self._mission_state else "none"}')
        elif op in ('approve', 'deny'):
            ms = self._mission_state
            if ms is None or ms['mission_id'] != mission_id:
                self.get_logger().warning(
                    f'{op} for {mission_id} but no matching active mission')
                return
            wp = int(cmd.get('waypoint_i', ms.get('pending_wp', ms['waypoint_i'])))
            ms['awaiting_approval'] = False
            if op == 'approve':
                ms['approved_wp'] = wp          # unblocks _mission_advance for wp
                self.get_logger().info(
                    f'mission {mission_id}: wp {wp} APPROVED by operator')
            else:  # deny -> skip this waypoint, ask again for the next
                if wp == ms['waypoint_i']:
                    ms['waypoint_i'] += 1
                    ms.setdefault('skipped', 0)
                    ms['skipped'] += 1
                self.get_logger().info(
                    f'mission {mission_id}: wp {wp} DENIED by operator — skipping')
            self._mission_goal_sent = False
            self._publish_mission_progress()

        else:
            self.get_logger().warning(f'unknown mission op "{op}"; ignoring')

    def _mission_send_nav_goal(self, x: float, y: float) -> None:
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.w = 1.0
        goal.behavior_tree = ''
        fut = self._mission_nav_client.send_goal_async(goal)
        fut.add_done_callback(self._on_mission_goal_response)

    def _on_mission_goal_response(self, future) -> None:
        goal_handle = future.result()
        ms = self._mission_state
        if not goal_handle.accepted:
            self.get_logger().warning('Nav2 rejected mission waypoint goal')
            self._mission_goal_sent = False
            if ms is not None:
                ms['state'] = 'failed'
                self._publish_mission_progress()
                self._mission_state = None
            return
        self._mission_current_goal_handle = goal_handle
        goal_handle.get_result_async().add_done_callback(self._on_mission_goal_result)

    def _on_mission_goal_result(self, future) -> None:
        ms = self._mission_state
        self._mission_goal_sent = False
        self._mission_current_goal_handle = None

        result = future.result()
        status = result.status

        if ms is None:
            return    # mission was aborted while waiting

        if ms['state'] not in ('active', 'paused'):
            return    # aborted/completed between goal send and result

        _MAX_RETRIES = 6   # outdoor: fail fast per-wp, skip+advance (below) keeps mission productive
        if status == _GoalStatus.STATUS_SUCCEEDED:
            ms['waypoint_i'] += 1
            self._mission_retry_count = 0
            n = ms['waypoint_n']
            ms['coverage_pct'] = ms['waypoint_i'] / n * 100.0
            self.get_logger().info(
                f'mission {ms["mission_id"]}: wp {ms["waypoint_i"]}/{n} done '
                f'coverage={ms["coverage_pct"]:.1f}%')
            self._publish_mission_progress()
        elif status in (_GoalStatus.STATUS_CANCELED, _GoalStatus.STATUS_ABORTED):
            # STATUS_CANCELED: external preemption (patrol goal) or our abort.
            # STATUS_ABORTED: Nav2 planner/controller failed — most commonly the
            #   goal is outside the current SLAM costmap bounds; the map will
            #   expand as the rover patrols, so we retry up to _MAX_RETRIES.
            if ms['state'] == 'active':
                self._mission_retry_count += 1
                if self._mission_retry_count <= _MAX_RETRIES:
                    # Backoff: aborted (costmap) waits longer than canceled (preempt)
                    delay_s = 5.0 if status == _GoalStatus.STATUS_ABORTED else 1.0
                    self._mission_next_retry_ns = (
                        self.get_clock().now().nanoseconds + int(delay_s * 1e9))
                    self.get_logger().info(
                        f'mission {ms["mission_id"]}: wp {ms["waypoint_i"]} '
                        f'status={status} — retry {self._mission_retry_count}/'
                        f'{_MAX_RETRIES} in {delay_s:.0f}s')
                else:
                    # Skip-and-advance: log the miss, count it, move to the next
                    # waypoint. Outdoor terrain slopes make some interior cells
                    # unreachable; best-effort coverage beats a whole-mission
                    # failure. If EVERY wp is skipped, we surface 'failed' at the
                    # end so the operator sees the story honestly.
                    self.get_logger().warning(
                        f'mission {ms["mission_id"]}: wp {ms["waypoint_i"]} '
                        f'unreachable after {_MAX_RETRIES} retries — skipping')
                    ms.setdefault('skipped', 0)
                    ms['skipped'] += 1
                    ms['waypoint_i'] += 1
                    self._mission_retry_count = 0
                    n = ms['waypoint_n']
                    ms['coverage_pct'] = (ms['waypoint_i'] - ms['skipped']) / n * 100.0
                    self._publish_mission_progress()
                    # If everything skipped so far, degrade to failed at end of mission
                    if ms['waypoint_i'] >= n and ms['skipped'] == n:
                        ms['state'] = 'failed'
                        self._publish_mission_progress()
                        self._mission_state = None
        else:
            self.get_logger().warning(
                f'mission {ms["mission_id"]}: wp {ms["waypoint_i"]} '
                f'failed (status={status})')
            ms['state'] = 'failed'
            self._publish_mission_progress()
            self._mission_state = None

    def _mission_cancel_nav_goal(self) -> None:
        handle = self._mission_current_goal_handle
        if handle is not None:
            handle.cancel_goal_async()
            self._mission_current_goal_handle = None
            self._mission_goal_sent = False

    def _publish_mission_progress(self) -> None:
        ms = self._mission_state
        if ms is None:
            return
        payload = {
            'class': 'mission',
            'mission_id': ms['mission_id'],
            'state': 'awaiting_approval' if ms.get('awaiting_approval') else ms['state'],
            'waypoint_i': ms['waypoint_i'],
            'waypoint_n': ms['waypoint_n'],
            'coverage_pct': round(ms['coverage_pct'], 1),
            'skipped': ms.get('skipped', 0),
            'awaiting_approval': bool(ms.get('awaiting_approval')),
            'pending_wp': ms.get('pending_wp', -1),
            'stamp': time.time(),
        }
        self._publish_signed_telemetry('tlm/mission', payload)

    # ---- authority tracking ------------------------------------------------
    def _on_authority(self, msg: AuthorityLease) -> None:
        # Track Core's lease for failover detection. Ignore our own echo while
        # holding, and ignore a stale lower-epoch lease (epoch-monotonic).
        if msg.holder_module_id == self._module_id:
            return
        if not authority.accept_lease(incoming_epoch=msg.epoch,
                                      current_epoch=self._epoch):
            return
        self._authority_holder = msg.holder_module_id
        self._epoch = msg.epoch
        self._core_lease_expiry_s = _t2s(msg.expires_at)
        self._core_seen = True

    def _on_safety_pulse(self, msg: Heartbeat) -> None:
        self._last_pulse_ns = self.get_clock().now().nanoseconds

    # ---- failover (self-promote on Core loss) ------------------------------
    def _check_failover(self) -> None:
        # Self-promote only when BOTH of Core's independent signals have failed:
        # its lease has expired AND its safety pulse has gone silent.
        if self._auth_state != TLM_MONITORING or not self._core_seen:
            return
        now_ns = self.get_clock().now().nanoseconds
        gap_s = ((now_ns - self._last_failover_check_ns) / 1e9
                 if self._last_failover_check_ns else 0.0)
        self._last_failover_check_ns = now_ns
        if authority.starved(gap_s=gap_s, period_s=FAILOVER_CHECK_S):
            # THIS process stalled between checks: the "Core silent" evidence
            # was gathered while we weren't scheduled. Discard it rather than
            # act on it — a starved Telemetry once self-promoted against a
            # healthy Core and quarantined the fleet (2026-07-19).
            self._last_pulse_ns = now_ns
            return
        lease_expired = (now_ns * 1e-9) >= self._core_lease_expiry_s
        pulse_lost = (now_ns - self._last_pulse_ns) / 1e9 >= PULSE_LOST_S
        if authority.should_failover(lease_expired=lease_expired, pulse_lost=pulse_lost):
            self._promote()

    def _promote(self) -> None:
        self._epoch += 1                       # last epoch + 1
        self._authority_holder = self._module_id
        self._auth_state = TLM_HOLDING
        self._lease_timer = self.create_timer(LEASE_RENEW_S, self._publish_authority_lease)
        self._pulse_timer = self.create_timer(PULSE_PERIOD_S, self._publish_safety_pulse)
        self._publish_authority_lease()        # assert authority immediately
        self.get_logger().warning(
            f'CORE LOST (lease expired + safety pulse silent) — Telemetry '
            f'self-promoting to authority at epoch {self._epoch}')

    def _publish_authority_lease(self) -> None:
        if self._auth_state != TLM_HOLDING:
            return
        msg = AuthorityLease()
        msg.header = self._header()
        msg.holder_module_id = self._module_id
        msg.epoch = self._epoch
        msg.expires_at = (self.get_clock().now() + Duration(seconds=2.0)).to_msg()
        self._authority_pub.publish(msg)

    def _publish_safety_pulse(self) -> None:
        if self._auth_state != TLM_HOLDING:
            return
        msg = Heartbeat()
        msg.header = self._header()
        msg.sequence = self._safety_seq
        msg.lifecycle_state = LCState.PRIMARY_STATE_ACTIVE
        self._safety_pulse_pub.publish(msg)
        self._safety_seq += 1

    # ---- authority return (clean hand-back to a recovering Core) -----------
    def _on_request_authority(self, request, response):
        if self._auth_state != TLM_HOLDING:
            response.granted = False
            response.new_epoch = self._epoch
            response.reason = 'telemetry does not hold authority'
            return response
        stable = self._is_stable()
        if not authority.may_grant_return(
                requester_epoch=request.last_known_epoch,
                holder_epoch=self._epoch, stable=stable):
            response.granted = False
            response.new_epoch = self._epoch
            response.reason = ('rover not stable (recent motion)' if not stable
                               else f'requester epoch {request.last_known_epoch} '
                                    f'behind holder {self._epoch}')
            self.get_logger().info(
                f'RequestAuthority from {request.requester_module_id} denied: '
                f'{response.reason}')
            return response
        new_epoch = self._epoch + 1
        response.granted = True
        response.new_epoch = new_epoch
        response.reason = 'granted'
        self.get_logger().info(
            f'RequestAuthority from {request.requester_module_id} granted at epoch '
            f'{new_epoch} — releasing and standing down')
        self._release_authority(new_epoch, request.requester_module_id)
        return response

    def _release_authority(self, new_epoch: int, requester: str) -> None:
        self._announce_release(f'authority returned to {requester} at epoch {new_epoch}')
        self._stand_down()

    def _announce_release(self, reason: str) -> None:
        # A holder must never stand down silently: consumers keep the epoch
        # high-water and reject every lower lease, so an unannounced stand-down
        # orphans the epoch and quarantines a lower-epoch Core forever. The
        # release rides TRANSIENT_LOCAL, so even a Core that boots later still
        # hears it and adopts a higher epoch.
        rel = ReleaseAuthority()
        rel.header = self._header()
        rel.releasing_module_id = self._module_id
        rel.epoch = self._epoch
        rel.reason = reason
        self._release_pub.publish(rel)

    def _stand_down(self) -> None:
        for attr in ('_lease_timer', '_pulse_timer'):
            timer = getattr(self, attr)
            if timer is not None:
                self.destroy_timer(timer)
                setattr(self, attr, None)
        self._auth_state = TLM_MONITORING
        # grace: Core keeps pulsing through the quiet window and its fresh lease
        # arrives just after — don't re-failover in that gap.
        now_ns = self.get_clock().now().nanoseconds
        self._last_pulse_ns = now_ns
        self._core_lease_expiry_s = now_ns * 1e-9 + 2.0
        self.get_logger().info('stood down — monitoring; Core resumes authority')

    def _is_stable(self) -> bool:
        quiet_s = (self.get_clock().now().nanoseconds - self._last_motion_ns) / 1e9
        return quiet_s >= STABLE_QUIET_S

    def _next_issued_nonce(self, holder: str) -> int:
        # Durable monotonic nonce for commands issued as the holder, so a Telemetry
        # restart can't replay-collide with Locomotion's persisted nonce floor.
        n = (self._nonce_store.last(holder) or 0) + 1
        self._nonce_store.commit(holder, n)
        return n

    def _report_rejection(self, category: str, reason: str, envelope) -> None:
        sender = envelope.get('sender_id', '?') if envelope else '?'
        cat_map = {
            protocol.SECURITY_AUTH: FaultReport.CATEGORY_SECURITY_AUTH,
            protocol.SECURITY_REPLAY: FaultReport.CATEGORY_SECURITY_REPLAY,
        }
        fr = FaultReport()
        fr.header = self._header()
        fr.severity = FaultReport.SEVERITY_ERROR
        fr.category = cat_map.get(category, FaultReport.CATEGORY_GENERAL)
        fr.description = f'command from "{sender}" rejected: {category} ({reason})'
        fr.recommended_action = 'alert operator; audit Command Center link'
        self._fault_pub.publish(fr)
        self.get_logger().warning(f'REJECTED {category}: {reason}')

    def _ack(self, msg_id, accepted: bool, category: str) -> None:
        if self._transport is None:
            return
        ack = {'msg_id': msg_id, 'accepted': accepted, 'category': category}
        nonce = self._next_issued_nonce(f'{self._rover_id}/tlm') if self._rover_priv else 0
        body = self._build_ack_body(ack, self._rover_priv, self._rover_id, nonce)
        self._transport.publish(f'mark1/{self._rover_id}/ack/{msg_id}', body)

    @staticmethod
    def _build_ack_body(ack: dict, rover_priv, rover_id: str, nonce: int) -> bytes:
        """ACK wire bytes: a signed envelope when the rover holds a key, else plain CBOR."""
        if rover_priv is None:
            return cbor2.dumps(ack)                        # plain ack (no rover key)
        now = time.time()
        env = protocol.sign_telemetry(                     # signed (operator-verifiable)
            rover_id=rover_id, msg_id=nonce, nonce=nonce, issued_at=now,
            expires_at=now + protocol.DEFAULT_EXPIRY_S,
            payload={'class': 'ack', **ack}, private_key=rover_priv)
        return protocol.encode(env)

    def _header(self):
        from friday_msgs.msg import Mark1Header
        h = Mark1Header()
        h.protocol_major = protocol.PROTOCOL_MAJOR
        h.protocol_minor = protocol.PROTOCOL_MINOR
        h.protocol_patch = protocol.PROTOCOL_PATCH
        h.module_id = self._module_id
        h.stamp = self.get_clock().now().to_msg()
        return h


def main(args=None):
    rclpy.init(args=args)
    node = TelemetryAgent()
    from rclpy.executors import ExternalShutdownException
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    executor.add_node(node._tf_node)       # dedicated TF clock (sim vs wall)
    # Crash-proof spin (matches friday_module_agent.runner.spin_agent): rclpy
    # lifecycle nodes RAISE on an invalid transition, and the supervisor's
    # recovery can trigger one after a transient heartbeat miss. A plain
    # spin() would let that RCLError kill the process (and ALL telemetry) —
    # this stays alive and re-enters spin instead.
    try:
        while rclpy.ok():
            try:
                executor.spin()
                break
            except (KeyboardInterrupt, ExternalShutdownException):
                break
            except Exception as exc:  # noqa: BLE001 -- deliberate: a daemon degrades, never dies
                node.get_logger().error(f'telemetry recovered from handler exception: {exc!r}')
    finally:
        node._tf_node.destroy_node()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
