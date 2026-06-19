# Aerial Bay Electronics

> Electronics design for the Aerial Companion Bay deck: the fail-safe Spark lock, charging, and bay sensors. Builds on the shared [Electronics Backbone](Electronics Backbone.md).
> **Version:** Draft 1.0 · **Deck compute:** ESP32-S3 (owned by the Core Hub via USB CDC). See also the [Aerial Companion Bay](../modules/Aerial Companion Bay.md) module spec.

## Decisions

| Area | Decision |
|---|---|
| ESP32-S3 power | Off the bus via local regulator; hardware watchdog (lock stays latched on trip) |
| Lock fail-safe | Bistable over-center latch — servo only toggles between latched/released, zero hold power in either state |
| Charging | Spark self-charges (charger lives with its battery); Bay supplies eFuse-gated regulated DC over the pogo pins |
| Charge sensing | INA219 on the charge feed for contact detection + current monitoring |
| Bay sensors | IR break-beam (launch-corridor clear), weight pad (Spark seated), limit switches (lock state) |
| Build | Custom PCB |

## Rationale Highlights

- **The lock must hold with zero power.** A hobby servo doesn't hold position unpowered, and Spark coming loose during transit is catastrophic. The **bistable over-center latch** is stable in both locked and released states — the servo applies brief power only to switch, none to hold. Combined with the existing "no rover motion until lock-engaged confirmed" interlock (see [Aerial Companion Bay](../modules/Aerial Companion Bay.md)), Spark is secured through any power loss.
- **Spark self-charges:** keeping the charger with the battery it charges is cleaner and safer than charging across pogo pins from a Bay-side charger. The Bay just delivers regulated DC, **eFuse-gated** so a bad contact or short can't damage anything. INA219 confirms contact and reads charge state.
- **Watchdog → lock stays latched:** on a watchdog trip the Bay defaults to the secured state — it never releases Spark unexpectedly.

## BOM Adders (approx.)

- ESP32-S3 + local regulator: ~$10
- Over-center latch mechanism + toggle servo: ~$20 (mechanical)
- Pogo pin contacts (power + 2 UART) + eFuse + charge regulator: ~$15
- INA219: ~$5
- IR break-beam + weight pad + 2 limit switches: ~$15

## Open Items

- Pogo pin count and current rating for Spark's charge rate.
- Over-center latch mechanical design (throw, holding force, Spark interface).
- Spark-side connector and charge-contact layout (defined with the future Spark dossier).

## Related

[Electronics Backbone](Electronics Backbone.md) · [Aerial Companion Bay](../modules/Aerial Companion Bay.md) · [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md) · [Mark 1 Index](../Mark 1 Index.md)
