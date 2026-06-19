# Aerial Companion Bay

> Launch, dock, charge, and ground-side coordination interface for **Spark** on [Mark 1](../architecture/Mark 1 Compute Architecture.md). Not Spark's flight brain — Spark owns flight authority per [Spark Authority](../addendums/Spark Authority and friday-core-os Definition.md).
> **Version:** Draft 1.0 · **Purpose:** Software team handoff · **Reports to:** [Friday Labs OS](../architecture/Friday Labs OS Architecture.md) as a managed lifecycle node.

## Role

The Aerial Companion Bay is the physical and ground-side coordination interface between Mark 1 and Spark. It is a [lifecycle node](../architecture/ROS 2 Interface and Message Contract.md) on an ESP32-S3, owned by the Core Compute Hub via USB CDC.

The Bay handles four concrete jobs:

1. Hold Spark securely during rover transit.
2. Enforce pre-launch safety interlocks and release Spark when conditions are met.
3. Receive Spark on return, lock it in the cradle, and charge it.
4. Pass mission and status data between Mark 1 and Spark while docked.

It does NOT control Spark in flight. Once Spark lifts off, its own flight controller is the authority — see [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md).

## Hardware Direction

| Component | Spec |
|---|---|
| MCU | ESP32-S3 with USB OTG (~$10) |
| Launch mechanism | Passive V-cradle — no actuator. Spark takes off on its own rotor power |
| Dock mechanism | Same V-cradle (passive landing guide) + single servo-controlled lock (~$45) |
| Charging interface | Pogo pin contacts on the cradle (~$15 in spring-loaded pins + ~$10 charge controller) |
| Bay-to-Spark data | UART over 2 dedicated pogo pins at 115200+ baud |
| Lock state sensors | 2× limit switches (lock open / lock closed) (~$3) |
| Dock detection | Weight pad or Hall-effect sensor in cradle (~$5) |
| Launch corridor safety | IR break-beam transmitter + receiver across the launch path (~$10) |
| Charging current monitor | INA219 on the charge bus (~$5) |
| Pi communication | USB CDC over ESP32-S3's native USB OTG |
| Owning Pi | Core Compute Hub |
| Module identity | `MARK1-SPARKBAY-001` |

Total Bay BOM (excluding Spark itself): **~$100-130**.

## Core Principle

**The Bay is the ground-side coordinator, not the flight brain.** Every behavior is shaped by the asymmetry: the Bay can refuse to launch, can lock the dock, can read sensors and report — but it cannot override Spark in flight. The pre-launch interlocks are the Bay's primary safety contribution.

## Three Internal Layers

**Layer 1 — Mechanism Control.** Single servo for the dock lock. Limit-switch monitoring. Pogo pin enable/disable for charging. No motors beyond the lock servo.

**Layer 2 — Safety Interlock.** `bay-safety-checker` evaluates the 8 pre-launch conditions from [Spark Authority](../addendums/Spark Authority and friday-core-os Definition.md) before consenting to any launch. All 8 must pass; one fail = refuse.

**Layer 3 — Coordination.** UART link to Spark while docked. Mission upload, charging status, battery state, pre-launch handshake. micro-ROS bridge to Core Hub for high-level coordination, reporting, and launch requests.

## Pre-Launch Safety Interlocks

The Bay enforces all eight interlocks from [Spark Authority](../addendums/Spark Authority and friday-core-os Definition.md). Each is tied to a specific Bay sensor:

| Interlock | Sensor / source | Required reading |
|---|---|---|
| Rover at zero velocity | `nav_msgs/Odometry` from Locomotion | linear ≤ 0.01 m/s for ≥ 1 s |
| Rover on stable ground | Locomotion IMU tilt | absolute tilt < 5° |
| Bay open and clear | IR break-beam | beam unbroken for ≥ 500 ms |
| Spark docked and locked | Weight pad + lock limit switches | both confirm "engaged" |
| Spark battery ≥ launch threshold | UART query to Spark | reports ≥ 70% SoC |
| Spark system health OK | UART query to Spark | reports `health=OK` |
| Lab Deck fault-free | Friday Labs OS health monitor | no `FaultReport` from Lab Deck pending |
| Operator explicit consent | Per-mission `SparkMissionRequest` from operator | consent flag true |

Any fail = launch refused. `FaultReport` with `category=INTERLOCK_FAILED` and the specific interlock named. Operator is notified.

## Launch Sequence

1. Core Hub publishes `SparkMissionRequest` to the Bay (area, type, mission_id).
2. `bay-safety-checker` evaluates all 8 interlocks. Any fail → refuse with `FaultReport`.
3. Bay confirms via UART to Spark: "preparing for launch, mission_id is X."
4. Spark responds with its own readiness state.
5. Pogo pin power disabled (Spark switches to its own battery).
6. Servo lock disengages. Limit switch confirms.
7. Bay publishes "ready for launch" event; Spark powers up rotors and takes off.
8. IR beam confirms Spark has cleared the corridor.
9. State transitions to "Spark in flight" — Bay's role narrows to passive monitoring and return coordination.

## Dock Sequence

1. Spark requests permission to dock (via its own RF link, routed through [Telemetry Command Node](../architecture/Telemetry Command Node.md) to Core, then to Bay).
2. Bay confirms cradle is clear (weight pad reads empty, IR beam unbroken).
3. Bay enables dock-mode (lock unengaged, charging contacts ready but unpowered).
4. Spark descends; V-cradle physically guides it into alignment.
5. Weight pad triggers (Spark seated).
6. Servo lock engages; limit switch confirms engaged.
7. Charging contacts powered; INA219 confirms current draw.
8. UART link re-established; Bay queries post-mission status.
9. State transitions to "docked and charging."

## Responsibilities

- Hold Spark securely during rover motion (lock engaged, verified by limit switch).
- Evaluate and enforce pre-launch interlocks.
- Operate the servo lock (open for launch / closed for transit and charging).
- Charge Spark via the pogo pin contacts; monitor current and battery state.
- Maintain UART link to Spark while docked.
- Publish Spark dock state, charging state, battery, and bay sensor states to Core.
- Cause the rover to refuse motion while Spark is mid-launch or mid-dock (by publishing a fault, not by direct authority — Locomotion holds motion authority).
- Publish heartbeat and health like every other module.
- Honor lifecycle safe-state: lock engaged, charging continues if Spark docked, no launches accepted.

## Lifecycle Behavior

| State | Behavior |
|---|---|
| `unconfigured` | Boot. No actuation. Sensors not polled. |
| `configuring` | Initialize servo, limit switches, IR beam, INA219, UART. Self-test the lock cycle (open/close/open) only if Spark is NOT docked. Register via `RegisterModule.srv`. |
| `inactive` (safe-state) | Lock engaged. Charging continues if Spark docked. No launches accepted. Sensors polled at reduced rate (1 Hz). Heartbeats at 1 Hz. |
| `active` | Full operation. All sensors polled. Launch/dock sequences enabled. Heartbeats at 5 Hz. |
| `error` | `FaultReport` published. Drop to `inactive` safe-state. Lock remains engaged. |
| `finalized` | Lock engaged. UART released. Power-off path. |

A Bay in `error` or `finalized` does NOT release the lock. Spark stays secured to the rover until the Bay is operator-recovered.

## Failover Behavior

| Trigger | Behavior |
|---|---|
| Pre-launch interlock fails | Launch refused. `FaultReport` with specific interlock named. |
| Spark UART unresponsive while docked | `FaultReport` with `category=SPARK_COMMS_LOST`. Lock remains engaged. Charging continues if current is flowing. |
| IR beam broken during launch sequence | Launch aborted. Lock re-engages. `FaultReport` with `category=LAUNCH_OBSTRUCTION`. |
| Lock limit switches disagree (lock partially engaged) | `FaultReport` with `category=LOCK_FAULT`. Bay enters `error`. Operator recovery required. |
| Charging over-current | Pogo pin power cut. `FaultReport` with `category=CHARGE_FAULT`. |
| Watchdog trips (Core Hub heartbeat lost ≥ 100 ms) | Lock engages if not already (default safe state). Charging continues if Spark docked. Bay continues passive monitoring. |
| Bay process crashes / micro-ROS bridge dies | Lock physically held in engaged position (servo holds against return spring). Spark remains secured. `safety-supervisor` on Core logs Bay loss and notifies operator. |

The Bay's safe-state is **"lock engaged, Spark secured."** This is the only sensible default for a system that holds an aircraft on a vehicle that drives around.

## Message Types

**Subscribed (input):**

- `friday_msgs/SparkMissionRequest` (QoS `state_default`)
- `friday_msgs/EmergencyStop` (QoS `critical_reliable`)
- `friday_msgs/RecoveryCommand` (QoS `critical_reliable`)
- `friday_msgs/AuthorityLease` (QoS `critical_reliable`)
- `nav_msgs/Odometry` from Locomotion (subscribed for the rover-stationary interlock)
- `sensor_msgs/Imu` from Locomotion (for the rover-stable interlock)
- `lifecycle_msgs/srv/ChangeState`

**Published (output):**

- `friday_msgs/SparkStatus` (QoS `state_default`, 1 Hz) — docked, charging, in_flight, battery_pct, mission_id, pose (rover-relative when docked).
- `friday_msgs/Heartbeat` (QoS `heartbeat`, 5 Hz active / 1 Hz safe-state).
- `friday_msgs/HealthStatus` (QoS `state_default`, 1 Hz) — includes bay sensor states.
- `friday_msgs/FaultReport` (QoS `critical_reliable`, on event).
- `friday_msgs/PowerState` (QoS `state_default`, 1 Hz) — Spark charging current and Bay subsystem draw.

## Software Tasks (firmware-internal)

- `spark-bay-controller` — top-level state machine, lifecycle compliance.
- `launch-sequence-manager` — orchestrates the 9-step launch sequence.
- `dock-sequence-manager` — orchestrates the 9-step dock sequence.
- `docking-state-monitor` — continuous sensor polling, dock state derivation.
- `charging-monitor` — INA219 polling, charge curve management, fault detection.
- `bay-safety-checker` — evaluates the 8 pre-launch interlocks.
- `spark-uart-bridge` — UART to Spark, message framing, timeout handling.
- `lock-controller` — single servo PWM control with limit-switch feedback.
- `ir-beam-monitor` — break-beam state with debouncing.
- `safe-stop-handler` — lock-engage on watchdog or EmergencyStop.
- `heartbeat-publisher` / `health-publisher`.

## Authority Compliance

The Bay never publishes motion commands. It enforces pre-launch interlocks, which is a *consent* relationship — Core Hub asks, Bay says yes or no. The Bay accepts `SparkMissionRequest` only from the current `authority` lease holder; requests from other sources are rejected per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).

## Provisioning

- ESP32-S3 firmware identity `MARK1-SPARKBAY-001` (configurable via NVS).
- USB CDC at 921600 baud minimum to Core Hub.
- Hardware Task WDT configured at 100 ms — on trip the lock engages (default safe state).
- Heartbeat protocol per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).
- OTA support via [dual-bank ESP-IDF OTA](../addendums/OTA Update Strategy.md).
- Self-test of lock cycle on boot only when Spark is NOT docked.

## Open Design Areas

- **Spark hardware specification** — drone form factor, weight, battery, RF link. To be specified in the Spark dossier (not in scope here).
- **Long-range Spark coordination** — Bay coordinates Spark only at dock; mid-mission Spark coordination rides on the [Telemetry Command Node](../architecture/Telemetry Command Node.md)'s LoRa channel. Interface between Telemetry and Bay for Spark mission relay to be specified.
- **Multi-Spark swarms** — Mark 2/3 feature. The Bay design here supports exactly one Spark.
- **Active alignment** (magnetic dock assist, optical alignment) — defer to Mark 2 unless V-cradle proves insufficient in field testing.
- **Spark return-without-docking** — what happens when Spark lands somewhere other than the Bay (low battery, comms loss). Recovery coordination spec to be written.

## Acceptance Criteria

- All 8 pre-launch interlocks correctly enforce on bench: each fails launch when its sensor reports a fail condition.
- Lock cycle (open → close → confirm) completes in ≤ 500 ms.
- Killing the Bay process during a charging session leaves the lock engaged and Spark secured. Verified on bench.
- Watchdog trip leaves the lock engaged.
- Launch sequence aborts cleanly if the IR beam breaks mid-sequence.
- Spark UART link survives a full 4-hour charging session with zero dropped messages.

## Related

[Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) · [Power Budget](../addendums/Power Budget.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
