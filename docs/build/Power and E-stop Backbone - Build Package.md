# Power & E-stop Backbone — Build Package

> The buildable package for the shared electrical foundation every deck plugs into: battery + BMS, distributed power tree, the fail-open E-stop, central fusing, bus-fail signal, star ground, and the M12 inter-deck harness. Turns the locked decisions in [Electronics Backbone](../electronics/Electronics Backbone.md) and [Power Budget](../addendums/Power Budget.md) into something you can buy and wire.
> **Version:** Draft 1.0 · **Build it before bench-powering any deck (including Locomotion).**

## Authoritative Sources

- **Architecture:** [Electronics Backbone](../electronics/Electronics Backbone.md) (distributed power tree, NC-loop E-stop, star ground, central fusing, M12 connectors).
- **Envelope:** [Power Budget](../addendums/Power Budget.md) (150 Wh, 14.8 V, 50-75 W typical, ~100 W peak, 2 hr target).
- **Consumes this backbone:** every deck — see the [Locomotion pin-level schematic](Locomotion Deck - Pin-Level Schematic.md) `+14V8_RAW` / `+14V8_SW` nets.

## Power Tree

```
4S Li-ion 21700 pack (~150 Wh, 14.8 V nom, 16.8 V full)
 └─[smart BMS: OVP/UVP/OCP/balance/temp + SOC telemetry]
    └─[master battery isolator switch]
       └─[master fuse 30 A]
          └─[reverse-polarity ideal-diode]
             ├──────────────────── RAW BUS (always-on) ───────────────┐
             │  central fuse block (per-deck):                         │
             │   ├─ Core Hub      ≈5 A  ─ M12 ─►                       │
             │   ├─ Telemetry     ≈5 A  ─ M12 ─►                       │
             │   ├─ Lab Deck      ≈5 A  ─ M12 ─►                       │
             │   ├─ Locomotion LOGIC ≈2 A ─ M12 ─►  (ESP32 stays alive)│
             │   └─ Aerial Bay LOGIC ≈2 A ─ M12 ─►                     │
             │                                                          │
             └─[solid-state pre-switch: soft-start + e-enable]         │
                └─[mechanical contactor — NC E-stop loop, FAILS OPEN]  │
                   └────────── SW BUS (motion) ──[fuse block]──────────┤
                      ├─ Locomotion motors/servos/pawls ≈20 A ─ M12 ─► │
                      └─ Aerial Bay actuators            ≈5 A  ─ M12 ─► │

 NC E-stop loop: latching mushroom button (NC) in series with the contactor enable.
 Bus comparator on RAW → "power-fail" GPIO to Core Hub (supercap shutdown) + Telemetry ESP32.
 Star ground: one node at battery negative; clean / motor / servo legs join only here.
```

**RAW vs SW is the safety split:** compute and every deck's *logic* sit on the always-on RAW bus, so the rover stays aware and reporting through an E-stop. Only *motion* power (Locomotion actuators, Aerial Bay actuators) is on the SW bus the E-stop cuts.

## BOM

| # | Part | Qty | Real-world example | ~Unit | Notes |
|---|---|---|---|---|---|
| 1 | Battery | 1 | 4S2P/3P 21700 Li-ion pack, ~150 Wh, 14.8 V | $60-120 | Per [Power Budget](../addendums/Power Budget.md) |
| 2 | Smart BMS | 1 | 4S Li-ion BMS w/ balance + UART/I2C SOC (JBD/Daly-class) | $20-40 | OVP/UVP/OCP/temp + fuel-gauge telemetry to a deck |
| 3 | Master isolator | 1 | Battery key/rotary isolator switch, ≥40 A | $10 | Full-system off (distinct from the E-stop) |
| 4 | Master fuse | 1 | 30 A ANL/MIDI fuse + holder | $6 | Whole-system protection at the battery |
| 5 | Reverse-polarity | 1 | Ideal-diode controller + P-FET (LM74700-class), ≥25 A | $8 | Blocks reversed battery; near-zero drop |
| 6 | Solid-state pre-switch | 1 | High-side P-FET + gate soft-start (inrush) + enable | $10 | Soft on/off + inrush limit; electronic cutoff |
| 7 | E-stop contactor | 1 | Automotive SPST contactor/relay ~40 A, **non-latching** | $10-25 | Coil-energized = closed; **fails open**; the hard motion disconnect |
| 8 | E-stop button | 1 | Latching mushroom, **NC** contact, panel mount, IP65 | $8 | Press / wire-break / unplug → loop opens |
| 9 | Central fuse block | 2 | 6-way blade-fuse block (1× RAW, 1× SW) | $6 ea | Per-deck + per-motion-feed fuses |
| 10 | Bus comparator | 1 | Voltage supervisor / comparator → open-drain "power-fail" | $3 | Asserts GPIO to Core Hub + Telemetry ESP32 |
| 11 | Star-ground bus | 1 | Brass/copper bus bar at battery negative | $5 | Single-point ground node |
| 12 | M12 bulkhead | per deck | M12 power (A/L-coded) + signal, panel mount | $8-15 ea | Inter-deck; weather-sealed |
| 13 | Charger | 1 | 4S Li-ion (16.8 V CC/CV) charger, off-rover | $20-30 | Hot-swap primary; wall-charge with power **off** |

## E-stop Safety Loop (the spec that makes it safe)

- **Normally-closed (NC) loop:** the latching mushroom button's NC contact is wired in series with the contactor's coil-enable. The loop must be *energized and intact* for motion power to flow.
- **Fail-open everywhere:** button pressed, any loop wire cut, any connector unplugged → loop breaks → contactor coil de-energizes → **contacts physically open (air gap)** → SW bus dead → Locomotion pawls drop (power-to-release) → wheels lock.
- **Two layers:** the **solid-state pre-switch** gives soft-start/inrush limiting and fast electronic on/off; the **mechanical contactor** is the true fail-open disconnect downstream of it. A shorted solid-state switch can't defeat the E-stop because the contactor still opens.
- **Compute survives:** the E-stop only opens the SW bus. RAW bus stays live → Core Hub logs the E-stop, Telemetry reports it, ESP32s hold safe-state and heartbeat.
- **Reset:** twist-release the mushroom + an explicit operator re-arm (not auto-resume) re-energizes the contactor.

## Bus-Fail Signal

A voltage supervisor on the RAW bus drives an open-drain **`PWR_FAIL`** line (active-low) to:
- **Core Hub GPIO** → triggers the supercap-backed clean NVMe shutdown ([Core Hub Electronics](../electronics/Core Hub Electronics.md)).
- **Telemetry backup ESP32** → wake/observe for the recovery beacon path.

Trip point ~13.6 V (4S Li-ion ~10% SoC, above the BMS UVP cutoff) so shutdown completes before the BMS hard-disconnects.

## M12 Inter-Deck Harness (per-deck pinout)

Each deck's M12 carries (exact coding/pin-count per connector chosen):

| Conductor | Decks | Purpose |
|---|---|---|
| `+14V8_RAW` | all | always-on deck logic power |
| `+14V8_SW` | Locomotion, Aerial Bay | motion power (E-stop-cut) |
| `GND` | all | star-ground return |
| `ESTOP_LOOP` (2-wire) | motion decks + button | NC safety loop continuity |
| `PWR_FAIL` | Core Hub, Telemetry | bus-fail signal |
| `BMS_SOC` (UART/I2C) | the deck that reads pack SOC | battery telemetry |

## Charging

- **Hot-swap primary:** pull the pack, drop in a charged one. Fast field turnaround.
- **On-rover wall charge:** 4S Li-ion charger (16.8 V CC/CV) via a charge port, **power off only** (no charging while powered — per [Power Budget](../addendums/Power Budget.md)). The smart BMS manages the charge + balance.
- **No solar** for Mark 1 (Mark 2 question).

## Assembly + Bring-Up Order

Each step has a verify gate.

1. **Battery + BMS bench test** — charge the pack; confirm BMS reports SoC over UART/I2C and trips OVP/UVP/OCP on a bench load. *Verify:* protection actuates; telemetry reads.
2. **RAW bus + protection** — master isolator → master fuse → reverse-polarity → RAW bus. *Verify:* reversed battery causes no damage (ideal-diode blocks); RAW bus reads ~14.8 V.
3. **Solid-state pre-switch + soft-start** — enable the high-side switch into a capacitive load. *Verify:* inrush is limited (no spark/dip); electronic on/off works.
4. **Contactor + NC E-stop loop** — wire the mushroom NC contact in series with the contactor coil. *Verify:* button press / pulled wire / unplugged connector all open the contactor (SW bus drops); audible/measured open.
5. **Fuse blocks + per-deck feeds** — RAW block + SW block, fuses per the estimated ratings. *Verify:* a deliberate short on one feed blows only that fuse.
6. **Bus-fail signal** — supervisor on RAW → `PWR_FAIL`. *Verify:* dropping RAW below the trip point asserts the line; Core Hub sees it.
7. **Star ground + M12 harness** — terminate all grounds at the single node; wire the M12 bulkheads. *Verify:* continuity per pinout; no ground loop (single-point only).
8. **Integrate Locomotion** — plug the Locomotion deck's M12 (RAW + SW + loop + ground). *Verify:* logic powers on RAW; E-stop cuts SW and drops the pawls while the ESP32 keeps heartbeating.

## Open Items

- **Fuse ratings** — the per-deck values above are estimates; finalize once each deck's measured idle/typical/peak draw lands (Phase 2 bring-up, per [Power Budget](../addendums/Power Budget.md) acceptance).
- **Exact contactor + coil voltage** — confirm a 14.8 V-compatible coil (or add a coil dropper); size continuous current to measured motion-bus peak (~20 A).
- **Specific battery pack + smart-BMS model** — within the 150 Wh / 14.8 V envelope; confirm continuous + peak discharge ≥ ~20 A.
- **M12 coding & pin count** — pick power-rated coding (A/L/T) and a pin count that carries RAW + SW + loop + signal per deck.
- **Soft-start ramp time** — sized to total bus capacitance to keep inrush within the contactor/fuse limits.

## Related

[Electronics Backbone](../electronics/Electronics Backbone.md) · [Power Budget](../addendums/Power Budget.md) · [Locomotion Deck — Build Package](Locomotion Deck - Build Package.md) · [Locomotion Deck — Pin-Level Schematic](Locomotion Deck - Pin-Level Schematic.md) · [Core Hub Electronics](../electronics/Core Hub Electronics.md) · [Mark 1 Index](../Mark 1 Index.md)
