---
name: lifecycle-node-scaffold
description: Scaffold a new ROS 2 lifecycle node that implements the Friday Labs OS module-agent contract. Use when adding a new module agent on a Pi (rclpy/rclcpp) or an ESP32 (rclc via micro-ROS). Wires the standard lifecycle callbacks, registration, heartbeat, health, and a safe-state handler. Refuses to use a custom state machine.
---

# Lifecycle Node Scaffold

Every module agent in Mark 1 is a managed (lifecycle) node. Do not invent state machines — use the standard one. Nav2's `lifecycle_manager` is the reference; `module-registry` and `safety-supervisor` drive transitions identically.

Reference: `ROS 2 Interface and Message Contract.md` (lifecycle contract section).

## Inputs the operator must provide

- **Target runtime**: `pi-python` | `pi-cpp` | `esp32-rclc`
- **Module id** (canonical): e.g. `MARK1-LAB-001`
- **Hardware type**: e.g. `adaptive-research-module`
- **Capabilities** (string list): e.g. `["lidar_capture", "camera_capture", "mapping"]`
- **Safe-state policy** for this module — what does "deactivated" mean physically?

If any are missing, ask before scaffolding.

## Procedure

### 1. Create the package

- `pi-python`: `ros2 pkg create --build-type ament_python <name> --dependencies rclpy rclpy_lifecycle friday_msgs lifecycle_msgs`
- `pi-cpp`: `ros2 pkg create --build-type ament_cmake <name> --dependencies rclcpp rclcpp_lifecycle friday_msgs lifecycle_msgs`
- `esp32-rclc`: clone the `micro_ros_setup` template, add `rclc_lifecycle` and the `friday_msgs` generated bindings.

### 2. Implement the five lifecycle callbacks against the contract

- **`on_configure`** — init publishers/subscribers, load params. Do NOT power on or move any hardware that could actuate.
- **`on_activate`** — call `RegisterModule.srv` against `module-registry`. On `accepted=true`, start the heartbeat and health publishers, then enable hardware.
- **`on_deactivate`** — hold the module-specific safe-state:
  - Locomotion: clamp motors to zero, lock brake, hold steering at neutral.
  - Adaptive Research: flush sensor buffers, idle DMA, power-gate non-essential sensors.
  - Telemetry: stay alive; do not deactivate channels unless explicitly commanded.
  - Aerial Bay: secure Spark in dock, lock release mechanism.
  - Continue heartbeats at degraded rate so the supervisor knows we're alive.
- **`on_cleanup`** — release resources, close drivers cleanly.
- **`on_shutdown`** / **`on_error`** — publish `FaultReport`, transition to `finalized`.

### 3. Wire mandatory publishers per contract

- `Heartbeat` at 200 ms (5 Hz), QoS profile `heartbeat` (BEST_EFFORT, KEEP_LAST 1, Deadline 500 ms, Liveliness AUTOMATIC lease 1 s).
- `HealthStatus` at 1 Hz, QoS profile `state_default`.
- Topic namespace: `/mark1/<module>/...` (e.g. `/mark1/research/heartbeat`).

### 4. Implement the safe-state behavior **for real**

The lifecycle `inactive` transition is a graceful handle. It is **not** the emergency reflex. For modules with motion or actuator authority, also implement:

- **Firmware-level watchdog** (ESP32 only, mandatory for Locomotion and Aerial Bay): trips on absence of heartbeats from the owning Pi, NOT on receipt of an EmergencyStop. Default budget: 100 ms inactivity → safe-state. Make this independent of the micro-ROS bridge process.
- **EmergencyStop subscriber** on QoS `critical_reliable` — handles operator/supervisor-initiated stops. Idempotent.

### 5. Register the namespace claim

Tell `module-registry` your topic namespace at registration so the supervisor's graph view stays coherent.

## Acceptance

- `ros2 lifecycle list` shows the node with the standard primary states.
- `ros2 lifecycle set /mark1/<module> configure` then `activate` succeeds; node appears in `module-registry` with the right capabilities.
- `ros2 topic hz /mark1/<module>/heartbeat` reports 5 Hz steady-state.
- Killing the micro-ROS agent process (for ESP32 agents) does NOT prevent the firmware watchdog from tripping safe-state within budget. **Test this on the bench before declaring the scaffold done.**
- `ros2 lifecycle set /mark1/<module> deactivate` triggers the module-specific safe-state and the module continues heartbeating.

## What this skill refuses to do

- Generate a node that uses a custom state machine instead of `rclcpp_lifecycle`/`rclpy_lifecycle`/`rclc_lifecycle`.
- Generate an ESP32 agent whose only safe-stop path goes through the micro-ROS bridge.
- Skip the registration step "for testing."
