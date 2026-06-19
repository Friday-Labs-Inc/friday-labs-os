# Locomotion Deck — Build Package

> The buildable package for the bottom deck: BOM, ESP32-S3 pinout/wiring map, power-domain & isolation wiring, connection diagram, and assembly + bench bring-up order. Turns the locked decisions in [Locomotion Control Unit](../modules/Locomotion Control Unit.md) and [Locomotion Electronics](../electronics/Locomotion Electronics.md) into something you can buy and wire.
> **Version:** Draft 1.0 · **Mechanical base:** JPL Open Source Rover (rocker-bogie) · **Electronics:** Friday Labs locked stack.

## Authoritative Sources

- **Mechanical BOM + frame build:** the live JPL Open Source Rover repo — `github.com/nasa-jpl/open-source-rover`. Pull the chassis, rocker-bogie, wheels, and corner-steer mechanical parts from there; it is the validated, maintained source. This doc covers the **Friday Labs electronics** that replace the OSR's stock control electronics, plus integration.
- **Electrical decisions:** [Locomotion Electronics](../electronics/Locomotion Electronics.md), [Electronics Backbone](../electronics/Electronics Backbone.md), [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md).

> **We keep the OSR mechanism; we replace its control electronics — and re-proportion its frame.** The OSR ships with RoboClaw controllers; we drive the same motors with our Cytron + galvanic-isolation + parking-pawl stack. Per the [Mechanical Design Reference](../addendums/Mechanical Design Reference.md), the frame is **re-proportioned to true Perseverance scale (~74 cm body, 0.2476×, 130 mm wheel)** — so OSR is the rocker-bogie mechanism donor, not a stock-dimension build; expect CAD re-spacing rather than a bolt-together kit.

## Electrical BOM (Friday Labs Locomotion stack)

| # | Part | Qty | Real-world example | ~Unit | Notes |
|---|---|---|---|---|---|
| 1 | MCU | 1 | ESP32-S3-DevKitC-1 (bench) → ESP32-S3-WROOM-1 module (PCB) | $15 | Native USB CDC to Core Hub |
| 2 | Dual motor driver | 4 | **Cytron MDD10A** (dual, 10 A/ch, 5-25 V, PWM+DIR) | $22 | 3 boards = 6 channels + **1 spare**. Buy MDD10A, **not** the RC-oriented MDDRC10. Confirmed by the [sizing calc](#drive-motor-sizing-resolved) (~5.5 A stall → 1.8× headroom). |
| 3 | Drive gearmotor | 6 | 12 V brushed DC gearmotor, ratio per torque calc (Pololu 37D-class) | $25-40 | **Gear ratio TBD by sizing calc** — see Open Items |
| 4 | Corner-steer servo | 4 | Metal-gear ~20-25 kg·cm, 6 V, ≥180° (DS3218/DS3225) | $15-20 | Open-loop PWM; ~4× margin over in-place scrub (see sizing) |
| 5 | Wheel encoder | 6 | AS5600 magnetic breakout + diametric magnet | $3 | On drive output shafts; all addr 0x36 |
| 6 | I2C mux | 1 | TCA9548A breakout (addr 0x70) | $7 | Fans out 6× AS5600 (shared 0x36) |
| 7 | IMU | 1 | Adafruit BNO085 (addr 0x4A) | $25 | On-chip fusion; clean-domain I2C |
| 8 | Current/voltage sense | 1 | INA219 breakout | $5 | Motor bus; on dirty domain via I2C isolator |
| 9 | Digital isolator | 5 | TI ISO7741 (quad-channel) | $3 | Drive PWM/DIR + servo PWM + pawl line across barrier |
| 10 | I2C isolator | 1 | TI ISO1640 (bidirectional) | $3 | Isolated I2C to motor-domain INA219 |
| 11 | Isolated DC-DC | 1 | 5 V 1-2 W isolated module (Recom/Murata) | $8 | Powers motor-side logic / isolator far side |
| 12 | Logic buck | 1 | 5 V/3 A buck (clean domain) | $5 | Feeds ESP32 + clean sensors |
| 13 | Servo BEC | 1 | 6 V 5 A UBEC (isolated servo rail) | $8 | Separate from logic + main motor power |
| 14 | Pawl solenoid | 4 | Push/pull solenoid (spring-return) | $5 | **Corner wheels only**; spring-engaged, power-to-release; tooth bears the load, solenoid actuates only |
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

## Drive-Motor Sizing (resolved)

Inputs: 11 kg loaded mass · 130 mm wheels (r = 0.065 m) · 20° max climb · 1.0 m/s target · 6 driven wheels · Crr = 0.10 (soil/grass).

| Quantity | Result |
|---|---|
| Wheel speed for 1.0 m/s | ω = v/r = 15.4 rad/s → **~147 RPM** |
| Tractive force on 20° slope | F = mg(sin20° + 0.10·cos20°) = **47 N** |
| Total wheel torque | F·r = **3.06 N·m** |
| Per motor (÷6) | **0.51 N·m** steady climb |
| Design target (2× for uneven loading) | **≥1.0 N·m (≥10 kg·cm) stall/motor** |

**Motor spec:** 12 V brushed DC gearmotor, **37D-class, ~70:1** → ~150 RPM, ~1.2–1.3 N·m (12–13 kg·cm) stall, ~5.5 A stall. Confirm against the chosen motor datasheet / live OSR BOM.

**Driver confirmed:** motor stall ~5.5 A → **10 A/channel = ~1.8× headroom.** Cytron 10 A class (MDD10A dual / MD-series single). Not 20/30 A.

**Firmware note — 4S over-voltage:** the 14.8 V bus reaches 16.8 V at full charge, over the 12 V motor rating. **Cap drive PWM duty at ~71% (12 ÷ 16.8)** so motors never exceed 12 V.

**Power note:** a sustained 20° climb draws ~12–15 A total (~100–160 W) — above the [Power Budget](../addendums/Power Budget.md) ~80 W motor-peak line. Per-channel current stays well under 10 A; mission planner should avoid long sustained steep ascents.

## Steering & Pawl Sizing (resolved)

**Steering servos — 4× corner.** Worst case is steering a wheel in place (scrub): with ~30 N per corner (up to ~40 N), μ ≈ 0.8 on soil, patch radius ≈ 0.02 m → scrub torque ≈ ⅔·μ·N·R ≈ **0.3–0.5 N·m (3–5 kg·cm)**. A **20–25 kg·cm servo gives ~4× margin.** Range ≥180° covers full crab walk (±90° at the pivot). **Open-loop PWM** — kinematics use the commanded angle; drive-encoder + IMU + nav-sensor fusion absorbs the few-degree error. (Closed-loop steering-pivot encoders are a future precision upgrade.)

**Parking pawls — 4× corner wheels.** Locking the four corners prevents chassis translation, so the middle wheels are redundant for holding. Each tooth bears **~0.45 N·m (15° hold) / ~0.60 N·m (20°)** — easy tooth design. The **solenoid actuates only** (retracts the pawl against its return spring, ~10–20 N); the tooth geometry bears the slope load. Tradeoff: **no pawl redundancy** — seating must be reliable.

## Open Items (need a number or a verification)

- **Pawl mechanical detailing** — tooth pitch (target settle <~5 mm of wheel rotation), return-spring force, solenoid stroke; reliable seating matters since 4 corners give no redundancy.
- **Exact GPIO finalization** — against the chosen ESP32-S3 module variant (strapping/flash pins).
- **OSR BOM cross-reference** — confirm the live JPL OSR motor/wheel parts and reconcile mounting for the AS5600 magnets on the drive shafts; verify the 70:1 motor's exact RPM/torque/stall-current against its datasheet.
- **Heavy/steep case** — if final mass ≥15 kg or climb >20°, re-run the calc: a higher ratio (~100:1, ~100 RPM, lower top speed) may be needed, and per-channel stall current rises toward the 10 A limit.

## Related

[Locomotion Control Unit](../modules/Locomotion Control Unit.md) · [Locomotion Electronics](../electronics/Locomotion Electronics.md) · [Electronics Backbone](../electronics/Electronics Backbone.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [Phase 1 Implementation Kickoff](../onboarding/Phase 1 Implementation Kickoff.md) · [Mark 1 Index](../Mark 1 Index.md)
