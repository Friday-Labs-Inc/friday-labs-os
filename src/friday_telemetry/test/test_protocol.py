"""Security acceptance tests for the Command Center envelope (no ROS, no MQTT).

Mirrors docs/addendums/Command Center Protocol Security.md acceptance criteria:
forged signature, replay, wrong-rover, expired, unknown operator all rejected.
"""

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol

ROVER = 'MARK1-001'
OP = 'OP-001'

# All wire timestamps are int64 epoch-ms.
ISSUED_MS = 1_000_000
EXPIRES_MS = ISSUED_MS + protocol.DEFAULT_EXPIRY_MS    # 1_030_000
NOW_MS = 1_010_000                                     # inside the freshness window


def _keypair():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def _payload():
    # The payload travels and is signed as an opaque bstr — serialized once.
    return cbor2.dumps({'class': 'motion', 'type': 1,
                        'linear_velocity': 0.5, 'angular_velocity': 0.3}, canonical=True)


def _env(priv, nonce=1, rover=ROVER, sender=OP, expires=EXPIRES_MS, payload=None):
    return protocol.build_envelope(
        rover_id=rover, sender_id=sender, msg_id=nonce, nonce=nonce,
        issued_at=ISSUED_MS, expires_at=expires,
        payload=payload if payload is not None else _payload(),
        private_key=priv)


def _validator(pub, now=NOW_MS):
    return protocol.CommandValidator(ROVER, {OP: pub}, lambda: now)


def test_valid_accepted():
    priv, pub = _keypair()
    r = _validator(pub).validate(_env(priv, nonce=1))
    assert r.accepted and r.category == protocol.OK


def test_forged_signature_rejected():
    priv, pub = _keypair()
    env = _env(priv, nonce=1)
    env['payload'] = env['payload'] + b'\x00'        # tamper the bstr after signing
    r = _validator(pub).validate(env)
    assert not r.accepted and r.category == protocol.SECURITY_AUTH


def test_replay_same_nonce_rejected():
    priv, pub = _keypair()
    v = _validator(pub)
    assert v.validate(_env(priv, nonce=5)).accepted
    r = v.validate(_env(priv, nonce=5))
    assert not r.accepted and r.category == protocol.SECURITY_REPLAY


def test_older_nonce_rejected():
    priv, pub = _keypair()
    v = _validator(pub)
    assert v.validate(_env(priv, nonce=5)).accepted
    assert v.validate(_env(priv, nonce=4)).category == protocol.SECURITY_REPLAY


def test_expired_rejected():
    priv, pub = _keypair()
    r = _validator(pub, now=2_000_000).validate(_env(priv, nonce=1))
    assert not r.accepted and r.category == protocol.EXPIRED


def test_wrong_rover_rejected():
    priv, pub = _keypair()
    r = _validator(pub).validate(_env(priv, nonce=1, rover='MARK1-999'))
    assert not r.accepted and r.category == protocol.ROVER_MISMATCH


def test_unknown_sender_rejected():
    priv, pub = _keypair()
    evil, _ = _keypair()
    r = _validator(pub).validate(_env(evil, nonce=1, sender='OP-EVIL'))
    assert not r.accepted and r.category == protocol.UNKNOWN_SENDER


def test_protocol_major_mismatch_rejected():
    priv, pub = _keypair()
    env = _env(priv, nonce=1)
    env['protocol_version'] = {'major': 9, 'minor': 0, 'patch': 0}
    r = _validator(pub).validate(env)
    assert not r.accepted and r.category == protocol.PROTOCOL_MISMATCH


def test_protocol_minor_mismatch_rejected():
    # Pre-1.0, a minor bump is breaking: same major, different minor -> rejected.
    priv, pub = _keypair()
    env = _env(priv, nonce=1)
    env['protocol_version'] = {'major': protocol.PROTOCOL_MAJOR,
                               'minor': protocol.PROTOCOL_MINOR + 1, 'patch': 0}
    r = _validator(pub).validate(env)
    assert not r.accepted and r.category == protocol.PROTOCOL_MISMATCH


def test_rejected_command_does_not_advance_nonce():
    priv, pub = _keypair()
    v = _validator(pub)
    forged = _env(priv, nonce=10)
    forged['payload'] = forged['payload'] + b'\x00'  # tamper the bstr
    assert not v.validate(forged).accepted          # rejected, must not consume nonce 10
    assert v.validate(_env(priv, nonce=10)).accepted  # a real command at 10 still works
