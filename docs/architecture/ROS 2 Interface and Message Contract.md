# ROS 2 Interface and Message Contract

> The shared interface layer that binds [Friday Labs OS](Friday Labs OS Architecture.md) and every module agent into one system. Ships **as a component of** Friday Labs OS, not as a sibling.
> **Version:** Draft 1.0 · **Purpose:** Phase 1 foundation — build this before any service logic.

## Why This Document Exists

Friday Labs OS and the module agents only cohere if they share **one** definition of how they talk. This contract is that definition — Friday Labs OS's public interface. It is distributed as a single versioned package (`friday_msgs`) that every OS service and every module agent compiles against. There is no second copy. Change it once, bump the version, everyone rebuilds against the same thing.

This is the standards-grounded approach used by production ROS 2 stacks (notably Nav2). It is the first thing the team builds; service logic comes after.

## Three Layers, One Vocabulary

1. **Transport** — ROS 2 / DDS. Topics, services, actions, QoS, discovery. Pure plumbing.
2. **Vocabulary** — the `friday_msgs` interface package: every `.msg` / `.srv` / `.action`. Code-generated into Python (Pi agents) and C (ESP32 agents via micro-ROS).
3. **Behavior** — Friday Labs OS services produce and consume the vocabulary; module agents implement the other side of the same definitions.

Reuse standard ROS 2 interfaces wherever they exist — do **not** reinvent `sensor_msgs`, `nav_msgs`, `geometry_msgs`, `std_msgs`. `friday_msgs` only defines what is genuinely Mark 1-specific.

## Service-to-Message Ownership Map

Every message exists because a specific Friday Labs OS service produces or consumes it. This map is the cohesion contract.

| Friday Labs OS service | Owns (authoritative for) | Direction |
|---|---|---|
| `module-registry` | `RegisterModule.srv`, `ModulePresence.msg` | agents → OS |
| `system-health-manager` | `Heartbeat.msg`, `HealthStatus.msg`, `PowerState.msg` | agents → OS |
| `command-router` | `MotionCommand.msg`, `ExecuteCommand.action`, `EmergencyStop.msg`, `RecoveryCommand.msg` | OS → agents |
| `fault-manager` | `FaultReport.msg`, `LogEvent.msg` | agents → OS |
| `sensor-fusion-manager` | `nav_msgs/Odometry`, `sensor_msgs/*`, `MapSegment.msg`, `DetectedObjectArray.msg`, `CoverageProgress.msg` | agents → OS |
| `mission-planner` | `MissionStatus.msg` | OS ↔ agents |
| `safety-supervisor` | lifecycle `change_state` / `get_state` services | OS → agents |
| Spark coordination | `SparkStatus.msg`, `SparkMissionRequest.msg` | OS ↔ Bay |

## The Module-Agent Contract = a Lifecycle Node

Every module agent is a ROS 2 **managed (lifecycle) node**. Do not invent a custom agent state machine — use the standard one. The `module-registry` and `safety-supervisor` drive and observe transitions exactly as Nav2's `lifecycle_manager` does (via `get_state` / `change_state` services, with transition events on `~/transition_event`).

Primary states: `unconfigured → inactive → active → finalized`. Mark 1 mapping:

- **configuring** — agent initializes hardware, publishers, and subscribers; registers with `module-registry`.
- **active** — agent does its job: streams data, accepts commands, heartbeats.
- **inactive / safe-state** — agent holds a defined safe behavior (Locomotion locks motors; Research flushes buffers and idles; Telemetry stays alive; Bay secures Spark).
- **finalized** — terminal; resources freed.

If any module fails to reach `active`, the supervisor can block dependent modules from activating and bring the stack down deterministically — the Nav2 pattern.

> Note: lifecycle on the Pi (rclcpp/rclpy) and on the ESP32 (the lighter `rclc` lifecycle) are **not** identical APIs. The state model is the same; the embedded implementation is thinner. Spec per-target accordingly.

## QoS Profiles

Defined once here, referenced by name on both sides.

| Profile | Reliability | Durability | History | Extra | Used for |
|---|---|---|---|---|---|
| `critical_reliable` | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST 10 | — | commands, emergency stop, recovery, registration |
| `state_default` | RELIABLE | VOLATILE | KEEP_LAST 10 | — | health, mission status, odometry |
| `sensor_stream` | BEST_EFFORT | VOLATILE | KEEP_LAST 5 | — | LiDAR, camera, raw sensor streams |
| `heartbeat` | BEST_EFFORT | VOLATILE | KEEP_LAST 1 | Deadline + Liveliness | heartbeats |

## Heartbeat and Fault Detection

Ride on DDS QoS, with an application-level belt-and-suspenders check (liveliness has edge cases; do not rely on it alone).

**Defaults (tune in field testing):**
- Heartbeat publish interval: **200 ms** (5 Hz).
- QoS Deadline: **500 ms**. Liveliness: AUTOMATIC, lease **1 s**.
- Declare **DEGRADED** after 3 consecutive missed deadlines (~1 s).
- Declare **DEAD** / trigger fallback on liveliness lease expiry or 5 missed (~1 s+).

When a module misses its deadline, the middleware raises the event — `system-health-manager` is notified rather than polling, and `fault-manager` acts.

## Core Message Definitions

Common convention: every Mark 1-specific message carries `uint16 protocol_version`, `string module_id`, and `builtin_interfaces/Time stamp`.

```
# Heartbeat.msg
uint16 protocol_version
string module_id
builtin_interfaces/Time stamp
uint64 sequence
uint8  lifecycle_state      # mirrors ROS 2 lifecycle primary states

# HealthStatus.msg
uint16 protocol_version
string module_id
builtin_interfaces/Time stamp
uint8  overall              # 0 OK, 1 DEGRADED, 2 FAULT
uint8  power_state
float32 temperature_c
float32 cpu_load
float32 mem_used_pct
float32 storage_used_pct
uint8  comms_status
uint32 last_error_code
uint64 uptime_s
string detail

# PowerState.msg
string module_id
builtin_interfaces/Time stamp
float32 battery_pct
float32 voltage_v
float32 current_a
float32 power_draw_w
bool    charging
float32 estimated_runtime_min

# RegisterModule.srv  (request / response)
string module_id
string hardware_type
string sw_version
string fw_version
string[] capabilities
uint16 protocol_version
---
bool   accepted
string assigned_namespace
string reason

# ModulePresence.msg
string module_id
bool   online
builtin_interfaces/Time stamp

# MotionCommand.msg
builtin_interfaces/Time stamp
uint8   type                # MOVE STOP TURN SET_VELOCITY SET_STEER PATH_SEGMENT SAFE_STOP
float32 linear_velocity     # m/s
float32 angular_velocity    # rad/s
float32 steer_angle_rad
geometry_msgs/Point[] path  # optional path segment

# EmergencyStop.msg   (QoS: critical_reliable)
string source
string reason
builtin_interfaces/Time stamp

# RecoveryCommand.msg (QoS: critical_reliable)
string target_module
uint8  action               # RESTART REBOOT SAFE_STATE RESUME
builtin_interfaces/Time stamp

# FaultReport.msg
string module_id
uint32 fault_code
uint8  severity             # 0 INFO 1 WARN 2 ERROR 3 CRITICAL
string description
string recommended_action
builtin_interfaces/Time stamp

# LogEvent.msg
string module_id
uint8  level
string tag
string message
builtin_interfaces/Time stamp

# MissionStatus.msg
string mission_id
uint8  phase
float32 progress_pct
string current_goal
builtin_interfaces/Time stamp

# MapSegment.msg / CoverageProgress.msg / DetectedObjectArray.msg
#   processed research outputs to the Core Compute Hub — decision-relevant only.

# SparkStatus.msg
bool   docked
bool   charging
bool   in_flight
float32 battery_pct
string mission_id
geometry_msgs/Pose pose
uint8  health

# SparkMissionRequest.msg   (semi-autonomous, high-level)
uint8  type                 # SCOUT_AREA CAPTURE_SECTOR RETURN
geometry_msgs/Polygon area
string mission_id
```

Raw sensor data uses standard interfaces: LiDAR → `sensor_msgs/PointCloud2`, camera → `sensor_msgs/Image`, IMU → `sensor_msgs/Imu`, GPS → `sensor_msgs/NavSatFix`, odometry → `nav_msgs/Odometry`.

## Namespacing

Topics live under `/mark1/<module>/...` — e.g. `/mark1/locomotion/odometry`, `/mark1/research/map_segment`, `/mark1/telemetry/health`. Keeps the DDS graph legible and avoids collisions.

## Versioning

`protocol_version` is semver-encoded. On registration, `module-registry` rejects (or flags) any agent whose **major** version differs from the OS. The `friday_msgs` package is semver'd; a breaking change bumps major and forces a coordinated rebuild.

## ESP32 / micro-ROS Integration

The ESP32 modules (Locomotion Control Unit, Telemetry backup, Spark Bay) join the same DDS graph via **micro-ROS / Micro XRCE-DDS**. A micro-ROS Agent on the owning Pi bridges the MCU (serial or UDP) into the DDS world, exposing its nodes to the rest of ROS 2. The same `friday_msgs` definitions are used, generated with Micro-XRCE-DDS-Gen. Where micro-ROS is not viable, a serial-bridge node on the owning Pi translates to the identical contract.

> **Safety note:** the micro-ROS agent is not certified for safety-critical production out of the box and should be validated against the relevant standard (e.g. ISO 26262) before field deployment. For a ruggedized/military-grade build, budget for this validation.

## External Boundary (Command Center)

The Command Center link is deliberately **not** ROS 2. DDS is LAN-oriented and unsuited to running over public cellular. The [Telemetry Command Node](Telemetry Command Node.md)'s **Telemetry Node Agent** is the translator: internal ROS 2 `friday_msgs` on one side, the Command Center protocol (MQTT-class over the cellular gateway) on the other. This contract defines the internal side; the Command Center protocol is a separate, mapped definition.

## Build Sequence (Phase 1)

1. Create the `friday_msgs` interface package; define the messages above.
2. Define the lifecycle-node base for agents (Pi + ESP32 variants) and the registry/supervisor services.
3. Lock QoS profiles and the heartbeat/deadline/liveliness defaults.
4. Stand up `module-registry`, `system-health-manager`, and `fault-manager` against the contract.
5. Study Nav2's `lifecycle_manager` as the working reference for the supervisor, then implement.

---

Related: [Friday Labs OS Architecture](Friday Labs OS Architecture.md) · [Telemetry Command Node](Telemetry Command Node.md) · [Mark 1 Compute Architecture](Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
