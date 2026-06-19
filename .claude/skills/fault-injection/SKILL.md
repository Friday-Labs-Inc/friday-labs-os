---
name: fault-injection
description: Run Stage 5 fault-injection scenarios against the Mark 1 sim with quantitative acceptance criteria. Use when validating the safety/recovery path, after any change to lifecycle, registry, supervisor, or safe-stop. Kills the Core node, cuts Locomotion comms, forces split-brain, and reports measured latencies against budget.
---

# Fault Injection (Sim Stage 5)

This is the most important stage of bring-up. It is where the real-time safe-stop path and the split-brain authority question become testable.

Reference: `Mark 1 Simulation and Dev Environment.md` (Stage 5 + Honest Limits).

## Budgets (the only thing that makes "pass" mean something)

| Scenario | Measure | Budget |
|---|---|---|
| Core Compute Hub process killed | Time until Telemetry Node detects loss and enters recovery mode | ≤ 1.5 s |
| Core Compute Hub process killed | Time until Locomotion safe-stop is active in sim | ≤ 500 ms from comms loss (firmware watchdog path) |
| Locomotion comms link cut | Time until motors at zero velocity in sim | ≤ 200 ms (firmware watchdog path) |
| Core Compute Hub restarted after recovery | Time until authority handoff completes cleanly | ≤ 2 s; zero conflicting commands during handoff |
| Telemetry Node killed while Core healthy | Time until Core declares Telemetry DEAD and notifies operator | ≤ 1.5 s |
| Both Core and Telemetry killed | ESP32 emergency beacon active over LoRa | ≤ 5 s |

If a budget is missing for a scenario you need, define it explicitly before running — do not run "to see what happens."

## Scenarios

### S1 — kill Core Compute Hub

1. With sim healthy and a mission in progress, `kill -9` the Core process.
2. Observe `system-health-manager` on Telemetry Node detect loss via DDS liveliness + app-level check.
3. Observe Locomotion firmware watchdog fire safe-stop.
4. Observe Telemetry Node enter recovery mode and send `EmergencyStatus` to mock Command Center.
5. Restart Core. Observe authority handoff per the (TBD) authority-lease protocol.
6. **Record:** detection latency, safe-stop latency, handoff latency, any conflicting commands during handoff.

### S2 — cut Locomotion comms

1. Use `tc` / `iptables` (or sim network shim) to drop all traffic to/from the Locomotion namespace.
2. Observe Locomotion firmware watchdog fire safe-stop.
3. Observe `fault-manager` log `LOCOMOTION_COMMS_LOST`.
4. Restore link; observe re-registration via `RegisterModule.srv`.
5. **Record:** time-to-stop, time-to-rejoin, any motion during the gap.

### S3 — force split-brain

1. Partition the network so Core and Telemetry can both reach Locomotion but not each other.
2. Observe each side's belief about who holds authority.
3. **This is the test that exposes the gap.** If both sides issue commands, the authority-lease protocol is not yet defined — file an issue against the contract and stop. Do not patch around it.

### S4 — Core restart mid-recovery

1. Run S1, but in the middle of Telemetry's recovery sequence, restart Core.
2. Observe whether Telemetry relinquishes authority cleanly.
3. **Record:** any duplicated commands, any state desync between Core's resumed view and Telemetry's shadow state.

### S5 — total compute loss

1. Kill Core and Telemetry Node simultaneously.
2. Observe backup ESP32 wake and begin minimal LoRa beacon.
3. **Record:** time-to-beacon, beacon content correctness.

## Output

Generate a report per run with: scenario id, measured latencies, budget pass/fail, any anomalies, bag file path for replay. CI failures should print the failing budget line first, not bury it.

## What this skill refuses to do

- Report "pass" without quantitative latencies.
- Run S3 without an authority-lease protocol on file — exposing the gap is the goal, not papering over it.
- Treat "Telemetry took over cleanly" as a vibe. Define what cleanly means before the run.
