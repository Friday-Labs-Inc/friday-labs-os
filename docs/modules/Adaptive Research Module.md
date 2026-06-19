# Adaptive Research Module

> Sensor processing, mapping, and plug-and-play research payload management for [Mark 1](../architecture/Mark 1 Compute Architecture.md) — informally "the Lab Deck." Owns the research-grade LiDAR, the baseline camera, environmental sensor plumbing, and plug-in mission payloads. Publishes decision-level outputs to Core; never owns the navigation path.
> **Version:** Draft 1.0 · **Purpose:** Software team handoff · **Reports to:** [Friday Labs OS](../architecture/Friday Labs OS Architecture.md) as a managed lifecycle node.

## Role

The Adaptive Research Module is Mark 1's research and sensor-processing brain. It owns the research-grade LiDAR, the baseline camera, the environmental sensor bus, and any plug-and-play mission payloads. It runs the mapping pipeline and publishes processed, decision-relevant outputs (`MapSegment`, `DetectedObjectArray`, `CoverageProgress`) to the Core Compute Hub.

It is **not** on the navigation critical path. Core Hub navigation uses its own dedicated nav sensor; the Lab Deck's research data is consumed by mission planning and operator-facing outputs, not by autonomy's safety loop. See [Sensor Ownership](../addendums/Sensor Ownership.md).

It is a [lifecycle node](../architecture/ROS 2 Interface and Message Contract.md) running on a Raspberry Pi 5.

## Hardware Direction

| Component | Spec |
|---|---|
| SBC | Raspberry Pi 5 (8 GB), same as Core Hub |
| Research LiDAR | Slamtec RPLIDAR A3 (2D, 360°, 25 m outdoor range, ~$350) |
| Baseline camera | Arducam IMX477 USB 3.0 with selectable lens (~$60) |
| Environmental baseline | BME280 (temp / humidity / pressure) via I2C (~$10) |
| Baseline radar | RD-03D mmWave + CH340/CP2102 USB-UART bridge (~$25-30) — fog/dark/foliage-piercing detection, see [mmWave Human Detection](../addendums/mmWave Human Detection.md) |
| Sensor buses | I2C for low-bandwidth sensors, USB 3.0 for high-bandwidth peripherals |
| Storage | 256 GB USB 3.0 SSD for research data and bag files (~$40) |
| Co-processor | None — Pi 5 handles all sensor I/O directly |
| Module identity | `MARK1-LAB-001` |

Total baseline Lab Deck BOM: **~$525-630** (excluding mission-specific plug-in sensors).

## Plug-and-Play Sensor Discovery

Two discovery paths, matched to how sensors actually communicate:

### USB Hot-Plug

For cameras, USB LiDAR, USB GPS, thermal cameras, multispectral sensors.

- Linux `udev` rules in `/etc/udev/rules.d/99-mark1-sensors.rules` match Friday Labs sensor VID/PID classes.
- On plug-in, `udev` fires a `mark1-sensor-attached` event with the sensor class.
- `sensor-plugin-manager` receives the event, looks up the appropriate driver, launches it under `/mark1/research/<sensor_class>/...`.
- The new sensor registers with `module-registry` as a sub-capability of the Lab Deck.

### I2C Scan

For low-bandwidth environmental sensors (soil moisture, temperature, humidity, gas, light, wind).

- `sensor-plugin-manager` scans the I2C bus every 30 s while in `active`.
- Each Friday Labs-compatible sensor exposes a 4-byte identity register at I2C address `0x76` (configurable per family): `[family_code, model_code, firmware_major, firmware_minor]`.
- On a new identity match, the driver loads and the sensor registers.

### Manual Escape Hatch

Sensors that don't conform require an entry in `/etc/mark1/lab_deck_sensors.yaml` declaring driver, bus, and address. Logged on load.

## Three Internal Layers

**Layer 1 — Capture.** Per-sensor driver nodes capture raw data at the sensor's native rate. LiDAR ~5-10 Hz, camera up to 30 Hz, environmental sensors 1 Hz. Drivers run as managed lifecycle child nodes under `lab-deck-manager`.

**Layer 2 — Processing.** Cartographer 2D SLAM on the RPLIDAR feed, TFLite-based object detection per the mission's enabled model set, coverage tracking, environmental data aggregation. Heavier detection models offload to the Core Hub's Coral via a defined action — the Lab Deck does NOT run on the Coral directly.

**Layer 3 — Publish.** Decision-level outputs to Core via `friday_msgs`: `MapSegment`, `CoverageProgress`, `DetectedObjectArray`, environmental summaries. Raw streams stay on the Lab Deck's SSD and sync on charger per [Mission Logging and Replay](../addendums/Mission Logging and Replay.md).

## Responsibilities

- Discover and manage baseline + plug-and-play sensors.
- Capture LiDAR, camera, and environmental data at native rates.
- Run Cartographer 2D SLAM, publishing `MapSegment` chunks.
- Detect mission-relevant objects (weeds, animals, persons, anomalies) per the mission's enabled model set.
- Compute coverage progress for area-sweep missions.
- Aggregate environmental sensor data into mission-relevant summaries.
- Log raw research data to the local SSD as `ros2 bag` files.
- Publish heartbeat and health like every other module.
- Honor lifecycle safe-state: flush write buffers, idle capture, keep SSD mounted.

## Lifecycle Behavior

| State | Behavior |
|---|---|
| `unconfigured` | Boot. Pi 5 services up. No sensor drivers loaded. |
| `configuring` | Discover baseline sensors. Verify LiDAR, camera, environmental bus. Register via `RegisterModule.srv`. |
| `inactive` (safe-state) | Active capture stopped. Write buffers flushed (sync to SSD). SSD stays mounted. Heartbeats at 1 Hz. |
| `active` | Full capture and processing pipeline running. Heartbeats at 5 Hz. Plug-and-play discovery enabled. |
| `error` | `FaultReport` published. Drop to `inactive` safe-state. Recovery requires operator. |
| `finalized` | All sensors released. SSD unmounted cleanly. |

The Lab Deck never holds authority over motion or commands. Lifecycle transitions are operator- or `safety-supervisor`-driven, not self-initiated.

## Failover Behavior

| Trigger | Behavior |
|---|---|
| Lab Deck crashes | Core's navigation continues using its own dedicated nav sensor. Mission downgrades: mapping pauses, research capture stops. `safety-supervisor` logs Lab Deck loss and notifies operator. Rover keeps moving safely. (See [S6](../addendums/Stage 5 Acceptance Criteria.md).) |
| LiDAR fails | Mapping pauses. `FaultReport` with `category=SENSOR_LOST`. Other sensors continue. Mission may continue if mapping isn't critical to it. |
| Camera fails | Visual detection pauses. `FaultReport`. Other sensors continue. |
| SSD write error / disk full | `FaultReport` with `category=STORAGE_FAULT`. Capture pauses gracefully. Mission may continue with no new data logged. |
| Plug-and-play sensor disconnects mid-mission | Its driver node deactivates. Other sensors unaffected. Operator notified. |

## Message Types

**Subscribed (input):**

- `friday_msgs/AuthorityLease` (QoS `critical_reliable`) — observed for context only; Lab Deck does not act on lease changes.
- `friday_msgs/MissionStatus` (QoS `state_default`) — scopes which sensors and models to enable.
- `lifecycle_msgs/srv/ChangeState`

**Published (output):**

- `friday_msgs/MapSegment` (QoS `state_default`, per-segment) — processed map chunks for Core's fusion.
- `friday_msgs/DetectedObjectArray` (QoS `state_default`, on detection) — ≤ 200 per frame per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).
- `friday_msgs/CoverageProgress` (QoS `state_default`, 1 Hz).
- `friday_msgs/Heartbeat` (QoS `heartbeat`, 5 Hz active / 1 Hz safe-state).
- `friday_msgs/HealthStatus` (QoS `state_default`, 1 Hz).
- `friday_msgs/FaultReport` (QoS `critical_reliable`, on event).
- `sensor_msgs/PointCloud2` (QoS `sensor_stream`, ~5 Hz) — raw research LiDAR, namespace `/mark1/research/lidar/...`. **Not consumed by Core's nav stack.**
- `sensor_msgs/Image` (QoS `sensor_stream`, on demand) — raw research camera, namespace `/mark1/research/camera/...`. Streamed only when explicitly requested; otherwise SSD-local.

## Software Services

- `lab-deck-manager` — lifecycle parent, owns child sensor drivers.
- `sensor-plugin-manager` — USB `udev` + I2C scan, registers/deregisters sub-capabilities.
- `lidar-capture-service` — RPLIDAR A3 driver, publishes raw `PointCloud2`.
- `camera-capture-service` — IMX477 USB driver, publishes raw `Image` on demand.
- `environmental-sensor-service` — generic driver dispatcher for I2C environmental sensors.
- `radar-capture-service` — RD-03D mmWave radar driver over USB-UART bridge. Publishes `DetectedObjectArray`. See [mmWave Human Detection](../addendums/mmWave Human Detection.md).
- `mapping-service` — Cartographer 2D SLAM, publishes `MapSegment`.
- `detection-service` — TFLite model runner for mission-enabled detectors.
- `coverage-tracker` — area-sweep progress computation.
- `research-data-logger` — bag-file writer to the SSD with the [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) retention policy.
- `processed-data-publisher` — gates which raw streams get republished vs kept local.

## Authority Compliance

The Lab Deck never publishes motion, recovery, or emergency commands. It has no `authority` lease relationship beyond observing the current holder for context. No authority check on its publications.

## Storage Layout

| Path | Content | Retention |
|---|---|---|
| `/var/mark1/research_data/raw/` | Per-mission `ros2 bag` of raw sensor streams | Ring buffer, 14 days or 80% of SSD, whichever comes first |
| `/var/mark1/research_data/processed/` | Per-mission summaries (maps, detections, environmental aggregates) | 90 days |
| `/var/mark1/research_data/sync_queue/` | Symlinks pending Command Center sync | Until acknowledged |

## Provisioning

- Ubuntu 24.04 LTS + ROS 2 Jazzy + Friday Labs OS Lab Deck runtime.
- A/B partition layout per [OTA Update Strategy](../addendums/OTA Update Strategy.md).
- Module identity in `/etc/mark1/identity.json`.
- Default sensor manifest in `/etc/mark1/lab_deck_sensors.yaml`.
- udev rules in `/etc/udev/rules.d/99-mark1-sensors.rules`.
- SSD mounted at `/var/mark1/research_data` with auto-mount on boot.
- SSH/debug access per Friday Labs provisioning standard.

## Open Design Areas

- **Mission-specific environmental sensor list** — locked during Phase 5 mission planner work. Baseline BME280 is the only one in this spec.
- **Mid-mission sensor swap policy** — discovery supports it architecturally; mission planner decides whether to accept hot-swap or reject during a running mission. To be locked Phase 5.
- **Detection model deployment** — operators push new TFLite models via a signed-package pattern reusing [OTA Update Strategy](../addendums/OTA Update Strategy.md). Implementation Phase 5.
- **Thermal / multispectral camera drivers** — plug-and-play architecturally; specific drivers Phase 5+.
- **Spark aerial data ingestion** — when **Spark** returns with aerial scans, the Lab Deck is the natural receiver. Interface defined alongside the Aerial Companion Bay spec.

## Acceptance Criteria

- Plug a Friday Labs-conforming I2C environmental sensor into a running Lab Deck; it appears in `module-registry` within 30 s.
- Plug a USB camera with a known VID/PID; its driver starts and publishes within 5 s.
- Killing the Lab Deck process during a mission does NOT cause Core's navigation to lose perception (verified by [S6](../addendums/Stage 5 Acceptance Criteria.md)).
- Lab Deck completes a 2-hour mapping mission writing to SSD with zero data loss; the mission_replay log validates after reboot.
- LiDAR + camera + 4 environmental sensors run concurrently with Pi 5 CPU load ≤ 70% and no missed `MapSegment` publishes for ≥ 99% of the mission.

## Related

[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Sensor Ownership](../addendums/Sensor Ownership.md) · [Power Budget](../addendums/Power Budget.md) · [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) · [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) · [OTA Update Strategy](../addendums/OTA Update Strategy.md) · [Stage 5 Acceptance Criteria](../addendums/Stage 5 Acceptance Criteria.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
