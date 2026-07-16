"""Phone sensor pod agent — bridges an Android phone's GPS + IMU into Mark 1.

The phone (module MARK1-PHONE-001) streams one-way over WiFi: GPSd Forwarder
sends NMEA to gpsd on the Pi, HyperIMU sends JSON datagrams straight to this
node's UDP socket. The bridge validates every packet (see ingest.py) and
publishes:

  * /mark1/phone/fix  — sensor_msgs/NavSatFix   (sensor_stream QoS)
  * /mark1/phone/imu  — sensor_msgs/Imu         (sensor_stream QoS)

Contract notes:
  * Advisory only, OUTSIDE the safety path. A silent phone drops health to
    DEGRADED; it never trips safe-stop and the heartbeat keeps running.
  * Registration keep-alive: RegisterModule is re-sent every 60 s (harmless
    upsert) so a Core-Hub restart that wipes the in-memory registry heals.
  * Messages are stamped on ARRIVAL with the Pi's clock; the phone's clock is
    untrusted. WiFi arrival jitter makes this display/tilt-grade data — do NOT
    feed it to an EKF/fusion pipeline without a resampling buffer.
  * No commands ever flow to the phone; the sockets are receive-only.
"""

import math
import select
import socket

import rclpy
from sensor_msgs.msg import Imu, NavSatFix, NavSatStatus

from friday_module_agent import qos
from friday_module_agent.runner import spin_agent
from friday_module_agent.module_agent import ModuleAgent

from friday_phone_bridge import ingest

FIX_TOPIC = '/mark1/phone/fix'
IMU_TOPIC = '/mark1/phone/imu'
FRAME_ID = 'phone_link'

POLL_PERIOD_S = 0.02            # 50 Hz socket drain
REREGISTER_PERIOD_S = 60.0      # registry keep-alive (heals registry restarts)
FIX_FRESH_ANCHOR_S = 30.0       # teleport check only against a fix this recent
MAX_DATAGRAMS_PER_TICK = 32     # bounded work per poll tick
MAX_DATAGRAM_BYTES = 4096
GPSD_RECONNECT_S = 5.0
GPSD_WATCH = b'?WATCH={"enable":true,"json":true};\n'


class PhoneBridge(ModuleAgent):
    """Lifecycle agent for the phone sensor pod (GPS + IMU over WiFi)."""

    def __init__(self):
        super().__init__(
            node_name='phone',
            module_id='MARK1-PHONE-001',
            module_ns='phone',
            hardware_type='phone',       # NOT 'sensor': MARK1-SENSOR-001 owns /mark1/sensor
            capabilities=['gps', 'imu'],
            sw_version='0.1.0',
        )
        self.declare_parameter('bind_address', '0.0.0.0')
        self.declare_parameter('imu_port', 5555)
        self.declare_parameter('phone_ip', '')       # '' accepts any source (bench)
        self.declare_parameter('gpsd_host', '127.0.0.1')
        self.declare_parameter('gpsd_port', 2947)
        self.declare_parameter('fix_timeout_s', 3.0)
        self.declare_parameter('imu_timeout_s', 1.0)
        self.declare_parameter('max_imu_msgs_per_s', 100)
        self.declare_parameter('csv_accel_index', 0)   # HyperIMU CSV field maps
        self.declare_parameter('csv_gyro_index', 3)    # (accel+gyro only ticked)

        self._fix_pub = None
        self._imu_pub = None
        self._imu_sock = None
        self._gpsd_sock = None
        self._gpsd_buffer = b''
        self._gpsd_retry_at_ns = 0
        self._poll_timer = None
        self._reregister_timer = None
        self._rate_window = ingest.RateWindow(window_start_s=0.0, count=0)
        self._last_fix = None
        self._last_fix_ns = None
        self._last_imu_ns = None
        self._drop_counts = {'imu_parse': 0, 'imu_rate': 0, 'imu_source': 0,
                             'fix_parse': 0, 'fix_jump': 0}

    # ---- ModuleAgent hardware hooks ---------------------------------------
    def configure_hardware(self) -> None:
        self._fix_pub = self.create_lifecycle_publisher(
            NavSatFix, FIX_TOPIC, qos.sensor_stream())
        self._imu_pub = self.create_lifecycle_publisher(
            Imu, IMU_TOPIC, qos.sensor_stream())
        bind = self.get_parameter('bind_address').value
        port = int(self.get_parameter('imu_port').value)
        self._imu_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._imu_sock.setblocking(False)
        self._imu_sock.bind((bind, port))
        self.get_logger().info(f'IMU ingest listening on udp://{bind}:{port}')
        self._reregister_timer = self.create_timer(
            REREGISTER_PERIOD_S, self._keepalive_register)

    def activate_hardware(self) -> None:
        self._drain_stale_datagrams()
        self._last_fix = None
        self._last_fix_ns = None
        self._last_imu_ns = None
        self._poll_timer = self.create_timer(POLL_PERIOD_S, self._poll)

    def enter_safe_state(self) -> None:
        # Nothing to actuate: safe state is simply "stop publishing".
        if self._poll_timer is not None:
            self.destroy_timer(self._poll_timer)
            self._poll_timer = None
        self._close_gpsd()

    def health_overall(self) -> int:
        overall, detail = self._health()
        if detail:
            self.get_logger().warning(detail, throttle_duration_sec=10.0)
        return overall

    # ---- lifecycle cleanup -------------------------------------------------
    def on_cleanup(self, state):
        self._teardown_sockets()
        return super().on_cleanup(state)

    def on_shutdown(self, state):
        self._teardown_sockets()
        return super().on_shutdown(state)

    # ---- registry keep-alive ----------------------------------------------
    def _keepalive_register(self) -> None:
        # Re-sending RegisterModule is an upsert in the registry; doing it
        # periodically heals a Core-Hub restart that wiped the in-memory
        # registry (confirmed gap in the ESP32 firmware — fixed here from day 1).
        if self._reg_client is not None and self._reg_client.service_is_ready():
            self._register_async()

    # ---- ingest loop -------------------------------------------------------
    def _poll(self) -> None:
        self._poll_imu()
        self._poll_gpsd()

    def _poll_imu(self) -> None:
        phone_ip = self.get_parameter('phone_ip').value
        limit = int(self.get_parameter('max_imu_msgs_per_s').value)
        for _ in range(MAX_DATAGRAMS_PER_TICK):
            try:
                raw, (src_ip, _src_port) = self._imu_sock.recvfrom(MAX_DATAGRAM_BYTES)
            except BlockingIOError:
                return
            if phone_ip and src_ip != phone_ip:
                self._drop('imu_source')
                continue
            now_s = self.get_clock().now().nanoseconds * 1e-9
            self._rate_window, allowed = ingest.rate_allow(
                self._rate_window, now_s, limit)
            if not allowed:
                self._drop('imu_rate')
                continue
            sample = ingest.parse_imu_datagram(
                raw,
                accel_i=int(self.get_parameter('csv_accel_index').value),
                gyro_i=int(self.get_parameter('csv_gyro_index').value))
            if sample is None:
                self._drop('imu_parse')
                continue
            self._publish_imu(sample)

    def _poll_gpsd(self) -> None:
        if self._gpsd_sock is None:
            self._connect_gpsd()
            return
        try:
            readable, _, _ = select.select([self._gpsd_sock], [], [], 0)
            if not readable:
                return
            chunk = self._gpsd_sock.recv(65536)
        except OSError:
            self._close_gpsd()
            return
        if not chunk:                       # gpsd closed the connection
            self._close_gpsd()
            return
        self._gpsd_buffer += chunk
        while b'\n' in self._gpsd_buffer:
            line, self._gpsd_buffer = self._gpsd_buffer.split(b'\n', 1)
            self._handle_gpsd_line(line)
        if len(self._gpsd_buffer) > MAX_DATAGRAM_BYTES:
            self._gpsd_buffer = b''         # bounded buffer: discard runaway line

    def _handle_gpsd_line(self, line: bytes) -> None:
        try:
            text = line.decode('utf-8')
        except UnicodeDecodeError:
            self._drop('fix_parse')
            return
        if not text.strip():
            return
        fix = ingest.parse_gpsd_line(text)
        if fix is None:
            return                          # VERSION/SKY/no-fix TPV: normal chatter
        now_ns = self.get_clock().now().nanoseconds
        anchor_fresh = (self._last_fix is not None and self._last_fix_ns is not None
                        and (now_ns - self._last_fix_ns) * 1e-9 < FIX_FRESH_ANCHOR_S)
        if anchor_fresh and ingest.jump_suspicious(self._last_fix, fix):
            self._drop('fix_jump')
            return
        self._publish_fix(fix)

    # ---- publishing (stamped on arrival, Pi clock) --------------------------
    def _publish_imu(self, sample: ingest.ImuSample) -> None:
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = FRAME_ID
        msg.orientation_covariance[0] = -1.0        # no orientation estimate
        msg.linear_acceleration.x = sample.ax
        msg.linear_acceleration.y = sample.ay
        msg.linear_acceleration.z = sample.az
        msg.angular_velocity.x = sample.gx
        msg.angular_velocity.y = sample.gy
        msg.angular_velocity.z = sample.gz
        self._imu_pub.publish(msg)
        self._last_imu_ns = self.get_clock().now().nanoseconds

    def _publish_fix(self, fix: ingest.FixSample) -> None:
        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = FRAME_ID
        msg.status.status = NavSatStatus.STATUS_FIX
        msg.status.service = NavSatStatus.SERVICE_GPS
        msg.latitude = fix.latitude
        msg.longitude = fix.longitude
        msg.altitude = fix.altitude
        msg.position_covariance = list(fix.position_covariance)
        msg.position_covariance_type = fix.covariance_type
        self._fix_pub.publish(msg)
        self._last_fix = fix
        self._last_fix_ns = self.get_clock().now().nanoseconds

    # ---- health -------------------------------------------------------------
    def _health(self):
        now_ns = self.get_clock().now().nanoseconds
        fix_age = ((now_ns - self._last_fix_ns) * 1e-9
                   if self._last_fix_ns is not None else None)
        imu_age = ((now_ns - self._last_imu_ns) * 1e-9
                   if self._last_imu_ns is not None else None)
        return ingest.health_from_ages(
            fix_age, imu_age,
            float(self.get_parameter('fix_timeout_s').value),
            float(self.get_parameter('imu_timeout_s').value))

    # ---- socket plumbing -----------------------------------------------------
    def _connect_gpsd(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns < self._gpsd_retry_at_ns:
            return
        self._gpsd_retry_at_ns = now_ns + int(GPSD_RECONNECT_S * 1e9)
        host = self.get_parameter('gpsd_host').value
        port = int(self.get_parameter('gpsd_port').value)
        try:
            sock = socket.create_connection((host, port), timeout=1.0)
            sock.sendall(GPSD_WATCH)
            sock.setblocking(False)
        except OSError as exc:
            self.get_logger().warning(
                f'gpsd unreachable at {host}:{port}: {exc}',
                throttle_duration_sec=30.0)
            return
        self._gpsd_sock = sock
        self._gpsd_buffer = b''
        self.get_logger().info(f'connected to gpsd at {host}:{port}')

    def _close_gpsd(self) -> None:
        if self._gpsd_sock is not None:
            try:
                self._gpsd_sock.close()
            except OSError:
                pass
            self._gpsd_sock = None
        self._gpsd_buffer = b''

    def _drain_stale_datagrams(self) -> None:
        # Packets that queued while inactive are stale by definition.
        while True:
            try:
                self._imu_sock.recvfrom(MAX_DATAGRAM_BYTES)
            except (BlockingIOError, OSError):
                return

    def _drop(self, reason: str) -> None:
        # Count drops, never log raw payloads (unbounded attacker-controlled data).
        self._drop_counts = {**self._drop_counts,
                             reason: self._drop_counts[reason] + 1}
        self.get_logger().warning(
            f'dropping {reason} (total {self._drop_counts[reason]})',
            throttle_duration_sec=10.0)

    def _teardown_sockets(self) -> None:
        if self._poll_timer is not None:
            self.destroy_timer(self._poll_timer)
            self._poll_timer = None
        if self._reregister_timer is not None:
            self.destroy_timer(self._reregister_timer)
            self._reregister_timer = None
        self._close_gpsd()
        if self._imu_sock is not None:
            try:
                self._imu_sock.close()
            except OSError:
                pass
            self._imu_sock = None


def main(args=None):
    rclpy.init(args=args)
    spin_agent(PhoneBridge())


if __name__ == '__main__':
    main()
