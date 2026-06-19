# Telemetry Node Electronics

> Electronics design for the Telemetry Command Node deck: cellular modem, dual LoRa, the independent backup ESP32, and antennas. Builds on the shared [Electronics Backbone](Electronics Backbone.md).
> **Version:** Draft 1.0 · **Deck compute:** Pi 4 (4 GB) + backup ESP32-S3.

## Decisions

| Area | Decision |
|---|---|
| Pi 4 power | 5 V/3 A buck → GPIO, input protection (no override needed; Pi 4 less power-picky) |
| LoRa | Pi owns radio #1 (SPI); backup ESP32 owns a dedicated radio #2 for the emergency beacon, with a periodic TX self-test |
| Cellular | 4G LTE M.2 module on a powered carrier (own burst-rated regulator), 5G-ready M.2 slot |
| Backup ESP32 | Independent always-on micro-regulator off the bus; reboot authority via watchdog-gated high-side load switches on each Pi feed |
| Antennas | External waterproof bulkhead SMA; long-range LoRa antennas on the mast |

## Rationale Highlights

- **Dual independent LoRa** (operator's call over a shared radio): the Pi's LoRa can fail entirely and the ESP32 still beacons. The cost is a second radio + antenna and a **mandatory periodic self-test** so the rarely-used emergency radio doesn't silently die before it's needed.
- **4G now, 5G-ready:** full 5G is over-built for a prototype operating within a few km (cost, ~3 A bursts, 4 MIMO antennas). The M.2 slot accepts a 5G module later with no redesign. The modem gets its **own burst-rated regulator** off the bus — never powered over USB (brownout source).
- **Backup ESP32 independence is the recovery linchpin:** it runs on its own always-on micro-regulator (microamp deep-sleep) so it outlives a Pi failure, and it can **power-cycle a hung Pi** via load switches. The reboot trigger is watchdog-gated/multi-step so a single ESP32 glitch can't cut a healthy Pi's power. It holds **no command authority** beyond this (see [Authority Lease Protocol](../addendums/Authority Lease Protocol.md)).
- **Mast antennas:** LoRa range scales hard with mounting height; the long-range antennas go up the Perseverance-style mast. Sealed enclosure → all antennas exit via waterproof bulkhead SMA.

## BOM Adders (approx.)

- 5 V/3 A buck: ~$6
- 2× LoRa modules (SX126x-class) + 2 antennas: ~$25
- 4G LTE M.2 module + powered carrier + burst regulator: ~$40-60
- Backup ESP32-S3 + always-on micro-regulator + load switches: ~$15
- Bulkhead SMA connectors (4G MIMO ×2, LoRa ×2, GPS, Wi-Fi/BT): ~$25

## Open Items

- Path-selection thresholds for channel failover (cellular ↔ Wi-Fi ↔ LoRa) — open in [Telemetry Command Node](../architecture/Telemetry Command Node.md).
- Load-switch current rating per Pi feed.
- ESP32 LoRa self-test cadence and pass/fail criteria.

## Related

[Electronics Backbone](Electronics Backbone.md) · [Telemetry Command Node](../architecture/Telemetry Command Node.md) · [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) · [Command Center Protocol Security](../addendums/Command Center Protocol Security.md) · [Mark 1 Index](../Mark 1 Index.md)
