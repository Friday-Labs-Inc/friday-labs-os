"""Unit tests for the pure split-brain authority-transition logic (no ROS)."""

from friday_module_agent import authority


# ---- should_failover: BOTH signals required ------------------------------
def test_failover_requires_both_signals():
    assert authority.should_failover(lease_expired=True, pulse_lost=True)


def test_no_failover_on_lease_expiry_alone():
    # a stuck renewer with a healthy safety pulse must NOT trigger failover
    assert not authority.should_failover(lease_expired=True, pulse_lost=False)


def test_no_failover_on_pulse_loss_alone():
    # a dropped pulse with a still-renewing lease must NOT trigger failover
    assert not authority.should_failover(lease_expired=False, pulse_lost=True)


def test_no_failover_when_core_healthy():
    assert not authority.should_failover(lease_expired=False, pulse_lost=False)


# ---- accept_lease: epoch-monotonic (the S3 keystone) ---------------------
def test_higher_epoch_accepted():
    # failover / clean hand-back acquires at a higher epoch
    assert authority.accept_lease(incoming_epoch=2, current_epoch=1)


def test_same_epoch_accepted():
    # the holder's own renewals stay at one epoch and must keep being honoured
    assert authority.accept_lease(incoming_epoch=1, current_epoch=1)


def test_stale_lower_epoch_rejected():
    # a rejoining Core's stale epoch-1 lease is ignored after Telemetry took epoch 2
    assert not authority.accept_lease(incoming_epoch=1, current_epoch=2)


# ---- may_grant_return: not-behind AND stable -----------------------------
def test_grant_when_stable_and_caught_up():
    assert authority.may_grant_return(requester_epoch=2, holder_epoch=2, stable=True)


def test_grant_when_requester_ahead():
    assert authority.may_grant_return(requester_epoch=3, holder_epoch=2, stable=True)


def test_reject_behind_requester():
    # a requester whose epoch is behind must re-observe before it can take over
    assert not authority.may_grant_return(requester_epoch=1, holder_epoch=2, stable=True)


def test_reject_when_unstable():
    # never hand authority back mid-motion / mid-fault, even if caught up
    assert not authority.may_grant_return(requester_epoch=2, holder_epoch=2, stable=False)


# ---- starved: self-starvation voids liveness evidence --------------------
def test_on_schedule_check_not_starved():
    assert not authority.starved(gap_s=0.1, period_s=0.1)


def test_small_jitter_not_starved():
    assert not authority.starved(gap_s=0.3, period_s=0.1)


def test_long_stall_is_starved():
    # a 0.5 s+ gap on a 0.1 s check: the process was not being scheduled, so
    # "Core silent" evidence gathered across the gap must be discarded
    assert authority.starved(gap_s=0.5, period_s=0.1)


def test_first_check_gap_zero_not_starved():
    assert not authority.starved(gap_s=0.0, period_s=0.1)
