# Mission Logging and Replay

> What gets logged, where it's stored, how long it's kept, and what streams to the Command Center. Makes the "replay what happened if Core crashes mid-mission" claim in [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) real.
> **Version:** Draft 1.0 · **Purpose:** Close the Phase 2 logging-design gap.

## Decision

Local-first with summary streaming. Full mission replay logs stay on the rover as `ros2 bag` files. Summaries stream to the Command Center in real time over cellular. Bulk data syncs on charger via WiFi.

## What Gets Logged Locally

| Stream | Contents | Rate |
|---|---|---|
| `mission_replay` | All commands, lifecycle transitions, faults, authority lease changes, decision-level outputs (`Odometry`, `MapSegment`, `DetectedObjectArray`, `CoverageProgress`) | Native rate of each topic |
| `nav_perception` | Core nav-sensor stream (depth frames / point cloud) at reduced rate | 5 Hz |
| `health_full` | All `HealthStatus`, `PowerState`, `Heartbeat` messages | Source rate |

Raw research sensor streams (Lab Deck LiDAR full-rate, environmental sensors, etc.) are stored ONLY if the mission spec requests it; otherwise the Lab Deck retains them on its own partition and they sync separately on charger.

## What Streams to Command Center

Real-time over cellular, priority order:

1. **Faults** (`FaultReport`) — always, immediately.
2. **Mission status** (`MissionStatus`) — every 5 s.
3. **Health summary** (per-module subset of `HealthStatus`) — 1 Hz.
4. **Position** (`base_link` pose in `map` frame) — 1 Hz.
5. **Operator-requested debug streams** — only on explicit request, lower priority.

Bulk sensor data and full bag files are NOT streamed during a mission. They sync on charger.

## Retention

- `mission_replay`: ring buffer of last 7 days. Oldest overwritten when storage hits 90%.
- `nav_perception`: ring buffer of last 3 days.
- `health_full`: 30 days.
- `FaultReport` ledger: indefinite (small).
- Mission outcome summaries: indefinite.

## Storage Sizing

Typical operation:

- `mission_replay`: ~50 MB/hour
- `nav_perception`: ~500 MB/hour at 5 Hz depth
- `health_full`: ~5 MB/hour

7-day window × 4 hours/day = ~16 GB. Fits comfortably in the `data` partition on a 32 GB SD card after OTA banks are reserved.

## Crash Safety

- Append-only bag writes. If Core crashes mid-write, the last frame may be lost; everything before it is intact.
- `mission_replay` is `fsync`'d every 1 s.
- A `mission_ledger.json` records mission start, every phase change, mission end — written synchronously. Identifies which bag files map to which mission.
- On boot, Friday Labs OS scans for un-terminated missions (start record, no end record). Found = marked "crashed," recovery report prepared for next CC sync.

## Sync to Command Center

When rover is on charger and connected to WiFi:

- Mission summaries upload immediately.
- Full bag files upload in priority order (most recent first; within each mission, faults first).
- Upload is resumable — partial uploads continue from where they left off.
- Upload progress is reported. Bag files cannot be auto-deleted until upload is acknowledged.

## Hard Rules

- No log write blocks the autonomy critical path. If the disk is slow, drops happen in the bag writer, never in the loop.
- Logs are never deleted by Friday Labs OS automatically while a mission is unsynced. Ring buffer only overwrites already-synced data.
- Disk full triggers a `FaultReport` and a graceful mission wind-down — never a crash.

## Acceptance Criteria

- Replay a bag file in sim and observe identical fault sequence to the original mission.
- Kill Core mid-mission; confirm replay log is intact up to the crash point.
- Run a mission with cellular disabled; full sync on charger correctly catches up.

## Related

[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Telemetry Command Node](../architecture/Telemetry Command Node.md) · [Command Center Protocol Security](Command Center Protocol Security.md) · [OTA Update Strategy](OTA Update Strategy.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
