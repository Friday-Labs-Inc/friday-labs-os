# Sensor Ownership

> Resolves the sensor-ownership ambiguity between the [Core Compute Hub](../architecture/Friday Labs OS Architecture.md) and the [Adaptive Research Module (Lab Deck)](../architecture/Mark 1 Compute Architecture.md#module-4-adaptive-research-module-lab-deck). Establishes that navigation perception is owned by Core and is never dependent on the Lab Deck being healthy.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 design gap before hardware selection.

## The Problem

The original [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) permits shared sensor access between Core and the Lab Deck but never fully specifies ownership. If the Lab Deck owns the main LiDAR and republishes a navigation stream to Core, a Lab Deck crash mid-mission blinds Core's navigation and forces a safe-stop — making the Lab Deck a single point of failure for autonomy. That contradicts the "Core is brain, not bottleneck" principle in [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md).

## Decision

**The Core Compute Hub owns its own navigation sensor**, electrically and logically independent of the Lab Deck. The Lab Deck owns its own research-grade sensors. Navigation perception never depends on Lab Deck health.

## Hardware Direction

The Core Hub gets a dedicated depth-class sensor. Candidates to be finalized in Phase 1 hardware alongside SBC selection:

- **Intel RealSense D435i** — ~$300, depth + IMU, mature ROS 2 driver, USB-C.
- **Luxonis OAK-D Pro** — ~$250-350, depth + RGB + on-device neural inference, USB-C.
- **2D LiDAR** (e.g. Slamtec RPLIDAR A2) — ~$300, simpler but loses vertical perception.

Final model selection depends on the [AI Inference Location decision](#related) and the [Power Budget decision](#related). The architectural commitment — *dedicated sensor on Core* — is locked here regardless of which model is chosen.

## Lab Deck Sensors

The Lab Deck owns whichever sensors are mission-appropriate:

- Main research LiDAR (3D, higher fidelity, for mapping workloads).
- Camera arrays for visual inspection.
- Environmental sensors (soil moisture, temperature, gas, humidity, wind).
- Thermal camera if mission requires.

The Lab Deck publishes processed, decision-relevant outputs (`MapSegment`, `DetectedObjectArray`, `CoverageProgress`) to Core. It does **not** publish raw sensor streams to Core under normal operation. Core's autonomy consumes its own nav sensor for perception.

## Failure Modes

| Scenario | Behavior |
|---|---|
| Lab Deck crashes mid-mission | Core's navigation continues using its own depth sensor. Mission downgrades — mapping pauses, research capture stops — but the rover continues moving safely. Safety-supervisor logs the Lab Deck loss and notifies operator via Telemetry. |
| Core's nav sensor fails | Core declares perception loss, issues safe-stop via Locomotion, raises a critical fault. The rover does NOT fall back to Lab Deck perception. |
| Both fail | Safe-stop. Recovery requires manual intervention. |

The deliberate asymmetry — Core's nav stack does not fall back to Lab Deck perception even if Lab Deck is healthy — is intentional. It keeps the dependency graph one-directional and prevents the Lab Deck from becoming a covert single point of failure through "fallback" code paths that never get tested.

## Sensor Discovery and Plug-and-Play

Plug-and-play sensor discovery (an open item in the original dossier) applies only to the Lab Deck. Sensors on Core's nav side are part of the locked hardware spec and do not hot-swap mid-mission.

## Implementation Surface

- Add Core's nav sensor to the hardware spec once selected.
- Update the `friday_msgs` ownership map: navigation-grade `sensor_msgs/PointCloud2` (or depth equivalent) is owned by Core's own driver, not by the Lab Deck Agent.
- Update the Adaptive Research Module Agent responsibilities: it does NOT publish navigation-class sensor streams. It publishes only processed research outputs.
- Extend `HealthStatus` with a `core_nav_sensor_ok` boolean so the supervisor can detect nav-sensor loss independently of Lab Deck health.

## Acceptance Criteria

- Killing the Lab Deck agent in sim (new [fault-injection](../../.claude/skills/fault-injection/SKILL.md) scenario S6) does NOT cause Core's navigation stack to lose perception. Core continues to issue safe motion commands; the mission downgrades but does not abort.
- Killing Core's nav sensor driver in sim DOES cause Core to issue safe-stop within the [500 ms DDS budget](Safe-Stop Latency Budget.md), even if Lab Deck is healthy.
- Code review confirms no fallback path exists where Core's autonomy subscribes to Lab Deck sensor streams.

## Open Items

- Specific nav sensor model — locked alongside SBC selection in Phase 1 hardware.
- Whether to add a redundant secondary cheap nav sensor (e.g. a simple 2D LiDAR alongside the depth camera) — deferred to Mark 2 unless cost analysis shows it's marginal.

## Related

[Authority Lease Protocol](Authority Lease Protocol.md) · [Safe-Stop Latency Budget](Safe-Stop Latency Budget.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Mark 1 Index](../Mark 1 Index.md)
