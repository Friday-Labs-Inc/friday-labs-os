# Authority Lease Protocol

> Resolves the split-brain authority gap between the [Core Compute Hub](../architecture/Friday Labs OS Architecture.md) and the [Telemetry Command Node](../architecture/Telemetry Command Node.md). Defines who is authorized to issue motion / recovery / emergency commands at any given moment.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 design gap before service logic is written.

## The Problem

When the Core Compute Hub crashes and the Telemetry Command Node takes over, both nodes must agree on who holds command authority — including when Core boots back up. Without a defined protocol, both can simultaneously believe they are in charge, sending conflicting commands to the Locomotion Control Unit. The rover sees contradictory orders and behavior is undefined.

## The Lease

A single rover-wide token called `authority`. Whoever holds it is the only node permitted to publish motion, recovery, or emergency commands. The Locomotion Control Unit rejects commands from any source that is not the current authority holder.

## Lease Parameters

- **Duration:** 2 seconds.
- **Renewal interval:** 500 ms.
- **Persistence:** in-memory only on the holder. Never written to disk.
- **Default holder on clean boot:** Core Compute Hub. Telemetry Node boots in monitoring mode.

A node that crashes and reboots MUST come back assuming it holds no authority. Disk-persisted leases would let a recovering node continue commanding without realizing Telemetry has taken over — that failure mode is excluded by design.

## Failover

Telemetry self-promotes (takes the lease) only when **both** of these are true:

1. Core's lease has expired — no renewal received for 2 seconds.
2. Core's heartbeat has been missing for ≥ 1.5 seconds.

Two independent signals are required. A stuck renewer with healthy heartbeats — or vice versa — does not trigger failover. Worst-case failover latency: ~2.5 seconds.

## Authority Return

When Core comes back online while Telemetry holds the lease:

1. Core broadcasts `RequestAuthority` to Telemetry.
2. Telemetry confirms the rover is in a stable state (no motion, no active fault).
3. Telemetry publishes `ReleaseAuthority` and stops issuing commands.
4. Core observes the release, takes the lease, begins commanding.
5. A **500 ms quiet window** sits between release and acquire. During this window, neither node commands; Locomotion treats this as "no new commands" and holds the previous safe state.

## What Losing the Lease Means

A non-authority node:

- Stops publishing motion, recovery, and emergency commands.
- Continues sensing, fusion, registry maintenance, and health reporting.
- Continues forwarding mission telemetry where applicable.

Authority is about command issuance, not about observation. Both nodes always have full situational awareness.

## Conflict Resolution

Every lease transition increments a monotonically increasing `epoch` counter. If a network partition heals and two nodes both believe they hold the lease, the node with the lower epoch immediately stands down and re-requests via the standard return procedure.

## ESP32 Backup Authority

The backup ESP32 on the Telemetry Command Node holds **no authority**. When both Pis are dead:

- ESP32 broadcasts the LoRa "Mark 1 alive, awaiting recovery" beacon.
- ESP32 does not issue motion, recovery, or stop commands.

Motion safety in this scenario is handled by the [Locomotion Control Unit](../architecture/Mark 1 Compute Architecture.md#module-3-locomotion-control-unit)'s firmware watchdog, which trips safe-stop independently when its own Pi heartbeat falls silent. See the safe-stop latency budget addendum for the firmware watchdog spec.

ESP32 authority may be revisited in Mark 2 once the Pi-only protocol is proven in the field.

## Implementation

**New service:** `authority-lease-service`, running on both the Core Compute Hub and the Telemetry Command Node.

**Topic:** `/mark1/system/authority` — QoS profile `critical_reliable`.

**New `friday_msgs` interfaces** (use the [friday-msgs-author](../../.claude/skills/friday-msgs-author/SKILL.md) skill to add these):

```
# AuthorityLease.msg
uint8  protocol_major
uint8  protocol_minor
uint16 protocol_patch
string holder_module_id
uint64 epoch
builtin_interfaces/Time expires_at
builtin_interfaces/Time stamp

# RequestAuthority.srv
string requester_module_id
uint64 last_known_epoch
builtin_interfaces/Time stamp
---
bool granted
uint64 new_epoch
string reason

# ReleaseAuthority.msg
string releasing_module_id
uint64 epoch
string reason
builtin_interfaces/Time stamp
```

Command-issuing services (`command-router`, `safety-supervisor`) on both nodes must check the current lease holder before publishing. The Locomotion Control Unit rejects commands whose `source` field does not match the current holder.

## Acceptance Criteria

- Killing the Core process while Telemetry is monitoring triggers Telemetry failover within 2.5 s — verified by Stage 5 scenario S1 ([fault-injection](../../.claude/skills/fault-injection/SKILL.md)).
- Restarting Core while Telemetry holds the lease completes a clean handoff with zero conflicting commands during the transition — verified by S4.
- Forced network partition (both nodes can reach Locomotion but not each other) does not result in both sides issuing motion commands — verified by S3.

**Status (Phase 4):** S1, S3, and S4 are ✅ **verified in node-sim on the Legion farm** — failover in ~2.0 s; a stale lower-epoch lease ignored at the consumer; clean hand-back with the holder/epoch sequence `CORE@1 → TLM@2 → CORE@3`. The formal Stage 5 fault-injection harness and the HIL 100 ms p99 watchdog remain.

## Open Items

- Confirm `epoch` width: `uint64` survives ~584 billion years at one transition per second. Locked.
- ✅ **Locked (Phase 4 build):** a `last_known_epoch` mismatch in `RequestAuthority` is **granted iff the requester's epoch ≥ the current holder's** (and only while the rover is stable — no motion / no active fault); rejected otherwise. Implemented in the ROS-free `authority.may_grant_return`; verified by S4.

## Related

[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Telemetry Command Node](../architecture/Telemetry Command Node.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) · [Mark 1 Index](../Mark 1 Index.md)
