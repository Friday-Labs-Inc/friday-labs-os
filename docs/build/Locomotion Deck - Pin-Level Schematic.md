# Locomotion Deck — Pin-Level Schematic (netlist)

> The net-by-net electrical spec for the Locomotion deck: ESP32-S3 pin assignment, isolation channel mapping, every connection, and the passives/protection with values. This is the schematic content; formal capture is KiCad. Builds on the [build package](Locomotion Deck - Build Package.md) and [Locomotion Electronics](../electronics/Locomotion Electronics.md).
> **Version:** Draft 1.0.

## Scope & honesty note

This is a **net-level** schematic: signals, nets, device terminals, and passive values — everything needed to capture the board in KiCad. Where a device's **physical pin number** depends on its package/datasheet (ISO7741, ISO1640, INA219, TCA9548A, AS5600, BNO085), the connection is given by **signal name** and marked *(pin per datasheet)*. Do not transcribe pin numbers from this doc into copper without checking the KiCad symbol against the datasheet. ESP32-S3 GPIO numbers are a reference assignment — finalize against the exact module variant (strapping/flash pins).

## Power rails / nets

| Net | Source | Domain | Feeds |
|---|---|---|---|
| `+14V8_RAW` | backbone, fused per-deck | — | buck, E-stop contactor |
| `+14V8_SW` | E-stop contactor output | motor/servo | MDD10A B+, isolated-5V DC-DC in, 6 V UBEC in, pawl solenoids |
| `+5V_CLEAN` | 5 V/3 A buck | clean | ESP32-S3 5V pin |
| `+3V3_CLEAN` | ESP32-S3 onboard LDO | clean | TCA9548A, BNO085, AS5600 ×6, ISO7741 VCC1, ISO1640 VCC1, I2C0 pull-ups |
| `+5V_ISO` | isolated 5 V DC-DC (in: `+14V8_SW`) | motor | ISO7741 VCC2 (#1–3,#5), MDD10A logic ref, INA219 VS, ISO1640 VCC2, motor-side I2C pull-ups |
| `+6V_SRV` | 6 V UBEC (in: `+14V8_SW`) | servo | 4× servo V+ |
| `+5V_SRV` | small LDO from `+6V_SRV` | servo | ISO7741 VCC2 (#4) servo-side logic ref |
| `GND_CLEAN` | star ground | clean | clean logic + sensors |
| `GND_MOTOR` | star ground | motor | drivers, motors, pawls, INA219 |
| `GND_SRV` | star ground | servo | UBEC, servos |

Clean / motor / servo grounds are separate, joining only at the battery-negative **star point** ([Electronics Backbone](../electronics/Electronics Backbone.md)).

## ESP32-S3 pin assignment (reference)

| GPIO | Net / signal | Peripheral | To |
|---|---|---|---|
| 4, 5, 6, 7 | `DRV_PWM1..4` | MCPWM | ISO7741 #1 inputs |
| 15, 16 | `DRV_PWM5..6` | MCPWM | ISO7741 #2 inputs |
| 17, 18 | `DRV_DIR1..2` | GPIO | ISO7741 #2 inputs |
| 8, 9, 10, 11 | `DRV_DIR3..6` | GPIO | ISO7741 #3 inputs |
| 12, 13, 14, 21 | `SRV_PWM1..4` | LEDC | ISO7741 #4 inputs |
| 38 | `PAWL_REL` | GPIO | ISO7741 #5 input |
| 1 | `SDA0` | I2C0 | TCA9548A, BNO085, AS5600 |
| 2 | `SCL0` | I2C0 | TCA9548A, BNO085, AS5600 |
| 41 | `SDA1_CLEAN` | I2C1 | ISO1640 side-1 SDA |
| 42 | `SCL1_CLEAN` | I2C1 | ISO1640 side-1 SCL |
| 39 | `ESTOP_LIVE` | GPIO in | opto-isolator output (motion-power sense) |
| 48 | `STAT_LED` | GPIO | status LED + 330 Ω |
| 19, 20 | `USB_DM`, `USB_DP` | USB OTG | Core Hub (USB CDC) |
| 5V pin | `+5V_CLEAN` | power in | buck output |
| 3V3 pin | `+3V3_CLEAN` | power out | clean sensors |
| GND | `GND_CLEAN` | — | clean star leg |

## Isolation channel map (ISO7741 ×5, all clean→power)

| Isolator | VCC1 / GND1 | VCC2 / GND2 | Channel inputs (clean) → outputs (power) |
|---|---|---|---|
| #1 | `+3V3_CLEAN` / `GND_CLEAN` | `+5V_ISO` / `GND_MOTOR` | `DRV_PWM1..4` → MDD10A PWM (M1,M2,M3,M4) |
| #2 | clean | `+5V_ISO` / `GND_MOTOR` | `DRV_PWM5..6`, `DRV_DIR1..2` → MDD10A PWM(M5,M6) + DIR(M1,M2) |
| #3 | clean | `+5V_ISO` / `GND_MOTOR` | `DRV_DIR3..6` → MDD10A DIR(M3,M4,M5,M6) |
| #4 | clean | `+5V_SRV` / `GND_SRV` | `SRV_PWM1..4` → servo signal 1..4 |
| #5 | clean | `+5V_ISO` / `GND_MOTOR` | `PAWL_REL` → pawl MOSFET gate (+ 3 spare ch) |

`ESTOP_LIVE` runs the other direction (power→clean), so it does **not** use the ISO7741 bank (all-forward). It uses a **dedicated optocoupler**: LED side across `+14V8_SW` (via series R), phototransistor side pulls `ESTOP_LIVE` on `GND_CLEAN`.

## Net-by-net connections

**Drive (×6, i = 1..6):** `DRV_PWMi` (ESP32) → ISO7741 INx → ISO7741 OUTx → `MDD10Ab.PWMc`; `DRV_DIRi` → ISO7741 → `MDD10Ab.DIRc`. Motor: `MDD10Ab.McA`/`McB` → drive motor i terminals. (b = board 1/2/3, c = channel 1/2.)
**Servo (×4):** `SRV_PWMj` → ISO7741 #4 → servo j signal; servo j V+ = `+6V_SRV`, GND = `GND_SRV`.
**Pawl:** `PAWL_REL` → ISO7741 #5 → MOSFET gate (via 100 Ω); MOSFET drain → 4× solenoid low side (solenoids paralleled), solenoid high side → `+14V8_SW`; flyback diode across each solenoid.
**I2C0 (clean):** `SDA0`/`SCL0` bus → TCA9548A *(SDA/SCL, pins per datasheet)*, BNO085 *(SDA/SCL)*; TCA9548A channels SD0/SC0..SD5/SC5 → AS5600 #1..6 *(each SDA/SCL)*. Pull-ups 4.7 kΩ to `+3V3_CLEAN`.
**I2C1 (isolated):** `SDA1_CLEAN`/`SCL1_CLEAN` → ISO1640 side-1; ISO1640 side-2 `SDA2`/`SCL2` → INA219 *(SDA/SCL)*. Pull-ups **both sides**: 4.7 kΩ to `+3V3_CLEAN` (side 1) and 4.7 kΩ to `+5V_ISO` (side 2).
**Current sense:** INA219 `VIN+`/`VIN-` across a shunt in the `+14V8_SW` motor feed; `VS` = `+5V_ISO`, addr `A0/A1` → 0x40.
**USB:** `USB_DP`/`USB_DM` → USB-C → Core Hub.

## Per-device power & address summary

| Device | VCC | GND | I2C addr |
|---|---|---|---|
| ESP32-S3 | `+5V_CLEAN` (→3V3) | `GND_CLEAN` | — |
| TCA9548A | `+3V3_CLEAN` | `GND_CLEAN` | 0x70 (A0–A2 low) |
| AS5600 ×6 | `+3V3_CLEAN` | `GND_CLEAN` | 0x36 (each behind a mux channel) |
| BNO085 | `+3V3_CLEAN` | `GND_CLEAN` | 0x4A (SA0 low) |
| ISO7741 ×5 | VCC1 `+3V3_CLEAN` / VCC2 `+5V_ISO` or `+5V_SRV` | GND1 clean / GND2 motor or servo | — |
| ISO1640 | VCC1 `+3V3_CLEAN` / VCC2 `+5V_ISO` | GND1 clean / GND2 motor | — |
| INA219 | `+5V_ISO` | `GND_MOTOR` | 0x40 |
| MDD10A ×3 | B+ `+14V8_SW`, logic ref `+5V_ISO` | `GND_MOTOR` | — |
| Servos ×4 | `+6V_SRV` | `GND_SRV` | — |

## Passives & protection (with values)

| Function | Part / value | Where |
|---|---|---|
| I2C0 pull-ups | 4.7 kΩ ×2 → `+3V3_CLEAN` | SDA0/SCL0 |
| I2C1 pull-ups | 4.7 kΩ ×2 each side | clean side → 3V3, motor side → `+5V_ISO` |
| IC decoupling | 100 nF per VCC pin + 10 µF bulk per rail | every IC |
| Motor bulk cap | 470–1000 µF electrolytic + 100 nF | across each MDD10A B+/B- |
| Motor snubber | 100 nF (or RC 100 nF + 10 Ω) | across each motor’s terminals |
| Solenoid flyback | 1N4007 / Schottky | across each pawl solenoid coil |
| MOSFET gate | 100 Ω series + **10 kΩ pull-down to `GND_MOTOR`** | pawl FET gate |
| Driver fail-safe | **pull-downs 10 kΩ on motor-side PWM** (→ `GND_MOTOR`) | MDD10A PWM inputs |
| Input protection | TVS on `+14V8_RAW`, local fuse | deck input |
| ESP32 strapping | EN 10 kΩ + 1 µF, boot pull-ups | (DevKitC handles on bench) |
| Status LED | 330 Ω series | `STAT_LED` |

## Fail-safe-on-signal-loss (the nets that make it safe)

- **MOSFET gate pull-down (10 kΩ → `GND_MOTOR`):** loss of `PAWL_REL` / dead ISO7741 #5 → gate low → solenoids de-energized → **pawls engage** (power-to-release). ✔
- **MDD10A PWM pull-downs (motor side):** loss of drive signal / dead isolator → PWM low → **motors off**. ✔
- **E-stop:** `+14V8_SW` removed by the NC loop → MDD10A B+ gone (motors dead), solenoid supply gone (**pawls engage**), servo supply gone. `ESTOP_LIVE` opto drops → ESP32 logs the state. ✔
- These pull-downs live on the **isolated (power) side**, so they hold the safe state even if the clean domain or the isolators are dead.

## KiCad verify checklist

- Map every *(pin per datasheet)* signal to the real symbol pin before routing.
- Confirm ISO7741 channel directions are all clean→power (4/0 part); the e-stop sense is a separate optocoupler.
- Confirm `+5V_ISO` and `+5V_SRV` are truly isolated DC-DC outputs (separate secondaries), not buck taps off the clean rail.
- Verify motor-side pull-downs resolve to the safe state with the clean domain powered **off**.
- Shunt resistor value for INA219 sized to expected motor current (≈ up to ~15 A total) without excessive burden voltage.
- Finalize ESP32-S3 GPIO against the chosen module (avoid GPIO0/3/45/46 strapping, GPIO19/20 USB, flash/PSRAM pins).

## Related

[Locomotion Deck — Build Package](Locomotion Deck - Build Package.md) · [Locomotion Electronics](../electronics/Locomotion Electronics.md) · [Electronics Backbone](../electronics/Electronics Backbone.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Mark 1 Index](../Mark 1 Index.md)
