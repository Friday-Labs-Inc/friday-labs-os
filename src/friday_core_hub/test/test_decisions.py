"""Table-driven tests pinning the safety brain's decision logic.

Every threshold and rule in decisions.py exists because a real fault taught
it to us (wire-pulls, the TX-cut incident, the FAULT flap). These tables ARE
the requirements — change the logic, and the table tells you what you broke.
"""

import pytest
from lifecycle_msgs.msg import State as LCState
from lifecycle_msgs.msg import Transition

from friday_core_hub.decisions import (LIVENESS_DEAD, LIVENESS_DEGRADED,
                                       LIVENESS_FAULT, LIVENESS_OK,
                                       classify_liveness, supervisor_action)
from friday_msgs.msg import HealthStatus

OK = HealthStatus.OVERALL_OK
FAULT = HealthStatus.OVERALL_FAULT
DEGRADED = HealthStatus.OVERALL_DEGRADED
NEVER = 1e9   # "health never heard" -> enormous age


# ---- liveness classification: (hb_age, health, health_age) -> verdict ------
@pytest.mark.parametrize('hb_age, health, health_age, expect', [
    # heartbeat age alone
    (0.1,  OK,    0.1,  LIVENESS_OK),
    (1.0,  OK,    0.1,  LIVENESS_OK),          # boundary: 1.0 is still OK (>)
    (1.2,  OK,    0.1,  LIVENESS_DEGRADED),
    (1.5,  OK,    0.1,  LIVENESS_DEGRADED),    # boundary: 1.5 still DEGRADED (>)
    (1.6,  OK,    0.1,  LIVENESS_DEAD),
    (9999, OK,    0.1,  LIVENESS_DEAD),
    # the TX-cut rule: a FRESH self-reported FAULT outranks everything
    (0.1,  FAULT, 0.5,  LIVENESS_FAULT),       # live heartbeat, faulted anyway
    (1.2,  FAULT, 0.5,  LIVENESS_FAULT),
    (9999, FAULT, 0.5,  LIVENESS_FAULT),       # dead + fresh fault -> FAULT wins
    (0.1,  FAULT, 2.4,  LIVENESS_FAULT),       # boundary: just inside freshness
    # the anti-flap rule: a STALE fault ages out
    (0.1,  FAULT, 2.5,  LIVENESS_OK),          # boundary: 2.5 is stale (<)
    (0.1,  FAULT, 60.0, LIVENESS_OK),
    (9999, FAULT, 60.0, LIVENESS_DEAD),        # stale fault + dead hb -> DEAD
    # non-FAULT health never overrides
    (0.1,  DEGRADED, 0.1, LIVENESS_OK),
    (0.1,  OK,       0.1, LIVENESS_OK),
    (0.1,  None,     NEVER, LIVENESS_OK),      # health never heard
    (1.6,  None,     NEVER, LIVENESS_DEAD),
])
def test_classify_liveness(hb_age, health, health_age, expect):
    assert classify_liveness(hb_age, health, health_age) == expect


# ---- supervisor action: (lifecycle state, liveness) -> (transition, recover)
UNCONF = LCState.PRIMARY_STATE_UNCONFIGURED
INACTIVE = LCState.PRIMARY_STATE_INACTIVE
ACTIVE = LCState.PRIMARY_STATE_ACTIVE
FINALIZED = LCState.PRIMARY_STATE_FINALIZED
CONFIGURING = LCState.TRANSITION_STATE_CONFIGURING


@pytest.mark.parametrize('state, liveness, expect_tid, expect_recover', [
    # normal bring-up
    (UNCONF,   None,             Transition.TRANSITION_CONFIGURE,  False),
    (UNCONF,   LIVENESS_DEAD,    Transition.TRANSITION_CONFIGURE,  False),
    (INACTIVE, None,             Transition.TRANSITION_ACTIVATE,   False),
    (INACTIVE, LIVENESS_OK,      Transition.TRANSITION_ACTIVATE,   False),
    # healthy active: hands off
    (ACTIVE,   LIVENESS_OK,       None, False),
    (ACTIVE,   LIVENESS_DEGRADED, None, False),   # degraded is NOT recovered
    (ACTIVE,   None,              None, False),   # unknown liveness: hands off
    # latched-fault recovery (the TX-cut-then-reconnect case)
    (ACTIVE,   LIVENESS_DEAD,  Transition.TRANSITION_DEACTIVATE, True),
    (ACTIVE,   LIVENESS_FAULT, Transition.TRANSITION_DEACTIVATE, True),
    # never touch finalized or mid-transition nodes
    (FINALIZED,   LIVENESS_DEAD, None, False),
    (CONFIGURING, LIVENESS_OK,   None, False),
])
def test_supervisor_action(state, liveness, expect_tid, expect_recover):
    action = supervisor_action(state, liveness)
    assert action.transition_id == expect_tid
    assert action.recover == expect_recover
