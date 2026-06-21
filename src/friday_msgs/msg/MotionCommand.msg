# A drive command for the Locomotion Control Unit.
# Topic: /mark1/locomotion/cmd_motion   QoS profile: critical_reliable
# Owner: command-router (Core Hub).
#
# Command-class message: it can MOVE the rover, so per the friday_msgs Schema
# Conventions it carries authority fields (source / token_id / nonce /
# expires_at). Those are validated from Phase 4 (safety/authority); in Phase 3
# the Locomotion agent records them but does not yet reject on them.
uint8 TYPE_STOP        = 0   # come to rest, stay active
uint8 TYPE_VELOCITY    = 1   # drive at linear_velocity / angular_velocity
uint8 TYPE_SAFE_STOP   = 2   # immediate safe-stop (motors off, hold)

Mark1Header header
uint8   type
float32 linear_velocity        # m/s,  + = forward
float32 angular_velocity       # rad/s, + = turn left (CCW)
float32 steer_angle_rad        # reserved for explicit corner-steer commands

# --- authority fields (enforced from Phase 4) ---
string  source                 # holder_module_id from the current authority lease
string  token_id               # which command-signing key was used
uint64  nonce                  # monotonic per (source, target); replay-rejected later
builtin_interfaces/Time expires_at
