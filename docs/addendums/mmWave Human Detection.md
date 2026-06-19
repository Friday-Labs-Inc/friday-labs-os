# mmWave Human Detection

> Baseline **RD-03D mmWave radar** on the [Lab Deck](../modules/Adaptive Research Module.md) for fog / dark / foliage-piercing detection of humans and other moving targets. Complements camera and LiDAR perception with a sensor modality that doesn't depend on visible light or clear sight lines.
> **Version:** Draft 1.0 · **Purpose:** Locks mmWave radar as a baseline Lab Deck capability and establishes the integration contract.

## Why mmWave

Camera fails in darkness, fog, smoke, dust. LiDAR fails when sight lines are blocked by foliage, wooden barriers, glass, or thin plastic. mmWave radar penetrates all of these and detects up to 3 simultaneous moving targets out to ~25 m. For a research-grade rover operating in agriculture, forestry, and surveillance — exactly the environments where humans and animals may be obscured — this fills a real gap that camera and LiDAR cannot.

## Decision

The RD-03D mmWave radar is a **baseline sensor** on every Lab Deck. Always present, always on, integrated as a plug-and-play USB module per the locked [Lab Deck discovery system](../modules/Adaptive Research Module.md#plug-and-play-sensor-discovery).

## Sensor Hardware

| Component | Spec |
|---|---|
| Module | RD-03D mmWave radar (Ai-Thinker / Hi-Link) |
| Frequency | 24 GHz mmWave |
| Range | ~25 m for moving targets |
| Field of view | ~120° horizontal |
| Targets tracked | Up to 3 simultaneously |
| Outputs per target | X-Y position, distance, angle, radial velocity |
| Update rate | ~10 Hz |
| Interface | UART (3.3 V) — exposed to the Pi via CH340 or CP2102 USB-UART bridge |
| Power | 5 V, ~150 mA (~0.75 W) |
| Cost | ~$20-25 (radar) + ~$5 (bridge) = ~$25-30 total |

## Integration with the Lab Deck

### Connection

USB-UART bridge plugs into a free USB port on the Lab Deck Pi 5. The bridge enumerates as `/dev/ttyUSB0` (or similar). The locked plug-and-play discovery flow handles the rest:

1. `udev` rule in `/etc/udev/rules.d/99-mark1-sensors.rules` matches the CH340 or CP2102 VID/PID combined with a sensor-class hint tag.
2. On plug-in, `udev` fires a `mark1-sensor-attached` event with class `uart-radar`.
3. `sensor-plugin-manager` launches the `radar-capture-service` lifecycle node and binds it to the new `/dev/ttyUSBx` device.
4. The service handshakes with the radar (model-ID query), confirms RD-03D, and begins parsing frames.
5. Service registers with `module-registry` as a sub-capability of the Lab Deck.

The baseline radar is provisioned at mounting time and is expected to be present on boot. Its absence raises a `FaultReport` with `category=BASELINE_SENSOR_MISSING`. Any secondary radar (future deployments) is treated as optional — absence is normal.

### radar-capture-service

A new lifecycle child node under `lab-deck-manager`:

- **Subscribes:** lifecycle transitions, `AuthorityLease` (observed only).
- **Publishes:**
  - `friday_msgs/DetectedObjectArray` on `/mark1/research/radar/detections` (QoS `state_default`, ~10 Hz).
  - `friday_msgs/Heartbeat` and `HealthStatus` like every other sub-module.
  - `friday_msgs/FaultReport` on UART loss or malformed frames.
- **Frame parsing:** binary RD-03D protocol → per-target `DetectedObject` records.

### Detection Format

Each `DetectedObject` carries:

- **`position`** in frame `base_link_radar` (origin at the radar module).
- **`velocity`** (radial component as reported by the radar).
- **`confidence`** (return strength, normalized 0-1).
- **`classification`** defaults to `MOVING_TARGET`. The RD-03D cannot distinguish human from animal from large moving object on its own. Species classification requires camera-radar fusion (Phase 5 work, depends on Core's Coral inference pipeline).

The radar's value is in **presence detection**, not species identification. A confirmed moving target inside the radar zone is reported; what kind of target is determined by camera fusion if needed.

## Mounting

Recommended: **forward-facing on the chassis body**, mounted ~15-25 cm above ground (low enough to cover near-field traffic, high enough to avoid ground clutter triggering false returns). Covers the rover's immediate travel zone — where proximity-to-people is most safety-critical.

Mast-mounting alongside Core's nav sensor is also valid for elevated coverage; defer to mechanical-integration phase once the chassis is in hand. A dual-radar setup (mast + forward) is a Mark 2 enhancement, not Phase 1.

Frame `base_link_radar` is declared in `friday_msgs` per [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md).

## Behavior Integration (Phase 5)

For Mark 1 Phase 1, the radar **publishes detections only** — it does not modify autonomy behavior. The autonomy stack and mission planner (Phase 5 work) decide what to do with detections. The candidate policies, to be locked per mission class during Phase 5:

- **Auto-slow** on close-range moving target (e.g., target < 2 m → throttle to 0.3 m/s).
- **Auto-stop** on close-range moving target (sensitive zones / proximity-to-people missions).
- **Alert-only** (publish to operator via Telemetry, no autonomy change).

Selection is per-mission via `UploadMission.action` parameters per [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md).

## Power and BOM Impact

- Adds ~0.75 W to the Lab Deck's typical power draw — well within the [Power Budget allocation](Power Budget.md) (Lab Deck typical is 8 W; this brings it to ~8.75 W).
- Adds ~$25-30 to the baseline Lab Deck BOM, taking it from ~$500-600 to ~$525-630.
- Total rover BOM impact: +$25-30. No other module affected.

## Future: LoRa Sentry Network (Mark 2)

The killer use case described in the inspiration video — **distributed LoRa sentries** covering a wide area without WiFi or cellular — is deferred to Mark 2. Architecture sketch for future reference:

- Standalone TTGO LoRa32 + RD-03D nodes deployed around the operating area (farm perimeter, forest entry points, warehouse boundary).
- Each sentry runs autonomously, solar-powered, transmits detections over LoRa.
- The rover's [Telemetry Command Node](../architecture/Telemetry Command Node.md) already has LoRa — it receives sentry detections and fuses them into the operator-facing situational picture.
- Requires a new `sentry-protocol` addendum: node provisioning, LoRa frame format, authentication of sentry detections (Ed25519 like the rest of [Command Center Protocol Security](Command Center Protocol Security.md)).

The onboard radar locked here is the foundation; sentries build on it later.

## Acceptance Criteria

- Plug the RD-03D + USB-UART bridge into the Lab Deck Pi 5; the radar appears in `module-registry` within 5 s.
- `DetectedObjectArray` publishes at ≥ 8 Hz steady-state on `/mark1/research/radar/detections`.
- Detection-to-publish latency p99 ≤ 50 ms.
- Unplugging the USB-UART bridge raises a `FaultReport` with `category=BASELINE_SENSOR_MISSING` within 1 s.
- In a 1-hour bench test with a walking person at 5 m, the radar reports continuous tracking with gaps ≤ 2 s.

## Open Items

- **Specific mount position** — locked during chassis integration.
- **Camera-radar fusion** for human-vs-animal classification — Phase 5, depends on Coral inference pipeline.
- **Sentry network protocol** — Mark 2, separate addendum.
- **Multi-radar setup** (mast + forward, redundant coverage) — Mark 2.

## Related

[Adaptive Research Module](../modules/Adaptive Research Module.md) · [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md) · [Sensor Ownership](Sensor Ownership.md) · [Power Budget](Power Budget.md) · [AI Inference Location](AI Inference Location.md) · [Telemetry Command Node](../architecture/Telemetry Command Node.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
