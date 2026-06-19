# Stage 5 Acceptance Criteria

> Quantitative pass/fail thresholds for the [sim Stage 5 fault-injection](../architecture/Mark 1 Simulation and Dev Environment.md) scenarios. Replaces "passes on a vibe" with measurable budgets that CI can enforce.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 testing-discipline gap.

## Background

Stage 5 of sim bring-up is the most important stage — it's where the real-time safe-stop path and the split-brain authority story are tested in a controlled, repeatable way. Without explicit numerical criteria, Stage 5 passes on hand-wave and the bugs it was supposed to catch reach the field.

The [fault-injection](../../.claude/skills/fault-injection/SKILL.md) skill enforces these budgets.

## Scenarios and Budgets

| ID | Scenario | Measure | Budget |
|---|---|---|---|
| S1 | Core process killed (SIGKILL) | Time until Telemetry detects loss and enters recovery mode | ≤ 1.5 s |
| S1 | Core process killed | Time until Locomotion safe-stop active in sim (firmware watchdog path) | ≤ 100 ms from heartbeat loss |
| S2 | Locomotion comms cut (`tc qdisc add drop`) | Time until motors at zero velocity | ≤ 200 ms |
| S2 | Locomotion comms restored | Time to rejoin registry and resume `active` lifecycle state | ≤ 5 s |
| S3 | Network partition (Core ↔ Telemetry) | Number of conflicting motion commands during partition | 0 |
| S3 | Network partition healed | Time to lease epoch reconciliation | ≤ 2 s |
| S4 | Core restart during Telemetry recovery | Conflicting commands during handoff | 0 |
| S4 | Core restart | Time to clean authority handoff | ≤ 2 s |
| S5 | Both Core + Telemetry killed | Time until ESP32 LoRa beacon active | ≤ 5 s |
| S5 | ESP32 beacon | Beacon contains valid `rover_id` and last-known position | true |
| S6 | Lab Deck killed mid-mission | Core navigation continues using its own nav sensor; mission downgrades but does not abort | true |
| S6 | Core nav sensor killed | Core issues safe-stop within DDS budget; mission aborts cleanly | ≤ 500 ms |

## Sample Sizes and Statistics

Each scenario runs **50 times** per CI cycle. Budget is enforced on **p99**, not average. A scenario that passes 49/50 but blows the budget on the 50th fails the gate.

## "Conflicting Commands" Definition (S3, S4)

During a partition or handoff, any of the following counts as one violation:

- Two motion commands published within 100 ms of each other from different sources, both addressed to Locomotion, where neither source is currently the authority holder.
- Any motion command published by a source that does not match the current `authority` lease holder.

Budget is **0** — even one violation is a fail.

## Headless CI

Stage 5 runs headlessly in CI on every commit to any of: `friday_msgs`, `module-registry`, `safety-supervisor`, `authority-lease-service`, `command-router`, or Locomotion firmware. CI reports per-scenario p99 latencies and pass/fail per row.

## Honest Limits

These criteria validate the **logic** of the safety system. They do not validate:

- Real-world timing under real cellular jitter, real motor inertia, or real serial-link noise.
- True sensor noise behavior.
- Power/thermal stress.

A green Stage 5 is necessary but not sufficient for field testing. Bench hardware-in-the-loop tests are required before field use; see [Safe-Stop Latency Budget Acceptance Criteria](Safe-Stop Latency Budget.md).

## Related

[Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) · [Authority Lease Protocol](Authority Lease Protocol.md) · [Safe-Stop Latency Budget](Safe-Stop Latency Budget.md) · [Sensor Ownership](Sensor Ownership.md) · [fault-injection](../../.claude/skills/fault-injection/SKILL.md) · [Mark 1 Index](../Mark 1 Index.md)
