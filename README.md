# Friday Labs OS

> Brain software and complete Phase 1 design dossier for **Mark 1** — Friday Labs' modular autonomous research rover for agriculture, forestry, environmental research, surveillance, and public welfare.

## Status

Phase 1 design complete. 24 internally-aligned documents covering architecture, locked design decisions, module specs, and onboarding. Phase 1 implementation kicked off — see [`docs/onboarding/Phase 1 Implementation Kickoff.md`](docs/onboarding/Phase%201%20Implementation%20Kickoff.md) for the 4-week ramp from "haven't read the dossier" to "contributing code."

## Read the dossier

Start at the index: [`docs/Mark 1 Index.md`](docs/Mark%201%20Index.md)

Organized under `docs/`:

| Directory | Contents |
|---|---|
| `architecture/` | 5 foundational documents — compute architecture, OS architecture, comms, interface contract, sim environment |
| `addendums/` | 13 design-gap addendums locking Phase 1 decisions — authority lease, safe-stop budget, sensor ownership, power budget, AI inference, schema conventions, mTLS security, OTA, logging, Stage 5 acceptance, Spark authority, mechanical reference, mmWave |
| `modules/` | 3 module specs — Locomotion Control Unit, Adaptive Research Module, Aerial Companion Bay |
| `onboarding/` | Phase 1 Implementation Kickoff — 4-week ramp for new engineers |

## Engineering discipline

`.claude/skills/` contains 8 project-specific Claude Code skills that enforce the dossier's discipline. Each refuses specific anti-patterns by design:

| Skill | Enforces |
|---|---|
| `friday-msgs-author` | Mandatory header, packed semver, bounded arrays, command auth fields, frame conventions |
| `lifecycle-node-scaffold` | Standard ROS 2 lifecycle pattern — refuses custom state machines |
| `sim-bringup` | REP-2000-correct ROS 2 + Gazebo pairing, seven-stage bring-up |
| `fault-injection` | Quantitative Stage 5 acceptance with p99 budgets, refuses vibes-based pass |
| `safe-stop-audit` | Refuses FreeRTOS soft timers; requires hardware watchdog peripheral; verifies bridge-independence |
| `module-spec` | House style for any new module spec |
| `qos-audit` | The four locked QoS profiles — refuses EmergencyStop on `BEST_EFFORT` |
| `command-center-protocol` | Refuses to specify external auth without mTLS + per-operator signing + nonce + expiry |

## Hardware target

- **Chassis:** 60-90 cm bench prototype, six-wheel rocker-bogie (NASA Perseverance anatomy — corner-only steering on 4 outer wheels, 2 middle wheels drive-only)
- **Compute:** Pi 5 + Coral USB (Core Hub), Pi 5 (Adaptive Research Module), Pi 4 (Telemetry Node), ESP32-S3 (Locomotion, Aerial Bay, backup)
- **Comms:** ROS 2 Jazzy + DDS internally; MQTT 5 over TLS 1.3 with per-rover mTLS externally
- **Power:** 150 Wh LiPo, 2-hour target mission, 50-75 W envelope
- **Total BOM:** ~$2,045-2,450 excluding companion drone

## Safety discipline

- Firmware-level safe-stop: ≤ 100 ms p99 from heartbeat loss, hardware watchdog (not soft timer), bridge-independent
- Authority lease: 2 s duration, 500 ms renewal, in-memory only, deterministic Core ↔ Telemetry handoff
- Every command source validated against the lease holder; unsigned commands rejected at the boundary
- mTLS + per-operator Ed25519 signing + monotonic nonces + 30 s expiry on every external command

## License

TBD — to be added before any external collaboration.
