# Mark 1 Simulation and Dev Environment

> How we prove the [Mark 1](Mark 1 Compute Architecture.md) software works before a dollar of hardware. The practical companion to the [ROS 2 Interface and Message Contract](ROS 2 Interface and Message Contract.md).
> **Version:** Draft 1.0 · **Purpose:** Dev/sim foundation and bring-up checklist.

## Why This Works: Sim/Hardware Parity

Because every module speaks `friday_msgs` over ROS 2, [Friday Labs OS](Friday Labs OS Architecture.md) cannot tell whether odometry came from a real wheel encoder or from Gazebo's physics. We swap only the hardware-facing edge — the Locomotion ESP32 firmware, the real LiDAR driver — for simulation equivalents that publish the **same** messages. The registry, health manager, fault manager, sensor fusion, mission planner, and safe-stop logic run byte-for-byte identical in sim and on hardware.

That means whatever we validate in Gazebo is a real test of the production stack, not an approximation. This is the entire payoff of building the interface contract first.

## The Stack

- **Simulator:** *current* Gazebo (formerly Ignition) — **not** Gazebo Classic, which is end-of-life. Pairing is governed by REP-2000; use the matching default Gazebo for the chosen ROS 2 distro, latest LTS of both for the best experience. Safe baseline: **ROS 2 Jazzy + Gazebo Harmonic** (confirm against REP-2000 when starting — don't mix arbitrarily).
- **Bridge:** `ros_gz` — `ros_gz_bridge` (bidirectional ROS↔Gazebo transport), `ros_gz_image`, `ros_gz_sim` (launch helpers).
- **Sim control:** the standard, simulator-agnostic **ROS 2 Simulation Interfaces** (spawn/reset/inject via a clean API), which Gazebo implements.
- **Rover model:** described once in URDF/SDF — the six-wheel rocker-bogie with corner steering — driven by `ros2_control` via `gz_ros2_control`. The same description carries to hardware.
- **Sensors:** Gazebo plugins emit `sensor_msgs/PointCloud2` (LiDAR), `Image` (camera), `Imu`, `NavSatFix` (GPS) — exactly what the Adaptive Research Module already consumes.
- **Visualization/inspection:** RViz2 and Foxglove (lifecycle state, transitions, topics).
- **Record/replay:** `ros2 bag` — also validates the mission-replay requirement.
- **micro-ROS:** keep ESP32 firmware out of the loop at first (a sim node stands in); add hardware-in-the-loop later.

## Module Swap Table

| Module | Real edge | Sim equivalent | Contract |
|---|---|---|---|
| Core Compute Hub | — | Runs **unchanged** | same |
| Locomotion Control Unit | ESP32 firmware | `gz_ros2_control` hardware interface (or sim node): subscribes `MotionCommand`, publishes `nav_msgs/Odometry` | same |
| Adaptive Research Module | Real LiDAR/camera drivers | Gazebo sensor plugins → `sensor_msgs/*` | same |
| Telemetry Command Node | Cellular/LoRa modems | Runs as real Linux node; channels stubbed; Command Center = mock endpoint | same |
| Aerial Companion Bay + **Spark** | ESP32 + drone | Stub first, then Spark as a second simulated model (quadrotor) | same |

## Seven-Stage Bring-Up

1. **Model + teleop.** URDF + a Gazebo world; drive by hand. Prove the rocker-bogie behaves over uneven terrain before anything else.
2. **Lifecycle orchestration.** Registry, heartbeats, health against sim agents as lifecycle nodes. Prove the Nav2-style deterministic startup/shutdown.
3. **Closed loop.** `MotionCommand` → motion → `Odometry` → fusion. The command-and-feedback spine, end to end.
4. **Sensing.** Gazebo LiDAR/camera → research agent → map segments. Prove the data discipline: Core Compute Hub receives summaries, not raw streams.
5. **Fault injection.** The most important stage. Kill the Core Compute Hub node and confirm the Telemetry Command Node takes over cleanly — **and what happens when the Core Compute Hub comes back** (the split-brain problem). Cut the Locomotion comms link and confirm safe-stop fires. Repeatable and automatable in sim in a way it never is on hardware.
6. **Spark.** Second model; launch/dock/coordinate.
7. **Headless CI.** Run Gazebo headless in continuous integration so every commit re-runs the bring-up and the fault scenarios. This is what turns "it worked once" into a foundation — regressions caught on push, not in a field.

## What This De-Risks

Stage 5 is where the two known design gaps finally become testable in a controlled, repeatable way:

- **Real-time safe-stop path** — does Locomotion actually stop in time when comms drop, through the lifecycle node + DDS + (eventually) micro-ROS chain?
- **Split-brain authority** — when both the Core Compute Hub and the Telemetry Command Node believe they hold authority, what happens? Sim lets you force this and watch.

## Honest Limits

Sim validates **logic and integration** superbly. It does **not** faithfully reproduce real comms flakiness, power/thermal behavior, true sensor noise, or hard real-time timing. So Gazebo proves the architecture and the failure-handling logic — but the real-time safe-stop path and the physical risks still need **hardware-in-the-loop** (a real ESP32 over micro-ROS, then a bench rig) and **field testing**. Sim shrinks the unknowns dramatically; it does not eliminate the ones flagged as lowest-confidence.

---

Related: [ROS 2 Interface and Message Contract](ROS 2 Interface and Message Contract.md) · [Friday Labs OS Architecture](Friday Labs OS Architecture.md) · [Telemetry Command Node](Telemetry Command Node.md) · [Mark 1 Compute Architecture](Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
