# Electronics Backbone

> The shared electrical foundation every deck taps into: power tree, physical E-stop, grounding, fusing, connectors, and build medium. Locked during the deck-by-deck electronics pass. Read this before any per-deck electronics doc.
> **Version:** Draft 1.0 · **Purpose:** Cross-cutting electrical architecture for all five decks.

## Power Tree — Distributed

Regulation is **distributed**, not central. Protected raw 14.8 V battery voltage is run to every deck; each deck's PCB makes only the rails it needs locally.

```
14.8V LiPo ──[BMS]──[master fuse]──[reverse-polarity ideal-diode]──[main switch + soft-start]
   │
   ├──[fuse]── Core Hub deck      → local bucks: 5V/6A (Pi), 5V (USB hub), 3.3V
   ├──[fuse]── Telemetry deck     → local bucks: 5V/3A (Pi 4), modem rail, ESP32 always-on micro-reg
   ├──[fuse]── Locomotion deck    → motor domain (raw) + isolated logic domain (clean 5V/3.3V) + 6V servo BEC
   ├──[fuse]── Lab Deck           → local bucks: 5V/6A (Pi), 5V (USB hub + expansion ports)
   └──[fuse]── Aerial Bay deck    → local bucks: ESP32, servo, Spark charge supply
```

**Why distributed:** matches the modular architecture (decks self-contained and swappable), isolates regulator faults to one deck, and is more efficient — distributing high-voltage/low-current over wire beats pushing 5 V at many amps (less drop, thinner copper, less radiated noise). See [Power Budget](../addendums/Power Budget.md) for the per-deck wattage budgets this serves.

## Physical E-Stop — NC Safety Loop

A hardware emergency stop independent of all software. A latching mushroom button sits in a **normally-closed safety loop** that energizes the **motion-power contactor** (motors + steering servos + parking-pawl solenoids).

- Button press, severed wire, or unplugged connector → loop opens → contactor drops → **motion power dies**.
- Loss of motion power → **parking pawls drop and lock the wheels** (they're spring-engaged, power-to-release — see [Locomotion Electronics](Locomotion Electronics.md)).
- **Compute stays alive** on its own rail → the rover reports "E-stopped," logs it, and stays in comms.

Fail-safe to wiring faults, not just button presses. Coordinates with the software safe-stop and the [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) firmware watchdog as the outermost, hardware-guaranteed layer.

## Grounding — Single-Point Star

Every deck's ground returns to **one star point at the battery negative**. Within each deck, clean (logic/sensor) and dirty (motor/high-current) grounds stay separate until they meet at the star. Combined with Locomotion's [full galvanic isolation](Locomotion Electronics.md), this keeps motor return current out of signal ground — protecting the I2C encoder bus and all RF. No ground loops.

## Fusing & Protection

Central fuse block with defense in depth:

- **Master fuse** at the battery (whole-system).
- **Per-deck fuse** in a central distribution block, individually sized — a short in one deck blows only that fuse.
- **Reverse-polarity protection** (ideal-diode MOSFET) at the battery.
- **Main switch + soft-start** to handle capacitor inrush on power-up.
- **Per-deck local protection** on each PCB: input fuse + TVS for transients.
- **BMS** on the LiPo handles cell-level safety (over-discharge, balance, over-temp) — complementary to the wiring fuses.

## Connectors & Harness

- **Inter-deck (through sealed enclosure walls):** IP-rated circular bulkhead connectors (M8/M12-class) for power and signal — consistent with the sealed-enclosure and bulkhead-antenna commitments.
- **Inside each enclosure:** keyed locking connectors — XT60/XT30 for power, JST-XH/GH (latching) for signal.
- **No Dupont jumpers, no unkeyed headers** anywhere on a moving rover. Keying prevents miswiring; latching survives vibration.

## Build Medium

- **Custom PCB per deck** (KiCad → JLCPCB-class fab). Vibration-proof, repeatable across the fleet, proper traces and locking connectors.
- **Breadboard is bench-only** — fast desk iteration, but nothing moves under motor power until it's on a custom carrier PCB. A loose jumper on a moving safety-critical board is a safety failure.

## Cross-Cutting Components (surfaced during the deck passes)

These shared elements were identified while specifying individual decks and live in the backbone:

- **Bus-voltage comparator** — monitors the main bus and asserts a GPIO "power-fail" line to the compute decks for clean shutdown. Feeds the Core Hub supercap shutdown and the Telemetry ESP32 wake logic.
- **Supercapacitor hold-up** (Core Hub) — holds the Pi 5 up ~10-30 s after bus power drops so it can flush and unmount the NVMe. See [Core Hub Electronics](Core Hub Electronics.md).
- **ESP32-controlled load switches** — high-side switches on each Pi's power feed, toggled by the Telemetry backup ESP32 (watchdog-gated) to power-cycle a hung Pi. See [Telemetry Node Electronics](Telemetry Node Electronics.md).

## Acceptance Criteria

- E-stop press cuts motion power and drops the pawls in hardware with the compute still reporting, verified on bench.
- Cutting any single inter-deck connector (simulating a wire fault) triggers the E-stop loop, not undefined behavior.
- A deliberate short on one deck's feed blows only that deck's fuse; other decks keep running.
- Reverse-connecting the battery causes no damage (ideal-diode blocks it).
- Bus-power-fail signal reaches the Core Hub and a clean NVMe shutdown completes within the supercap hold-up window.

## Open Items

- Specific battery + BMS model within the [Power Budget](../addendums/Power Budget.md) envelope.
- Master and per-deck fuse ratings — sized once final per-deck current draws are measured (Phase 2 bring-up).
- Soft-start / precharge component sizing against total bus capacitance.
- M8 vs M12 selection per connection (pin count, current rating).
- KiCad library of standard Friday Labs footprints and the inter-deck connector pinout standard.

## Related

[Power Budget](../addendums/Power Budget.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Core Hub Electronics](Core Hub Electronics.md) · [Telemetry Node Electronics](Telemetry Node Electronics.md) · [Locomotion Electronics](Locomotion Electronics.md) · [Lab Deck Electronics](Lab Deck Electronics.md) · [Aerial Bay Electronics](Aerial Bay Electronics.md) · [Mark 1 Index](../Mark 1 Index.md)
