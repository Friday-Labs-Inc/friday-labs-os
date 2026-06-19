# Mark 1 Compute Architecture

> Software team handoff spec for the Mark 1 modular compute architecture.
> **Version:** Draft 1.0 · **Purpose:** Software Team Handoff

## Product Context

Mark 1 is an autonomous modular research rover by **Friday Labs**. Core use cases: public welfare, environmental research, agriculture monitoring, forest monitoring, non-destructive surveillance, safety/security monitoring, field data collection, multi-sensor terrain awareness, and companion drone deployment via **Spark**.

Mark 1 is **not** designed for explosive or destructive use — it is for research, monitoring, autonomy, surveillance, and data intelligence. The rover must be modular, resilient, and expandable: each major subsystem owns its own compute/control layer so the rover never depends on a single computer for everything.

## High-Level Architecture

Mark 1 uses a **distributed modular compute architecture** split into five modules:

1. [Core Compute Hub](#module-1-core-compute-hub)
2. [Telemetry Command Node](#module-2-telemetry-command-node)
3. [Locomotion Control Unit](#module-3-locomotion-control-unit)
4. [Adaptive Research Module / Lab Deck](#module-4-adaptive-research-module-lab-deck)
5. [Aerial Companion Bay](#module-5-aerial-companion-bay)

Each module operates as an independent subsystem but communicates through [Friday Labs OS](Friday Labs OS Architecture.md). The Core Compute Hub is the main brain, but every module must support local processing, health reporting, and fallback behavior.

## Operating System Direction

The platform is provisioned under [Friday Labs OS](Friday Labs OS Architecture.md). All Pi compute modules run Ubuntu 24.04 LTS — the official ROS 2 Jazzy target with the largest robotics community. (Fedora was considered in the original draft and explicitly rejected; see [Mark 1 Index](../Mark 1 Index.md) resolved gaps.)

The system should support: ROS 2-based modular communication, inter-process messaging, health monitoring, fault detection, deck/module discovery, telemetry routing, sensor data streaming, mission logging, remote command execution, emergency fallback mode, and companion drone integration.

## Module 1: Core Compute Hub

**Role** — Primary brain. Runs main Friday Labs OS services, high-level autonomy, mission logic, planning, coordination, and decision-making.

**Hardware** — Raspberry Pi 5 (8 GB) with Google Coral USB Accelerator for local AI inference (locked in [AI Inference Location](../addendums/AI Inference Location.md)); dedicated nav sensor (Intel RealSense D435i or equivalent, see [Sensor Ownership](../addendums/Sensor Ownership.md)); USB CDC links to the Locomotion and Aerial Bay ESP32-S3s for micro-ROS; Ubuntu 24.04 LTS base image with [A/B partition layout](../addendums/OTA Update Strategy.md); connected to all major subsystems; receives processed data from other modules and sends commands to deck-level controllers.

**Responsibilities** — Run Friday Labs OS core services; ROS 2 master/service orchestration; mission planning; autonomous navigation logic; high-level behavior control; decision-level sensor fusion; receive telemetry from all decks; send commands to all decks; monitor system health; decide fallback actions; communicate with command center via the Telemetry Command Node; coordinate with Spark.

**The Core Hub should not do everything.** It must not be overloaded with raw sensor processing. Example: when mapping 5 acres of farmland or forest, heavy LiDAR and research capture is handled by the Adaptive Research Module — the Core Hub receives processed data, summaries, alerts, maps, and navigation-relevant outputs. This keeps the Core Hub focused on planning, safety, autonomy, command execution, and module coordination.

## Module 2: Telemetry Command Node

**Role** — Dedicated communication and recovery subsystem. Manages all communication between Mark 1 and the outside world: command center, remote operator, mobile network, local wireless, and future long-range systems.

**Hardware** — Raspberry Pi 4 (4 GB) running the main Node services plus a backup ESP32-S3 for emergency support. Comms interfaces: LoRa, Bluetooth, Wi-Fi, 2G, 4G, 5G modem, plus future satellite and long-range radio support. External link uses MQTT 5 over TLS 1.3 with per-rover mTLS — see [Command Center Protocol Security](../addendums/Command Center Protocol Security.md).

**Responsibilities** — Manage all telemetry channels; maintain command-center connection; handle remote control comms; manage fallback routing; stream rover status, selected sensor data, and mission progress; maintain heartbeat with the Core Hub; detect comms failure; support recovery mode if the Core Hub fails; provide partial control/recovery when main compute is down.

**Backup ESP32-S3 role** — Not the main computer; an emergency support controller that broadcasts a LoRa beacon when both Pis are dead. Duties: minimal "Mark 1 alive, awaiting recovery" beacon over LoRa, basic status broadcast, wake/reboot signal to compute boards. It stays in low-power mode unless activated by failure-detection logic. Per [Authority Lease Protocol](../addendums/Authority Lease Protocol.md), the backup ESP32-S3 holds **no command authority** — it does not issue motion, recovery, or stop commands. Motion safety when both Pis are dead is handled by the [Locomotion firmware watchdog](../addendums/Safe-Stop Latency Budget.md) (sub-100 ms, completely independent of the Pis).

## Module 3: Locomotion Control Unit

**Role** — Handles all movement and low-level mobility control. Receives high-level movement commands and locally controls motors, encoders, steering, and mobility safety — it must not depend on the Core Hub for every motor signal.

**Hardware** — ESP32-S3 with native USB OTG; 6× brushed DC geared drive motors with 3× dual H-bridges; 4× corner-steering hobby servos (Perseverance-pattern; middle pair drive-only per [Mechanical Design Reference](../addendums/Mechanical Design Reference.md)); 6× AS5600 magnetic encoders via I2C multiplexer; BNO085 IMU with on-chip sensor fusion; INA219 motor-bus current monitor; ESP32-S3 hardware watchdog timer enforcing 100 ms safe-stop per [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md). See [Locomotion Control Unit](../modules/Locomotion Control Unit.md) for the full BOM.

**Responsibilities** — Control drive motors and steering actuators; read encoders and IMU; monitor motor current/load; detect wheel stall, slip, and uneven traction; maintain local mobility state; execute movement commands from the Core Hub; report odometry and faults; enter safe stop on lost comms.

**Mobility sensors** — Wheel encoders, IMU, motor current sensors, steering position feedback, drive-system voltage/current monitoring, optional outdoor GPS, optional wheel/motor temperature sensing.

**Software behavior** — The Core Hub sends commands like: move forward, stop, turn left/right, set velocity, set steering angle, execute path segment, enter safe stop. The unit converts these into real motor and steering behavior.

## Module 4: Adaptive Research Module / Lab Deck

**Role** — Dedicated research and sensor-processing module ("Lab Deck"). Handles plug-and-play research sensors, high-volume capture, and mission-specific analysis.

**Hardware** — Dedicated Raspberry Pi 5 (8 GB); no co-processor (the Pi 5 handles all sensor I/O directly per the locked [Adaptive Research Module](../modules/Adaptive Research Module.md) spec); sensor expansion ports; power/data interface to the common rover bus; modular sensor payload support.

**Why it needs a Pi** — An ESP32 is not enough: the deck may handle LiDAR, camera, and radar data, environmental sensor arrays, data logging, plug-and-play discovery, local processing, mapping workloads, and research mission scripts. It therefore needs its own full Linux compute layer.

**Responsibilities** — Manage research sensors; capture LiDAR/imaging data; process environmental data; run mapping workloads; handle plug-and-play sensor modules; send processed outputs to the Core Hub; store raw research data locally when needed; run domain-specific research logic; support agriculture, forest, surveillance, and scientific payloads.

**Supported sensor categories (future)** — LiDAR; camera/vision; thermal camera; radar; soil temperature; soil moisture; water level; humidity; air temperature; wind; gas/environmental; insect/bird/wildlife movement; human/animal movement detection; agriculture weed-growth monitoring.

**Relationship with Core Hub** — Process heavy data locally; send the Core Hub only what it needs. Example (5-acre LiDAR map): the Core Hub receives map segments, obstacle updates, area-coverage progress, detected objects, alerts, navigation-relevant summaries, and research metadata — never every raw stream.

## Shared LiDAR and Camera Design

The main LiDAR and main camera may serve both the Core Hub and the Adaptive Research Module, so the architecture should support shared sensor access.

Preferred model: one module owns the physical sensor connection; others receive data via a software stream; avoid unsafe electrical dual-connection unless hardware supports it.

Recommended design: publish the core navigation LiDAR/camera stream over ROS 2; the Research Module subscribes; if the Research Module owns a sensor, it publishes processed data to the Core Hub; sensor ownership must be clearly defined in software config. Possible stream types: LiDAR point cloud, camera image, depth data, object detection output, terrain classification, map updates.

## Module 5: Aerial Companion Bay

**Role** — Integration module for **Spark**, the companion drone launched by Mark 1 to extend field awareness, provide aerial surveillance, capture video, perform aerial mapping, and assist where Mark 1 cannot reach.

**Hardware** — ESP32-S3 owned by the Core Compute Hub via USB CDC; passive V-cradle for launch and dock; single servo-controlled lock; pogo pin contacts for charging with 2 dedicated UART pins to Spark; IR break-beam, weight pad, limit switches, and INA219 current monitor for the 8 pre-launch safety interlocks; ESP32-S3 hardware watchdog (lock engages on trip). See [Aerial Companion Bay](../modules/Aerial Companion Bay.md) for the full BOM and [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md) for the launch-authority boundary.

**Responsibilities** — Detect Spark docked/undocked state; control launch mechanism; control landing/recovery lock; manage Spark charging; exchange mission data with Spark; report Spark status to the Core Hub; support launch and abort-launch commands; verify bay safety before launch; confirm Spark is physically secured before rover movement.

**Software module name** — *Spark Deployment & Coordination Service*.

**Spark future capabilities** — Video feed, lightweight LiDAR or visual SLAM, aerial mapping, emergency data ferry, terrain scouting, communication relay, return-to-rover, return-to-home.

## Inter-Module Communication

Transport: ROS 2 / DDS for internal robotics messages; **MQTT 5 over TLS 1.3 with per-rover mTLS** for Command Center comms (locked in [Command Center Protocol Security](../addendums/Command Center Protocol Security.md)); I2C / SPI / UART for local hardware; Ethernet or Wi-Fi between Pi modules when bandwidth is needed; **USB CDC over micro-ROS** between Pis and ESP32-S3 modules. The four QoS profiles (`critical_reliable`, `state_default`, `sensor_stream`, `heartbeat`) and the schema rules live in [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).

**Core message types** — Heartbeat, health status, power state, module online/offline, sensor data, motor command, odometry, mission status, emergency stop, recovery command, communication status, Spark status, research payload status, fault report, log event.

## Health Monitoring and Fallback Behavior

Friday Labs OS must continuously monitor all modules.

**Health checks** — Heartbeats for Core Hub, Telemetry Node, Locomotion Unit, Research Module, and Aerial Companion Bay; plus power, communication, sensor, motor-controller, storage, temperature, and network status.

**Failure cases handled** — Core Hub failure; Telemetry Node failure; Locomotion failure; Research Module failure; Spark dock failure; communication loss; sensor failure; motor stall; low battery; overtemperature; storage full; software crash.

**Fallback rules**

- *Core Hub OK, Telemetry Node fails:* Core Hub attempts telemetry restart/recovery; if possible activate backup ESP32 minimal comms; log fault; continue mission only if safe.
- *Core Hub fails, Telemetry Node alive:* Telemetry Pi enters recovery mode; tries to re-establish the Core Hub; sends emergency status to command center; allows limited recovery command; triggers safe stop via the Locomotion Unit if possible.
- *Both Core Hub and Telemetry Pi fail, backup ESP32 alive:* ESP32 sends minimal emergency signal; maintains lowest-power "alive" beacon if supported; waits for recovery or manual intervention.
- *Locomotion Unit loses command link:* stop motors safely; lock current state; report fault if possible.

## Command Center Integration

The Command Center communicates primarily through the Telemetry Command Node and should support: live rover status, communication status, battery/power status, mobility state, map progress, sensor health, research mission status, Spark status, manual control mode, autonomous mission upload, emergency stop, recovery command, and logs/diagnostics. Core Hub instructions arrive via the Telemetry Command Node — not random network paths.

## Software Services List

**Core Compute Hub** — friday-core-os, mission-planner, autonomy-manager, system-health-manager, sensor-fusion-manager, command-router, module-registry, fault-manager, safety-supervisor, logging-service.

**Telemetry Command Node** — telemetry-router, network-manager, modem-manager, lora-service, bluetooth-service, command-center-link, fallback-manager, emergency-esp32-bridge, remote-command-proxy.

**Locomotion Control Unit (firmware)** — motor-control-loop, steering-control-loop, encoder-reader, imu-reader, odometry-estimator, stall-detector, traction-monitor, safe-stop-handler, mobility-heartbeat.

**Adaptive Research Module** — lab-deck-manager, sensor-plugin-manager, lidar-capture-service, camera-capture-service, radar-adapter-service, environmental-sensor-service, mapping-service, research-data-logger, processed-data-publisher.

**Aerial Companion Bay** — spark-bay-controller, launch-sequence-manager, docking-state-monitor, charging-monitor, spark-communication-bridge, spark-mission-sync, bay-safety-checker.

## Provisioning Requirements

**Raspberry Pi / Linux compute** (Core Hub, Telemetry Node, Research Module) — **Ubuntu 24.04 LTS** base image with [A/B partition layout](../addendums/OTA Update Strategy.md); Friday Labs OS runtime; ROS 2 Jazzy; systemd (`friday-core-os.target` / `friday-telemetry-os.target` per [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md)); network config; logging per [Mission Logging and Replay](../addendums/Mission Logging and Replay.md); health monitoring agent; module identity file; signed-OTA update mechanism per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md); SSH/debug access; hardware interface permissions; time sync; crash recovery behavior.

**ESP32-S3 firmware** (Locomotion Unit, Telemetry backup, Aerial Companion Bay) — Firmware identity (`MARK1-MOB-001`, `MARK1-TEL-BACKUP-001`, `MARK1-SPARKBAY-001`); USB CDC at 921600+ baud (or LoRa for the backup); hardware Task WDT at 100 ms; heartbeat protocol per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md); safe-state behavior per [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md); [dual-bank ESP-IDF OTA](../addendums/OTA Update Strategy.md); fault reporting; low-power support where required.

## Module Identity

Every module has a unique identity, e.g. `MARK1-CORE-001`, `MARK1-TEL-001`, `MARK1-MOB-001`, `MARK1-LAB-001`, `MARK1-SPARKBAY-001`.

Each module reports: module name, hardware type, software version, firmware version, health state, uptime, last error, power state, communication status.

## Data Flow Example: 5-Acre Mapping Mission

1. Command Center sends mission to Mark 1.
2. Telemetry Command Node receives mission.
3. Core Compute Hub validates mission.
4. Core Hub sends movement goals to Locomotion Control Unit.
5. Lab Deck starts LiDAR/camera/environmental capture.
6. Locomotion Unit sends odometry to Core Hub.
7. Lab Deck builds map segments and detects terrain features.
8. Lab Deck sends processed map data to Core Hub.
9. Core Hub updates route based on terrain and mission progress.
10. Telemetry Node sends progress to Command Center.
11. If needed, Core Hub commands Spark launch.
12. Aerial Companion Bay launches Spark.
13. Spark provides aerial view or mapping data.
14. Mission completes.
15. Data is logged and synchronized.

## Design Principles

- Modular by design; each deck has a clear responsibility.
- Core Hub is the brain, not the bottleneck.
- Heavy research workloads run on the Lab Deck; communication has its own compute layer.
- Emergency fallback must exist; locomotion must fail safe.
- Spark is part of the Mark 1 ecosystem.
- All modules report health; all faults are logged.
- No destructive behavior — built for research, public welfare, agriculture, forestry, safety, and surveillance.
- Future-ready for radar, LiDAR, AI, drones, and multi-agent orchestration.

## Immediate Software Team Tasks

**Phase 1 — Architecture Setup:** define module names/responsibilities; choose final base OS for Pi boards; define ROS 2 communication model, message schemas, heartbeat protocol, module registry, fault states, and safe-stop behavior.

**Phase 2 — Core Services:** build skeletons for Core Hub, Telemetry Node, Locomotion firmware, Lab Deck service, and Spark Bay firmware.

**Phase 3 — Communication:** Core Hub ↔ Telemetry Node; Core Hub ↔ Locomotion Unit; Core Hub ↔ Lab Deck; Core Hub ↔ Spark Bay; Telemetry Node ↔ Command Center.

**Phase 4 — Safety:** heartbeat monitoring; failover detection; safe stop; telemetry recovery mode; backup ESP32 emergency signal logic.

**Phase 5 — Sensor & Mission Integration:** LiDAR stream; camera stream; odometry; environmental sensor plugins; mapping mission workflow; Spark deployment workflow.

## Final Architecture Summary

- **Core Compute Hub** — Main Friday Labs OS brain and autonomy manager.
- **Telemetry Command Node** — Dedicated communication, command-center link, and recovery compute layer.
- **Locomotion Control Unit** — Real-time movement, motor, steering, encoder, and IMU control.
- **Adaptive Research Module / Lab Deck** — Dedicated sensor processing and research payload compute layer.
- **Aerial Companion Bay** — Spark drone launch, dock, charge, and coordination.

This gives Mark 1 a resilient autonomous platform for public welfare, agriculture, forestry, research, surveillance, and future multi-agent robotic ecosystems. The most important architectural decision: **do not make the Core Hub process everything** — heavy sensor work goes to the Adaptive Research Module, communication to the Telemetry Command Node, movement to the Locomotion Control Unit, and drone operations to the Aerial Companion Bay.

---

Related: **Friday Labs** · [Friday Labs OS](Friday Labs OS Architecture.md) · **Spark** · [Mark 1 Index](../Mark 1 Index.md)
