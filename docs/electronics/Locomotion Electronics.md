# Locomotion Electronics

> Electronics design for the Locomotion Control Unit deck: motor drivers, galvanic isolation, the slope-hold parking pawls, and the layered safe-stop. The densest, most safety-critical deck. Builds on the shared [Electronics Backbone](Electronics Backbone.md).
> **Version:** Draft 1.0 · **Deck compute:** ESP32-S3. See also the [Locomotion Control Unit](../modules/Locomotion Control Unit.md) module spec and the [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md).

## Decisions

| Area | Decision |
|---|---|
| ESP32-S3 power | Clean buck on the isolated logic domain |
| Motor drivers | 3× Cytron-class dual drivers, sized for ≥2× stall current, heatsinked for continuous active-hold |
| Power isolation | **Full galvanic isolation** — digital isolators on all driver, servo, and pawl-release control lines; isolated DC-DC for motor-side logic; separate motor/logic grounds |
| Servo rail | Isolated 6 V BEC for the 4 corner-steer servos (separate from logic and main motor power) |
| Current sense | INA219 on the motor domain via an isolated I2C bridge |
| Encoders | 6× AS5600 via TCA9548A I2C mux, on the clean logic domain |
| IMU | BNO085 on the clean logic domain |
| Slope hold | Solenoid parking pawls per driven wheel — spring-engaged, power-to-release |
| Build | Custom PCB (breadboard for bench bring-up only) |

## Layered Safe-Stop

Three independent layers, weakest assumption to strongest:

1. **Software safe-stop** — autonomy/operator commands drivers to brake.
2. **Hardware watchdog (100 ms)** — ESP32 Task WDT trips on lost Pi heartbeat, commands brake; independent of the micro-ROS bridge. See [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md).
3. **Total power loss** — parking pawls mechanically lock the wheels; nothing electronic required.

The pawl-release lines cross the isolation barrier wired **signal-loss-defaults-to-engaged**, so any failure of the barrier drops the pawls rather than releasing them.

## Rationale Highlights

- **Full galvanic isolation** (operator's call over separate-domains-with-star-ground): brushed-motor brush noise is fully decoupled from the I2C encoder bus and IMU — bad encoder reads would corrupt odometry and the stall detector, which are safety-relevant. Maximum immunity, accepted complexity.
- **Parking pawls preserve full motion:** the operator rejected non-backdrivable gearing because it taxes every motion (speed, efficiency, all four locomotion modes). Pawls *decouple* holding from the drivetrain — efficient backdrivable motors keep full capability, and a separate device handles power-loss holding. The price is 4–6 small solenoids.
- **Drivers sized for active-hold:** holding torque on a slope is a near-continuous near-stall current, a thermal load, not just a peak — hence ≥2× headroom and heatsinking.

## BOM Adders (approx.)

- 3× Cytron-class dual drivers: ~$45-65
- Digital isolators + isolated DC-DC + isolated I2C bridge: ~$25
- 6 V servo BEC: ~$8
- TCA9548A I2C mux + 6× AS5600: ~$20
- BNO085 IMU: ~$28
- INA219: ~$5
- 4–6× pawl solenoids + release drivers + mechanism: ~$40-70 (mechanical)

## Open Items

- Final driver amp rating once the motor (chassis kit) is chosen.
- Pawl count: 4 vs 6 wheels — depends on rocker-bogie weight distribution and worst-case slope.
- Pawl mechanism mechanical design (tooth pitch, solenoid force, settle tolerance).

## Related

[Electronics Backbone](Electronics Backbone.md) · [Locomotion Control Unit](../modules/Locomotion Control Unit.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [Mark 1 Index](../Mark 1 Index.md)
