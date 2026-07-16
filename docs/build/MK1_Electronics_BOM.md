# Mark 1 Rover — Electronics & Motors Procurement BOM

> Sourced 2026-06-30 against the canonical reference design
> ([HowToMechatronics Perseverance](https://howtomechatronics.com/projects/diy-mars-perseverance-rover-replica-with-arduino/)),
> priced live on Indian vendors. All prices INR. **Verified** = read directly from the
> live product page at sourcing time. Pairs with the
> [Interface Control Document](MK1_Interface_Control_Document.md).
> Prices/stock drift — re-check at checkout.

---

## Bill of Materials

### DRIVE

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| ThinkRobotics 37 mm Gearmotor 12 V / 70 RPM (MOT1012-70) — **built-in 64 CPR quadrature encoder** | 6 | 12 V, 70 RPM, 8 kg·cm, 1:94.85; load 0.9 A @ 36 RPM, no-load 0.1 A | thinkrobotics.com | 879.99 | 5,279.94 | In stock | ✓ |
| DRV8871 DC Motor Driver Breakout (3.6 A) | 6 | Single H-bridge, 6.5–45 V, 3.6 A peak, IN1/IN2 PWM | robodo.in | 318.00 | 1,908.00 | In stock | ✓ |

**DRIVE subtotal: ₹7,187.94**

### STEERING

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| AUSTARHOBBY AX8601 25 kg Waterproof Metal-Gear Digital Servo | 4 | 25 kg·cm @ 6 V, digital, IP66, 0.15 s/60° | thinkrobotics.com | 1,499.99 | 5,999.96 | **Pre-order** | ✓ |

**STEERING subtotal: ₹5,999.96**
> In-stock alt if timeline is tight: **DS3225 25 kg** at kitsguru.com ≈ ₹1,249 ea (90° in stock) → steering drops to ≈₹4,996. Avoid MG996R (~10 kg·cm, too weak).

### POWER & SAFETY

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| 11.1 V 5200 mAh 3S 60C LiPo (XT60) | 1 | 3S, 60C, XT60 | embeddinator.com | 3,577.00 | 3,577.00 | Yes (3) | ✓ |
| iMAX B6-AC balance charger | 1 | 3S AC/DC, built-in adapter | flyrobo.in | 2,591.00 | 2,591.00 | Yes | ✓ |
| XL4016E1 8 A buck — **servo 6 V rail** | 1 | 8–36 V in → set 6 V, 8 A; trim pot before install | robocraze.com | 173.00 | 173.00 | Yes (66) | ✓ |
| XL4016E1 8 A buck — **logic 5 V rail** | 1 | set 5 V, 8 A (Pi 4B ~3 A + Pi 3B+ ~2.5 A + ESP32 ~0.5 A); heatsink >6 A | robocraze.com | 173.00 | 173.00 | Yes (66) | ✓ |
| E-stop relay (12 V coil, 30 A, NC path) + 22 mm latching mushroom button | 1 | fail-open motor-rail kill; button in coil circuit only (10 A), not the 30 A path | robocraze.com | 249.00 | 249.00 | Yes | ✓ |
| INA219 I²C voltage/current monitor | 1 | 0–26 V, bidirectional current (pack monitoring) | robocraze.com | 233.00 | 233.00 | Yes (29) | ✓ |

**POWER & SAFETY subtotal: ₹6,996.00**

### COMPUTE & CONTROL

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| Raspberry Pi 4B 8 GB | 1 | **Core Hub** — ROS 2 Jazzy, full Friday Labs OS | — | **OWNED — ₹0** | 0 | — | — |
| Raspberry Pi 3B+ 1 GB | 1 | **Telemetry Gateway** — Linux gateway, dual 4G, LoRa, routing | — | **OWNED — ₹0** | 0 | — | — |
| ESP32-WROOM-32 (38-pin, CP2102) | 4 | 1× Mobility Hub + 3× spare (Lab Deck / Aerial Bay / bench) | — | **OWNED — ₹0** | 0 | — | — |
| PCA9685 16-ch I²C PWM driver | 1 | offloads motor+servo PWM over I²C, frees GPIO for quadrature encoders | thinkrobotics.com | 429.99 | 429.99 | 7 (confirm) | ✓ |
| SanDisk Ultra 32 GB A1 microSD | 3 | Pi 4B + Pi 3B+ + spare | robocraze.com | 1,454.00 | 4,362.00 | Yes (18) | ✓ |

**COMPUTE & CONTROL (new spend): ₹4,791.99**

### SENSORS

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| BNO085 9-DOF IMU (on-chip fusion) | 1 | I²C/SPI/UART, rotation-vector output | robocraze.com | 2,068.00 | 2,068.00 | **Only 1 left** | ✓ |

**SENSORS subtotal: ₹2,068.00**
> LiDAR / camera / GPS / mmWave deferred — see Buy-now vs Later.

### TELEMETRY COMMS (Telemetry Gateway — Pi 3B+)

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| 4G LTE USB dongle | 2 | dual-carrier (Jio + Airtel), USB to Pi 3B+ | — | **OWNED — ₹0** | 0 | — | — |
| Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262 LoRa 433 MHz, antenna included) | 1 | 10 km+ LOS, 148 dBm link budget, ESP32-S3 on-board, USB-C to Pi | robocraze.com / aliexpress | 2,200.00 | 2,200.00 | Check | — |
| Prepaid SIM cards (Jio + Airtel) | 2 | dual-carrier redundancy (if not already in the dongles) | local | 250.00 | 500.00 | — | — |

**TELEMETRY COMMS subtotal: ₹2,700.00**
> 4G dongles already owned — plug into Pi 3B+ USB, managed via ModemManager.
> LoRa = ESP32-S3 combo board (self-contained with antenna). Pi 3B+ routes all traffic.

### CONNECTORS & MISC

| Part | Qty | Key spec | Vendor | INR each | Line total | Stock | ✓ |
|------|-----|----------|--------|----------|-----------|-------|---|
| Power connector + fuse kit (2× blade fuse holders + 7 fuses 10–40 A; XT60 pair; XT30 pair) | 1 | fuses Flipkart/Ovicart ₹159; XT60 robocraze ₹27; XT30 robomart ₹57 | Multiple | 243.00 | 243.00 | Yes | ✓ |
| Dupont 2.54 mm housing + crimp kit | 1 | 220 housings + 500 pins; add JST-XH packs for locked connections | robocraze.com | 368.00 | 368.00 | Yes (31) | ✓ |

**CONNECTORS & MISC subtotal: ₹611.00**

---

## Totals

| Subsystem | INR |
|-----------|-----|
| Drive | 7,187.94 |
| Steering | 5,999.96 |
| Power & Safety | 6,996.00 |
| Compute & Control (new) | 4,791.99 |
| Sensors | 2,068.00 |
| Telemetry Comms | 2,700.00 |
| Connectors & Misc | 611.00 |
| **GRAND TOTAL (new spend)** | **₹30,354.89** |

Excludes: the owned 1× Pi 4B 8 GB + 1× Pi 3B+ 1 GB + 4× ESP32, local 10–14 AWG silicone
wire, and per-vendor shipping. DS3225 servo substitution lowers steering to ≈₹4,996.

---

## Buy now vs later

**Buy now (prototype bring-up — drive + steer + safe-stop + comms):**

- **Mobility Hub:** 6 motors, 6 DRV8871, 4 servos (or DS3225), PCA9685, BNO085 (**order now — 1 in stock**), INA219
- **Power & Safety:** 3S LiPo, iMAX charger, 2× XL4016E1 bucks (6 V servo + 5 V logic), E-stop kit
- **Telemetry Gateway:** 1× Heltec LoRa32 V3 (ESP32-S3+LoRa combo), 2× SIM cards (4G USB dongles already owned)
- **Compute:** 3× microSD, connector/fuse kits

**Defer (Phase 2+ sensing — rover navigates + sim validates without them):** LiDAR
(RPLIDAR A1/A2), camera (OAK-D / RealSense / Pi Cam), GPS/RTK, mmWave human-detection
(see `docs/addendums/mmWave Human Detection.md`), extra ToF/environmental sensors,
Coral TPU, NVMe storage, supercap hold-up.

---

## Engineering note — ICD change from the chosen motor

The MOT1012-70 has a **64 CPR quadrature encoder built in**, which changes the earlier plan:

- **DROP:** 6× AS5600 magnetic encoders + the TCA9548A I²C mux (7 boards gone — they only existed to read external encoders).
- **ADD:** the PCA9685 (in this BOM) — pushes all motor-driver + servo PWM over I²C so the Drive ESP32's GPIO is freed for the encoders.
- **Drive ESP32 now:** reads 6 quadrature encoders via the ESP32 **PCNT** hardware counter (2 GPIO per motor, A+B = 12 pins, zero CPU cost); all PWM goes out over I²C to the PCA9685.

**⚠️ I²C address collision to resolve in the ICD:** the **PCA9685 and INA219 both default to `0x40`.** On the Drive deck's shared I²C bus that's a conflict — re-strap one (PCA9685 A0–A5 pads → e.g. `0x41`, or move INA219 to `0x41`). Update the ICD address map accordingly.

**ICD action:** revise the Drive-deck pin map — 12 GPIO → PCNT encoder A/B inputs; I²C → PCA9685 (PWM) + INA219 + BNO085 with non-colliding addresses; remove the AS5600/TCA9548A entries.
