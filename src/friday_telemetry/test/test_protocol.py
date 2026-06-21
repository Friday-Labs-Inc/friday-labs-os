"""Security acceptance tests for the Command Center envelope (no ROS, no MQTT).

Mirrors docs/addendums/Command Center Protocol Security.md acceptance criteria:
forged signature, replay, wrong-rover, expired, unknown operator all rejected.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol

ROVER = 'MARK1-001'
OP = 'OP-001'


def _keypair():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def _env(priv, nonce=1, rover=ROVER, sender=OP, expires=1030.0, payload=None):
    return protocol.build_envelope(
        rover_id=rover, sender_id=sender, msg_id=nonce, nonce=nonce,
        issued_at=1000.0, expires_at=expires,
        payload=payload or {'class': 'motion', 'type': 1,
                            'linear_velocity': 0.5, 'angular_velocity': 0.3},
        private_key=priv)


def _validator(pub, now=1010.0):
    return protocol.CommandValidator(ROVER, {OP: pub}, lambda: now)


def test_valid_accepted():
    priv, pub = _keypair()
    r = _validator(pub).validate(_env(priv, nonce=1))
    assert r.accepted and r.category == protocol.OK


def test_forged_signature_rejected():
    priv, pub = _keypair()
    env = _env(priv, nonce=1)
    env['payload'] = {**env['payload'], 'linear_velocity': 99.0}  # tamper after signing
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
    r = _validator(pub, now=2000.0).validate(_env(priv, nonce=1))
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


def test_rejected_command_does_not_advance_nonce():
    priv, pub = _keypair()
    v = _validator(pub)
    forged = _env(priv, nonce=10)
    forged['payload'] = {**forged['payload'], 'tamper': 1}
    assert not v.validate(forged).accepted          # rejected, must not consume nonce 10
    assert v.validate(_env(priv, nonce=10)).accepted  # a real command at 10 still works
