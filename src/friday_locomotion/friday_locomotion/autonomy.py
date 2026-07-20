"""Pure autonomy-level helpers (no ROS) — tested independently."""

LEVEL_MANUAL = 0       # L0: full operator control; all autonomy-sourced motion gated
LEVEL_ASSISTED = 1     # L1: autonomy assists; motion permitted
LEVEL_SUPERVISED = 2   # L2: operator supervises; motion permitted (per-wp approval: future)
LEVEL_AUTONOMOUS = 3   # L3: fully autonomous; motion permitted

VALID_LEVELS = frozenset({LEVEL_MANUAL, LEVEL_ASSISTED, LEVEL_SUPERVISED, LEVEL_AUTONOMOUS})
VALID_PROFILES = frozenset({'Bench', 'Agriculture', 'Forestry', 'Environmental', 'Surveillance'})
VALID_BRAINS = frozenset({'Rules', 'Nav2', 'Vision', 'Hermes'})


def motion_allowed(autonomy_level: int) -> bool:
    """L0 (Manual) gates all autonomy-sourced motion; L1/L2/L3 pass."""
    return autonomy_level != LEVEL_MANUAL
