"""Unit tests for rover-originated telemetry signing (protocol.sign_telemetry).

The rover signs its outbound odom/fault/ack so the Command Center can prove the
data came from THIS rover. These tests pin the contract: the sender is the rover,
a genuine signature verifies, and any tamper fails — independent of ROS/MQTT.
"""

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol

ROVER = 'MARK1-001'


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex('11' * 32))


def _sign(payload: dict) -> dict:
    now = 1_000_000.0
    return protocol.sign_telemetry(
        rover_id=ROVER, msg_id=7, nonce=7, issued_at=now, expires_at=now + 30.0,
        payload=payload, private_key=_key())


def test_sender_is_the_rover_itself():
    env = _sign({'class': 'odom', 'x': 1.0})
    assert env['sender_id'] == ROVER          # rover-originated, not an operator
    assert env['rover_id'] == ROVER


def test_signature_verifies_with_rover_pubkey():
    env = _sign({'class': 'fault', 'severity': 2})
    _key().public_key().verify(env['signature'], protocol._signing_bytes(env))   # raises if bad


def test_tampered_payload_fails_verification():
    env = _sign({'class': 'odom', 'x': 1.0})
    env['payload']['x'] = 9.0                 # spoof the position after signing
    try:
        _key().public_key().verify(env['signature'], protocol._signing_bytes(env))
        raise AssertionError('tampered telemetry must not verify')
    except InvalidSignature:
        pass


def test_telemetry_envelope_round_trips_on_the_wire():
    env = _sign({'class': 'ack', 'msg_id': 3, 'accepted': True, 'category': 'OK'})
    decoded = protocol.decode(protocol.encode(env))
    assert decoded['payload']['class'] == 'ack'
    _key().public_key().verify(decoded['signature'], protocol._signing_bytes(decoded))
