# friday_msgs Schema Conventions

> Locks the conventions every `.msg`, `.srv`, and `.action` in the `friday_msgs` package must follow. Closes a Phase 1 contract-discipline gap. Enforced by the [friday-msgs-author](../../.claude/skills/friday-msgs-author/SKILL.md) skill.
> **Version:** Draft 1.0 · **Purpose:** Closes Phase 1 schema gaps before service logic is written.

## Mandatory Header on Every Mark 1-Specific Message

```
uint8  protocol_major
uint8  protocol_minor
uint16 protocol_patch
string module_id                  # canonical id, e.g. MARK1-LAB-001
builtin_interfaces/Time stamp
```

**Why packed semver:** the original spec called `protocol_version` a single `uint16` "semver-encoded." Semver has three fields. One number cannot carry major + minor + patch. The packed-three-field form is what `module-registry` compares against; major-version mismatch rejects registration.

## Lifecycle State Encoding

Any field that represents a lifecycle state uses the **numeric constants from `lifecycle_msgs/State`**, not a custom enum. Pi (`rclcpp_lifecycle`, `rclpy_lifecycle`) and ESP32 (`rclc_lifecycle`) agree on these values; a custom mapping would drift.

## Frame Conventions

| Frame | Meaning | Owner |
|---|---|---|
| `map` | World frame, fixed origin per mission | Core sensor-fusion-manager |
| `odom` | Continuously-evolving local frame, smooth but drifts | Locomotion Control Unit |
| `base_link` | Rover body frame, origin at chassis center | Core (static) |
| `base_link_*` | Per-sensor frames (e.g. `base_link_lidar`, `base_link_nav_cam`) | Module owning the sensor |

- Right-handed coordinate system.
- X forward, Y left, Z up.
- Units: meters, radians, seconds. SI throughout.
- Any spatial field must declare `string frame_id` or inherit from a `std_msgs/Header`.

## Command-Class Authority Fields

Any message that can move the rover, REBOOT a module, or trigger safe-stop MUST carry:

```
string source             # holder_module_id from the current authority lease
string token_id           # which command-signing key was used
uint64 nonce              # monotonic per (source, target); replay rejected
builtin_interfaces/Time expires_at
```

`command-router` and Locomotion firmware reject commands where:

- `source` does not match the current authority lease holder.
- `nonce` is not strictly greater than the last seen for this `(source, target)` pair.
- `expires_at` has passed.
- Signature (validated separately at transport layer) is invalid.

This rule applies to: `MotionCommand`, `EmergencyStop`, `RecoveryCommand`, `ExecuteCommand.action`, lifecycle `change_state` services.

## Bounded Arrays

No `geometry_msgs/Point[]`, `byte[]`, or other unbounded array on a topic with QoS RELIABLE. Unbounded RELIABLE arrays can stall the DDS queue and block downstream messages.

Specific caps:

| Field | Cap | Rationale |
|---|---|---|
| `MotionCommand.path` | `geometry_msgs/Point[<=1000]` | 1000 points × 1 m spacing = 1 km of path; covers any single MotionCommand chunk. Larger missions break into multiple commands or use `UploadMission.action`. |
| `MapSegment.points` | `<=20000` | Single segment, ~250 KB at 12 B/point. |
| `DetectedObjectArray.detections` | `<=200` | One frame's worth of detections. |
| `LogEvent.message` | `string<=512` | Bounded to prevent log-flood DoS. |

## Category Fields on Faults and Emergencies

`EmergencyStop.msg` and `RecoveryCommand.msg` add a `uint8 category` field:

```
# EmergencyStop categories
uint8 CATEGORY_OPERATOR    = 0   # human-initiated via Command Center
uint8 CATEGORY_COLLISION   = 1   # perception-detected obstacle, autonomy-initiated
uint8 CATEGORY_CASCADE     = 2   # downstream of another fault (power, comms loss)
uint8 CATEGORY_WATCHDOG    = 3   # firmware-level safe-stop, post-hoc reported
uint8 CATEGORY_TEST        = 4   # injected by fault-injection skill, not real

# RecoveryCommand actions
uint8 ACTION_RESTART       = 0
uint8 ACTION_REBOOT        = 1
uint8 ACTION_SAFE_STATE    = 2
uint8 ACTION_RESUME        = 3
```

The category tells the audit log and the operator what kind of stop just happened, and informs what's needed to recover from it.

## New Interface — UploadMission Action

`MissionStatus.msg` is reportback only. The original dossier never defined how a mission *enters* the system. Adding it as an action with proper goal/feedback/result semantics:

```
# UploadMission.action  (goal)
string mission_id
uint8  mission_type          # MAPPING | INSPECTION | SURVEILLANCE | TRANSIT
geometry_msgs/Polygon area
string[] required_capabilities
string[] sensors_required
float32 max_duration_min
string source                # operator id
string token_id
uint64 nonce
---
# result
bool accepted
string rejection_reason
string assigned_mission_id
---
# feedback
uint8 phase
float32 progress_pct
string current_goal
```

Owner: `mission-planner` on Core. Routed in via `command-router` after authority-holder + signature validation.

## Topic Namespacing

`/mark1/<module>/<topic>` — locked. Examples:

- `/mark1/locomotion/odometry`
- `/mark1/locomotion/cmd_motion`
- `/mark1/locomotion/emergency_stop`
- `/mark1/research/map_segment`
- `/mark1/telemetry/health`
- `/mark1/system/authority` (system-wide, not per-module)

## Acceptance Criteria

- `colcon build --packages-select friday_msgs` clean on Ubuntu 24.04 + ROS 2 Jazzy.
- `ros2 interface show` round-trips every Mark 1-specific message correctly on both Pi (Python) and ESP32 (micro-ROS C).
- Code review confirms no unbounded arrays on RELIABLE QoS topics.
- Code review confirms `command-router` rejects unsigned commands at the boundary.

## Related

[ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Authority Lease Protocol](Authority Lease Protocol.md) · [Safe-Stop Latency Budget](Safe-Stop Latency Budget.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
