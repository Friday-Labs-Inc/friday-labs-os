"""The safety brain's pure decision logic -- no ROS, fully unit-testable.

Extracted from core_hub_node so the two most safety-critical judgments the
Core Hub makes are plain functions over plain values (NASA-style: the logic
a life may depend on must be testable without hardware, executors, or time):

  * classify_liveness -- OK / DEGRADED / DEAD / FAULT from heartbeat age and
    the module's own health verdict (a fresh OVERALL_FAULT outranks a live
    heartbeat: learned from the TX-cut incident where an intact wire kept a
    faulted board looking healthy).
  * supervisor_action -- which lifecycle transition (if any) the reconcile
    loop should send a managed node, including the latched-fault recovery
    (ACTIVE but DEAD/FAULT and reachable -> deactivate to clear the latch).

The node feeds these with measured ages and applies the results; every rule
and boundary here is pinned by test/test_decisions.py.
"""

from typing import NamedTuple, Optional

from lifecycle_msgs.msg import State as LCState
from lifecycle_msgs.msg import Transition

from friday_msgs.msg import HealthStatus

LIVENESS_OK = 'OK'
LIVENESS_DEGRADED = 'DEGRADED'
LIVENESS_DEAD = 'DEAD'
LIVENESS_FAULT = 'FAULT'   # the module itself reports OVERALL_FAULT (fresh)

DEGRADED_AGE_S = 1.0        # ~3 missed 200 ms heartbeats / 500 ms deadlines
DEAD_AGE_S = 1.5            # liveliness lease + margin
HEALTH_FAULT_FRESH_S = 2.5  # only honor a FAULT verdict while health still arrives


def classify_liveness(hb_age_s: float,
                      health_overall: Optional[int],
                      health_age_s: float) -> str:
    """Liveness verdict for one module.

    hb_age_s        seconds since the last heartbeat was received
    health_overall  the module's last HealthStatus.overall (None = never heard)
    health_age_s    seconds since that health report arrived
    """
    if hb_age_s > DEAD_AGE_S:
        verdict = LIVENESS_DEAD
    elif hb_age_s > DEGRADED_AGE_S:
        verdict = LIVENESS_DEGRADED
    else:
        verdict = LIVENESS_OK
    if (health_overall == HealthStatus.OVERALL_FAULT
            and health_age_s < HEALTH_FAULT_FRESH_S):
        # The module's own live verdict outranks a fresh heartbeat -- and a
        # stale FAULT ages out so a recovered module is not flapped back down.
        verdict = LIVENESS_FAULT
    return verdict


class SupervisorAction(NamedTuple):
    """What the reconcile loop should do with one managed node."""

    transition_id: Optional[int]   # ChangeState transition to send, or None
    recover: bool                  # True = clearing a latched fault (log loudly)


def supervisor_action(lifecycle_state_id: int, liveness: Optional[str]) -> SupervisorAction:
    """Next reconcile step for a REACHABLE node (its get_state answered).

    unconfigured -> configure (registration happens there)
    inactive     -> activate  (heartbeat starts there)
    active + DEAD/FAULT -> deactivate (latched-watchdog recovery: reachable
                   yet not heartbeating/faulted; the deactivate->activate
                   cycle clears the firmware latch)
    active otherwise, or mid-transition -> nothing
    """
    if lifecycle_state_id == LCState.PRIMARY_STATE_ACTIVE:
        if liveness in (LIVENESS_DEAD, LIVENESS_FAULT):
            return SupervisorAction(Transition.TRANSITION_DEACTIVATE, True)
        return SupervisorAction(None, False)
    if lifecycle_state_id == LCState.PRIMARY_STATE_UNCONFIGURED:
        return SupervisorAction(Transition.TRANSITION_CONFIGURE, False)
    if lifecycle_state_id == LCState.PRIMARY_STATE_INACTIVE:
        return SupervisorAction(Transition.TRANSITION_ACTIVATE, False)
    return SupervisorAction(None, False)   # finalized / mid-transition
