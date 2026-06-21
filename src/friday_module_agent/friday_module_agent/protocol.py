"""Protocol-level constants for the Friday Labs OS contract.

Single source of truth for the packed-semver protocol version and the health
enums shared by agents and the Core Hub registry. See
docs/addendums/friday_msgs Schema Conventions.md.
"""

# Packed semver of the friday_msgs contract this code targets.
PROTOCOL_MAJOR = 0
PROTOCOL_MINOR = 1
PROTOCOL_PATCH = 0

# Health "overall" codes (mirror friday_msgs/HealthStatus constants).
HEALTH_OK = 0
HEALTH_DEGRADED = 1
HEALTH_FAULT = 2


def major_compatible(their_major: int) -> bool:
    """Registration rule: only a matching MAJOR version is accepted.

    A breaking interface change bumps MAJOR and forces a coordinated rebuild;
    until then an agent on a different major must be rejected.
    """
    return their_major == PROTOCOL_MAJOR
