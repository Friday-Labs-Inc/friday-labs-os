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

Mark 1 runs **two distinct OS images**, not one — reflecting the clean boundary between robotics compute and network gateway:

| Image | Target | Base | Stack |
|-------|--------|------|-------|
| **`friday-core-os`** | Core Hub (Pi 4B 8 GB), Lab Deck (future Pi) | Ubuntu 24.04 LTS | ROS 2 Jazzy + Friday Labs OS runtime |
| **`friday-telemetry-os`** | Telemetry Gateway (Pi 3B+ 1 GB) | Debian 12 Lite (headless) | systemd services, mosquitto, ModemManager — **no ROS 2** |

**Why two images:** the Telemetry Gateway is a **network boundary**, not a robot brain. Its job — route signed packets between the rover's internal MQTT bus and the outside world (dual 4G, LoRa, Wi-Fi) — is pure Linux networking. ROS 2 Jazzy would consume 300–400 MB on a 1 GB Pi 3B+, leaving nothing for ModemManager + dual modems + gateway routing. Keeping it lightweight also reduces the attack surface at the rover's internet-facing edge, speeds up boot and OTA, and means the gateway can stay alive longer on degraded power.

**Internal bridge:** Core Hub runs a local `mosquitto` broker on its Ethernet interface. The Telemetry Gateway subscribes to it and relays signed CBOR envelopes to the external Command Center EMQX broker (and vice versa). No DDS crosses the Core↔Telemetry boundary — the wire format is the same Ed25519-signed CBOR envelope used for the CC link.

**Safe-stop independence:** when Core Hub dies, the Locomotion ESP32's hardware watchdog fires safe-stop in 100 ms — completely independent of both Pis. The Telemetry Gateway does NOT command safe-stop; it reports "Core down" to the Command Center and activates the health beacon.

(Fedora was considered in the original draft and explicitly rejected; see [Mark 1 Index](../Mark 1 Index.md) resolved gaps.)

## Module 1: Core Compute Hub

**Role** — Primary brain. Runs main Friday Labs OS services, high-level autonomy, mission logic, planning, coordination, and decision-making.

**Hardware** — Raspberry Pi 4B (8 GB) running `friday-core-os` (Ubuntu 24.04 LTS + ROS 2 Jazzy). Future: Google Coral USB Accelerator for local AI inference (locked in [AI Inference Location](../addendums/AI Inference Location.md)); dedicated nav sensor (Intel RealSense D435i or equivalent, see [Sensor Ownership](../addendums/Sensor Ownership.md)). USB CDC links to the Locomotion and Aerial Bay ESP32s for micro-ROS; Ethernet link to Telemetry Gateway (internal MQTT bridge); [A/B partition layout](../addendums/OTA Update Strategy.md); connected to all major subsystems; receives processed data from other modules and sends commands to deck-level controllers.

**Responsibilities** — Run Friday Labs OS core services; ROS 2 master/service orchestration; mission planning; autonomous navigation logic; high-level behavior control; decision-level sensor fusion; receive telemetry from all decks; send commands to all decks; monitor system health; decide fallback actions; communicate with command center via the Telemetry Command Node; coordinate with Spark.

**The Core Hub should not do everything.** It must not be overloaded with raw sensor processing. Example: when mapping 5 acres of farmland or forest, heavy LiDAR and research capture is handled by the Adaptive Research Module — the Core Hub receives processed data, summaries, alerts, maps, and navigation-relevant outputs. This keeps the Core Hub focused on planning, safety, autonomy, command execution, and module coordination.

## Module 2: Telemetry Gateway

**Role** — Dedicated communication and recovery gateway. Manages all communication between Mark 1 and the outside world: command center, remote operator, mobile network, local wireless, and future long-range systems. This is a **network boundary, not a robot brain** — it routes signed packets, it does not process robotics data.

**Hardware** — Raspberry Pi 3B+ (1 GB) running `friday-telemetry-os` (Debian 12 Lite, headless — **no ROS 2**). Connected to Core Hub via Ethernet (internal MQTT bridge). Radio interfaces: 2× 4G LTE USB dongles (dual-carrier, Jio + Airtel), 1× Heltec LoRa32 V3 (ESP32-S3 + SX1262, USB-serial to Pi), Wi-Fi, Bluetooth. Plus a backup ESP32-WROOM-32 for emergency LoRa beacon. External link uses MQTT 5 over TLS 1.3 with per-rover mTLS — see [Command Center Protocol Security](../addendums/Command Center Protocol Security.md).

**Why no ROS 2:** every service on this node is a networking/routing job (ModemManager, mosquitto relay, LoRa bridge, failover logic). ROS 2 Jazzy would consume 300–400 MB of the 1 GB RAM for zero benefit. The internal bridge to Core Hub is plain MQTT over Ethernet — the same signed CBOR envelope format used for the CC link, no DDS translation needed.

**Software services** (`friday-telemetry-os.target`):

| Service | Job |
|---------|-----|
| `mosquitto` (relay) | Bridges internal MQTT (Core Hub) ↔ external EMQX (Command Center) |
| `modem-manager` | Manages dual 4G USB dongles, APN config, connection watchdog |
| `network-router` | iptables/nftables, route selection: 4G-1 → 4G-2 → LoRa → Wi-Fi |
| `lora-bridge` | Talks to Heltec LoRa32 over USB-serial, last-resort long-range link |
| `health-beacon` | Sends "rover alive" to CC even when Core Hub is dead |
| `esp32-watchdog` | Monitors backup ESP32; activates emergency LoRa beacon if both Pis die |

**Responsibilities** — Manage all telemetry channels; maintain command-center connection; handle remote control comms; manage radio failover routing (4G → 4G → LoRa → Wi-Fi); relay rover status and mission progress from Core Hub to CC; maintain heartbeat with the Core Hub over Ethernet; detect comms failure; enter beacon mode if the Core Hub fails; report "Core down" to Command Center for remote recovery.

**What the Telemetry Gateway does NOT do:** it does not sign or verify CBOR envelopes (the rover key stays on Core Hub), it does not command safe-stop (the Locomotion ESP32 watchdog handles that independently), and it does not run any ROS 2 nodes or process robotics data.

**Backup ESP32 role** — Not the main computer; an emergency support controller that broadcasts a LoRa beacon when both Pis are dead. Duties: minimal "Mark 1 alive, awaiting recovery" beacon over LoRa, basic status broadcast, wake/reboot signal to compute boards. It stays in low-power mode unless activated by failure-detection logic. Per [Authority Lease Protocol](../addendums/Authority Lease Protocol.md), the backup ESP32 holds **no command authority** — it does not issue motion, recovery, or stop commands. Motion safety when both Pis are dead is handled by the [Locomotion firmware watchdog](../addendums/Safe-Stop Latency Budget.md) (sub-100 ms, completely independent of the Pis).

## Module 3: Locomotion Control Unit

**Role** — Handles all movement and low-level mobility control. Receives high-level movement commands and locally controls motors, encoders, steering, and mobility safety — it must not depend on the Core Hub for every motor signal.

**Hardware** — ESP32-WROOM-32; 6× XD-37GB555 12 V brushed DC gearmotors with **built-in 64 CPR quadrature encoders** (read via ESP32 PCNT hardware counters — 2 GPIO per motor, 12 pins, zero CPU cost); 6× DRV8871 single H-bridge motor drivers (PWM via PCA9685 I2C); 4× 25 kg corner-steering servos (Perseverance-pattern; middle pair drive-only per [Mechanical Design Reference](../addendums/Mechanical Design Reference.md)); BNO085 IMU with on-chip sensor fusion; INA219 motor-bus current monitor; ESP32 hardware watchdog timer enforcing 100 ms safe-stop per [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md). See [Electronics BOM](../build/MK1_Electronics_BOM.md) for the full parts list.

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

Transport layers (three distinct domains):

1. **Robotics (Core Hub ↔ ESP32s):** ROS 2 / DDS for internal robotics messages; **USB-serial micro-ROS** between Core Hub Pi 4B and ESP32 modules. The four QoS profiles (`critical_reliable`, `state_default`, `sensor_stream`, `heartbeat`) and the schema rules live in [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).
2. **Internal bridge (Core Hub ↔ Telemetry Gateway):** **MQTT over Ethernet** (static IPs, internal subnet). Core Hub runs a local `mosquitto` broker; Telemetry Gateway subscribes. Wire format = the same Ed25519-signed CBOR envelopes used for the CC link. No DDS crosses this boundary.
3. **External (Telemetry Gateway ↔ Command Center):** **MQTT 5 over TLS 1.3 with per-rover mTLS** (locked in [Command Center Protocol Security](../addendums/Command Center Protocol Security.md)). The Telemetry Gateway relays signed envelopes from the internal broker to the external EMQX broker via whichever radio is alive (4G primary → 4G backup → LoRa → Wi-Fi).
4. **Local hardware:** I2C / SPI / UART within each deck.

**Core message types** — Heartbeat, health status, power state, module online/offline, sensor data, motor command, odometry, mission status, emergency stop, recovery command, communication status, Spark status, research payload status, fault report, log event.

## Health Monitoring and Fallback Behavior

Friday Labs OS must continuously monitor all modules.

**Health checks** — Heartbeats for Core Hub, Telemetry Node, Locomotion Unit, Research Module, and Aerial Companion Bay; plus power, communication, sensor, motor-controller, storage, temperature, and network status.

**Failure cases handled** — Core Hub failure; Telemetry Node failure; Locomotion failure; Research Module failure; Spark dock failure; communication loss; sensor failure; motor stall; low battery; overtemperature; storage full; software crash.

**Fallback rules**

- *Core Hub OK, Telemetry Gateway fails:* Core Hub logs fault; internal MQTT traffic queues locally; Core Hub can still operate autonomously but has no external comms; mission continues if safe; backup ESP32 activates emergency LoRa beacon if configured.
- *Core Hub fails, Telemetry Gateway alive:* Telemetry Gateway detects loss of internal MQTT heartbeat; reports "Core down" to Command Center via health-beacon service; allows CC to send recovery commands (power-cycle Core Hub via ESP32-controlled load switch); Locomotion ESP32 watchdog fires safe-stop independently (100 ms).
- *Both Core Hub and Telemetry Gateway fail, backup ESP32 alive:* ESP32 sends minimal emergency LoRa signal; maintains lowest-power "alive" beacon; waits for recovery or manual intervention; Locomotion ESP32 already in safe-stop.
- *Locomotion Unit loses command link:* stop motors safely; lock current state; report fault if possible.

## Command Center Integration

The Command Center communicates primarily through the Telemetry Command Node and should support: live rover status, communication status, battery/power status, mobility state, map progress, sensor health, research mission status, Spark status, manual control mode, autonomous mission upload, emergency stop, recovery command, and logs/diagnostics. Core Hub instructions arrive via the Telemetry Command Node — not random network paths.

## Software Services List

**Core Compute Hub** — friday-core-os, mission-planner, autonomy-manager, system-health-manager, sensor-fusion-manager, command-router, module-registry, fault-manager, safety-supervisor, logging-service.

**Telemetry Gateway** (`friday-telemetry-os`, no ROS 2) — mosquitto-relay, network-router, modem-manager, lora-bridge, health-beacon, esp32-watchdog.

**Locomotion Control Unit (firmware)** — motor-control-loop, steering-control-loop, encoder-reader, imu-reader, odometry-estimator, stall-detector, traction-monitor, safe-stop-handler, mobility-heartbeat.

**Adaptive Research Module** — lab-deck-manager, sensor-plugin-manager, lidar-capture-service, camera-capture-service, radar-adapter-service, environmental-sensor-service, mapping-service, research-data-logger, processed-data-publisher.

**Aerial Companion Bay** — spark-bay-controller, launch-sequence-manager, docking-state-monitor, charging-monitor, spark-communication-bridge, spark-mission-sync, bay-safety-checker.

## Provisioning Requirements

**`friday-core-os`** (Core Hub Pi 4B, future Lab Deck Pi) — **Ubuntu 24.04 LTS** base image with [A/B partition layout](../addendums/OTA Update Strategy.md); Friday Labs OS runtime; ROS 2 Jazzy; systemd `friday-core-os.target` per [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md); local `mosquitto` broker on Ethernet interface (internal MQTT bridge to Telemetry Gateway); logging per [Mission Logging and Replay](../addendums/Mission Logging and Replay.md); health monitoring agent; module identity file; signed-OTA update mechanism per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md); SSH/debug access; hardware interface permissions; time sync; crash recovery behavior.

**`friday-telemetry-os`** (Telemetry Gateway Pi 3B+) — **Debian 12 Lite** headless image; **no ROS 2**; systemd `friday-telemetry-os.target`; `mosquitto` relay bridging internal MQTT (Core Hub Ethernet) ↔ external EMQX (Command Center); ModemManager for dual 4G USB dongles; `lora-bridge` service for Heltec LoRa32 (USB-serial); `network-router` for radio failover (4G → 4G → LoRa → Wi-Fi); `health-beacon` for Core-down reporting; `esp32-watchdog` for backup ESP32 emergency beacon; signed-OTA update over cellular; module identity (`MARK1-TEL-001`); SSH/debug access; time sync.

**ESP32 firmware** (Locomotion Unit, Telemetry backup, Aerial Companion Bay) — Firmware identity (`MARK1-MOB-001`, `MARK1-TEL-BACKUP-001`, `MARK1-SPARKBAY-001`); USB-serial at 921600+ baud to host Pi (or LoRa for the backup); hardware Task WDT at 100 ms; heartbeat protocol per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md); safe-state behavior per [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md); [dual-bank ESP-IDF OTA](../addendums/OTA Update Strategy.md); fault reporting; low-power support where required.

## Module Identity

Every module has a unique identity, e.g. `MARK1-CORE-001`, `MARK1-TEL-001`, `MARK1-MOB-001`, `MARK1-LAB-001`, `MARK1-SPARKBAY-001`.

Each module reports: module name, hardware type, software version, firmware version, health state, uptime, last error, power state, communication status.

## Data Flow Example: 5-Acre Mapping Mission

1. Command Center sends signed mission envelope to EMQX broker.
2. Telemetry Gateway (Pi 3B+) receives it over 4G/LoRa and relays to internal MQTT (Ethernet).
3. Core Hub (Pi 4B) picks up the envelope, verifies the CC signature, extracts the mission.
4. Core Hub sends movement goals to Locomotion ESP32 (USB-serial micro-ROS).
5. Lab Deck starts LiDAR/camera/environmental capture.
6. Locomotion ESP32 sends odometry to Core Hub (micro-ROS).
7. Lab Deck builds map segments and detects terrain features.
8. Lab Deck sends processed map data to Core Hub (ROS 2 DDS).
9. Core Hub updates route based on terrain and mission progress.
10. Core Hub signs a progress envelope, publishes to internal MQTT.
11. Telemetry Gateway relays the signed envelope to EMQX over 4G/LoRa → Command Center.
12. If needed, Core Hub commands Spark launch via Aerial Bay ESP32 (USB-serial micro-ROS).
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

- **Core Compute Hub** (Pi 4B, `friday-core-os`) — Main Friday Labs OS brain, ROS 2, autonomy, mission logic, envelope signing.
- **Telemetry Gateway** (Pi 3B+, `friday-telemetry-os`) — Dedicated network gateway, dual 4G + LoRa + Wi-Fi routing, CC link, health beacon. **No ROS 2.**
- **Locomotion Control Unit** (ESP32-WROOM-32) — Real-time movement, 6× DRV8871 motor drivers, 4× steering servos, built-in quadrature encoders, BNO085 IMU, safe-stop watchdog.
- **Adaptive Research Module / Lab Deck** (future Pi, `friday-core-os`) — Dedicated sensor processing and research payload compute layer.
- **Aerial Companion Bay** (ESP32-WROOM-32) — Spark drone launch, dock, charge, and coordination.

Two OS images, three transport domains, five modules. The most important architectural decisions: (1) **do not make the Core Hub process everything** — heavy sensor work goes to the Lab Deck, communication to the Telemetry Gateway, movement to the Locomotion Unit, and drone operations to the Aerial Bay; (2) **the Telemetry Gateway is a network boundary, not a robot brain** — no ROS 2, no crypto, no robotics data processing — just packet routing and radio failover.

---

Related: **Friday Labs** · [Friday Labs OS](Friday Labs OS Architecture.md) · **Spark** · [Mark 1 Index](../Mark 1 Index.md)
