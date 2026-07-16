# Mark 1 — Interface Control Document (ICD) v0.1

> **What this is, in one line:** the wiring + signal contract for the real Mark 1 —
> which board talks to what, on which pin, over which wire, at what voltage — so the
> mechanical parts (now printing at reference scale), the electronics, and the
> Friday Labs OS firmware all agree before anything is soldered.
>
> **Status:** DRAFT v0.1 — baseline locked from the canonical reference design; pin
> maps drafted for the boards in hand. Fuse values + the motor connector are still
> provisional (need a stall-current bench test). This is the document every wire,
> PCB, and firmware build should check against.

---

## 0. Locked baseline (the decisions behind this ICD)

Mark 1 is a **scaled clone of the NASA-JPL / HowToMechatronics Perseverance rover**
([reference](https://howtomechatronics.com/projects/diy-mars-perseverance-rover-replica-with-arduino/)),
*upgraded* from a single Arduino + hobby RC to the Friday Labs OS (a Raspberry Pi
brain + ESP32 reflex decks + a signed Command Center).

| Decision | Locked value | Source |
|---|---|---|
| Scale | Reference (≈130 mm wheels); **parts printing now at this scale** | reference + sim |
| Drive | **6 wheels, independent** — XD-37GB555 12 V gearmotor each | reference |
| Drive drivers | **6× DRV8871** (one per motor, 3.6 A peak) | reference |
| Steering | **4-corner Ackermann**, 4× 25 kg·cm digital servos; middle 2 drive-only | reference + sim `kinematics.py` |
| Battery | **3S LiPo ~12 V** (11.1 V nom / 12.6 V full) | locked 2026-06-30 |
| Suspension | rocker-bogie + 3-piece differential bar | reference |
| Brain | 2× Raspberry Pi 4B (Core, Telemetry) | this build |
| Reflex decks | 3× ESP32-WROOM-32 (DevKitC, 38-pin, CP2102) — Drive / Steer / Sensor | boards in hand |
| Link | micro-ROS over USB-serial (CP2102 → /dev/ttyUSB*) | this build |
| Operator link | signed Command Center over MQTT (replaces the FlySky RC) | Friday Labs OS |

---

## 1. System block diagram (text)

```
            ┌─────────────── Command Center (operator) ───────────────┐
            │           signed CBOR / Ed25519 over MQTT                 │
            └──────────────────────────┬───────────────────────────────┘
                                        │ (internet / Tailscale)
                            ┌───────────┴───────────┐
                            │  Telemetry Pi (Pi 4B)  │  the ONLY internet-facing node
                            │  friday_telemetry      │  validates every command + signs telemetry
                            └───────────┬───────────┘
                                        │ DDS / Ethernet (LAN-only, between the Pis)
                            ┌───────────┴───────────┐
                            │   Core Pi (Pi 4B)      │  Core Hub (authority + 20 Hz safety pulse
                            │   friday_core_hub +    │  + supervisor) and Locomotion agent
                            │   friday_locomotion    │  (kinematics.drive_and_steer)
                            └───┬─────────┬─────────┬┘
                  USB-serial    │         │         │   USB-serial (micro-ROS, one /dev/ttyUSB* each)
                  ┌─────────────┘   ┌─────┘     └─────────────┐
            ┌─────┴──────┐    ┌──────┴─────┐          ┌────────┴────┐
            │ Drive ESP32 │    │ Steer ESP32│          │ Sensor ESP32│
            │ 6× DRV8871  │    │ 4 servos   │          │ IMU? thermal│
            │ +encoders   │    │ +pawls     │          │ GPS, mmWave │
            │ +IMU +Istat │    └─────┬──────┘          └─────────────┘
            └──────┬──────┘          │
              6 motors           4 corner servos
```

---

## 2. The Pi ↔ ESP32 link

- **Transport:** micro-ROS over serial. Each ESP32's onboard **CP2102** appears on the
  Core Pi as `/dev/ttyUSB0/1/2`. One `micro_ros_agent` instance per board (or one
  multi-port agent). Base ESP32-WROOM-32 has **no native USB**, so this UART-via-CP2102
  path is the link — fully supported by micro-ROS's serial transport.
- **Baud:** 921600 (start at 115200 for bring-up, raise once stable).
- **UART0 (GPIO1 TX / GPIO3 RX) is reserved** on every ESP32 for this link — do not
  assign those pins to anything else.
- **Why micro-ROS:** the ESP32 decks become real ROS 2 nodes. The Locomotion agent on
  the Core Pi publishes the same wheel/steer commands it already sends to the Gazebo
  controllers — on hardware they go to the Drive/Steer ESP32 nodes instead. The OS
  cannot tell sim from silicon: the interface-first promise.

---

## 3. Pin maps (ESP32-WROOM-32, 38-pin DevKitC)

**Board-wide rules (apply to all three):** GPIO6–11 are wired to flash — NEVER use.
GPIO34/35/36/39 are **input-only** (no output, no pull-up). GPIO0/2/5/12/15 are
**strapping** pins (boot-sensitive) — avoided here. GPIO1/3 = UART0 (the Pi link) —
reserved. ADC2 pins are fine for analog because Wi-Fi is OFF (wired rover).

### 3a. DRIVE deck — 6 motors (GPIO budget is tight here; this map fits)

| Function | GPIO | Notes |
|---|---|---|
| M1 LF DRV8871 IN1 / IN2 | 4 / 13 | both LEDC PWM (PWM the active input, other = 0) |
| M2 LM IN1 / IN2 | 14 / 16 | |
| M3 LR IN1 / IN2 | 17 / 18 | |
| M4 RF IN1 / IN2 | 19 / 23 | |
| M5 RM IN1 / IN2 | 25 / 26 | |
| M6 RR IN1 / IN2 | 27 / 32 | 12 PWM lines total (≤16 LEDC channels ✔) |
| I2C SDA / SCL | 21 / 22 | → TCA9548A mux `0x70` [ch0–5 = 6× AS5600 `0x36`], BNO085 IMU `0x4A`, INA219 `0x40` |
| ESTOP_LIVE sense | 34 | input-only; reads whether the motor contactor is closed |
| spare | 33, 35, 36, 39 | 35/36/39 input-only |

All 12 motor inputs get **10 kΩ pull-downs** so motors stay OFF while the ESP32 is
unpowered, booting, or reset. (Encoders are an upgrade over the open-loop reference.)

### 3b. STEER deck — 4 corner servos + parking pawls (plenty of GPIO)

| Function | GPIO | Notes |
|---|---|---|
| Servo LF / RF / LR / RR (PWM) | 13 / 14 / 25 / 26 | 50 Hz LEDC; fed the Ackermann angles |
| Parking-pawl solenoids ×4 | 16 / 17 / 18 / 19 | low-side N-MOSFET; **power-to-release (fail-engaged)** |
| ESTOP_LIVE sense (optional) | 34 | input-only |
| I2C (spare) | 21 / 22 | for a deck health sensor if needed |

### 3c. SENSOR deck — IMU/thermal/GPS/radar (easy)

| Function | GPIO | Notes |
|---|---|---|
| Thermal OneWire (DS18B20 bus) | 4 | 4.7 kΩ pull-up; multiple sensors on one bus |
| GPS UART (UART2) | TX 17 / RX 16 | + optional PPS on 18 |
| mmWave RD-03D UART (UART1, remapped) | TX 25 / RX 26 | remap off the default 9/10 (flash pins) |
| Ambient light (ADC1) | 35 | input-only analog |
| I2C (aux IMU / sensors) | 21 / 22 | |

> **If the Drive deck's 12+2 pins ever feel too tight:** drop in a **PCA9685** 16-ch
> PWM driver over I2C for the motors — frees all 12 motor GPIO down to the 2 I2C lines.
> Adds one chip; PWM-over-I2C latency is fine at these motor speeds. Flagged, not adopted.

---

## 4. Power architecture

```
3S LiPo (11.1 V nom / 12.6 V full)
  ├─ MAIN FUSE (provisional, size after stall test) ─ NC CONTACTOR (E-stop, fail-open)
  │     └─ +12V_MOTOR ─ 6× DRV8871 VM   (per-motor fuse, provisional 5–7 A)
  ├─ Buck → +6V_SERVO (≥8 A) ─ 4 servos      (bulk cap near servo bus)
  ├─ Buck → +5V_LOGIC (≥8 A) ─ Core Pi 4B + Telemetry Pi 4B + 3× ESP32 (VIN)
  └─ telemetry tap: pack V + pack I (INA219)  → reported up to the operator
star ground at the battery negative; logic returns meet power returns ONLY at the star
```

- **2× Pi 4B** is a deviation from the reference's single controller — the 5 V buck is
  sized for both (each Pi 4B up to ~3 A peak) **plus** the ESP32s. Use ≥8 A and short,
  thick 5 V runs.
- Servos on their own 6 V rail (NOT off the Pi 5 V) — stall spikes must not brown out
  the logic.
- Motor 12 V is raw battery, gated by the contactor (see §5).

---

## 5. Safe-stop chain (the foundational safety guarantee)

Three independent layers, motor side first:

1. **Hardware contactor (fail-open).** A normally-closed contactor sits in the +12V_MOTOR
   line. Its coil must be actively held for motors to have power; lose the hold (E-stop
   button, watchdog relay, power loss) → contacts open → **all motor power gone**,
   while the Pis + ESP32s stay alive to report why.
2. **Firmware watchdog (Drive ESP32).** If no fresh command/heartbeat arrives from the
   Core Pi within the timeout (**target ≤100 ms**), the Drive ESP32 zeros all 12 PWM
   lines. This is the **HIL 100 ms watchdog** that was "honestly open / not closeable in
   sim" — it now has a real home. `ESTOP_LIVE` on GPIO34 lets firmware confirm the
   contactor state.
3. **OS authority + pulse (Core Pi).** Above the firmware: the Core Hub's authority lease
   + 20 Hz safety pulse and the Locomotion safe-stop (already verified in sim) ride on
   top. If the Core dies, the Telemetry Pi self-promotes (Phase 4 failover) — and even if
   both Pis fall over, layers 1–2 still stop the motors.

Pull-downs on every DRV8871 input (§3a) make "no signal = stopped" the default.

---

## 6. micro-ROS topic contract (what each deck speaks)

| Deck | Subscribes (from Core Pi) | Publishes (to Core Pi) |
|---|---|---|
| **Drive** | 6 wheel velocities (rad/s) — from `kinematics.drive_and_steer` | 6 encoder counts/velocity (odom feedstock), IMU, motor currents (INA219) |
| **Steer** | 4 corner steer angles (rad) — from `kinematics.drive_and_steer` | servo status / pawl state |
| **Sensor** | — | temperatures, GPS fix, ambient light, mmWave detections |

On the Core Pi, the **Locomotion agent already produces exactly these** (6 wheel vel + 4
steer angles). Today it publishes to the Gazebo controllers; on hardware it publishes to
the Drive + Steer micro-ROS nodes. **No new kinematics — just a new output target.**
The Sensor deck's data feeds the same fault/telemetry path the Telemetry agent already
signs and ships to the Command Center.

---

## 7. Connectors & wiring (from the reference + harness spec)

| Link | Connector | Gauge |
|---|---|---|
| Battery main | XT60 / XT90-S anti-spark | 10–12 AWG |
| Per-motor power | XT30 / sealed 2-pin | 14 AWG |
| Servo | sealed 3-pin | 18 AWG power / 22 AWG signal |
| Encoder (AS5600) | JST-GH | 24–26 AWG |
| Signal (general) | JST-GH / locking | 22–26 AWG |
| Pi ↔ ESP32 | short locking USB (micro-B/USB-C per board) | — |

**Segregation rule:** high-current motor wiring in one channel; encoder/signal wiring in
a separate channel ≥25 mm away; cross only at 90°.

---

## 8. Open items (decide / measure before final wiring)

- [ ] **Motor connector + exact XD-37GB555 variant** (shaft, mount, encoder option).
- [ ] **Stall-current bench test** → lock main fuse + per-motor fuse values.
- [ ] **Servo part number** (25 kg·cm class) + UBEC current rating for 4 at stall.
- [ ] **NC contactor + coil** part (≥ motor stall current, fail-open coil).
- [ ] **Parking pawls?** — reference has none; our design adds 4. Confirm we want them in v0.1.
- [ ] **Telemetry Pi networking** — Ethernet vs USB-gadget between the two Pis.
- [ ] **PCA9685 fallback** for the Drive deck if the direct 12-GPIO map proves awkward.
- [ ] **AS5600 encoders** are an addition over the reference — confirm we're doing closed-loop in v0.1 or deferring to open-loop first.

---

**Related:** [Locomotion Deck – Full Schematic](Locomotion%20Deck%20-%20Full%20Schematic.pdf) ·
[Stage 1 — Gazebo Simulation](../software/Stage%201%20-%20Gazebo%20Simulation.md) ·
reference: HowToMechatronics Perseverance replica.
