# Legion handoff — Mark 1 Stage 1 (Gazebo)

You are Claude Code running on the Legion PC (Ubuntu 26.04, GNOME/Wayland, AMD
iGPU `card1` + NVIDIA RTX 3070 `card2`). Legion is **both** the build farm and the
day-to-day dev box now — the Mac can't run the ROS toolchain.

**Repo:** `~/friday-ws/friday-labs-os`, branch **`stage1/gazebo`** (HEAD as of this
write-up: `d51de76 harden(telemetry): security-review fixes`).
**Full project memory:** `~/.claude/projects/-home-friday-friday-ws-friday-labs-os/memory/MEMORY.md`.

## Where Stage 1 stands today

All headless **and** verified live in the Gazebo GUI on this screen:

- **Rover model** — rigid chassis + Ackermann **corner steering** (4 corner wheels
  steer, 2 middle drive-only); spawns level z=0.070, all six wheels grounded.
  The articulated rocker-bogie was tried and removed: it tipped on every turn
  (skid-steer + no cross-body differential = unstable). The frame still *draws*
  the rocker-bogie geometry as a tube frame. See `src/friday_description/urdf/
  mark1.urdf.xacro` and the pure `src/friday_locomotion/.../kinematics.py`.
- **Real OS drives physics** (`sim_os.launch.py`) — Core Hub + Locomotion +
  corner-steer kinematics. An authorized `MotionCommand` drives the rover (1.6 m
  straight, ~120° coordinated arc, dead level) and **killing Core safe-stops it**.
- **Command Center boundary in sim** (`sim_cc.launch.py`) — adds the Telemetry
  agent. An operator-signed `MotionCommand` over a real MQTT broker → validated
  (Ed25519 + allowlist + nonce + expiry + rover_id) → re-issued as the authority
  holder → rover drives. Forged / expired / replayed commands are rejected at the
  boundary and never reach the wheels, each ACKed with its category.
- **Signed return path** — the rover signs its outbound odom (downsampled to
  `telemetry_rate_hz`, default 2 Hz), faults, and ACKs to `mark1/<rover>/tlm/*`.
  Independent verifier on Legion checked **66 odom + 2 ack + 1 fault, 0 bad**;
  a **tampered odometry message was rejected**. Both directions authenticated.
- **Wire-contract drift guard** — `src/friday_telemetry/test/test_protocol_golden.py`
  pins a deterministic golden vector (fixed seed, fixed envelope → exact
  `_signing_bytes` + Ed25519 signature hex). The FCC repo asserts the same
  constants — either side drifting goes red in CI.
- **Tests green:** 54 across friday_telemetry / friday_module_agent / friday_locomotion.

## Critical: use NATIVE Docker, not Docker Desktop

The single biggest footgun on this machine. Two daemons coexist:

| Context | Daemon | Verdict |
|---|---|---|
| `desktop-linux` (default) | Docker Desktop VM | **DO NOT USE for sim.** No GPU, throttled CPU → Gazebo runs at **~6 % real-time**, the safety pulse jitters → a *working* sim looks broken (commands accepted but "no motion", false safe-stop trips). Hours wasted on this. |
| native | `/var/run/docker.sock` | The one to use. Real-time physics, steady pulse, GPU render on `card1`. User `friday` is in the `docker` group; passwordless `sudo -n` works. |

Always run sim containers with: `sudo -n docker -H unix:///var/run/docker.sock …`

GUI also needs: `-e DISPLAY=:0 -e XAUTHORITY=/tmp/xauth -v /run/user/1000/.mutter-Xwaylandauth.*:/tmp/xauth:ro --device /dev/dri`. The image `friday-os:sim` was copied into the native daemon via `docker save | docker load`.

## How to run

**Build.** Both daemons see the same workspace mount; build in either, but run sim in native:

```bash
sudo -n docker -H unix:///var/run/docker.sock run --rm \
  -v ~/friday-ws/friday-labs-os:/ws friday-os:sim bash -lc \
  'source /opt/ros/jazzy/setup.bash && cd /ws && colcon build'
```

**Tier 1 — physics + controllers only** (`sim.launch.py`). For hand-driving the
wheels via the controllers. Headless by default.

**Tier 2 — real OS drives physics** (`sim_os.launch.py`). Adds Core + Locomotion;
send a `MotionCommand` on `/mark1/locomotion/cmd_motion` and the rover drives.
Param `safe_stop_timeout_s` defaults to 0.6 s in `sim_os` (HW spec is 0.1 s; the
sim loosens it because DDS pulse on a physics-loaded CPU jitters past 100 ms —
not a real safety event).

**Tier 3 — full Command Center boundary** (`sim_cc.launch.py`). Adds the
Telemetry agent. The headless e2e you'll re-run most often:

```bash
S=unix:///var/run/docker.sock
# 1) test broker (NOT the live FCC broker)
sudo -n docker -H $S rm -f fl_test_broker >/dev/null 2>&1
printf 'listener 1893 0.0.0.0\nallow_anonymous true\n' > ~/_cc/mosquitto.conf
sudo -n docker -H $S run -d --name fl_test_broker --network host \
  -v ~/_cc/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro eclipse-mosquitto:2

# 2) provision an operator + a rover key, launch sim_cc, send a signed command
mkdir -p ~/_cc_out
sudo -n docker -H $S run --rm --network host \
  -v ~/friday-ws/friday-labs-os:/ws -v ~/_cc_out:/out friday-os:sim bash -lc '
    source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; cd /ws
    ros2 run friday_telemetry mock_command_center provision \
      --operator-id OP-001 --key-file /out/op.key --allowlist /out/operators.json
    python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as K; \
      p=K.generate(); open(\"/out/rover.key\",\"w\").write(p.private_bytes_raw().hex()); \
      open(\"/out/rover.pub\",\"w\").write(p.public_key().public_bytes_raw().hex())"
    ros2 launch friday_description sim_cc.launch.py headless:=true \
      mqtt_port:=1893 operators_file:=/out/operators.json \
      rover_key_file:=/out/rover.key telemetry_rate_hz:=5.0 &
    sleep 28
    ros2 run friday_telemetry mock_command_center send --rover MARK1-001 \
      --host 127.0.0.1 --port 1893 --operator-id OP-001 --key-file /out/op.key \
      --nonce 1 --linear 0.3 --mode valid'
```

**GUI on the Legion screen.** Add `headless:=false` to any launch, and the docker
flags above (DISPLAY/XAUTHORITY/dri). Detached `--name friday_sim` so you can
`exec ... gz model -m mark1 -p` to read pose while it runs.

## Memory: how the comms layer is wired (don't re-derive)

- **Wire envelope** (signed, replay-resistant): `src/friday_telemetry/.../protocol.py`
  — Ed25519 / CBOR, monotonic nonce (rejects `nonce <= last`, gaps OK), 30 s expiry,
  rover_id binding. Mirror byte-identical on the FCC side at `bridge/envelope.py`.
- **NonceStore** has an internal lock now (security-review fix `d51de76`) — every
  agent shares this, so don't add another concurrency layer on top.
- **Authority Lease Protocol** (Phase 4): Core publishes lease + 20 Hz safety
  pulse; Locomotion obeys only the holder and runs the safe-stop watchdog;
  Telemetry self-promotes on Core loss and hands back cleanly.

## Two-OS architecture (decided 2026-07-01)

Mark 1 now runs **two distinct OS images** — see `docs/architecture/Mark 1 Compute Architecture.md`:

| Image | Repo | Target hardware | Stack |
|-------|------|-----------------|-------|
| **`friday-core-os`** | [Friday-Labs-Inc/friday-core-os](https://github.com/Friday-Labs-Inc/friday-core-os) | Pi 4B 8 GB | Ubuntu 24.04 + ROS 2 Jazzy + Friday Labs OS |
| **`friday-telemetry-os`** | [Friday-Labs-Inc/friday-telemetry-os](https://github.com/Friday-Labs-Inc/friday-telemetry-os) | Pi 3B+ 1 GB | Debian 12 Lite — no ROS 2, pure network gateway |

**Internal bridge:** Core Hub runs `mosquitto` on `10.0.1.1:1883` (Ethernet);
Telemetry Gateway connects at `10.0.1.2`, relays signed CBOR envelopes to the
external EMQX over 4G/LoRa/Wi-Fi. No DDS crosses that boundary.

**Safe-stop is independent:** Locomotion ESP32 watchdog fires in 100 ms when the
authority pulse stops — neither Pi needs to be alive for safe-stop.

## Hardware inventory (actual, corrected 2026-07-01)

| Board | Spec | Role |
|-------|------|------|
| Pi 4B 8 GB | owned | Core Hub (`friday-core-os`) |
| Pi 3B+ 1 GB | owned | Telemetry Gateway (`friday-telemetry-os`) |
| 4× ESP32-WROOM-32 | owned | 1× Mobility Hub + 3 spare |
| 2× 4G USB dongles | owned | Telemetry Gateway (dual-carrier) |

**BOM to order: ~₹30,355** — see `docs/build/MK1_Electronics_BOM.md`.

## Open items (genuinely blocked on the FCC side)

1. **Live FCC broker hookup** — `sim_cc` already takes `mqtt_tls:=true` +
   `mqtt_ca/cert/key/client_id`. Needs the FCC session to: bring `fcc-emqx` up
   (mTLS :8883), add ACL for **CN=MARK1-001** (SUB `mark1/MARK1-001/cmd/+`,
   PUB `mark1/MARK1-001/ack/#` and `mark1/MARK1-001/tlm/#`), hand over the
   cert + key + CA, and **register the rover's signing public key** so it can
   verify telemetry. ACK is now a signed envelope, not plain CBOR — their
   consumer needs to unwrap.
2. **Operator allowlist refresh on revocation** — confirmed gap (allowlist is
   loaded once in `configure_hardware`, never refreshed; a revoked operator
   keeps working until the node restarts). Fix is small (reload on MQTT
   reconnect + optional `mark1/<rover>/revoke` subscription) but needs the FCC
   to tell us what signal they emit: forced reconnect, `revoke` topic, or
   epoch re-pull. Wait, then wire the matching receiver.
3. **Bumpy-terrain stress with the new model** — re-run the ridge/rock traverse
   on the rigid corner-steer chassis (the old bumpy test was on the articulated
   model that got rebuilt).

## Open items (hardware bring-up)

4. **ICD revision** — Drive-deck pin map needs updating for built-in encoders
   (PCA9685 + PCNT, drop AS5600/TCA9548A). PCA9685/INA219 I2C address collision
   (both default 0x40) — re-strap one before they share the bus.
5. **Electronics Backbone.md** — still says 14.8 V / Pi 5; needs updating to
   12 V / Pi 4B + Pi 3B+.
6. **Core Hub bring-up on Pi 4B** — flash `friday-core-os`, build ROS 2 workspace,
   run Friday Labs OS.
7. **Telemetry Gateway bring-up on Pi 3B+** — flash `friday-telemetry-os`, plug
   dual 4G dongles, test MQTT relay to CC.

## Conventions

- **Plain-English first** — user is self-taught; lead with a simple summary,
  jargon supports.
- **Per-phase walk-through docs** in `docs/software/` (8th-grade readable +
  glossary + "if this breaks, look here"); document a phase in the SAME PR.
- **Tight diffs** (every line traces to the request); no scope creep.
- **One question at a time** with a recommended option, only for real decisions.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Don't touch the FCC repo or `fcc-emqx`** from the rover session — they're the
  Command Center session's. Coordinate via cross-session messages.
