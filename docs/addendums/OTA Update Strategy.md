# OTA Update Strategy

> A/B partition update model with auto-rollback for all Pi compute modules, with matching dual-OTA on ESP32s. Closes the Phase 2 operational-readiness gap around field-safe updates.
> **Version:** Draft 1.0 · **Purpose:** Never brick a rover in the field with a bad update.

## Decision

A/B partition (dual-bank) updates. Every Pi has two boot partitions of equal size. One is "active" (running), the other "standby." Updates write to standby. Reboot switches active. If the new active fails to validate within a window, the bootloader auto-switches back.

## Storage Layout (Pi)

| Partition | Size | Purpose |
|---|---|---|
| `boot` | 512 MB | Bootloader, kernel selection (read-only after provisioning) |
| `system_a` | 8 GB | Bank A — Ubuntu 24.04 + ROS 2 Jazzy + Friday Labs OS services |
| `system_b` | 8 GB | Bank B — identical layout, holds the standby image |
| `data` | rest | Mission logs, config, identity, persistent state |
| `state` | 16 MB | Boot state: active bank, retry counter, last-known-good marker |

Cost vs single-partition: ~8 GB extra. On a 32 GB SD card you trade ~25% of storage for "a bad update never strands a rover."

## Update Procedure

1. Telemetry Node receives a signed OTA package from Command Center (signature + nonce validated as per [Command Center Protocol Security](Command Center Protocol Security.md)).
2. Package is downloaded to the **standby** bank only. Active bank is untouched.
3. Package signature is verified against the on-rover CA chain.
4. Active bank is marked "last known good." Standby is marked "trial."
5. Pi reboots into the trial bank.
6. Friday Labs OS services start. Within **60 seconds**, the `module-registry` must report the new image is up and all expected modules are registered.
7. On success: trial → "active," previous bank demoted to "standby."
8. On failure (no registration in 60 s, kernel panic, or service crash loop): bootloader counts 3 failed boots and auto-switches back to last-known-good.

## Hard Rules

- Updates are **never** applied while a mission is in progress. Queue until mission ends and rover is on charger.
- Both banks must remain bootable at all times.
- OTA signing key is separate from operator command-signing keys; stored in the Friday Labs CA HSM; rotated annually.
- Rollback restores the previous bank verbatim. No partial rollback.
- Image-version-specific config lives inside the image. `data` is untouched by updates.

## ESP32 Firmware OTA

ESP32 updates ride on the ESP-IDF dual OTA partition scheme (`ota_0`, `ota_1`). The Pi that owns the ESP32 brokers the flash:

- **Core Compute Hub** owns the Locomotion ESP32 and the Aerial Bay ESP32 (mission-level actuator control belongs with the brain).
- **Telemetry Node Pi** owns the backup emergency ESP32.

Same signed-package, signature-verify, dual-bank, auto-rollback rules apply to every ESP32.

`friday_msgs` schema is the contract: a firmware with mismatched `protocol_major` is rejected before flashing.

## Acceptance Criteria

- OTA push of a deliberately-broken image (kernel panic on boot) auto-rolls back within 5 minutes. Verified on bench.
- OTA push during a simulated active mission queues and does not apply until the mission ends. Verified in sim.
- OTA push with an invalid signature is rejected at download. No bytes touch the standby bank.
- Mission logs in `data` survive a full update cycle.

## Related

[Command Center Protocol Security](Command Center Protocol Security.md) · [Telemetry Command Node](../architecture/Telemetry Command Node.md) · [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
