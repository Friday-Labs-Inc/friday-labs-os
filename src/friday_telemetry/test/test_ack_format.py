"""ACK wire-format coverage for both arms of TelemetryAgent._build_ack_body.

Pins the contract the Command Center's ack consumer relies on: a plain flat CBOR
dict when the rover holds no key, and a signed envelope (verifiable, payload
class 'ack') when it does. The plain arm is the silent-regression risk flagged by
the security review, so both arms are asserted here.
"""

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol
from friday_telemetry.telemetry_agent_node import TelemetryAgent

ACK = {'msg_id': 1, 'accepted': True, 'category': 'OK'}


def test_plain_ack_is_flat_cbor_when_no_key():
    body = TelemetryAgent._build_ack_body(ACK, None, 'MARK1-001', 0)
    msg = cbor2.loads(body)
    assert msg == ACK                                 # flat dict, no envelope/signature
    assert 'signature' not in msg


def test_signed_ack_is_a_verifiable_envelope():
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex('11' * 32))
    body = TelemetryAgent._build_ack_body(ACK, key, 'MARK1-001', 5)
    env = cbor2.loads(body)
    assert env['sender_id'] == 'MARK1-001' and 'signature' in env
    assert env['payload'] == {'class': 'ack', **ACK}
    key.public_key().verify(env['signature'], protocol._signing_bytes(env))   # raises if bad
