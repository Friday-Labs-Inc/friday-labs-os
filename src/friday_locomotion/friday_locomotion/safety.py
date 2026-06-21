"""Pure authority-enforcement logic for the Locomotion Control Unit (no ROS).

Implements the command-acceptance rules from the Authority Lease Protocol +
friday_msgs Schema Conventions: a MotionCommand is obeyed only if the rover is
not in safe-state, a valid authority lease exists, the command's `source` is the
current lease holder, the command has not expired, and its nonce strictly
increases per source (replay protection). Kept ROS-free so it is unit-testable.
"""

from dataclasses import dataclass

ACCEPT = 'ACCEPT'
SAFE_STATE = 'SAFE_STATE'        # node is safe-stopped; obeys nothing until re-activated
NO_AUTHORITY = 'NO_AUTHORITY'    # no holder / lease expired
WRONG_SOURCE = 'WRONG_SOURCE'    # source is not the current lease holder
EXPIRED = 'EXPIRED'              # command's own expiry has passed
REPLAY = 'REPLAY'               # nonce <= last seen for this source


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str


def authorize(*, source, nonce, cmd_expires_s, holder, lease_expires_s,
              last_nonce, now_s, in_safe_state) -> Decision:
    """Decide whether a MotionCommand may be obeyed. Times are unix seconds.

    `cmd_expires_s` / `last_nonce` may be 0 / None to skip that check (an
    unset command expiry or the first command from a source).
    """
    if in_safe_state:
        return Decision(False, SAFE_STATE)
    if not holder or now_s >= lease_expires_s:
        return Decision(False, NO_AUTHORITY)
    if source != holder:
        return Decision(False, WRONG_SOURCE)
    if cmd_expires_s and now_s >= cmd_expires_s:
        return Decision(False, EXPIRED)
    if last_nonce is not None and nonce <= last_nonce:
        return Decision(False, REPLAY)
    return Decision(True, ACCEPT)
