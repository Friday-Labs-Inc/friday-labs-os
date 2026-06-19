---
name: qos-audit
description: Audit a ROS 2 node's publishers/subscribers/services against the locked Friday Labs OS QoS policy. Use after writing a new module agent, after a `friday_msgs` change, or before merging into main. Catches the silent failure where a critical command is published BEST_EFFORT and gets dropped under load.
---

# QoS Audit

QoS mismatches are silent — the build is green, the test passes once, and then under load the wrong messages get dropped. This skill makes the policy enforceable.

Reference: `ROS 2 Interface and Message Contract.md` (QoS Profiles section).

## The four locked profiles

| Profile | Reliability | Durability | History | Extras |
|---|---|---|---|---|
| `critical_reliable` | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST 10 | — |
| `state_default` | RELIABLE | VOLATILE | KEEP_LAST 10 | — |
| `sensor_stream` | BEST_EFFORT | VOLATILE | KEEP_LAST 5 | — |
| `heartbeat` | BEST_EFFORT | VOLATILE | KEEP_LAST 1 | Deadline 500 ms, Liveliness AUTOMATIC lease 1 s |

## Which interface gets which profile

| Interface | Profile |
|---|---|
| `Heartbeat.msg` | `heartbeat` |
| `HealthStatus.msg`, `PowerState.msg`, `ModulePresence.msg`, `MissionStatus.msg`, `nav_msgs/Odometry`, `FaultReport.msg`, `LogEvent.msg` | `state_default` |
| `MotionCommand.msg` (non-emergency), `RegisterModule.srv`, `ExecuteCommand.action` | `state_default` |
| `EmergencyStop.msg`, `RecoveryCommand.msg`, `SAFE_STOP MotionCommand` | `critical_reliable` |
| `sensor_msgs/PointCloud2`, `sensor_msgs/Image`, `sensor_msgs/Imu`, `MapSegment.msg`, `DetectedObjectArray.msg` | `sensor_stream` |

If you encounter an interface not on this list, the contract is incomplete — file an issue, do not guess.

## Procedure

1. Get the live QoS for every topic on the node:
   ```
   ros2 topic info -v /mark1/<module>/<topic>
   ```
2. Compare against the table above. Flag any mismatch.
3. For each mismatch, classify:
   - **Critical** — `EmergencyStop` / `RecoveryCommand` / `SAFE_STOP` not on `critical_reliable`. **Block merge.**
   - **High** — `Heartbeat` not on `heartbeat` (no Deadline → presence detection broken). Block merge.
   - **Medium** — sensor stream on `state_default` (will back-pressure the bus). Fix before integration test.
   - **Low** — state topic on `sensor_stream` (occasional loss of e.g. fault report). Fix before field test.
4. Check that subscribers' QoS is **compatible** with publishers (RELIABLE sub on BEST_EFFORT pub will silently drop). `ros2 topic info -v` reports the compatibility status.
5. For `heartbeat`, verify Deadline events actually fire when expected — `ros2 topic echo --qos-profile heartbeat` and stop the publisher; the subscriber should see a deadline-missed event.

## Output

```
Module: <id>
Topics audited: <N>
Critical issues: <list with topic + actual QoS + required QoS>
High issues: <list>
Medium issues: <list>
Low issues: <list>
QoS-compatibility breaks: <list of pub/sub pairs>
Overall: PASS / FAIL
```

## What this skill refuses to do

- Pass a node that publishes EmergencyStop on anything other than `critical_reliable`.
- Pass a node whose Heartbeat publisher has no Deadline (presence detection silently degrades to "missing topic forever").
- Ignore a pub/sub compatibility break with the excuse "it works in testing." It will not work under load.
