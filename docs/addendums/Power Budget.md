# Power Budget

> The power envelope and battery sizing for the Mark 1 bench prototype. Constrains SBC choice, sensor selection, motor sizing, and mission duration. Resolved first because it bounds every downstream hardware decision.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 hardware-design gap before SBC selection.

## Decisions

| Parameter | Value |
|---|---|
| **Chassis class** | 60-90 cm bench prototype, 6-wheel rocker-bogie |
| **Power envelope (continuous)** | 50-75 W |
| **Power envelope (peak)** | 100 W |
| **Battery capacity target** | 150 Wh |
| **Battery weight budget** | ~1 kg (LiPo or LiFePO4) |
| **Target mission duration** | 2 hours typical, 1 hour worst-case under peak load |
| **Charge strategy** | Hot-swap battery pack between runs; on-rover wall charging for overnight |

## Battery Spec

- **Capacity:** 150 Wh nominal (e.g. 14.8 V × 10000 mAh = 148 Wh).
- **Chemistry:** Lithium polymer (LiPo) for prototype; consider LiFePO4 for higher cycle life later.
- **Connector:** XT60 or XT90 with integrated current/voltage telemetry tap.
- **Margin policy:** never run below 20% state-of-charge in autonomous mode. Below 15% triggers return-to-dock; below 10% triggers safe-stop and beacon.

## Per-Module Power Budget

These are budgets, not measurements. Each module owner is accountable for measuring real draw at idle / typical / peak during Phase 2 bring-up. If actuals exceed budget, the module owner files a revision before integration.

| Module | Idle | Typical | Peak | Notes |
|---|---|---|---|---|
| Core Compute Hub | 4 W | 12 W | 18 W | Depends on SBC choice (Gap 5). Pi 5 typical ~8 W; Jetson Orin Nano typical ~10-15 W under inference. |
| Telemetry Command Node | 3 W | 5 W | 10 W | 5G modem dominates peak. |
| Locomotion Control Unit (ESP32 + motor drivers logic) | 0.5 W | 1 W | 2 W | Motor power is separate, see below. |
| Adaptive Research Module (Lab Deck Pi) | 4 W | 8 W | 15 W | LiDAR processing under peak load. |
| Aerial Companion Bay (ESP32) | 0.2 W | 0.5 W | 5 W | Charging Spark adds substantial peak — sequence so it does not coincide with motion peak. |
| Sensors (Core nav + Lab Deck LiDAR + IMU + GPS) | 3 W | 6 W | 10 W | Depth camera ~3 W; LiDAR ~5 W. |
| **Compute / electronics subtotal** | **~15 W** | **~33 W** | **~60 W** | |
| Drive motors (6× brushed/brushless) | 0 W | 20 W | 80 W | Heavily duty-cycle dependent. Assume 50% duty in typical. |
| Steering actuators | 0 W | 2 W | 8 W | Spikes during turn commands. |
| **System total** | **~15 W** | **~55 W** | **~150 W (instantaneous)** | Battery sizing assumes 60 W average. |

## Battery Runtime Math

At 150 Wh battery and 60 W typical average draw:

```
150 Wh / 60 W = 2.5 hours theoretical
With 20% reserve (never below 20% SoC): 2.0 hours operational
```

At peak sustained 100 W: 1.2 hours operational. Mission planner should never schedule sustained peak-power phases longer than 1 hour without a return-to-charge.

## Hard Rules

- **Power budget must be measured, not assumed.** Every module owner instruments idle / typical / peak during Phase 2 bring-up. The numbers above are budgets to design against, not predictions of reality.
- **Peak power events must not coincide.** Don't charge Spark while motor power-up; don't run heavy AI inference while transmitting bulk research data over 5G. Mission planner is responsible for scheduling.
- **No silent overrun.** A module that exceeds its peak budget for >10 seconds raises a `FaultReport` with `category=POWER_BUDGET_EXCEEDED`. Safety-supervisor decides whether to throttle, deactivate the module, or abort the mission.
- **Battery state telemetry on `state_default` QoS** at 1 Hz minimum. Estimated runtime must be in `PowerState.estimated_runtime_min` — and the estimate must account for current actual draw, not nameplate budget.

## Charging Strategy

- **Hot-swap primary** — pack swap between runs is the fast iteration path.
- **On-rover wall charging** — overnight or between long missions.
- **No solar for Mark 1.** Solar augmentation is a Mark 2 question once the baseline runtime envelope is proven.
- **Charging while powered on** is disallowed for the prototype to keep the BMS simple. Power off, swap, power on.

## Open Items

- Specific battery model and BMS selection — Phase 1 hardware.
- Motor sizing depends on chassis kit chosen; revise drive-motor budget once kit is locked.
- Add a small dedicated 5 V rail for ESP32s and sensors to isolate from motor voltage noise — confirm during electrical design.

## Acceptance Criteria

- All five modules report measured idle / typical / peak power in Phase 2 acceptance reviews. Any module over its peak budget blocks integration until it's revised or its hardware reduced.
- A nominal 2-hour mission completes with ≥ 20% battery remaining in bench testing, with all modules active and no peak-coincidence events.
- `PowerState.estimated_runtime_min` reports within ±15% of the actual remaining runtime, verified across at least 10 full-cycle runs.

## Related

[Authority Lease Protocol](Authority Lease Protocol.md) · [Safe-Stop Latency Budget](Safe-Stop Latency Budget.md) · [Sensor Ownership](Sensor Ownership.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
