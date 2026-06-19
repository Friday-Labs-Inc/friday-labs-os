# Locomotion Deck — Build Package

> The buildable package for the bottom deck: BOM, ESP32-S3 pinout/wiring map, power-domain & isolation wiring, connection diagram, and assembly + bench bring-up order. Turns the locked decisions in [Locomotion Control Unit](../modules/Locomotion Control Unit.md) and [Locomotion Electronics](../electronics/Locomotion Electronics.md) into something you can buy and wire.
> **Version:** Draft 1.0 · **Mechanical base:** JPL Open Source Rover (rocker-bogie) · **Electronics:** Friday Labs locked stack.

## Authoritative Sources

- **Mechanical BOM + frame build:** the live JPL Open Source Rover repo — `github.com/nasa-jpl/open-source-rover`. Pull the chassis, rocker-bogie, wheels, and corner-steer mechanical parts from there; it is the validated, maintained source. This doc covers the **Friday Labs electronics** that replace the OSR's stock control electronics, plus integration.
- **Electrical decisions:** [Locomotion Electronics](../electronics/Locomotion Electronics.md), [Electronics Backbone](../electronics/Electronics Backbone.md), [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md).

> **We keep the OSR mechanics; we replace its control electronics.** The OSR ships with RoboClaw controllers; we drive the same motors with our Cytron + galvanic-isolation + parking-pawl stack.

## Electrical BOM (Friday Labs Locomotion stack)

| # | Part | Qty | Real-world example | ~Unit | Notes |
|---|---|---|---|---|---|
| 1 | MCU | 1 | ESP32-S3-DevKitC-1 (bench) → ESP32-S3-WROOM-1 module (PCB) | $15 | Native USB CDC to Core Hub |
| 2 | Dual motor driver | 3 | Cytron MDD10A (dual, 10 A/ch, 5-25 V) | $22 | 6 channels for 6 drive motors; ≥2× stall headroom |
| 3 | Drive gearmotor | 6 | 12 V brushed DC gearmotor, ratio per torque calc (Pololu 37D-class) | $25-40 | **Gear ratio TBD by sizing calc** — see Open Items |
| 4 | Corner-steer servo | 4 | Metal-gear ~20 kg·cm, 6 V (DS3218-class) | $15 | **Torque + range check** vs OSR corner geometry |
| 5 | Wheel encoder | 6 | AS5600 magnetic breakout + diametric magnet | $3 | On drive output shafts; all addr 0x36 |
| 6 | I2C mux | 1 | TCA9548A breakout (addr 0x70) | $7 | Fans out 6× AS5600 (shared 0x36) |
| 7 | IMU | 1 | Adafruit BNO085 (addr 0x4A) | $25 | On-chip fusion; clean-domain I2C |
| 8 | Current/voltage sense | 1 | INA219 breakout | $5 | Motor bus; on dirty domain via I2C isolator |
| 9 | Digital isolator | 5 | TI ISO7741 (quad-channel) | $3 | Drive PWM/DIR + servo PWM + pawl line across barrier |
| 10 | I2C isolator | 1 | TI ISO1640 (bidirectional) | $3 | Isolated I2C to motor-domain INA219 |
| 11 | Isolated DC-DC | 1 | 5 V 1-2 W isolated module (Recom/Murata) | $8 | Powers motor-side logic / isolator far side |
| 12 | Logic buck | 1 | 5 V/3 A buck (clean domain) | $5 | Feeds ESP32 + clean sensors |
| 13 | Servo BEC | 1 | 6 V 5 A UBEC (isolated servo rail) | $8 | Separate from logic + main motor power |
| 14 | Pawl solenoid | 6 | Push/pull solenoid (spring-return) | $5 | Spring-engaged, power-to-release |
| 15 | Solenoid MOSFET | 1-2 | Logic-level N-FET bank (IRLZ44N-class) + flyback diodes | $2 | Drives the pawl bank |
| 16 | Protection | — | Input fuse, TVS, RC snubbers across motors, bulk caps | $10 | Per [Electronics Backbone](../electronics/Electronics Backbone.md) |
| 17 | Connectors | — | XT60 (power), JST-XH (signal), M12 bulkhead (inter-deck) | $20 | No Dupont on a moving rover |
| 18 | Carrier PCB | 1 | Custom KiCad → JLCPCB (breadboard for bench first) | $5 | Build medium decision |

**Electrical subtotal (excl. mechanical/OSR + motors):** ~$200-260. Motors add ~$150-240. Mechanical frame per OSR BOM.

## ESP32-S3 Pinout / Wiring Map (reference assignment)

> Functional allocation. **Finalize exact GPIO numbers against the specific module variant** — avoid strapping pins (GPIO0, 3, 45, 46), the USB pins (GPIO19/20, reserved for CDC), and the flash/PSRAM pins (≈GPIO26-37 on WROOM-1, variant-dependent).

| Function | Signals | Peripheral | Crosses isolation? | Reference GPIO |
|---|---|---|---|---|
| Drive motor PWM ×6 | 6 | **MCPWM** (2 units × 6 = ample) | Yes → motor domain | 4, 5, 6, 7, 15, 16 |
| Drive motor DIR ×6 | 6 | GPIO out | Yes → motor domain | 17, 18, 8, 9, 10, 11 |
| Steering servo PWM ×4 | 4 | **LEDC** (50 Hz) | Yes → servo domain | 12, 13, 14, 21 |
| Encoders + IMU | 2 | I2C0 (clean) | No | SDA 1, SCL 2 |
| Motor-bus INA219 | 2 | I2C1 via ISO1640 | Yes → motor domain | SDA 41, SCL 42 |
| Pawl release (bank) | 1 | GPIO out → MOSFET | Yes → pawl domain | 38 |
| E-stop / motion-power live sense | 1 | GPIO in | (sensed across) | 39 |
| Status LED | 1 | GPIO out | No | 48 |
| USB CDC to Core Hub | 2 | Native USB OTG | — | 19, 20 (reserved) |

**Why MCPWM for drive + LEDC for servos:** 6 drive + 4 servo = 10 PWM outputs, but the ESP32-S3 LEDC has only 8 channels. The S3's two MCPWM units are purpose-built for motor PWM — drive motors go there, servos take 4 LEDC channels. This is the detail that makes 10 PWMs actually fit.

## Power Domains & Isolation

Three electrically separate domains, bridged only through isolators (full galvanic isolation):

```
                 ┌── CLEAN LOGIC DOMAIN ──────────────────────────┐
  raw 14.8V ──┬──┤ 5V/3A buck → ESP32-S3 (3.3V onboard)           │
  (fused,     │  │  I2C0: TCA9548A → 6×AS5600, BNO085             │
   per deck)  │  │  control logic, watchdog                       │
              │  └───────────────┬────────────────────────────────┘
              │      digital isolators (ISO7741) │  I2C isolator (ISO1640)
              │  ┌───────────────┴──── MOTOR DOMAIN ──────────────┐
              ├──┤ 3× Cytron MDD10A → 6 drive motors              │
              │  │ isolated 5V DC-DC powers driver-side logic     │
              │  │ INA219 (bus sense), RC snubbers, bulk caps     │
              │  │ pawl MOSFET bank → 6 solenoids                 │
              │  └────────────────────────────────────────────────┘
              │  ┌──────────────── SERVO DOMAIN ──────────────────┐
              └──┤ 6V UBEC → 4 corner-steer servos                │
                 │ servo PWM arrives via isolators                │
                 └─────────────────────────────────────────────────┘
  Grounds: clean / motor / servo separate, meet only at the battery-negative star point.
  Fail-safe: all isolated control lines default to SAFE on signal loss
             (drivers→brake, pawls→engaged).
```

## Layered Safe-Stop (wiring intent)

1. **Software** → ESP32 commands MDD10A brake.
2. **Hardware watchdog (100 ms)** → Task WDT trips on lost Pi heartbeat → brake; independent of the micro-ROS bridge.
3. **Total power loss / E-stop** → pawl solenoids de-energize → springs drop the pawls → wheels mechanically locked. The [Electronics Backbone](../electronics/Electronics Backbone.md) NC safety loop cuts motion power here.

Pawl logic: **energize = release** (hold pawls clear for motion); **no power = engage**. So any failure direction locks the wheels.

## Assembly + Bench Bring-Up Order

Each step has a verify gate — don't advance until it passes. Mirrors [Phase 1 Implementation Kickoff](../onboarding/Phase 1 Implementation Kickoff.md).

1. **Frame** — build the OSR rocker-bogie per the JPL BOM. *Verify:* suspension articulates freely; corners steer through full range by hand.
2. **Bench power (no motors)** — wire the clean 5V buck + ESP32-S3. *Verify:* ESP32 boots, enumerates as USB CDC on the Core Hub (`/dev/ttyACM*`).
3. **Sensors first** — I2C0: TCA9548A + one AS5600 + BNO085. *Verify:* read all 6 encoder channels through the mux; BNO085 returns a stable quaternion.
4. **One motor, isolated** — wire ONE MDD10A channel through the ISO7741, isolated DC-DC, on the bench (wheel off ground). *Verify:* PWM+DIR spins the wheel both directions; encoder count tracks; INA219 reads current through the I2C isolator.
5. **All six drives** — replicate. *Verify:* all 6 wheels driven independently; odometry integrates.
6. **Steering** — 6V UBEC + 4 servos via LEDC + isolators. *Verify:* each corner steers to commanded angle; full range clears the frame.
7. **Parking pawls** — solenoids + MOSFET bank. *Verify:* powered = pawls clear (wheels free); cut power = pawls drop and lock; matches fail-safe direction.
8. **Watchdog safe-stop** — run [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md). *Verify:* killing the Pi heartbeat / micro-ROS agent / USB cable trips brake within budget; pawls hold on a 15° slope.
9. **Move to PCB** — once the breadboard passes 1-8, lay out the custom carrier PCB (KiCad → JLCPCB). *Verify:* re-run steps 4-8 on the PCB before the deck goes on a moving rover.

## Open Items (need a number or a verification)

- **Drive gear ratio** — torque/speed calc from wheel diameter + target ≤1 m/s + worst-case slope + rover mass. Sets the exact gearmotor.
- **Steering servo torque + range** — check against OSR corner-steer geometry and ground-contact resistance.
- **Pawl solenoid force + tooth pitch** — mechanical sizing so a pawl reliably holds the worst-case slope torque.
- **Pawl count** — 6 (all wheels) vs 4 — depends on rocker-bogie weight distribution. Default 6 until a load calc says fewer.
- **Exact GPIO finalization** — against the chosen ESP32-S3 module variant (strapping/flash pins).
- **OSR BOM cross-reference** — confirm the live JPL OSR motor/wheel parts and reconcile mounting for the AS5600 magnets on the drive shafts.
- **MDD10A final amp rating** — confirm ≥2× measured stall once the gearmotor is chosen (MDD10A's 10 A/ch should cover most 37D-class motors).

## Related

[Locomotion Control Unit](../modules/Locomotion Control Unit.md) · [Locomotion Electronics](../electronics/Locomotion Electronics.md) · [Electronics Backbone](../electronics/Electronics Backbone.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [Phase 1 Implementation Kickoff](../onboarding/Phase 1 Implementation Kickoff.md) · [Mark 1 Index](../Mark 1 Index.md)
