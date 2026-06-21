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

import json
import queue
import time

import cbor2
import rclpy
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from rclpy.executors import MultiThreadedExecutor

from friday_msgs.msg import FaultReport, MotionCommand
from friday_module_agent import qos
from friday_module_agent.module_agent import ModuleAgent

from friday_telemetry import protocol
from friday_telemetry.transport import MqttTransport

LOCOMOTION_CMD_TOPIC = '/mark1/locomotion/cmd_motion'
FAULT_TOPIC = '/mark1/telemetry/fault'


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

        self._rover_id = self.get_parameter('rover_id').value
        self._inbound = queue.Queue()
        self._transport = None
        self._validator = None
        self._motion_pub = None
        self._fault_pub = None
        self._drain_timer = None

    # ---- ModuleAgent hooks -------------------------------------------------
    def configure_hardware(self) -> None:
        self._motion_pub = self.create_lifecycle_publisher(
            MotionCommand, LOCOMOTION_CMD_TOPIC, qos.critical_reliable())
        self._fault_pub = self.create_lifecycle_publisher(
            FaultReport, FAULT_TOPIC, qos.state_default())
        self._validator = protocol.CommandValidator(
            rover_id=self._rover_id,
            operator_keys=self._load_operator_allowlist(),
            now=time.time)
        self._transport = MqttTransport(
            host=self.get_parameter('mqtt_host').value,
            port=int(self.get_parameter('mqtt_port').value),
            client_id=f'{self._module_id}-bridge')

    def activate_hardware(self) -> None:
        try:
            self._transport.connect()
            self._transport.subscribe(f'mark1/{self._rover_id}/cmd/+', self._on_cc_message)
        except Exception as exc:  # noqa: BLE001 - link down must not crash the node
            self.get_logger().error(f'Command Center link failed: {exc}')
        self._drain_timer = self.create_timer(0.02, self._drain_inbound)
        self.get_logger().info(
            f'Command Center boundary up for rover {self._rover_id} '
            f'(operators allowlisted: {len(self._validator._keys)})')

    def enter_safe_state(self) -> None:
        if self._drain_timer is not None:
            self.destroy_timer(self._drain_timer)
            self._drain_timer = None
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
        # authority provenance from the validated envelope (enforced internally in Phase 4)
        cmd.source = envelope.get('sender_id', '')
        cmd.nonce = int(envelope.get('nonce', 0))
        cmd.expires_at = self.get_clock().now().to_msg()
        self._motion_pub.publish(cmd)
        self.get_logger().info(
            f'ACCEPTED motion from {cmd.source} (nonce {cmd.nonce}) '
            f'-> v={cmd.linear_velocity:.2f} w={cmd.angular_velocity:.2f}')

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
        body = cbor2.dumps({'msg_id': msg_id, 'accepted': accepted, 'category': category})
        self._transport.publish(f'mark1/{self._rover_id}/ack/{msg_id}', body)

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
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
