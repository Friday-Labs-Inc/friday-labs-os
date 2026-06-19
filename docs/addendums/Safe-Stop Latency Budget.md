# Safe-Stop Latency Budget

> Defines the worst-case latency from heartbeat loss to motors-off on the [Locomotion Control Unit](../architecture/Mark 1 Compute Architecture.md#module-3-locomotion-control-unit), the physical safe-state the rover holds, and the firmware-watchdog independence that makes the budget meet-able in the real world.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 safety-design gap before service logic is written.

## The Problem

The heartbeat numbers in the [interface contract](../architecture/ROS 2 Interface and Message Contract.md) (200 ms publish, 500 ms deadline, ~1 s liveliness lease) are a presence-detection budget, not a safety-stop budget. At a 1 m/s travel speed, a 1+ second detection-then-route chain means the rover continues to move more than 1 meter after Core or its bridge fails. That is incompatible with field testing near people, livestock, or property.

Safe-stop must beat presence detection by an order of magnitude, and it must not depend on the micro-ROS bridge being alive.

## Two Stop Paths, Two Budgets

Two paths exist in parallel. Both must be implemented; neither alone is sufficient.

| Path | Trigger | p99 budget |
|---|---|---|
| **Firmware watchdog (primary)** | Absence of heartbeat from owning Pi for >100 ms on the Locomotion ESP32 | **≤ 100 ms** from heartbeat loss to motors at zero |
| **DDS EmergencyStop (secondary)** | `EmergencyStop.msg` received over `/mark1/locomotion/emergency_stop` (QoS `critical_reliable`) | ≤ 500 ms from publish to motors at zero |

The firmware path is the safety net. The DDS path is the normal operator-initiated stop. The firmware path MUST function with the micro-ROS bridge process killed.

## Stopping-Distance Implications

At the 100 ms p99 budget, on flat ground:

| Travel speed | Reaction distance (100 ms) | Approx. braking distance | Total stopping distance |
|---|---|---|---|
| 0.5 m/s | 5 cm | ~5 cm | **~10 cm** |
| 1.0 m/s | 10 cm | ~10-20 cm | **~20-30 cm** |
| 1.5 m/s | 15 cm | ~20-30 cm | **~35-45 cm** |

On slopes, braking distance grows. The maximum allowed travel speed for proximity-to-people work must be set per mission, not as a global. Recommend 1.0 m/s ceiling for any mission within 1 m of a person or animal.

## Safe-State Physical Definition

When safe-stop trips, the rover holds:

- **Motors at zero velocity, with active holding torque applied.** Wheels do not freewheel. The rover does not roll on slopes.
- **Steering frozen at its current angle.** Steering does not re-center, does not unlock, does not move at all during or after safe-stop.
- **Heartbeats continue at degraded rate** (1 Hz) so the supervisor still sees the module is alive.
- **Fault published** as `FaultReport.msg` with `category=WATCHDOG` and the cause if known.

Battery cost of active hold: small continuous drain, accepted as the cost of slope safety.

## Firmware Watchdog Requirements

Non-negotiable on the Locomotion ESP32:

1. **Hardware peripheral, not software timer.** Use the ESP32's hardware watchdog timer (the chip-level peripheral). FreeRTOS soft timers are explicitly disallowed for this path — they share scheduling with the bug that may have hung the firmware in the first place.
2. **Independent timer source.** The watchdog timer source must not be derived from any code path that runs in normal duty.
3. **Bridge-independent.** Killing the micro-ROS agent on the owning Pi must not prevent the watchdog from tripping within budget. Verified by [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) Path B.
4. **Cannot be silenced by malformed input.** A corrupted or replayed heartbeat from the bridge must not reset the watchdog.
5. **100 ms inactivity timeout** by default. Reset whenever a well-formed heartbeat with a fresh, valid timestamp arrives from the owning Pi.

## Implementation Notes

- The Locomotion firmware listens for Pi heartbeats on its dedicated serial / USB / Ethernet link, NOT on the DDS topic. The DDS heartbeat is for the supervisor; the firmware heartbeat is for the watchdog. They may share content but they must be independent signals.
- When the watchdog trips, the firmware enters safe-state synchronously. Recovery to `active` requires an explicit `lifecycle_msgs/ChangeState` transition through `inactive → active` driven by `safety-supervisor`. The firmware does not self-recover.
- The safe-state behavior is identical whether triggered by the firmware watchdog, by a DDS `EmergencyStop`, or by a lifecycle `deactivate`. One safe-state, three triggers.

## Acceptance Criteria

The [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) skill must report PASS before any field test:

| Test | Path | p99 budget |
|---|---|---|
| Kill Pi heartbeat publisher cleanly | DDS chain (Path A) | ≤ 500 ms |
| Kill micro-ROS agent process | Firmware watchdog (Path B) | ≤ 150 ms |
| Yank serial cable | Firmware watchdog (Path C) | ≤ 150 ms |

Sample size: 50 per path. Numbers must be measured on hardware-in-the-loop, not pure sim — pure sim cannot reproduce serial / USB jitter.

Additional checks that must pass:

- Watchdog source is hardware peripheral, verified by code review.
- Bridge-independence verified: agent process killed mid-test, watchdog still trips on schedule.
- Active motor hold maintains rover position on a 15° slope for ≥ 10 minutes without drift.
- Steering does not move during or after safe-stop entry.

## Open Items

- Travel-speed ceilings per mission class to be locked during Phase 5 (mission planner build).
- Slope-angle limits for safe operation to be locked once chassis selection is final.

## Related

[Authority Lease Protocol](Authority Lease Protocol.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) · [Mark 1 Index](../Mark 1 Index.md)
