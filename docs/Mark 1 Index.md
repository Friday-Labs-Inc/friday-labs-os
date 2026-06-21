# Mark 1 Index

> Map of the **Friday Labs** Mark 1 rover design dossier. Start here.

## What Mark 1 Is

An autonomous modular research rover for public welfare, agriculture, forestry, environmental research, non-destructive surveillance, and safety monitoring — with a companion drone (**Spark**). Distributed compute across five modules so no single computer is a bottleneck or a single point of failure. Built to do research-grade work with modest, cost-optimized sensors by leaning on strong software and sensor fusion rather than expensive hardware. No destructive use.

## The Documents

**Foundation:**
- [Mark 1 Compute Architecture](architecture/Mark 1 Compute Architecture.md) — the system overview: five modules, responsibilities, data flow, design principles.
- [Friday Labs OS Architecture](architecture/Friday Labs OS Architecture.md) — the brain software on the Core Compute Hub; orchestration, health, fault handling, autonomy, the module-agent model.
- [Telemetry Command Node](architecture/Telemetry Command Node.md) — communication, recovery, and internet-gateway subsystem; multi-path cellular routing, ESP32 emergency beacon, debug streaming.
- [ROS 2 Interface and Message Contract](architecture/ROS 2 Interface and Message Contract.md) — the shared interface layer that binds the OS and all agents; **build this first**.
- [Mark 1 Simulation and Dev Environment](architecture/Mark 1 Simulation and Dev Environment.md) — how to prove the stack in Gazebo before hardware; module-swap table and seven-stage bring-up.

**Phase 1 design-gap addendums (locked decisions):**
- [Authority Lease Protocol](addendums/Authority Lease Protocol.md) — resolves split-brain; 2 s lease, 500 ms renew, ESP32 beacon-only.
- [Safe-Stop Latency Budget](addendums/Safe-Stop Latency Budget.md) — 100 ms p99 firmware watchdog path; active motor hold + steering frozen.
- [Sensor Ownership](addendums/Sensor Ownership.md) — Core Hub has its own nav sensor, never depends on Lab Deck for perception.
- [Power Budget](addendums/Power Budget.md) — 60-90 cm chassis, 50-75 W envelope, 150 Wh battery, 2 hr target mission.
- [AI Inference Location](addendums/AI Inference Location.md) — local on Pi 5 + Coral USB Accelerator, ~$140, ~6 W.
- [friday_msgs Schema Conventions](addendums/friday_msgs Schema Conventions.md) — packed semver, frame conventions, bounded arrays, command auth fields.
- [Command Center Protocol Security](addendums/Command Center Protocol Security.md) — mTLS + signed commands + nonce + expiry from day one.
- [OTA Update Strategy](addendums/OTA Update Strategy.md) — A/B partition with auto-rollback for Pi and ESP32.
- [Mission Logging and Replay](addendums/Mission Logging and Replay.md) — local-first ros2 bag replay, summaries streamed.
- [Stage 5 Acceptance Criteria](addendums/Stage 5 Acceptance Criteria.md) — quantitative p99 budgets for every fault-injection scenario.
- [Spark Authority and friday-core-os Definition](addendums/Spark Authority and friday-core-os Definition.md) — Bay is launch interface, not flight brain; `friday-core-os` is the systemd target.
- [Mechanical Design Reference](addendums/Mechanical Design Reference.md) — NASA Perseverance rover as the locked mechanical-anatomy reference; 6 drive + 4 corner steer; four locomotion modes.
- [mmWave Human Detection](addendums/mmWave Human Detection.md) — RD-03D mmWave radar baseline on the Lab Deck; fog/dark/foliage-piercing detection complementing camera + LiDAR; LoRa sentry network deferred to Mark 2.

**Electronics (deck-by-deck electrical design):**
- [Electronics Backbone](electronics/Electronics Backbone.md) — shared electrical foundation: distributed power tree, NC-loop physical E-stop, single-point star ground, central fusing, M8/M12 bulkhead connectors, custom-PCB build medium. **Read before the per-deck docs.**
- [Core Hub Electronics](electronics/Core Hub Electronics.md) — buck→GPIO+override, powered USB hub, conduction cooling, NVMe, supercap shutdown.
- [Telemetry Node Electronics](electronics/Telemetry Node Electronics.md) — dual independent LoRa, 4G M.2 (5G-ready), backup-ESP32 reboot authority, mast antennas.
- [Locomotion Electronics](electronics/Locomotion Electronics.md) — Cytron drivers, full galvanic isolation, parking-pawl slope hold, layered safe-stop.
- [Lab Deck Electronics](electronics/Lab Deck Electronics.md) — eFuse + isolated-I2C plug-and-play expansion ports.
- [Aerial Bay Electronics](electronics/Aerial Bay Electronics.md) — bistable over-center lock, self-charging Spark.

**Build packages (deck-by-deck, buildable):**
- [Locomotion Deck — Build Package](build/Locomotion Deck - Build Package.md) — bottom deck: electrical BOM, ESP32-S3 pinout/wiring map, power-domain & isolation diagram, assembly + bench bring-up order. Built on JPL Open Source Rover mechanics + the Friday Labs locked electronics stack.
- [Locomotion Deck — Pin-Level Schematic](build/Locomotion Deck - Pin-Level Schematic.md) — net-by-net schematic spec: ESP32-S3 pin assignment, ISO7741 isolation channel map, every connection, passives/protection with values, fail-safe-on-signal-loss nets, and a KiCad-verify checklist.
- [Power & E-stop Backbone — Build Package](build/Power and E-stop Backbone - Build Package.md) — the shared electrical foundation: 4S Li-ion + smart BMS, RAW/SW power tree, fail-open E-stop (contactor + solid-state pre-switch), central fusing, bus-fail signal, star ground, M12 inter-deck harness. Build before bench-powering any deck.
- [Deck Layout, Sizing & CG](build/Deck Layout, Sizing and CG.md) — **proposed** deck packaging + electronics-driven sizing check + analytical center-of-gravity (CG ~16 mm rear, ~217 mm high; tip angles ~53°/55° — very stable). Closes the deck-footprint open item; 3D verification pending in Blender.

**Onboarding (read after the dossier):**
- [Phase 1 Implementation Kickoff](onboarding/Phase 1 Implementation Kickoff.md) — day-zero guide for any engineer joining the build; 4-week ramp from "haven't read the dossier" to "contributing code." Hand this to any new joiner (including yourself after a break).

**Software (the living Software Manual — grows one chapter per foundation phase, written in parallel with the code):**
- [Friday Labs OS — Software Manual](software/Friday Labs OS Software Manual.md) — **start here for the software.** The big-picture architecture, the workspace map, build/run + the dev workflow, the debugging toolkit, a plain-language glossary, and the foundation-phase map. Each finished phase adds a chapter.
  - [Phase 0 — Genesis: The First Line of Code](software/Phase 0 - Genesis - The First Line of Code.md) — **read first.** From an empty folder to Friday Labs' literal first line of code (`uint8 protocol_major`) and the first program that runs; the from-zero origin story any newcomer can follow.
  - [Phase 2 — The Walking Skeleton](software/Phase 2 - Walking Skeleton.md) — first running software (lifecycle orchestration, Stage 2): Core Hub registry + supervisor + health monitor and the Locomotion agent stub on the reusable `ModuleAgent` base. Beginner-traceable walk-through: boot trace, design rationale, debugging guide, verification. Code in `src/` (`friday_msgs`, `friday_module_agent`, `friday_core_hub`, `friday_locomotion`).
  - [Phase 3 — Closed-Loop Motion](software/Phase 3 - Closed-Loop Motion.md) — first *moving* behavior: `MotionCommand` → unicycle motion model → `nav_msgs/Odometry` (verified command-to-odometry loop on the `odom` frame).
  - [Phase 3 — Command Center Boundary](software/Phase 3 - Command Center Boundary.md) — the guarded external door: the Telemetry Node Agent validates Ed25519-signed, CBOR MQTT commands (allowlist + nonce + expiry), republishing valid ones to ROS and rejecting forged/replayed/expired (live-verified). Completes foundation Phase 3.

**Command Center (operator application — design blueprint):**
- [Command Center Application Blueprint](command-center/Command Center Application Blueprint.md) — system architecture for the operator-facing app that commands/monitors the fleet over the secure boundary. **Hybrid: Frappe control plane** (rovers/operators/missions/audit/RBAC/REST) **+ a dedicated MQTT broker + async bridge + time-series DB** for the real-time data plane; OIDC login + local-HSM command signing; Foxglove for live viz. Architecture diagram, phased build plan, and a second-pass tech review.
- [Architecture Review — 7-Expert Comparative Analysis](command-center/Architecture Review - 7-Expert Comparative Analysis.md) — seven senior architects (application · system · connectivity · radio/RF · cloud · data lake · data pipeline) reviewed the design; scorecard, ranked consensus gaps (nonce durability, offline-revocation handshake, edge↔cloud sync contract, the LoRa-e-stop correction, concrete TSDB), cross-dimension conflicts, and a P0/P1/P2 fix plan.
- [Deployment, Connectivity & Fleet Monitoring](command-center/Deployment, Connectivity & Fleet Monitoring.md) — **edge-first topology**: the Local Command Center (broker + console + signing) runs at the *site* so field control survives an internet cut; cloud is a roll-up. The 20–30 km field-link comms tiers (LoRa emergency · MANET mesh · 5 GHz directional · satellite backhaul), and **Friday Labs' own device-health / fault-detection plane** (catch a failure before the customer does; opt-in / air-gappable for defense). Topology diagram included.

## The Five Modules

| Module | Role | Compute | Spec status |
|---|---|---|---|
| Core Compute Hub | Brain — runs Friday Labs OS, autonomy, fusion | Pi / SBC | Covered in OS doc |
| Telemetry Command Node | Comms, recovery, internet gateway | Pi + backup ESP32 | ✅ Standalone spec |
| Locomotion Control Unit | Real-time motion, motor/steer/encoder/IMU | ESP32-S3 | ✅ [Locomotion Control Unit](modules/Locomotion Control Unit.md) |
| Adaptive Research Module (Lab Deck) | Sensor capture + processing, mapping | Pi 5 (no co-processor) | ✅ [Adaptive Research Module](modules/Adaptive Research Module.md) |
| Aerial Companion Bay | Spark launch/dock/charge/coordinate | ESP32-S3 | ✅ [Aerial Companion Bay](modules/Aerial Companion Bay.md) |

## Key Decisions (Locked)

- Friday Labs OS runs **on the Core Compute Hub** and orchestrates the rest via the module-agent contract.
- Module agents are **ROS 2 lifecycle nodes**; the registry + safety-supervisor drive transitions (Nav2 pattern).
- One shared `friday_msgs` interface package is the single source of truth; reuse `sensor_msgs`/`nav_msgs`/`geometry_msgs`.
- Heartbeat/fault detection rides on DDS Deadline/Liveliness QoS **plus** an app-level check.
- **Offline-first autonomy** — the Core Compute Hub has no direct internet; cloud is optional and brokered through the Telemetry Command Node.
- Telemetry Command Node is a **peer with failure authority**, not a subordinate.
- **Spark is semi-autonomous**; the Bay is the physical interface, not the flight brain. Multi-Spark swarms are a Mark 2/3 future.
- ESP32 modules join the DDS graph via **micro-ROS / Micro XRCE-DDS**; the Command Center link is MQTT-class, not DDS over WAN.
- Debug streaming to a dedicated Command Center endpoint: **provision now, build in Phase 2**.

## Build Sequence

1. **Phase 1 — Foundation:** build `friday_msgs` and the lifecycle-node base; lock message schemas, QoS profiles, heartbeat protocol. *(See the ROS 2 Interface and Message Contract.)*
2. **Phase 2 — Core services:** Core Compute Hub services (registry, health, command-router, fault-manager, safety-supervisor, logging); Telemetry Node Agent; debug-streaming plumbing.
3. **Phase 3 — Communication:** wire Core Compute Hub ↔ each module agent; Telemetry Command Node ↔ Command Center.
4. **Phase 4 — Safety:** heartbeat monitoring, failover, safe stop, telemetry recovery mode, ESP32 emergency beacon.
5. **Phase 5 — Autonomy & missions:** mission planner, sensor fusion, mapping workflow, Spark deployment.

Validate every phase in **Gazebo** before hardware — see [Mark 1 Simulation and Dev Environment](architecture/Mark 1 Simulation and Dev Environment.md). Fault injection (Stage 5) is where the real-time safe-stop path and split-brain authority get tested.

## Still Pending (Before / During Build)

- All three module specs are complete: [Locomotion Control Unit](modules/Locomotion Control Unit.md), [Adaptive Research Module](modules/Adaptive Research Module.md), [Aerial Companion Bay](modules/Aerial Companion Bay.md).
- **Module discovery / hot-swap** protocol for plug-and-play research sensors on the Lab Deck (Core Hub nav sensors do NOT hot-swap; see [Sensor Ownership](addendums/Sensor Ownership.md)).
- **Safety validation** of the micro-ROS stack before field/ruggedized deployment (ISO 26262 considerations).
- **Specific battery, BMS, and chassis kit selection** within the locked [Power Budget](addendums/Power Budget.md) envelope.
- **Friday Labs CA setup** — provisioning workflow, HSM for CA root (referenced in [Command Center Protocol Security](addendums/Command Center Protocol Security.md)).

## Resolved (Phase 1)

| Gap | Decision | Addendum |
|---|---|---|
| Split-brain authority | 2 s lease, 500 ms renew, ESP32 beacon-only, in-memory | [Authority Lease Protocol](addendums/Authority Lease Protocol.md) |
| Safe-stop latency | 100 ms p99, hardware watchdog, active motor hold + steering frozen | [Safe-Stop Latency Budget](addendums/Safe-Stop Latency Budget.md) |
| Sensor ownership | Core has dedicated nav sensor; Lab Deck never on nav critical path | [Sensor Ownership](addendums/Sensor Ownership.md) |
| Power budget | 60-90 cm bench prototype, 50-75 W envelope, 150 Wh battery | [Power Budget](addendums/Power Budget.md) |
| AI inference location | Local on Pi 5 + Coral USB Accelerator | [AI Inference Location](addendums/AI Inference Location.md) |
| `friday_msgs` schema discipline | Packed semver, frame conventions, bounded arrays, command auth | [friday_msgs Schema Conventions](addendums/friday_msgs Schema Conventions.md) |
| Command Center auth | mTLS + per-operator Ed25519 signing + nonce + expiry | [Command Center Protocol Security](addendums/Command Center Protocol Security.md) |
| Base Linux distro | Ubuntu 24.04 LTS (not Fedora) | [Mark 1 Compute Architecture](architecture/Mark 1 Compute Architecture.md) *(noted)* |
| OTA strategy | A/B partition with auto-rollback | [OTA Update Strategy](addendums/OTA Update Strategy.md) |
| Mission logging | Local-first ros2 bag, summaries streamed, 7-day ring buffer | [Mission Logging and Replay](addendums/Mission Logging and Replay.md) |
| Stage 5 acceptance | Quantitative p99 budgets per scenario | [Stage 5 Acceptance Criteria](addendums/Stage 5 Acceptance Criteria.md) |
| Spark flight authority | Bay is launch/dock interface; Spark owns flight | [Spark Authority and friday-core-os Definition](addendums/Spark Authority and friday-core-os Definition.md) |
| `friday-core-os` definition | systemd target owning all Core Hub service units | [Spark Authority and friday-core-os Definition](addendums/Spark Authority and friday-core-os Definition.md) |
| Mechanical anatomy reference | NASA Perseverance; 6 drive + 4 corner steer; rocker-bogie + mast; true proportions 0.2668× (~74 cm body, 140 mm wheel); OSR = mechanism donor | [Mechanical Design Reference](addendums/Mechanical Design Reference.md) |
| mmWave human/animal detection | RD-03D radar baseline on Lab Deck; plug-and-play via USB-UART; LoRa sentries deferred to Mark 2 | [mmWave Human Detection](addendums/mmWave Human Detection.md) |
| Power tree | Distributed — fused raw 14.8 V to each deck, local regulation | [Electronics Backbone](electronics/Electronics Backbone.md) |
| Physical E-stop | NC safety loop → motion-power contactor; compute stays alive; pawls drop | [Electronics Backbone](electronics/Electronics Backbone.md) |
| Grounding / fusing / connectors | Single-point star ground; central fuse block + per-deck protection; M8/M12 bulkhead | [Electronics Backbone](electronics/Electronics Backbone.md) |
| Build medium | Custom PCB per deck; breadboard bench-only | [Electronics Backbone](electronics/Electronics Backbone.md) |
| Core Hub electronics | Buck→GPIO+override, powered USB hub, conduction cooling, NVMe, supercap shutdown | [Core Hub Electronics](electronics/Core Hub Electronics.md) |
| Telemetry electronics | Dual independent LoRa, 4G M.2 (5G-ready), ESP32 reboot authority, mast antennas | [Telemetry Node Electronics](electronics/Telemetry Node Electronics.md) |
| Locomotion electronics | Cytron drivers, full galvanic isolation, parking pawls, layered safe-stop | [Locomotion Electronics](electronics/Locomotion Electronics.md) |
| Lab Deck electronics | eFuse + isolated-I2C plug-and-play expansion ports | [Lab Deck Electronics](electronics/Lab Deck Electronics.md) |
| Aerial Bay electronics | Bistable over-center lock, self-charging Spark | [Aerial Bay Electronics](electronics/Aerial Bay Electronics.md) |

## Reference

Nav2's `lifecycle_manager` is the working precedent for the Friday Labs OS supervisor — study it before implementing.

---

Related: **Friday Labs** · **Spark** · [Friday Labs OS Architecture](architecture/Friday Labs OS Architecture.md) · [Telemetry Command Node](architecture/Telemetry Command Node.md) · [ROS 2 Interface and Message Contract](architecture/ROS 2 Interface and Message Contract.md) · [Mark 1 Compute Architecture](architecture/Mark 1 Compute Architecture.md)
