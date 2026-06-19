# Friday Labs OS Architecture

> Core operating system and service-orchestration framework for the [Mark 1](Mark 1 Compute Architecture.md) rover.
> **Version:** Draft 1.0 · **Purpose:** Foundational software blueprint · **Runs on:** Core Compute Hub

## What Friday Labs OS Is

Friday Labs OS is the brain software of Mark 1. It runs **on the Core Compute Hub** and orchestrates the four other subsystems — the Telemetry Command Node, the Adaptive Research Module, the Locomotion Control Unit, and the Aerial Companion Bay — over a distributed, message-based architecture built on ROS 2.

It is **not** a monolithic OS and **not** a from-scratch kernel. It is a modular service framework layered on top of a standard Linux base. The Core Compute Hub is the *brain, not the bottleneck*: Friday Labs OS coordinates and decides, while heavy work (sensor processing, motor loops, comms) stays on the module that owns it.

Each of the other four subsystems runs its own local firmware or **module agent** that speaks the Friday Labs OS protocol. Friday Labs OS does not run *on* those modules — it talks *to* them through a defined contract.

## Core Principles

- **Modular by design** — each module owns a clear responsibility; the OS coordinates, it doesn't absorb.
- **Core Compute Hub is the brain, not the bottleneck** — raw sensor crunching lives on the Adaptive Research Module, real-time motor control on the Locomotion Control Unit.
- **Offline-first autonomy** — Mark 1 must complete a mission with zero internet. Cloud is optional augmentation, never a dependency.
- **Fail safe, always** — every module reports health; every fault is logged; loss of the Core Compute Hub must degrade gracefully, not catastrophically.
- **No destructive behavior** — research, public welfare, agriculture, forestry, safety, and surveillance only.

## Architecture Layers

**Layer 1 — Linux base.** Ubuntu 24.04 LTS for all Pi compute modules — the official ROS 2 Jazzy target and the distribution with the largest robotics community. Provides process scheduling, networking, storage, and hardware abstraction on the Raspberry Pi / SBC. (Fedora was considered in the original draft and explicitly rejected; see [Mark 1 Index](../Mark 1 Index.md) resolved gaps.)

**Layer 2 — ROS 2 middleware.** The DDS-backed communication bus: node-to-node publish/subscribe for streaming data, services for request/response, actions for long-running goals, and a parameter system for configuration. This is the transport every module agent plugs into.

**Layer 3 — Friday Labs OS service framework.** The Friday Labs OS layer itself: module registry, health/heartbeat supervision, mission planning, sensor fusion coordination, command routing, fault management, and logging. This is where the rover's "operating system" behavior lives.

**Layer 4 — Application services.** The concrete services that deliver behavior (mission-planner, autonomy-manager, sensor-fusion-manager, etc.), each running as a managed unit under the framework.

## Module Orchestration: The Agent Model

Every non-Core module connects to Friday Labs OS through a small local program — its **module agent** — that implements a common contract. This keeps the Core Compute Hub decoupled from each module's internals.

Every module agent must:

- **Register** itself on startup (identity, hardware type, software/firmware version, capabilities).
- **Heartbeat** on a fixed interval so the OS knows it's alive.
- **Report health** (power state, status, last error, sensor/actuator status).
- **Accept commands** routed from Friday Labs OS, validated against current rover state.
- **Publish data** (odometry, sensor streams, mission/payload status) back to the OS.
- **Honor safe-state** — execute a defined safe behavior on command or on loss of the Core Compute Hub link. ESP32 agents trip firmware-level safe-stop within 100 ms per [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md); command source is validated against the current [authority lease holder](../addendums/Authority Lease Protocol.md).

The known agents/firmware are:

- **Telemetry Node Agent** — on the Telemetry Command Node. The bridge between the Command Center and Friday Labs OS. Lightweight, reliable, and able to operate independently if the Core Compute Hub goes silent.
- **Adaptive Research Module Agent** — manages sensors, captures/process LiDAR, camera, and environmental data, and publishes only decision-relevant outputs to the Core Compute Hub.
- **Locomotion Control Unit firmware** — real-time motor/steering/encoder/IMU control; converts high-level movement goals into motion; fails safe on lost link.
- **Aerial Companion Bay firmware** — handles the physical **Spark** handshake (launch, dock, charge, secure) and relays semi-autonomous mission requests.

## Message Bus and Communication Model

ROS 2 / DDS is the internal backbone. A lightweight telemetry bus (MQTT-class) handles Command Center traffic via the Telemetry Command Node. Local hardware links use UART/SPI/I2C/CAN; Pi-to-Pi uses Ethernet/Wi-Fi where bandwidth is needed; Pi-to-ESP32 uses serial.

Friday Labs OS defines a standard message set — heartbeat, health status, power state, module online/offline, sensor data, motor command, odometry, mission status, emergency stop, recovery command, communication status, Spark status, research payload status, fault report, log event. Each message type carries a defined QoS (which are guaranteed-delivery vs. fire-and-forget) so the system behaves predictably under degraded comms. The four locked profiles (`critical_reliable`, `state_default`, `sensor_stream`, `heartbeat`) and the schema discipline are in [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).

## Module Registry and Discovery

On boot, each module agent registers with the OS and appears in the **module registry** — the live map of who is present, what they can do, and their current state. The registry is what fallback logic reads from: if a registered module stops heartbeating, the OS knows exactly what was lost and can decide the safe response. Plug-and-play sensor discovery on the Adaptive Research Module reports new payloads up through the same path.

## Health Monitoring and Fault Handling

Friday Labs OS continuously supervises heartbeats and health for all modules plus power, communication, sensor, motor-controller, storage, temperature, and network status.

**Fallback rules**

- *Core Compute Hub OK, Telemetry Command Node fails* → Core Compute Hub attempts telemetry restart/recovery; activates backup ESP32 minimal comms if needed; logs fault; continues mission only if safe.
- *Core Compute Hub fails, Telemetry Command Node alive* → the Telemetry Command Node enters recovery mode, tries to re-establish the Core Compute Hub, sends emergency status to the Command Center, allows limited recovery commands, and triggers safe stop on the Locomotion Control Unit if possible. **The Telemetry Command Node is a peer with failure authority, not a subordinate.**
- *Both fail, backup ESP32 alive* → ESP32 broadcasts a minimal "Mark 1 alive, awaiting recovery" beacon over LoRa at lowest power and waits for recovery/manual intervention.
- *Locomotion Control Unit loses command link* → stop motors safely, lock state, report fault if possible.

## Mission Planning and Autonomy

Running on the Core Compute Hub, the autonomy stack validates incoming missions, plans routes, issues movement goals to the Locomotion Control Unit, triggers capture on the Adaptive Research Module, updates the route from terrain/progress feedback, and decides when to deploy **Spark**. All of this runs offline.

## Sensor Fusion Coordination

The Core Compute Hub fuses *decision-level* inputs — odometry from the Locomotion Control Unit, processed maps/obstacles/detections from the Adaptive Research Module, and aerial data from Spark — into a coherent world model. It does **not** ingest every raw stream. Shared sensors (main LiDAR/camera) follow a clear ownership model: one module owns the physical connection and publishes a stream over ROS 2; others subscribe.

## Internet and Cloud Strategy

The Core Compute Hub has **no direct internet path**. Core autonomy, navigation, motor control, and sensor fusion are fully local. When connectivity exists, the Core Compute Hub may *optionally* request cloud services — heavy AI inference, map/terrain pre-fetch, research-data upload, remote diagnostics — and the **Telemetry Command Node brokers that request** over whatever channel is available (4G/5G/Wi-Fi). This keeps Mark 1 fully functional in remote areas and keeps comms security and bandwidth control in one place.

## Command Routing and Security

Commands flow **Core Compute Hub → modules**, never peer-to-peer between modules. Command Center instructions enter only through the Telemetry Command Node, are validated against rover state, then routed. Every command is logged for mission replay and debugging.

## Logging, Mission Replay, and Debug Streaming

Friday Labs OS maintains a mission log sufficient to **replay what happened** if the Core Compute Hub crashes mid-mission. Policy is locked in [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) — local-first `ros2 bag` files on each Pi with a 7-day ring buffer, decision-level summaries streamed to the Command Center at 1 Hz, full bag sync on charger via WiFi. Separately, a **debug-streaming-service** on the Telemetry Command Node routes live debug data (logs, sensor dumps, stack traces) from any module to a **dedicated Command Center debug endpoint** (`mark1/<rover_id>/dbg/...`), isolated from mission telemetry and deprioritized against mission-critical traffic; signed and encrypted like every other channel per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md).

## Core Compute Hub Services (Friday Labs OS)

`friday-core-os` · `mission-planner` · `autonomy-manager` · `system-health-manager` · `sensor-fusion-manager` · `command-router` · `module-registry` · `fault-manager` · `safety-supervisor` · `logging-service`

## Open Design Areas

These shape Friday Labs OS and were resolved during Phase 1:

- **Power budgeting** — ✅ resolved in [Power Budget](../addendums/Power Budget.md) (60-90 cm bench prototype, 50-75 W envelope, 150 Wh battery, 2 hr target).
- **AI inference location** — ✅ resolved in [AI Inference Location](../addendums/AI Inference Location.md) (local on Pi 5 + Coral USB Accelerator, ~$140, ~6 W).
- **Module discovery / hot-swap** — ✅ discovery protocol locked in [Adaptive Research Module](../modules/Adaptive Research Module.md) (USB hot-plug + I2C scan). Mid-mission swap policy still open, to be locked in Phase 5 mission planner work.
- **Mission logging volume** — ✅ resolved in [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) (local-first, 7-day ring buffer, summaries streamed).
- **Software philosophy** — guiding principle, kept: strong algorithms + sensor fusion let *modest sensors* produce research-grade data; the value is in the software, the hardware is the platform.

## Build Phases for Friday Labs OS

**Phase 1 — Framework.** Linux base + ROS 2; define the module-agent contract, message schemas, heartbeat protocol, module registry, fault states, and safe-stop behavior.

**Phase 2 — Core services.** Build skeletons: `friday-core-os`, module-registry, system-health-manager, command-router, safety-supervisor, logging-service; stand up the Telemetry Node Agent and debug-streaming plumbing.

**Phase 3 — Communication.** Wire Core Compute Hub ↔ each module agent, and Telemetry Command Node ↔ Command Center.

**Phase 4 — Safety.** Heartbeat monitoring, failover detection, safe stop, telemetry recovery mode, backup ESP32 emergency beacon.

**Phase 5 — Autonomy & missions.** Mission planner, sensor fusion, mapping workflow, Spark deployment workflow.

---

Related: [Mark 1 Compute Architecture](Mark 1 Compute Architecture.md) · **Friday Labs** · **Spark** · [Telemetry Command Node](Telemetry Command Node.md) · [Mark 1 Index](../Mark 1 Index.md)
