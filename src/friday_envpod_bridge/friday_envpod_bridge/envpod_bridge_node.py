"""Environmental sensor pod agent -- bridges the Zero W SensorHub into Mark 1.

A Raspberry Pi Zero W with a DockerPi SensorHub HAT (no ROS: ARMv6) reads the
HAT over I2C and streams one JSON datagram per second over WiFi UDP to this
node, which validates it (ingest.py) and publishes:

  * /mark1/envpod/temperature -- sensor_msgs/Temperature
  * /mark1/envpod/humidity    -- sensor_msgs/RelativeHumidity
  * /mark1/envpod/pressure    -- sensor_msgs/FluidPressure
  * /mark1/envpod/illuminance -- sensor_msgs/Illuminance
  * /mark1/envpod/presence    -- std_msgs/Bool

Contract notes (mirror the phone pod, PR #6):
  * Advisory only, OUTSIDE the safety path. A silent pod drops health to
    DEGRADED; it never trips safe-stop and the heartbeat keeps running.
  * Registration keep-alive: RegisterModule re-sent every 60 s (harmless
    upsert) so a Core-Hub restart that wiped the in-memory registry heals.
  * Readings are stamped on ARRIVAL with the Pi's clock; the pod's clock is
    untrusted.
  * Receive-only socket; no commands ever flow to the pod.
  * INTERIM host: raw-sensor ingest belongs on the Research Deck (Pi 5) per the
    data-gate rule; the Core Hub hosts it until that hardware exists.
"""

import socket

import rclpy
from sensor_msgs.msg import (FluidPressure, Illuminance, RelativeHumidity,
                             Temperature)
from std_msgs.msg import Bool

from friday_module_agent import qos
from friday_module_agent.runner import spin_agent
from friday_module_agent.module_agent import ModuleAgent

from friday_envpod_bridge import ingest

FRAME_ID = 'envpod_link'
POLL_PERIOD_S = 0.2            # 5 Hz socket drain (pod sends ~1 Hz)
REREGISTER_PERIOD_S = 60.0     # registry keep-alive (heals registry restarts)
MAX_DATAGRAMS_PER_TICK = 8     # bounded work per poll tick
MAX_DATAGRAM_BYTES = 1024


class EnvpodBridge(ModuleAgent):
    """Lifecycle agent for the environmental sensor pod (SensorHub over WiFi)."""

    def __init__(self):
        super().__init__(
            node_name='envpod',
            module_id='MARK1-ENVPOD-001',
            module_ns='envpod',
            hardware_type='envpod',      # own type: keeps clear of MARK1-SENSOR-001
            capabilities=['temperature', 'humidity', 'pressure', 'light',
                          'presence'],
            sw_version='0.1.0',
        )
        self.declare_parameter('bind_address', '0.0.0.0')
        self.declare_parameter('udp_port', 5556)
        self.declare_parameter('pod_ip', '')          # '' accepts any source (bench)
        self.declare_parameter('stale_timeout_s', 5.0)
        self.declare_parameter('max_msgs_per_s', 50)

        self._temp_pub = None
        self._rh_pub = None
        self._press_pub = None
        self._lux_pub = None
        self._presence_pub = None
        self._sock = None
        self._poll_timer = None
        self._reregister_timer = None
        self._last_sample_ns = None
        self._rate_window = ingest.RateWindow(window_start_s=0.0, count=0)
        self._drop_counts = {'parse': 0, 'source': 0, 'rate': 0}

    # ---- ModuleAgent hardware hooks ---------------------------------------
    def configure_hardware(self) -> None:
        self._temp_pub = self.create_lifecycle_publisher(
            Temperature, self._topic('temperature'), qos.sensor_stream())
        self._rh_pub = self.create_lifecycle_publisher(
            RelativeHumidity, self._topic('humidity'), qos.sensor_stream())
        self._press_pub = self.create_lifecycle_publisher(
            FluidPressure, self._topic('pressure'), qos.sensor_stream())
        self._lux_pub = self.create_lifecycle_publisher(
            Illuminance, self._topic('illuminance'), qos.sensor_stream())
        self._presence_pub = self.create_lifecycle_publisher(
            Bool, self._topic('presence'), qos.sensor_stream())
        bind = self.get_parameter('bind_address').value
        port = int(self.get_parameter('udp_port').value)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.bind((bind, port))
        self.get_logger().info(f'envpod ingest listening on udp://{bind}:{port}')
        self._reregister_timer = self.create_timer(
            REREGISTER_PERIOD_S, self._keepalive_register)

    def activate_hardware(self) -> None:
        self._drain_stale_datagrams()
        self._last_sample_ns = None
        self._poll_timer = self.create_timer(POLL_PERIOD_S, self._poll)

    def enter_safe_state(self) -> None:
        # Nothing to actuate: safe state is simply "stop publishing".
        if self._poll_timer is not None:
            self.destroy_timer(self._poll_timer)
            self._poll_timer = None

    def health_overall(self) -> int:
        now_ns = self.get_clock().now().nanoseconds
        age = ((now_ns - self._last_sample_ns) * 1e-9
               if self._last_sample_ns is not None else None)
        overall, detail = ingest.health_from_age(
            age, float(self.get_parameter('stale_timeout_s').value))
        if detail:
            self.get_logger().warning(detail, throttle_duration_sec=10.0)
        return overall

    # ---- lifecycle cleanup -------------------------------------------------
    def on_cleanup(self, state):
        self._teardown()
        return super().on_cleanup(state)

    def on_shutdown(self, state):
        self._teardown()
        return super().on_shutdown(state)

    # ---- registry keep-alive ----------------------------------------------
    def _keepalive_register(self) -> None:
        if self._reg_client is not None and self._reg_client.service_is_ready():
            self._register_async()

    # ---- ingest loop -------------------------------------------------------
    def _poll(self) -> None:
        pod_ip = self.get_parameter('pod_ip').value
        limit = int(self.get_parameter('max_msgs_per_s').value)
        for _ in range(MAX_DATAGRAMS_PER_TICK):
            try:
                raw, (src_ip, _src_port) = self._sock.recvfrom(MAX_DATAGRAM_BYTES)
            except BlockingIOError:
                return
            if pod_ip and src_ip != pod_ip:
                self._drop('source')
                continue
            now_s = self.get_clock().now().nanoseconds * 1e-9
            self._rate_window, allowed = ingest.rate_allow(
                self._rate_window, now_s, limit)
            if not allowed:
                self._drop('rate')
                continue
            sample = ingest.parse_datagram(raw)
            if sample is None:
                self._drop('parse')
                continue
            self._publish(sample)

    # ---- publishing (stamped on arrival, Pi clock) --------------------------
    def _publish(self, sample: ingest.EnvSample) -> None:
        stamp = self.get_clock().now().to_msg()

        temp = Temperature()
        temp.header.stamp = stamp
        temp.header.frame_id = FRAME_ID
        temp.temperature = sample.temp_c
        temp.variance = 0.0
        self._temp_pub.publish(temp)

        rh = RelativeHumidity()
        rh.header.stamp = stamp
        rh.header.frame_id = FRAME_ID
        rh.relative_humidity = sample.rh_pct / 100.0   # msg convention: 0.0-1.0
        rh.variance = 0.0
        self._rh_pub.publish(rh)

        press = FluidPressure()
        press.header.stamp = stamp
        press.header.frame_id = FRAME_ID
        press.fluid_pressure = sample.press_pa
        press.variance = 0.0
        self._press_pub.publish(press)

        lux = Illuminance()
        lux.header.stamp = stamp
        lux.header.frame_id = FRAME_ID
        lux.illuminance = sample.lux
        lux.variance = 0.0
        self._lux_pub.publish(lux)

        presence = Bool()
        presence.data = sample.human
        self._presence_pub.publish(presence)

        self._last_sample_ns = self.get_clock().now().nanoseconds

    # ---- socket plumbing ----------------------------------------------------
    def _drain_stale_datagrams(self) -> None:
        # Packets that queued while inactive are stale by definition.
        while True:
            try:
                self._sock.recvfrom(MAX_DATAGRAM_BYTES)
            except (BlockingIOError, OSError):
                return

    def _drop(self, reason: str) -> None:
        # Count drops, never log raw payloads (unbounded attacker-controlled data).
        self._drop_counts = {**self._drop_counts,
                             reason: self._drop_counts[reason] + 1}
        self.get_logger().warning(
            f'dropping {reason} (total {self._drop_counts[reason]})',
            throttle_duration_sec=10.0)

    def _teardown(self) -> None:
        for attr in ('_poll_timer', '_reregister_timer'):
            timer = getattr(self, attr)
            if timer is not None:
                self.destroy_timer(timer)
                setattr(self, attr, None)
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


def main(args=None):
    rclpy.init(args=args)
    spin_agent(EnvpodBridge())


if __name__ == '__main__':
    main()
