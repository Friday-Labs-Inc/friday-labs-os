# Locomotion Control Unit

> Real-time motor, steering, and motion-safety controller for [Mark 1](../architecture/Mark 1 Compute Architecture.md). Owns the firmware-level safe-stop watchdog and the closed-loop velocity / steering / odometry path.
> **Version:** Draft 1.0 · **Purpose:** Software team handoff · **Reports to:** [Friday Labs OS](../architecture/Friday Labs OS Architecture.md) as a managed lifecycle node.

## Role

The Locomotion Control Unit is Mark 1's hands and feet. It converts high-level motion commands from the Core Compute Hub into real motor and steering behavior, reports odometry and faults back, and — most importantly — trips safe-stop autonomously when its link to the Pi goes silent.

It is a [lifecycle node](../architecture/ROS 2 Interface and Message Contract.md) running on an ESP32-S3 microcontroller, joining the Friday Labs OS DDS graph via micro-ROS over USB CDC to the Core Compute Hub.

The unit is the **only module with direct motor authority**. Every other module that influences motion does so by publishing requests; the Locomotion Control Unit decides whether and how those requests become PWM signals.

## Hardware Direction

| Component | Spec |
|---|---|
| Microcontroller | ESP32-S3 with USB OTG (e.g. ESP32-S3-DevKitC, ~$10) |
| Drive motors | 6× brushed DC geared motors, ~$10-30 each |
| Drive motor drivers | 3× dual-channel H-bridges (TB6612FNG for low current, BTS7960 for higher) |
| Steering | 4× hobby servos with metal gears (~$15 each), corner-only steering on the 4 outer wheels (middle pair drive-only, per [Mechanical Design Reference](../addendums/Mechanical Design Reference.md) — Perseverance anatomy) |
| Wheel encoders | 6× AS5600 magnetic absolute encoders, I2C-multiplexed via TCA9548A |
| IMU | BNO085 with on-chip 9-DoF sensor fusion (I2C, ~$25-30) |
| Optional GPS | NEO-M9N or similar (UART, mission-dependent) |
| Pi communication | USB CDC over ESP32-S3's native USB OTG |
| Power monitoring | INA219 current/voltage sensor on the motor power bus |
| Watchdog source | ESP32-S3 hardware watchdog timer peripheral (Task WDT) |

Total Locomotion BOM target (excluding chassis kit and motors): **~$90-150**.

## Core Principle

**The firmware-level safe-stop is the rover's primary safety reflex, not its fallback.** Every other safety mechanism — DDS EmergencyStop, lifecycle deactivate, operator commands — is a graceful interface. The hardware watchdog is the only one that survives a Pi crash, a USB cable yank, or a micro-ROS bridge failure. The rest of this spec is shaped by that priority.

## Three Internal Layers

**Layer 1 — Motion Control Loop.** Real-time closed-loop velocity and steering control. Runs at 100 Hz as FreeRTOS task `motion_loop`, pinned to core 1 of the ESP32-S3. Reads encoder positions, computes per-wheel velocity error against the current goal, applies PID, writes PWM duty to the H-bridges. Drives the 4 corner-steering servos via PWM at 50 Hz on a separate LEDC timer.

**Layer 2 — Safe-Stop Watchdog.** ESP32-S3 hardware Task WDT with 100 ms inactivity timeout. Reset only when a well-formed, fresh, in-sequence heartbeat arrives over USB CDC from the Core Hub. On trip: PWM to all 6 drive motors clamped to active-hold (zero commanded velocity with holding torque applied), 4 corner-steering servos commanded to *current* angle (no movement), state stored in NVS for post-recovery debug. See [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) for budgets and rationale.

**Layer 3 — micro-ROS Bridge.** `rclc_lifecycle` node exposing the Friday Labs OS contract on the DDS graph. Publishes Odometry, HealthStatus, Heartbeat. Subscribes MotionCommand, EmergencyStop, RecoveryCommand, AuthorityLease. Handles lifecycle transitions per [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md).

## Responsibilities

- Receive `MotionCommand` from the current authority-lease holder (Core Hub during normal operation, Telemetry Node during failover).
- Reject any command whose `source` does not match the current authority lease ([Authority Lease Protocol](../addendums/Authority Lease Protocol.md)).
- Reject any command whose signature is invalid or whose nonce is not strictly greater than the last seen for that source.
- Drive 6 wheel motors and 4 corner-steering servos to achieve commanded velocity and pose.
- Publish Odometry at 50 Hz, frame `odom`.
- Publish Heartbeat at 5 Hz active / 1 Hz safe-state.
- Publish HealthStatus at 1 Hz.
- Detect wheel stall (commanded vs measured velocity divergence > 50% for > 2 s) and report `FaultReport` with `category=STALL`.
- Detect slip (left/right wheel pair velocity differential > 30% inconsistent with steering command) and report `FaultReport` with `category=SLIP`.
- Monitor motor current per channel; trip safe-stop and FaultReport on sustained over-current.
- Trip safe-stop on hardware watchdog timeout (100 ms).
- Honor [active-hold safe-state](../addendums/Safe-Stop Latency Budget.md) on lifecycle deactivate and on watchdog trip.

## Movement Command Types

| Type | Behavior |
|---|---|
| `MOVE` | Steering angle held; drive motors at commanded linear velocity. |
| `STOP` | All drive motors to zero velocity via graceful 500 ms deceleration ramp. |
| `TURN` | Steering computed for the requested angular velocity; drive speeds differentially adjusted for the turn. |
| `SET_VELOCITY` | Linear and angular velocity set directly. Used by autonomy stack. |
| `SET_STEER` | Steering angle set without changing drive (slow maneuvers, pre-launch alignment). |
| `PATH_SEGMENT` | Execute a sequence of waypoints (≤ 1000 points per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md)). |
| `SAFE_STOP` | Immediate active-hold safe-state. Mirrors watchdog-trip behavior. |

## Sensors Owned

- 6× wheel encoders (position, velocity, integrated wheel odometry) via AS5600 + TCA9548A I2C multiplexer.
- 4× corner-steering position feedback (from servo analog feedback pins where available; commanded position otherwise).
- IMU (`sensor_msgs/Imu`) at 100 Hz, frame `base_link`. BNO085 publishes fused quaternion + raw accel/gyro.
- INA219 current/voltage on motor bus, reported in `HealthStatus` and `PowerState`.
- Optional GPS (`sensor_msgs/NavSatFix`) at 5 Hz when present.

Wheel temperature and per-wheel current sensing are deferred to Mark 2.

## Lifecycle Behavior

| State | Behavior |
|---|---|
| `unconfigured` | Boot. No PWM output. No publishers active. Watchdog armed at default 100 ms (no motion authority yet, no impact). |
| `configuring` | Initialize encoders, IMU, ADC. Verify all 6 encoders respond. Register via `RegisterModule.srv`. |
| `inactive` (safe-state) | Steering servos commanded to current angle and powered to hold. Drive motors at zero velocity with active holding torque. Watchdog armed. Heartbeats at 1 Hz (degraded). |
| `active` | Full motion control loop running. Watchdog armed at 100 ms. Heartbeats at 5 Hz. MotionCommands accepted from current authority holder. |
| `error` | FaultReport published. Equivalent to `inactive` safe-state. Recovery requires explicit `safety-supervisor` transition through `inactive → active`. |
| `finalized` | All PWM disabled. Power-off path. |

The lifecycle node does NOT self-recover from `error`. An operator-issued `RecoveryCommand` is required to clear the fault and re-enter `active`.

## Failover Behavior

| Trigger | Behavior |
|---|---|
| Hardware watchdog trip (≥100 ms no heartbeat) | Active motor hold + steering frozen. FaultReport with `category=WATCHDOG` published when bridge reconnects. |
| DDS `EmergencyStop` from authority holder | Same safe-state as watchdog trip. Immediate. |
| `MotionCommand.source` mismatched to authority lease | Command rejected, no execution. Rate-limited FaultReport with `category=SECURITY_AUTH`. |
| Stall (>50% velocity divergence >2 s) | Motors clamped, FaultReport with `category=STALL`. Recovery requires operator. |
| Sustained over-current (>peak >500 ms on motor bus) | Motors disabled, FaultReport with `category=OVERCURRENT`. |
| micro-ROS agent disconnects (USB unplugged or agent process killed) | Watchdog trips within 100 ms (no heartbeats arrive). Bridge attempts auto-reconnect on USB re-detect. |

## Message Types

**Subscribed (input):**

- `friday_msgs/MotionCommand` (QoS `state_default`)
- `friday_msgs/EmergencyStop` (QoS `critical_reliable`)
- `friday_msgs/RecoveryCommand` (QoS `critical_reliable`)
- `friday_msgs/AuthorityLease` (QoS `critical_reliable`)
- `lifecycle_msgs/srv/ChangeState`

**Published (output):**

- `nav_msgs/Odometry` (QoS `state_default`, 50 Hz)
- `sensor_msgs/Imu` (QoS `sensor_stream`, 100 Hz)
- `sensor_msgs/NavSatFix` (QoS `sensor_stream`, 5 Hz, when GPS is present)
- `friday_msgs/Heartbeat` (QoS `heartbeat`, 5 Hz active / 1 Hz safe-state)
- `friday_msgs/HealthStatus` (QoS `state_default`, 1 Hz)
- `friday_msgs/FaultReport` (QoS `critical_reliable`, on event)
- `friday_msgs/PowerState` (QoS `state_default`, 1 Hz, includes motor bus current/voltage)

## Software Tasks (firmware-internal)

- `motion_loop` — 100 Hz closed-loop velocity/steering control. Core 1, pinned.
- `encoder_reader` — I2C polling of 6 AS5600s via TCA9548A. Every motion_loop tick.
- `imu_reader` — BNO085 polling at 100 Hz. Publishes fused quaternion + raw accel/gyro.
- `odometry_estimator` — Integrates encoder velocity + IMU heading into `nav_msgs/Odometry`.
- `stall_detector` — Monitors commanded-vs-measured divergence per wheel.
- `traction_monitor` — Cross-wheel speed differential consistency check.
- `current_monitor` — INA219 polling. Trips over-current safe-stop.
- `safe_stop_handler` — Single authoritative path into safe-state. Idempotent. Called by watchdog ISR, EmergencyStop subscriber, stall detector, or over-current monitor.
- `heartbeat_publisher` — 5 Hz active / 1 Hz safe-state.
- `health_publisher` — 1 Hz HealthStatus.
- `micro_ros_agent_handler` — Manages USB CDC connection, lifecycle node, rclc executor.
- `command_validator` — Checks authority-lease holder + signature + nonce before forwarding any command to `motion_loop`.

## Authority Compliance

The Locomotion Control Unit subscribes to `/mark1/system/authority` and tracks the current lease holder. `MotionCommand`, `EmergencyStop`, and `RecoveryCommand` messages whose `source` field does not match the current holder are rejected silently (except for a rate-limited counted FaultReport to avoid log flood under sustained mismatch). See [Authority Lease Protocol](../addendums/Authority Lease Protocol.md).

## Provisioning

- ESP32-S3 firmware identity (`MARK1-MOB-001` by default; configurable via NVS).
- USB CDC at 921600 baud minimum.
- Hardware Task WDT configured at 100 ms.
- Heartbeat protocol per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).
- Safe-state behavior verified by [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) before any field test.
- OTA support via [dual-bank ESP-IDF OTA](../addendums/OTA Update Strategy.md).
- Fault reporting per `friday_msgs/FaultReport`.
- Low-power deep-sleep support deferred to Mark 2.

## Open Design Areas

- **Chassis kit selection** — within the [Power Budget](../addendums/Power Budget.md) BOM target. Candidates: Lynxmotion 6WD chassis ($300-500), generic AliExpress 6-wheel rocker-bogie ($150-300), or 3D-printed Curio Rover (~$200 in parts if printer available). To be locked in Phase 1 hardware.
- **PID tuning per wheel** — must be done on bench with the chosen motors and gearing.
- **GPS** — optional, mission-dependent, not in baseline BOM.
- **Per-wheel temperature sensing** — Mark 2.
- **Redundant secondary heartbeat path** (e.g. UART alongside USB CDC) for double-fault tolerance — defer to Mark 2 unless [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) reveals USB jitter exceeding budget on real hardware.

## Acceptance Criteria

- All 6 wheels respond correctly to MOVE, STOP, TURN, SET_VELOCITY, SET_STEER commands in [Gazebo Stage 1](../../.claude/skills/sim-bringup/SKILL.md) and on bench.
- Odometry publishes at 50 Hz steady-state with no missed deadlines under load.
- [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) passes all three paths (DDS, micro-ROS kill, USB unplug) within budget — see [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md#acceptance-criteria).
- [fault-injection](../../.claude/skills/fault-injection/SKILL.md) scenarios S1, S2, S3, S4 pass with this node in the loop, all p99 latencies under budget.
- Command rejection works: a `MotionCommand` published with `source` != current lease holder does NOT result in motor PWM change, verified by S3.
- Active-hold safe-state holds the rover stationary on a 15° slope for ≥ 10 minutes without drift.

## Related

[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Power Budget](../addendums/Power Budget.md) · [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
