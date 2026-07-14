# Phone Sensor Pod — an old Android phone as the rover's GPS + IMU

**What this is (plain English).** Mark 1 had no GPS module in its parts bin. An old
OnePlus 6T (camera broken, otherwise healthy) fills that gap for free: the phone
rides on the rover, streams its GPS and motion sensors one-way over WiFi, and a
small bridge node on the Core Hub turns those streams into normal ROS 2 topics.
The phone is **advisory only** — it can inform the rover, it can never stop it,
steer it, or be commanded by it.

```
OnePlus 6T (stock Android)                 Core Hub Pi 4B
┌──────────────────────────┐               ┌──────────────────────────────┐
│ GPSd Forwarder app       │─ NMEA/UDP ───▶│ gpsd ──┐                     │
│ HyperIMU app             │─ JSON/UDP ───▶│        ▼ (TCP 2947)          │
└──────────────────────────┘   :29998      │  phone_bridge (lifecycle)    │
        one-way only           :5555       │   ├─▶ /mark1/phone/fix       │
   no commands flow back                   │   ├─▶ /mark1/phone/imu       │
                                           │   └─▶ heartbeat + health     │
                                           └──────────────────────────────┘
```

**The module.** `MARK1-PHONE-001`, hardware type `phone` (the registry derives the
namespace from the hardware type, and `sensor` is already owned by the ESP32 sensor
board — so the phone gets its own `/mark1/phone`). It is a standard `ModuleAgent`
lifecycle node: it registers on `configure`, heartbeats at 5 Hz while `active`, and
appears automatically as a card in the FCC deck's Modules view once registered.

**Three deliberate design choices.**

1. *One-way UDP, stamped on arrival.* Sensor data is only valuable fresh, so lost
   packets are dropped, never retransmitted late. The phone's clock is untrusted —
   every message is stamped with the Pi's clock when it arrives. WiFi adds jitter,
   which makes this **tilt/vibration/display-grade** data: good for the deck and
   sanity checks, not for feeding an EKF or sensor-fusion pipeline (a resampling
   buffer would be needed first — there's a comment in the node saying exactly that).

2. *A silent phone is DEGRADED, not dead.* If the phone falls off WiFi, runs flat,
   or Android kills the app, the bridge **keeps heartbeating** and reports
   `HEALTH_DEGRADED` with a detail string. A stopped heartbeat would read as module
   failure in the registry — the wrong story. The phone is outside the safety path:
   losing it never trips safe-stop.

3. *Registration keep-alive.* The bridge re-sends `RegisterModule` every 60 s even
   when already registered. Re-registering is a harmless upsert, and it heals the
   case where a Core-Hub restart wipes the in-memory registry (a real gap found
   during the ESP32 live bring-up — this node avoids it from day one).

**Trust and abuse handling.** The real security boundary is the WiFi network's
WPA2 password (source-IP filtering is spoofable and only a second layer). Inside
that, the bridge treats every packet as hostile until proven boring: strict JSON
parsing, per-field NaN policy (IMU values must be finite; a NaN altitude is legal —
that's just a 2D fix), range gates (|accel| ≤ 80 m/s², |gyro| ≤ 35 rad/s), a
teleport check (a fix that jumps > ~55 km from a fresh previous fix is dropped),
a 100 msg/s rate limit, bounded buffers, and drop *counters* in the log — never
the raw payload.

**Configuration** (all ROS parameters on the `phone` node):

| Parameter | Default | Meaning |
|---|---|---|
| `bind_address` | `0.0.0.0` | Set to the internal interface IP in the field |
| `imu_port` | `5555` | HyperIMU's UDP target port |
| `phone_ip` | `''` (any) | Set to the phone's static IP to filter sources |
| `gpsd_host` / `gpsd_port` | `127.0.0.1:2947` | Where gpsd runs |
| `fix_timeout_s` / `imu_timeout_s` | `3.0` / `1.0` | Stale-stream watchdogs |
| `max_imu_msgs_per_s` | `100` | UDP ingest rate limit |

Add `phone` to `managed_nodes` in `/etc/friday/core_hub.params.yaml` and the
supervisor reconcile loop wakes it on every boot — no bespoke autostart.
Deployment artifacts (systemd unit, gpsd config `gpsd -N udp://<iface-ip>:29998`,
hostapd profile for the field AP) live in **friday-core-os**, not this repo —
same split as the module registry service.

**Phone setup checklist.**
1. Install *GPSd Forwarder* (F-Droid) → target = Pi's IP, port `29998`.
2. Install *HyperIMU* (Play Store) → accelerometer + gyroscope, JSON over UDP,
   target = Pi's IP, port `5555`, ~50 Hz.
3. Battery settings → both apps → "Don't optimize" (or Android kills them).
4. Location mode → device-only GPS (no WiFi/cell blending).
5. Give the phone a DHCP reservation; put that IP in `phone_ip`.
6. Don't park the phone at 100% charge forever — swollen-battery risk; cap the
   charge or cycle it with a smart plug.

**Smoke test (no ROS needed).** On the Pi: `gpsd -N -D2 udp://*:29998` in one
terminal, `nc -ul 5555` in another. NMEA lines scrolling in the first and JSON in
the second proves the whole phone side works before any ROS code runs.

**If this breaks, look here.**
- *No `/mark1/phone/fix`:* is gpsd running and does `gpsdctl`/`cgps` show a fix?
  The phone needs sky view — GPS indoors is normal-fail. The node logs
  "gpsd unreachable" every 30 s if the daemon is down.
- *No `/mark1/phone/imu`:* check the phone screen — HyperIMU stopped? Battery
  optimization killed it? Then check `dropping imu_...` warnings in the node log:
  `imu_source` means the packets come from a different IP than `phone_ip`.
- *Health DEGRADED:* that's the watchdog doing its job — the detail string says
  which stream is stale (`gps`, `imu`, or both).
- *Module missing from the registry after a Core-Hub restart:* wait ≤ 60 s — the
  keep-alive re-registers on its next tick.

**Glossary.** *gpsd* — a small Linux daemon that speaks every GPS dialect and hands
apps clean JSON fixes; we feed it the phone's NMEA over UDP. *NMEA* — the ancient
text format all GPS receivers emit (`$GPGGA,...`). *Advisory sensor* — data the
rover may use to inform decisions but never to trigger safety actions. *Upsert* —
an insert-or-update write; re-registering an already-known module just refreshes
its record.
