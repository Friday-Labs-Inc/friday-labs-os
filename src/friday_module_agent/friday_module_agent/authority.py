"""Pure split-brain authority-transition logic (no ROS).

Three decisions, extracted from the Authority Lease Protocol so they are
unit-testable without a robot (mirrors friday_locomotion.safety):

  * should_failover(lease_expired, pulse_lost) — Telemetry self-promotes ONLY
    when BOTH of Core's independent liveness signals have failed. A stuck
    renewer with a healthy pulse (or vice-versa) does NOT trigger failover.

  * accept_lease(incoming_epoch, current_epoch) — a lease consumer honours a
    lease only if its epoch is not behind the highest epoch it has already seen.
    After a failover bumps the epoch, a stale lower-epoch lease from a rejoining
    Core is rejected. This is the keystone that makes a dual-command partition
    (scenario S3) impossible *at the consumer*, independent of who is publishing.

  * may_grant_return(requester_epoch, holder_epoch, stable) — the holder grants a
    RequestAuthority only to a requester that is not behind (epoch >= holder's)
    AND only while the rover is stable (no motion, no active fault). Resolves the
    addendum's open item on a last_known_epoch mismatch: grant if the requester's
    epoch is >= the holder's, reject otherwise.
"""


def should_failover(*, lease_expired: bool, pulse_lost: bool) -> bool:
    """Self-promote only when BOTH of Core's independent signals have failed."""
    return lease_expired and pulse_lost


def accept_lease(*, incoming_epoch: int, current_epoch: int) -> bool:
    """Honour a lease only if its epoch is not behind what the consumer has seen.

    `>=` (not `>`) so the current holder's own renewals at the same epoch keep
    being accepted; only a strictly-lower (stale) epoch is rejected.
    """
    return incoming_epoch >= current_epoch


def may_grant_return(*, requester_epoch: int, holder_epoch: int,
                     stable: bool) -> bool:
    """Grant a RequestAuthority only to a non-behind requester while stable.

    Never hand authority back mid-motion or mid-fault; never hand it to a node
    whose view of the epoch is behind the holder's (force it to re-observe first).
    """
    return stable and requester_epoch >= holder_epoch


STARVED_FACTOR = 5.0


def starved(*, gap_s: float, period_s: float,
            factor: float = STARVED_FACTOR) -> bool:
    """True when a periodic liveness check ran far later than scheduled.

    The check's own process was not being scheduled, so any "peer silent"
    evidence accumulated across the gap is void — the peer may have been
    talking the whole time. A starved Telemetry once declared a healthy Core
    lost and self-promoted, quarantining the fleet (2026-07-19).
    """
    return gap_s >= period_s * factor
