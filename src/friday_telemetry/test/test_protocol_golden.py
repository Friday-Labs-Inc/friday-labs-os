"""Cross-repo wire-contract golden vector — the drift guard for the signed envelope.

`protocol.py` (this repo) and the Command Center's `bridge/envelope.py` (the
`friday-command-center` repo) are two HAND-MAINTAINED copies of the same signing
contract. One edit to `_signing_bytes` (the key set, `canonical=True`, or a field's
CBOR type) on either side silently breaks every signature in production.

This test pins a deterministic golden vector — a fixed key + a fully-specified
envelope → the exact `_signing_bytes` and Ed25519 signature it must produce. The
FCC repo asserts the SAME two constants against its own implementation
(`bridge/tests/test_golden_vector.py`). If either side drifts, that side's CI goes
red before it ships. Ed25519 (RFC 8032) is deterministic, so the signature is a
stable constant.

This vector encodes the LOCKED v0.1.0 contract (see
docs/software/command-center-boundary.md): int64 epoch-ms timestamps and an
opaque-bstr payload. The inner payload bytes contain float16 (`f93800`/`f9b400`) —
that is irrelevant to interop BECAUSE the payload is signed as opaque bytes; only
the outer map must canonicalize identically across JS/Python/C++.

DO NOT regenerate these constants to "fix" a failure — a failure means the contract
changed and BOTH repos (and the protocol_version) must be updated together.
The seed is a non-secret test fixture; it must never be used in production.
"""

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol

# Fixed, non-secret test key (operator) — shared verbatim with the FCC golden test.
SEED_HEX = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'

# The payload is serialized ONCE by the producer and signed as an opaque bstr.
# These bytes are an INPUT to the vector — the verifier never re-encodes them.
# Inner object: {"class": "motion", "v": 0.5, "w": -0.25}
PAYLOAD_BSTR = bytes.fromhex('a36176f938006177f9b40065636c617373666d6f74696f6e')

# Fully-specified envelope inputs — no time.time(), no randomness.
GOLDEN = dict(
    rover_id='MARK1-001',
    sender_id='operator@fcc',
    msg_id='msg-0001',
    nonce=1,
    issued_at=1782777600000,                      # int64 epoch-ms UTC — NOT float
    expires_at=1782777630000,                     # issued_at + 30_000 ms (DEFAULT_EXPIRY_MS)
    payload=PAYLOAD_BSTR,
)

# The pinned contract. Identical strings MUST appear in the FCC golden test.
SIGNING_BYTES_HEX = (
    'a8656e6f6e636501666d73675f6964686d73672d30303031677061796c6f61645818a36176f93800'
    '6177f9b40065636c617373666d6f74696f6e68726f7665725f6964694d41524b312d303031696973'
    '737565645f61741b0000019f15d358006973656e6465725f69646c6f70657261746f72406663636a'
    '657870697265735f61741b0000019f15d3cd307070726f746f636f6c5f76657273696f6ea3656d61'
    '6a6f7200656d696e6f720165706174636800')
SIGNATURE_HEX = (
    '81fc9c18505c1ebf645afeab532982715a72e0dbb5c7851fccc75aa08bbcfa04'
    'a6ce763dd934750f284768e976aa61a5ff394a1e52ba2600be2eaed9bb21ab0b')


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SEED_HEX))


def test_protocol_version_matches_golden():
    # The golden vector is valid only for this contract version. A bump here MUST
    # be coordinated with the FCC and a re-pinned vector.
    assert (protocol.PROTOCOL_MAJOR, protocol.PROTOCOL_MINOR, protocol.PROTOCOL_PATCH) == (0, 1, 0)
    assert protocol.DEFAULT_EXPIRY_MS == 30_000
    assert protocol.SKEW_MS == 5_000


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


def test_payload_signed_as_opaque_bstr():
    # The payload must survive as bytes through the signed map — never re-encoded as
    # a CBOR map (which would drag inner floats onto the signature path).
    envelope = protocol.build_envelope(private_key=_priv(), **GOLDEN)
    decoded = cbor2.loads(protocol._signing_bytes(envelope))
    assert decoded['payload'] == PAYLOAD_BSTR
    assert isinstance(decoded['payload'], (bytes, bytearray))


def test_signing_bytes_excludes_signature_only():
    # Pin the exact signed key set: every envelope key EXCEPT 'signature'.
    envelope = protocol.build_envelope(private_key=_priv(), **GOLDEN)
    signed_keys = set(cbor2.loads(protocol._signing_bytes(envelope)).keys())
    assert signed_keys == set(envelope.keys()) - {'signature'}
