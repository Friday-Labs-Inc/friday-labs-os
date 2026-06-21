"""Unit tests for the pure authority-enforcement logic (no ROS runtime)."""

from friday_locomotion import safety

HOLDER = 'MARK1-CORE-001'


def _auth(**over):
    base = dict(source=HOLDER, nonce=5, cmd_expires_s=2000.0, holder=HOLDER,
                lease_expires_s=1010.0, last_nonce=4, now_s=1000.0,
                in_safe_state=False)
    base.update(over)
    return safety.authorize(**base)


def test_valid_command_accepted():
    assert _auth().accepted and _auth().reason == safety.ACCEPT


def test_wrong_source_rejected():
    assert _auth(source='ATTACKER').reason == safety.WRONG_SOURCE


def test_no_authority_when_lease_expired():
    assert _auth(now_s=1020.0).reason == safety.NO_AUTHORITY  # past lease_expires 1010


def test_no_authority_when_no_holder():
    assert _auth(holder='').reason == safety.NO_AUTHORITY


def test_replayed_nonce_rejected():
    assert _auth(nonce=4).reason == safety.REPLAY      # equal to last
    assert _auth(nonce=3).reason == safety.REPLAY      # below last


def test_first_command_accepted_when_no_last_nonce():
    assert _auth(last_nonce=None).accepted


def test_expired_command_rejected():
    assert _auth(cmd_expires_s=999.0).reason == safety.EXPIRED


def test_unset_command_expiry_skips_check():
    assert _auth(cmd_expires_s=0).accepted


def test_safe_state_rejects_everything():
    assert _auth(in_safe_state=True).reason == safety.SAFE_STATE


def test_safe_state_takes_priority_over_valid_command():
    # even a perfectly valid command is refused while safe-stopped
    assert not _auth(in_safe_state=True).accepted
