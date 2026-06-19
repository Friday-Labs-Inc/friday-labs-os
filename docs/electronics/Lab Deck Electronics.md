# Lab Deck Electronics

> Electronics design for the Adaptive Research Module (Lab Deck) deck: power, USB budget, and the signature plug-and-play expansion ports. Builds on the shared [Electronics Backbone](Electronics Backbone.md).
> **Version:** Draft 1.0 · **Deck compute:** Pi 5 (8 GB). See also the [Adaptive Research Module](../modules/Adaptive Research Module.md) module spec.

## Decisions

| Area | Decision |
|---|---|
| Pi 5 power | Core Hub pattern — 5 V/6 A buck → GPIO + `usb_max_current_enable=1` + input protection |
| Cooling | Conduction cooling to a sealed chassis radiator plate |
| Boot / storage | NVMe boot via M.2 HAT (A/B OTA) + the 256 GB USB SSD kept purely for research data |
| USB power | Powered USB 3.0 hub off the 5 V rail with spare per-port-switched ports for plug-and-play |
| Expansion ports | Per-port eFuse / hot-swap controllers + isolated I2C buffers (PCA9306/LTC4302-class) |
| Build | Custom PCB |

## Rationale Highlights

- **The expansion ports are the deck's reason to exist.** A field tech plugs an unknown sensor into a running rover, so each port must let a faulty sensor isolate *itself*:
  - **eFuse / hot-swap controller** per port — inrush limiting on plug-in, over-current cutoff, auto-recovery. A short or hungry sensor can't brown out the rail or disturb other sensors.
  - **Isolated I2C buffer with enable** per I2C port — a misbehaving sensor that holds the bus low can be electrically dropped, so it can't hang the shared bus and take the Lab Deck down mid-mission.
- **OS/data split:** NVMe carries the OS (reliable, A/B OTA); the USB SSD carries bulk research capture. A storage hiccup on one doesn't compromise the other.
- **Spare powered ports** give plug-and-play discovery (USB hot-plug + I2C scan, per the [Adaptive Research Module](../modules/Adaptive Research Module.md)) the headroom to add sensors in the field.

## On-Deck Sensors (USB hub)

RPLIDAR A3, Arducam IMX477, RD-03D mmWave (via USB-UART bridge — see [mmWave Human Detection](../addendums/mmWave Human Detection.md)), 256 GB USB SSD. BME280 on I2C.

## BOM Adders (approx.)

- 5 V/6 A buck + M.2 HAT + NVMe: ~$50
- Powered USB 3.0 hub (per-port switching): ~$25
- eFuse / hot-swap controllers + isolated I2C buffers (per port × N): ~$5-8 per port

## Open Items

- Number and mix of expansion ports (USB vs I2C) to provision.
- Connector standard for expansion ports (must survive field plugging — keyed, sealed).
- Mid-mission hot-swap acceptance policy (architecturally supported; mission-planner decides) — Phase 5.

## Related

[Electronics Backbone](Electronics Backbone.md) · [Adaptive Research Module](../modules/Adaptive Research Module.md) · [mmWave Human Detection](../addendums/mmWave Human Detection.md) · [Sensor Ownership](../addendums/Sensor Ownership.md) · [Mark 1 Index](../Mark 1 Index.md)
