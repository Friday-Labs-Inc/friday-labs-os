"""Cross-repo wire-contract golden vector — the drift guard for the signed envelope.

`protocol.py` (this repo) and the Command Center's `bridge/envelope.py` (the
`friday-command-center` repo) are two HAND-MAINTAINED copies of the same signing
contract. One edit to `_signing_bytes` (the key set, `canonical=True`, or a field's
CBOR type) on either side silently breaks every signature in production.

This test pins a deterministic golden vector — a fixed key + a fully-specified
envelope → the exact `_signing_bytes` and Ed25519 signature it must produce. The
FCC repo asserts the SAME two constants against its own implementation
(`bridge/tests/test_envelope_golden.py`). If either side drifts, that side's CI
goes red before it ships. Ed25519 (RFC 8032) is deterministic, so the signature is
a stable constant.

DO NOT regenerate these constants to "fix" a failure — a failure means the contract
changed and BOTH repos (and the protocol_version) must be updated together.
The seed is a non-secret test fixture; it must never be used in production.
"""

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol

# Fixed, non-secret test key — shared verbatim with the FCC golden test.
SEED_HEX = '0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20'

# Fully-specified envelope inputs — no time.time(), no randomness.
GOLDEN = dict(
    rover_id='MARK1-001',
    sender_id='OP-001',
    msg_id=42,
    nonce=42,
    issued_at=1_000_000.0,                       # float (CBOR float64) — NOT int
    expires_at=1_000_030.0,                       # issued_at + DEFAULT_EXPIRY_S (30.0)
    payload={'class': 'motion', 'linear_velocity': 0.5, 'angular_velocity': 0.0},
)

# The pinned contract. Identical strings MUST appear in the FCC golden test.
SIGNING_BYTES_HEX = (
    'a8656e6f6e6365182a666d73675f6964182a677061796c6f6164a365636c617373666d6f74696f'
    '6e6f6c696e6561725f76656c6f63697479f9380070616e67756c61725f76656c6f63697479f900'
    '0068726f7665725f6964694d41524b312d303031696973737565645f6174fa49742400697365'
    '6e6465725f6964664f502d3030316a657870697265735f6174fa497425e07070726f746f636f6c'
    '5f76657273696f6ea3656d616a6f7200656d696e6f720165706174636800')
SIGNATURE_HEX = (
    'a978d78333e25d43f7b9678f8c9e88eb04412671a04fb9f51a7475ff52befaa6'
    '560d8c21c8dbb6e7241da3b5559b36b40bfb3310e15580cf81e476de6c8e5609')


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SEED_HEX))


def test_protocol_version_matches_golden():
    # The golden vector is valid only for this contract version. A bump here MUST
    # be coordinated with the FCC and a re-pinned vector.
    assert (protocol.PROTOCOL_MAJOR, protocol.PROTOCOL_MINOR, protocol.PROTOCOL_PATCH) == (0, 1, 0)
    assert protocol.DEFAULT_EXPIRY_S == 30.0


def test_signing_bytes_match_golden():
    envelope = protocol.build_envelope(private_key=_priv(), **GOLDEN)
    assert protocol._signing_bytes(envelope).hex() == SIGNING_BYTES_HEX, (
        '_signing_bytes drifted — protocol.py and the FCC bridge/envelope.py are no '
        'longer byte-identical (key set, canonical flag, or a CBOR field type changed).')


def test_signature_matches_golden():
    envelope = protocol.build_envelope(private_key=_priv(), **GOLDEN)
    # Ed25519 is deterministic: same key + same message -> same 64-byte signature.
    assert envelope['signature'].hex() == SIGNATURE_HEX, (
        'signature drifted — the signed bytes or the key path changed.')


def test_golden_signature_verifies():
    # Sanity: the pinned signature genuinely covers the pinned signing bytes.
    _priv().public_key().verify(bytes.fromhex(SIGNATURE_HEX), bytes.fromhex(SIGNING_BYTES_HEX))


def test_signing_bytes_excludes_signature_only():
    # Pin the exact signed key set: every envelope key EXCEPT 'signature'.
    envelope = protocol.build_envelope(private_key=_priv(), **GOLDEN)
    signed_keys = set(cbor2.loads(protocol._signing_bytes(envelope)).keys())
    assert signed_keys == set(envelope.keys()) - {'signature'}
