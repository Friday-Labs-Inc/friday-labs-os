# Telemetry Command Node

> Communication, recovery, and internet-gateway subsystem for the [Mark 1](Mark 1 Compute Architecture.md) rover.
> **Version:** Draft 1.0 · **Purpose:** Software team handoff · **Reports to:** [Friday Labs OS](Friday Labs OS Architecture.md) (as a peer, not a subordinate)

## Role

The Telemetry Command Node is Mark 1's lifeline to the outside world and its recovery layer if the Core Compute Hub goes silent. It is three things at once:

1. **Resilient command proxy** — receives, validates, and routes Command Center instructions to Friday Labs OS on the Core Compute Hub.
2. **Recovery layer** — maintains a shadow copy of rover state and can act independently when the Core Compute Hub is unreachable.
3. **Internet gateway** — manages all external connectivity with multi-path routing across cellular and other channels, and brokers optional cloud access for the Core Compute Hub.

It is **not** subordinate to the Core Compute Hub. It is a peer with different responsibilities and decision-making authority in a failure scenario.

## Hardware Direction

- Raspberry Pi 4 (4 GB) running the main Node services. Ubuntu 24.04 LTS with [A/B partition layout](../addendums/OTA Update Strategy.md).
- Backup ESP32-S3 emergency support controller. Holds no command authority per [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) — LoRa beacon only.
- Communication interfaces: LoRa, Bluetooth, Wi-Fi, 2G, 4G, 5G modem, with future satellite and long-range radio support.
- External transport: **MQTT 5 over TLS 1.3 with per-rover mTLS + per-operator Ed25519 signing** per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md).

## Core Principle

The Node is not a dumb pipe. It is an intelligent gateway and recovery brain. On long-range autonomous missions — mapping tens of acres in remote terrain — network hiccups or a Core Compute Hub crash must never blind the operator or endanger the rover. The Node keeps Mark 1 connected and safe even when things fail.

## Three Internal Layers

**Layer 1 — Communication Abstraction.** LoRa, Bluetooth, Wi-Fi, 2G/4G/5G cellular, and future satellite all sit behind a single interface. Each channel has its own driver and retry logic. The Node selects the best available channel per traffic type: heavy data (LiDAR map updates, research uploads) over 5G/4G/Wi-Fi when available, lightweight heartbeats and critical alerts over LoRa.

**Layer 2 — Command Routing and Queuing.** Command Center instructions are not blasted straight through. They land in a queue, are validated against current rover state, then routed to Friday Labs OS. If the Core Compute Hub is unreachable, a defined set of critical commands — emergency stop, safe shutdown, recovery reboot — can be executed directly via the Locomotion Control Unit or by activating the backup ESP32.

**Layer 3 — State Sync and Recovery.** The Node maintains a **shadow copy** of Mark 1's state: last known position, battery, module health, mission progress. If the Core Compute Hub goes silent, the Node knows what Mark 1 was doing and can make recovery decisions. It also buffers critical telemetry locally so no data is lost when the network drops.

## Internet Gateway and Multi-Path Routing

The Telemetry Command Node is the rover's internet gateway, and the only path to external networks. The Core Compute Hub has **no direct internet** — it requests cloud services *through* the Node, which decides how to deliver them.

**Multi-path cellular routing.** The Node manages multiple cellular modems (2G/4G/5G) plus Wi-Fi, LoRa, and future satellite as a pool of paths. The routing logic continuously evaluates each path on signal strength, bandwidth, latency, and availability, then:

- **Selects** the best path per traffic class (bulk data vs. control vs. critical alert).
- **Fails over** automatically when a path degrades or drops — e.g. spotty 4G hands off to 5G when in range, or to LoRa for critical alerts when all cellular is gone.
- **Balances** traffic so a bulk upload doesn't starve mission-critical telemetry.

**Brokered cloud access.** When connectivity exists, the Node can serve optional Core Compute Hub requests — map/terrain pre-fetch, research-data upload, remote diagnostics, model retraining pulls — over whatever path is available. Per [AI Inference Location](../addendums/AI Inference Location.md), **AI inference is LOCAL** on the Core Hub's Coral USB Accelerator; the cloud never sits on the autonomy critical path. When connectivity is absent, Mark 1 remains fully autonomous offline; cloud is augmentation, never a dependency. Concentrating this on the Node also centralizes comms security and bandwidth control.

## Telemetry Node Agent

A lightweight agent on the Node speaks the Friday Labs OS protocol. It is the bridge between the Command Center and Friday Labs OS: it receives commands, validates them, routes them to the Core Compute Hub, and sends back telemetry and status. Crucially, it keeps running and can make fallback decisions if the Core Compute Hub is unreachable. It must be lightweight, reliable, and independent.

## Backup ESP32-S3 Emergency Role

The backup ESP32 is **not** the main computer — it is an emergency support controller. It normally sits in ultra-low-power mode. If the main Pi or the Core Compute Hub fails, the Node (or failure-detection logic) wakes it to: broadcast a minimal "Mark 1 alive, awaiting recovery" beacon over LoRa, send basic status, issue wake/reboot signals to compute boards, trigger emergency recovery, and support a basic safe-state command. It is the last line that keeps the Command Center informed in the worst case.

## Software Services

- **network-abstraction-service** — owns all channels; runs the multi-path selection, failover, and load-balancing logic.
- **modem-manager** — manages the 2G/4G/5G cellular modems specifically (registration, signal, SIM/APN, health).
- **command-validation-service** — checks incoming commands against rover state before routing.
- **state-sync-service** — maintains the shadow copy of rover state from the Core Compute Hub, or last-known state on comms loss.
- **fallback-decision-engine** — decides what the Node handles itself when the Core Compute Hub is down (emergency stop, safe shutdown, recovery).
- **telemetry-buffer-service** — local log/audit trail of everything, survives network drops.
- **command-center-link** — maintains the Command Center connection and session.
- **lora-service** / **bluetooth-service** — channel-specific drivers.
- **emergency-esp32-bridge** — interface to the backup ESP32 and its beacon/recovery logic.
- **remote-command-proxy** — handles remote-operator control routing.
- **debug-streaming-service** — see below.

## Failover Behavior

- *Core Compute Hub OK, Telemetry Command Node degraded* → Friday Labs OS attempts restart/recovery of the Node; backup ESP32 minimal comms activated if needed; fault logged; mission continues only if safe.
- *Core Compute Hub fails, Node alive* → Node enters recovery mode, tries to re-establish the Core Compute Hub, sends emergency status to the Command Center, allows limited recovery commands, and triggers safe stop on the Locomotion Control Unit if possible.
- *Both fail, backup ESP32 alive* → ESP32 broadcasts the lowest-power "alive" beacon over LoRa and waits for recovery or manual intervention.

## Command Center Integration

The Command Center talks to Mark 1 primarily through this Node. It supports: live rover status, communication status, battery/power status, mobility state, map progress, sensor health, research mission status, Spark status, manual control mode, autonomous mission upload, emergency stop, recovery command, and logs/diagnostics. Core Compute Hub instructions arrive only through the Node — never via random network paths.

## Debug Streaming

A **debug-streaming-service** routes live debug data (logs, sensor dumps, stack traces) from any module to the **dedicated Command Center debug endpoint** (`mark1/<rover_id>/dbg/...`), isolated from mission telemetry and deprioritized against mission-critical traffic — using a low-bandwidth channel like LoRa for critical alerts when needed. Signed and encrypted like every other channel per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md); on-rover retention follows [Mission Logging and Replay](../addendums/Mission Logging and Replay.md).

## Message Types Handled

Heartbeat, health status, power state, module online/offline, communication status, mission status, emergency stop, recovery command, Spark status, fault report, log event — plus the selected sensor/telemetry streams forwarded to the Command Center.

## Provisioning

**Ubuntu 24.04 LTS** base image with [A/B partition layout](../addendums/OTA Update Strategy.md); Friday Labs OS runtime + Telemetry Node Agent; ROS 2 Jazzy; systemd (`friday-telemetry-os.target` per [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md)); network configuration for all modems/channels; logging per [Mission Logging and Replay](../addendums/Mission Logging and Replay.md); health monitoring agent; module identity file (`MARK1-TEL-001`); signed-OTA update mechanism per [Command Center Protocol Security](../addendums/Command Center Protocol Security.md); SSH/debug access; hardware interface permissions; time sync; crash recovery behavior. The backup ESP32-S3 (`MARK1-TEL-BACKUP-001`) gets firmware identity, serial protocol to the Telemetry Pi, hardware Task WDT, heartbeat protocol per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md), safe-state behavior (LoRa beacon only — no command authority), [dual-bank OTA](../addendums/OTA Update Strategy.md), fault reporting, and low-power deep-sleep support.

## Open Design Areas

- **Path-selection policy** — exact thresholds and scoring for choosing/failing over between cellular, Wi-Fi, LoRa, satellite. Still open.
- **Critical-command set** — when [Telemetry holds authority](../addendums/Authority Lease Protocol.md) during Core Hub failover, the standard motion + recovery + emergency stop interfaces are the command set. Whether to add Telemetry-specific commands (e.g. forced charge-return) deferred to Mark 1.5.
- **Shadow-state fidelity** — how much state to mirror and at what refresh rate, bounded by bandwidth. Still open.
- **Security** — ✅ resolved in [Command Center Protocol Security](../addendums/Command Center Protocol Security.md) (mTLS + per-operator Ed25519 signing + monotonic nonce + 30 s expiry; SIM PIN + APN lock).

---

Related: [Friday Labs OS Architecture](Friday Labs OS Architecture.md) · [Mark 1 Compute Architecture](Mark 1 Compute Architecture.md) · **Friday Labs** · **Spark** · [Mark 1 Index](../Mark 1 Index.md)
