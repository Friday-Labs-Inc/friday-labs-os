---
name: friday-msgs-author
description: Author or modify a message/service/action in the `friday_msgs` interface package. Use when adding, renaming, or changing any Mark 1 ROS 2 interface. Enforces the contract — standard-interface reuse, mandatory header fields, QoS profile naming, frame conventions, bounded arrays, packed semver protocol_version, lifecycle constant reuse.
---

# friday-msgs Authoring

`friday_msgs` is the single source of truth for Mark 1's vocabulary. Drift here breaks every module agent at once. This skill keeps schema changes disciplined.

Reference: `ROS 2 Interface and Message Contract.md` (root of the dossier).

## Before you write any message

1. **Reuse first.** Check whether a standard ROS 2 interface already covers the need: `sensor_msgs`, `nav_msgs`, `geometry_msgs`, `std_msgs`, `diagnostic_msgs`, `lifecycle_msgs`. If yes, reuse — do not redefine.
2. **One owner.** Confirm the new interface maps to exactly one Friday Labs OS service in the Service-to-Message Ownership Map. If no owner exists, the design is incomplete — stop and resolve ownership first.
3. **QoS upfront.** Decide which profile applies: `critical_reliable`, `state_default`, `sensor_stream`, or `heartbeat`. The profile is part of the contract — write it in a comment at the top of the file.

## Required header on every Mark 1-specific message

```
uint8  protocol_major
uint8  protocol_minor
uint16 protocol_patch
string module_id                  # canonical id, e.g. MARK1-LAB-001
builtin_interfaces/Time stamp
```

For any field that represents a lifecycle state, use the numeric constants from `lifecycle_msgs/State`. Do not mint your own values — Pi (`rclcpp_lifecycle`/`rclpy_lifecycle`) and ESP32 (`rclc_lifecycle`) must agree.

## Hard rules

- **No unbounded arrays on RELIABLE QoS.** Cap with `<=N` length specifier, or move to an action with chunked feedback.
- **Frames are mandatory** for any spatial field. Declare `string frame_id` (default `map`, `odom`, or `base_link` per ownership) and document handedness/units in a header comment.
- **Authority on commands.** Anything that can STOP, REBOOT, or move motors must carry `string source`, `string token_id`, and `uint64 nonce`. Unsigned commands must be rejected by `command-router`.
- **Categorize emergencies.** `EmergencyStop` and `RecoveryCommand` carry a `uint8 category` (operator / collision / cascade / watchdog) and a `string reason`.
- **No floats for safety-critical thresholds** without a documented unit and range.

## Procedure

1. Open the `friday_msgs` package — edit `CMakeLists.txt` and `package.xml` to add the new `.msg`/`.srv`/`.action`.
2. Write the schema. Cross-check against the hard rules above.
3. Bump the package version:
   - **patch** for clarification/comment-only changes
   - **minor** for additive changes (new field with default; new message)
   - **major** for breaking changes (renamed field, removed field, type change)
4. Regenerate bindings on both target architectures:
   - Pi: `colcon build --packages-select friday_msgs`
   - ESP32: regenerate via `micro_ros_setup` + Micro-XRCE-DDS-Gen
5. Update the Service-to-Message Ownership Map in the contract doc.
6. Add a CHANGELOG entry with: who owns it, which QoS profile, which agents must rebuild.

## Acceptance

- `colcon build --packages-select friday_msgs` clean on both architectures.
- `ros2 interface show friday_msgs/msg/<NewMessage>` lists every field with the expected types.
- The ownership map in `ROS 2 Interface and Message Contract.md` reflects the new interface.
- A major version bump is mirrored in `protocol_major` checks in `module-registry`.

## Common mistakes to refuse

- "I'll just use a `string` for the enum" — no. Use a `uint8` + named constants header.
- "It's only used internally so I'll skip the header fields" — no. The header is part of the contract; uniform parsing across agents depends on it.
- "I'll add an unbounded `byte[]` for the payload" — no. Cap it or move to an action.
