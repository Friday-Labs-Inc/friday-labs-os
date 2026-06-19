---
name: safe-stop-audit
description: Audit the end-to-end safe-stop chain on a Mark 1 module and report worst-case latency from heartbeat-loss to motors-off. Use before any field test, before adding a new actuator, or after touching the Locomotion firmware, micro-ROS bridge, or heartbeat QoS. Refuses to declare pass without firmware-level watchdog independence verified.
---

# Safe-Stop Audit

The contract heartbeat numbers (200 ms publish, 500 ms deadline, ~1 s liveliness) are NOT a safe-stop budget — they are a presence-detection budget. Safe-stop must beat them by an order of magnitude, and must not depend on the micro-ROS bridge being alive.

Reference: `ROS 2 Interface and Message Contract.md` (Heartbeat + Fault Detection); `Friday Labs OS Architecture.md` (Fallback rules).

## What you are auditing

Trace and time each link in the chain:

```
Pi heartbeat publisher
  → DDS deadline event on subscriber
  → system-health-manager declares DEGRADED/DEAD
  → fault-manager decides safe-stop
  → command-router publishes EmergencyStop
  → micro-ROS agent on owning Pi
  → ESP32 firmware receives EmergencyStop
  → motor PWM at zero
```

Parallel to this, the **independent firmware watchdog** path:

```
ESP32 watchdog: heartbeat-from-Pi missing for >100 ms
  → firmware-local safe-state
  → motor PWM at zero
```

The firmware-watchdog path MUST be shorter and MUST function with the micro-ROS bridge dead.

## Procedure

1. **Instrument both paths.** Add timestamping at each named hop.
2. **Run bench tests** (sim or hardware-in-the-loop is fine; pure sim is not because it cannot reproduce real serial/USB jitter):
   - Path A: kill the Pi heartbeat publisher cleanly. Measure time to motor-off via DDS chain.
   - Path B: kill the micro-ROS agent process on the Pi. Heartbeat goes silent. Measure time to motor-off via firmware watchdog.
   - Path C: yank the serial cable. Same measurement.
3. **Repeat each 50 times.** Report p50, p95, p99, max. p99 is the budget number.

## Budgets

| Path | p99 budget |
|---|---|
| Firmware watchdog (B and C) | ≤ 150 ms |
| DDS chain emergency stop (A) | ≤ 500 ms |

If the firmware watchdog p99 exceeds 150 ms, the rover is not safe to field-test in proximity to people, livestock, or property — say so plainly in the report.

## Hard requirements before declaring pass

- The firmware watchdog timer source is independent of any code path that runs in normal duty (use the ESP32's hardware watchdog peripheral, not a FreeRTOS soft timer).
- Killing the micro-ROS agent does NOT prevent path B from firing within budget.
- The safe-state behavior holds steering and brake — not just motor PWM. Audit both.
- The watchdog cannot be silenced by a malformed or replayed heartbeat from the bridge.

## Output

Report format:

```
Module: <id>
Bench: <sim | hil | bench>
Samples: 50

Path A (DDS EmergencyStop):  p50 _ ms  p95 _ ms  p99 _ ms  max _ ms  [PASS/FAIL ≤500ms]
Path B (firmware watchdog):  p50 _ ms  p95 _ ms  p99 _ ms  max _ ms  [PASS/FAIL ≤150ms]
Path C (serial yank):        p50 _ ms  p95 _ ms  p99 _ ms  max _ ms  [PASS/FAIL ≤150ms]

Brake engaged on safe-state: yes / no
Steering held: yes / no
Watchdog source: hw timer / fw timer  [must be hw]
Bridge-independence verified: yes / no  [must be yes]

Overall: PASS / FAIL
Sign-off: <author>, <date>
```

## What this skill refuses to do

- Declare pass with a FreeRTOS soft-timer-based watchdog.
- Declare pass without bench-measured numbers — sim alone is not sufficient.
- Round latencies down or report averages instead of p99.
