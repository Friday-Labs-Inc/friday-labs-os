"""Command Center protocol envelope — signing, encoding, and validation.

Implements docs/addendums/Command Center Protocol Security.md: every command
crossing the external boundary is an Ed25519-signed, CBOR-encoded envelope with a
monotonic nonce and an expiry. This module is pure (no ROS, no MQTT) so the
security logic is fully unit-testable.

A command is accepted only if ALL hold: protocol major matches, rover_id matches,
sender is allowlisted, signature verifies, not expired, nonce strictly increases.
Anything else is rejected with a category — never executed, never queued.
"""

from __future__ import annotations

from dataclasses import dataclass

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from friday_module_agent.nonce_store import NonceStore

# friday_msgs contract version this boundary speaks (packed semver).
PROTOCOL_MAJOR = 0
PROTOCOL_MINOR = 1
PROTOCOL_PATCH = 0

# Freshness window + clock-skew tolerance, in MILLISECONDS (the wire timestamps are
# int64 epoch-ms). A field rover's clock drifts with no guaranteed time sync, so the
# nonce floor is the HARD replay guarantee and the timestamp is a soft freshness gate
# with ±SKEW_MS tolerance on both ends of [issued_at, expires_at].
DEFAULT_EXPIRY_MS = 30_000
SKEW_MS = 5_000

# Rejection categories (mirror friday_msgs/FaultReport CATEGORY_* + outcomes).
OK = "OK"
PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"
ROVER_MISMATCH = "ROVER_MISMATCH"
UNKNOWN_SENDER = "UNKNOWN_SENDER"
SECURITY_AUTH = "SECURITY_AUTH"          # bad/forged signature
EXPIRED = "EXPIRED"
SECURITY_REPLAY = "SECURITY_REPLAY"      # nonce <= last seen


@dataclass(frozen=True)
class Validation:
    accepted: bool
    category: str
    reason: str
    envelope: dict | None = None         # the decoded envelope when accepted


def _signing_bytes(envelope: dict) -> bytes:
    """Canonical bytes that the signature covers: the envelope minus `signature`.

    Binds payload, nonce, rover_id, expiry AND sender_id / msg_id / issued_at /
    protocol_version — a superset of the spec's minimum, so nothing signed can be
    swapped. Canonical CBOR (RFC 8949 §4.2) makes the encoding deterministic on both
    sides.

    `payload` is carried as an opaque CBOR byte-string (bstr): the producer
    serializes it ONCE and those exact bytes are signed — never decoded-then-
    re-encoded. That keeps floats inside the payload (a pose, a velocity setpoint)
    off the signature path, where different CBOR libraries would otherwise shrink
    them to different widths and break the seal across the JS/Python/C++ boundary.
    Only the outer map (ints + text strings + the nested protocol_version int map +
    the payload bstr) has to canonicalize identically everywhere.
    """
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    return cbor2.dumps(unsigned, canonical=True)


def build_envelope(*, rover_id, sender_id, msg_id, nonce, issued_at, expires_at,
                   payload, private_key: Ed25519PrivateKey) -> dict:
    """Build and sign a command/telemetry envelope (operator side).

    `payload` MUST be pre-serialized bytes (an opaque CBOR bstr) — passing a dict
    would let it be re-encoded on each side, reintroducing the cross-language float
    drift the bstr design exists to prevent. `issued_at`/`expires_at` MUST be int64
    epoch-ms; a float would canonicalize to a non-portable width.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError(
            "payload must be pre-serialized bytes (opaque CBOR bstr), not "
            f"{type(payload).__name__} — re-encoding it breaks cross-language signatures")
    if not (isinstance(issued_at, int) and isinstance(expires_at, int)):
        raise TypeError("issued_at/expires_at must be int64 epoch-ms, not float")
    envelope = {
        "protocol_version": {
            "major": PROTOCOL_MAJOR, "minor": PROTOCOL_MINOR, "patch": PROTOCOL_PATCH,
        },
        "rover_id": rover_id,
        "sender_id": sender_id,
        "msg_id": msg_id,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "payload": payload,
    }
    envelope["signature"] = private_key.sign(_signing_bytes(envelope))
    return envelope


def sign_telemetry(*, rover_id, msg_id, nonce, issued_at, expires_at, payload,
                   private_key: Ed25519PrivateKey) -> dict:
    """Sign a ROVER-ORIGINATED telemetry envelope (odom / fault / ack).

    Same wire envelope as a command, but the rover is the sender (sender_id =
    rover_id) and it signs with the rover's own key. The Command Center verifies
    it against the rover's registered public key, so spoofed telemetry (a faked
    position, an absent fault) is rejected. Identical signing path as
    build_envelope, so the wire-contract golden vector covers it."""
    return build_envelope(
        rover_id=rover_id, sender_id=rover_id, msg_id=msg_id, nonce=nonce,
        issued_at=issued_at, expires_at=expires_at, payload=payload,
        private_key=private_key)


def encode(envelope: dict) -> bytes:
    """Serialize an envelope to wire bytes (CBOR)."""
    return cbor2.dumps(envelope)


def decode(raw: bytes) -> dict:
    """Deserialize wire bytes to an envelope dict."""
    return cbor2.loads(raw)


class CommandValidator:
    """Validates inbound command envelopes against the allowlist + replay state.

    `operator_keys` maps sender_id -> Ed25519PublicKey (the rover's allowlist).
    `now` is a callable returning the current unix time in MILLISECONDS (injected
    for tests), matching the int64 epoch-ms wire timestamps.
    """

    def __init__(self, rover_id: str, operator_keys: dict, now, nonce_store=None):
        self._rover_id = rover_id
        self._keys = dict(operator_keys)
        self._now = now
        # Durable per-sender nonce floor (survives a restart). In-memory if no path.
        self._nonces = nonce_store if nonce_store is not None else NonceStore()

    def validate(self, envelope: dict) -> Validation:
        pv = envelope.get("protocol_version", {})
        # Pre-1.0, minor is breaking: require exact (major, minor).
        if (pv.get("major"), pv.get("minor")) != (PROTOCOL_MAJOR, PROTOCOL_MINOR):
            return Validation(False, PROTOCOL_MISMATCH,
                              f"protocol {pv.get('major')}.{pv.get('minor')} != "
                              f"{PROTOCOL_MAJOR}.{PROTOCOL_MINOR} (pre-1.0: minor is breaking)")
        if envelope.get("rover_id") != self._rover_id:
            return Validation(False, ROVER_MISMATCH,
                              f"rover_id {envelope.get('rover_id')} != {self._rover_id}")
        sender = envelope.get("sender_id")
        key = self._keys.get(sender)
        if key is None:
            return Validation(False, UNKNOWN_SENDER, f"operator '{sender}' not allowlisted")
        try:
            key.verify(envelope["signature"], _signing_bytes(envelope))
        except (InvalidSignature, KeyError, TypeError):
            return Validation(False, SECURITY_AUTH, "signature invalid")
        now_ms = self._now()
        if not (envelope.get("issued_at", 0) - SKEW_MS
                <= now_ms <= envelope.get("expires_at", 0) + SKEW_MS):
            return Validation(False, EXPIRED,
                              "outside freshness window [issued_at-5s, expires_at+5s]")
        nonce = envelope.get("nonce")
        last = self._nonces.last(sender)
        if last is not None and nonce <= last:
            return Validation(False, SECURITY_REPLAY,
                              f"nonce {nonce} <= last {last} for '{sender}'")
        # Accept: commit the nonce only now (a rejected command must not advance it).
        self._nonces.commit(sender, nonce)
        return Validation(True, OK, "accepted", envelope)
