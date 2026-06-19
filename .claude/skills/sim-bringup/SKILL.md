---
name: sim-bringup
description: Stand up the Gazebo + ros_gz simulation environment for Mark 1 and walk the seven-stage bring-up. Use when starting a fresh sim, regression-checking after a contract change, or onboarding a developer. Locks the REP-2000-correct ROS 2 + Gazebo pairing and verifies each stage before progressing.
---

# Mark 1 Sim Bring-Up

The whole point of the interface-first build is that Friday Labs OS cannot tell whether odometry came from a real encoder or Gazebo physics. This skill makes that promise hold in practice.

Reference: `Mark 1 Simulation and Dev Environment.md`.

## Locked stack (do not deviate without a written reason)

- **ROS 2:** Jazzy (LTS)
- **Gazebo:** Harmonic (matched per REP-2000)
- **Bridge:** `ros_gz` (`ros_gz_bridge`, `ros_gz_image`, `ros_gz_sim`)
- **Sim control:** ROS 2 Simulation Interfaces (spawn/reset/inject)
- **ros2_control bridge:** `gz_ros2_control`
- **Visualization:** RViz2 + Foxglove
- **Bag:** `ros2 bag` (also satisfies mission-replay requirement)

If a developer proposes Gazebo Classic, refuse — it is end-of-life.

## Procedure

### Stage 0 — preflight

1. Verify ROS 2 Jazzy + Gazebo Harmonic installed; print versions.
2. Source the workspace; confirm `friday_msgs` builds clean.
3. Confirm `ros_gz_bridge`, `gz_ros2_control`, and the Mark 1 URDF/SDF package are present.

### Stage 1 — model + teleop

1. Launch the Gazebo world with the six-wheel rocker-bogie URDF/SDF.
2. Bring up `gz_ros2_control` for the drive joints.
3. Teleop with `teleop_twist_keyboard` (Twist on `/mark1/locomotion/cmd_vel`).
4. **Verify:** rocker-bogie behaves over uneven terrain; no inverted suspension, no joint runaway.

### Stage 2 — lifecycle orchestration

1. Launch sim agents as lifecycle nodes against `friday_msgs`.
2. Bring up `module-registry`, `system-health-manager`, `fault-manager`.
3. Drive lifecycle transitions via the supervisor.
4. **Verify:** deterministic startup; all agents reach `active`; registry reports them online; heartbeats steady at 5 Hz.

### Stage 3 — closed loop

1. Subscribe Core's autonomy to `nav_msgs/Odometry` from the sim Locomotion agent.
2. Publish `MotionCommand` from Core → motion in sim → odometry back to Core.
3. **Verify:** odometry round-trip integrates to commanded path within tolerance; sensor-fusion-manager updates pose at steady rate.

### Stage 4 — sensing

1. Enable Gazebo plugins for LiDAR (`PointCloud2`), camera (`Image`), IMU (`Imu`), GPS (`NavSatFix`).
2. Bring up the Adaptive Research agent against the sensor topics.
3. **Verify:** Core receives `MapSegment` / `CoverageProgress` / `DetectedObjectArray` — NOT raw point clouds. If Core is subscribing to raw streams, the contract is broken — stop and fix.

### Stage 5 — fault injection

Run the `fault-injection` skill. Do not declare bring-up complete until Stage 5 passes with the documented latency budgets.

### Stage 6 — Spark

1. Spawn the Spark quadrotor model.
2. Bring up Aerial Bay agent + Spark coordination services.
3. **Verify:** launch/dock handshake completes; `SparkStatus` reflects in-flight state; Bay rejects rover-motion commands while Spark is mid-launch.

### Stage 7 — headless CI

1. Wrap stages 1–6 as a headless `ros2 launch` invocation.
2. Add to CI; every commit reruns the bring-up + Stage 5 fault scenarios.
3. **Verify:** CI green on a clean main; regressions surface on push, not in the field.

## What this skill refuses to do

- Pair ROS 2 and Gazebo in a combination not endorsed by REP-2000 for the chosen distro.
- Skip Stage 5 to make a demo work.
- Subscribe Core to raw sensor streams as a shortcut to "make the map render."
