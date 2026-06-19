# Core Hub Electronics

> Electronics design for the Core Compute Hub deck: power input, USB budget, cooling, boot, and power-loss handling. Builds on the shared [Electronics Backbone](Electronics Backbone.md).
> **Version:** Draft 1.0 · **Deck compute:** Pi 5 (8 GB) + Coral USB + RealSense D435i + 2× ESP32-S3 (USB CDC).

## Decisions

| Area | Decision |
|---|---|
| Pi 5 power | 5 V/6 A buck → GPIO 5V pins (locking connector); `usb_max_current_enable=1` firmware flag; input fuse + reverse-polarity protection |
| USB power | Powered USB 3.0 hub off the 5 V rail (power-isolated, no back-feed); RealSense + Coral on USB 3.0, ESP32s on USB 2.0 |
| Cooling | Conduction cooling to a sealed chassis radiator plate (no fan) |
| Timekeeping | RTC coin cell on the Pi 5 RTC connector (real offline log timestamps) |
| Boot | NVMe SSD via M.2 HAT, A/B [OTA](../addendums/OTA Update Strategy.md) layout |
| Power-loss | Supercapacitor hold-up + GPIO power-fail signal from the bus comparator |

## Rationale Highlights

- **The 5 V trap:** the Pi 5 silently caps total USB current to ~600 mA unless it detects a proper 5 V/5 A supply. Feeding via GPIO bypasses PD negotiation, so `usb_max_current_enable=1` is mandatory to unlock full USB current. Without it, the RealSense + Coral + 2 ESP32 brown out.
- **Powered hub is not optional:** even with the override, the Pi shares only ~1.6 A across all USB ports; the four devices peak at ~3.4 A. The hub gives the devices their own power; only data goes to the Pi.
- **Conduction cooling** (operator's call over the simpler active cooler) commits the Core Hub to a sealed enclosure with a thermal path to a chassis radiator plate — no air intake, fully field-ready. Adds a thermal-sizing task (~10–15 W dissipation in outdoor ambient).
- **Supercap shutdown** protects the NVMe filesystem and mission-log data partition from corruption on ungraceful power loss (battery yank, E-stop, brownout). The A/B scheme protects OS banks; the supercap protects live data.

## BOM Adders (approx.)

- 5 V/6 A buck converter: ~$10
- Powered USB 3.0 hub (power-isolating): ~$20
- M.2 HAT + 256 GB NVMe: ~$40
- RTC coin cell + holder: ~$2
- Supercap bank + power-fail comparator (shared backbone): ~$15
- Conduction cooling (thermal pad + plate; mechanical): ~$15

## Open Items

- Thermal-path sizing for the conduction-cooling plate (~10–15 W, outdoor ambient) — mechanical integration.
- Routing the conduction path around the stacked M.2 HAT.
- Supercap capacitance sized to the measured clean-shutdown time.

## Related

[Electronics Backbone](Electronics Backbone.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [AI Inference Location](../addendums/AI Inference Location.md) · [Sensor Ownership](../addendums/Sensor Ownership.md) · [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) · [Mark 1 Index](../Mark 1 Index.md)
