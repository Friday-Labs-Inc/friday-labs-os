# Stage 1 — Gazebo Simulation (Walk-Through)

> 📘 **Chapter for Stage 1 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> Read [Phase 4 — Safety](Phase 4 - Safety.md) first. Until now the rover OS was
> tested in a *node sim* — the logic ran, but nothing had a body. Stage 1 gives
> Mark 1 a **physical body in a physics world**.
>
> **Status:** ✅ rover spawns level, drives straight, **corner-steers** through a
> coordinated arc staying dead level, **the real OS drives it** (an authorized
> `MotionCommand` moves the Gazebo rover and a Core death safe-stops it), it **runs
> live in the Gazebo GUI** on the Legion PC, and **a remote operator drives it through
> the signed Command Center boundary** (forged/expired/replayed commands rejected at
> the boundary). Verified headless *and* on-screen. **Branch:** `stage1/gazebo`.

---

## 1. The 30-second version

We gave Mark 1 a body in **Gazebo** (a physics simulator). It has a real chassis,
six wheels, gravity, friction, and contact, and **four corner wheels that steer**.
We can now watch it **drive, turn, and stop** — and the *same OS* that ran in the
node-sim is what's driving it. No real hardware needed yet.

Verified on Legion, headless and in the live GUI: the rover **spawns** level, **drives
1.6 m straight**, **corner-steers** through a coordinated arc (≈120° of heading,
staying flat the whole way), and **safe-stops on its own** the instant the Core
brain dies.

---

## 2. Why a physics sim, and why now

- **The interface-first promise.** The OS can't tell whether odometry came from a
  real wheel encoder or from sim physics — same `nav_msgs/Odometry` either way. A
  physics sim is how we *prove* that promise before hardware exists.
- **Autonomy needs a practice ground.** Phase 5 (self-driving) must drive — and
  crash — safely thousands of times before we risk a real rover. Stage 1 is that
  safe practice ground.

**Locked stack** (REP-2000): **ROS 2 Jazzy ↔ Gazebo Harmonic**, the `ros_gz`
bridge, and `gz_ros2_control` for the wheels. (Gazebo Classic is end-of-life —
refused.)

---

## 3. New words (glossary)

| Word | Plain meaning |
|---|---|
| **URDF / xacro** | The robot's blueprint — its links, joints, sizes, and weights. `xacro` is the blueprint with reusable macros (it does the maths for us). |
| **Gazebo Harmonic** | The physics simulator — gravity, contact, friction, the lot. |
| **Rocker-bogie** | The real rover's six-wheel layout. Here it's drawn as a rigid tube frame in the true geometry (see §5b for why we didn't articulate it). |
| **Corner / Ackermann steering** | The 4 corner wheels turn to point along the arc; the 2 middle wheels just drive. Inner wheels turn sharper than outer — like a car, not a tank. |
| **ros2_control** | The joint controllers: one feeds **6 wheel speeds**, one feeds **4 steer angles**, and one publishes joint states back. |
| **Bag (MCAP)** | The black-box recording of every message during a run — replayable later. |

---

## 4. What we built

| Piece | What it is |
|---|---|
| `friday_description` package | The rover blueprint (`mark1.urdf.xacro`), a ground **world**, the wheel + steer **controllers** (`controllers.yaml`), and two **launches** (`sim`, `sim_os`). |
| `friday_locomotion/kinematics.py` | Pure, ROS-free **corner-steer maths**: turns one `MotionCommand` `(v, ω)` into 6 wheel speeds + 4 steer angles. Unit-tested on its own. |
| `.devcontainer/Dockerfile.sim` | The sim environment (Gazebo Harmonic + `ros_gz` + `ros2_control`) — built on the farm as `friday-os:sim`, keeping the lean dev image Gazebo-free. |

The model is **measured, not guessed** — straight from the scaled-Perseverance
model (see `Mechanics/reference-models/perseverance/mark1_sim_spec.md`): 6 wheels of
**7 cm** radius, track **~0.65 m**, body **0.41 × 0.55 × 0.22 m**, total **~10.5 kg**.

---

## 5. Walk-through

### 5a. From blueprint to a standing robot
The launch turns the `xacro` blueprint into a URDF, starts Gazebo with the ground
world, **spawns** the rover, then loads the controllers. Under gravity it settles
onto its six wheels. Real trace: settled body height **z = 0.070 m**, identical 3 s
later — *stable*, not sinking or bouncing, and **dead level** (roll/pitch ≈ 0).

### 5b. The suspension story (and why the chassis is rigid)
This is the honest version, because it took three tries:

1. **Rigid first-light** — a plain box on six wheels, to prove the whole pipeline
   (spawn → stand → drive → record) with the fewest moving parts.
2. **Articulated rocker-bogie** — we then swapped in the real passive linkage (rocker
   + bogie arms, no motors, no springs). It *did* self-level on flat ground… but on
   **any turn it tipped over**: skid-steering a tall, articulated body with no
   cross-body differential is genuinely unstable. (We also caught the arms collapsing
   to their joint limit and pitching the body 21–39° — fixed, but the turn instability
   remained.)
3. **Rigid chassis + corner steering (current)** — we rebuilt it: a rigid body that
   *draws* the rocker-bogie arms as a tube frame in the true geometry, with **all six
   wheels planted on the ground** and **four corner wheels that steer**. It drives and
   turns rock-steady and level. The passive linkage is a later refinement; coordinated
   steering is what a research rover actually needs first.

### 5c. Driving + steering
Two controllers move the rover:
- **`wheel_velocity_controller`** — 6 wheel speeds (rad/s).
- **`steer_position_controller`** — 4 corner steer angles (rad, limit ±0.6).

The maths lives in **`kinematics.drive_and_steer(v, ω)`**: each wheel's ground
velocity in the body frame is `(v − ω·y, ω·x)` — a corner wheel points along that
vector and rolls at its speed; a middle wheel rolls only the forward part. So on a
turn the **inner wheels steer sharper and roll slower than the outer** (true
coordinated steering), and a straight command is just "all six at `v/r`, steer zero".
Real trace: 1.6 m straight, then a left arc sweeping ≈120° of heading — body flat the
whole way.

### 5d. The real OS driving the physics rover (`sim_os.launch.py`)
The whole point of interface-first: the **same OS** runs the node-sim *and* the
physics rover. `sim_os.launch.py` brings up the physics layer **plus** the real
**Core Hub** (authority lease + safety pulse + lifecycle supervisor) and the real
**Locomotion agent**. The Locomotion agent keeps every bit of its Phase 4 logic — it
obeys a `MotionCommand` only from the authority holder, runs the safe-stop watchdog —
and then runs the *same* `kinematics.drive_and_steer` and publishes the result to the
two controllers. So:

```
ACCEPT motion src=MARK1-CORE-001 nonce=1 v=0.30   →  physics rover drives 0 → 1.60 m straight
# send a turn → coordinated corner-steer arc to yaw ≈120°, dead level
# kill the Core →
SAFE-STOP entered: safety pulse lost (606 ms)     →  rover halts, pose frozen 3 s later
```

An *authorized* command moves the physical body; the instant the brain (Core) dies,
the watchdog stops it. Phase 4 safety, proven against physics — not just logic.

> **About that 606 ms.** The **100 ms** safe-stop is the *hardware* spec — a firmware
> watchdog on a dedicated serial link, validated in HIL. In sim the pulse rides DDS on
> a CPU shared with the physics engine, so it jitters; we expose `safe_stop_timeout_s`
> as a param and loosen it to **0.6 s** in `sim_os` so CPU jitter isn't mistaken for a
> real pulse loss. The *logic* is identical — only the sim's tolerance is relaxed.

### 5e. Watching it live (Gazebo GUI on Legion)
The headless run proves correctness; the GUI is for seeing it. The sim runs in a
container on the Legion PC with the GPU and X display passed in, so a Gazebo window
opens on the physical screen and you watch the OS-driven rover drive, corner-steer,
and freeze on a Core kill in real time.

> ⚠️ **Run the sim in the *native* Docker daemon, not Docker Desktop.** Docker Desktop
> runs in a CPU-throttled VM with no GPU — Gazebo there crawls at **~6 % real-time**
> (the rover barely moves and the safety pulse arrives gappy, so a *working* sim looks
> broken). Use `sudo docker -H unix:///var/run/docker.sock …` for both headless and
> GUI runs → real-time physics, steady pulse, GPU render.

### 5f. The full Command Center boundary in sim (`sim_cc.launch.py`)
The last link: a *remote operator* driving the physics rover through the real
security boundary. `sim_cc.launch.py` adds the Phase 3 **Telemetry agent** (the
signed-CBOR-over-MQTT Command Center boundary) next to Core + Locomotion. The chain:

```
operator signs a MotionCommand (Ed25519)  →  publish to mark1/MARK1-001/cmd/motion on the broker
  →  Telemetry VALIDATES (signature + allowlist + monotonic nonce + expiry + rover_id)
  →  re-issues it AS the authority holder (MARK1-CORE-001) on /mark1/locomotion/cmd_motion
  →  Locomotion accepts  →  physics rover drives.  Telemetry ACKs every command.
```

Verified against a real MQTT broker (4 commands, one operator):

| Command | Operator ACK | Rover |
|---|---|---|
| **valid** v=0.3 | `accepted: True, OK` | drove **0 → 2.19 m** |
| **forged** (payload tampered after signing) | `accepted: False, SECURITY_AUTH` | no motion |
| **expired** | `accepted: False, EXPIRED` | no motion |
| **replay** (reused nonce) | `accepted: False, SECURITY_REPLAY` | no motion |

So a *signed, fresh, allowlisted* command moves the rover; a forged, stale, or
replayed one is rejected at the boundary and **never reaches the wheels**. The OS
can't tell this command came from sim physics rather than a real radio — that's the
interface-first promise, end to end.

**And the return path is signed too.** The rover signs its outbound telemetry with
its *own* key (`rover_key_file`), so the operator can prove the data came from *this*
rover — a spoofed position or a faked "all-clear" is rejected. It bridges odometry
(downsampled to `telemetry_rate_hz`, default 2 Hz), fault reports, and the command
ACK to `mark1/<rover>/tlm/*` as signed envelopes. Verified on Legion: an independent
subscriber checked **66 odom + 2 ack + 1 fault — all signature-valid, zero bad** —
and a **tampered odometry message failed verification** (the signature binds the
data). Both directions of the boundary are now authenticated. (The matching operator side — the live
[Friday Command Center](Friday Labs OS Software Manual.md) console + its
mutual-TLS EMQX broker — is the remaining hook-up: `sim_cc` takes `mqtt_tls:=true`
+ ca/cert/key and a real operator key for that.)

---

## 6. Decisions & why

| Decision | Why |
|---|---|
| **Rigid first-light, then iterate** | Prove the whole pipeline with the fewest moving parts before adding suspension or steering. Fewer variables when something breaks. |
| **Rigid chassis + corner steering over articulated rocker-bogie** | The articulated body tipped on every turn (skid steer + no differential = unstable). A research rover needs *coordinated steering* first; the passive linkage is a later refinement. The frame still draws the rocker-bogie geometry. |
| **Pure `kinematics.py`, ROS-free** | The corner-steer maths is the easy thing to get wrong, so it's isolated and unit-tested away from ROS/Gazebo. |
| **Safe-stop timeout as a param (0.1 s HW / 0.6 s sim)** | The 100 ms hardware watchdog can't be met by a DDS pulse on a physics-loaded CPU; loosen *only the sim's tolerance*, keep the logic identical. |
| **Native Docker, not Docker Desktop, for sim** | Docker Desktop's VM has no GPU and throttles the CPU → ~6 % real-time. Native daemon gives real-time physics + GPU render. |
| **Separate `friday-os:sim` image** | Gazebo is ~GBs; keep the everyday dev image lean and add sim weight only where it's needed. |

---

## 7. Run it yourself

```bash
# on the sim image (friday-os:sim), in the workspace:
colcon build --packages-select friday_description friday_locomotion && source install/setup.bash

# A) physics + controllers only (drive it by hand):
ros2 launch friday_description sim.launch.py            # headless; headless:=false for GUI
ros2 topic pub -r 10 /wheel_velocity_controller/commands std_msgs/msg/Float64MultiArray \
  "{data: [4.3, 4.3, 4.3, 4.3, 4.3, 4.3]}"             # ~0.3 m/s straight

# B) the REAL OS driving it (Core + Locomotion):
ros2 launch friday_description sim_os.launch.py         # headless:=false for the GUI
ros2 topic pub -r 10 --qos-durability transient_local /mark1/locomotion/cmd_motion \
  friday_msgs/msg/MotionCommand \
  "{type: 1, linear_velocity: 0.25, angular_velocity: 0.35, source: MARK1-CORE-001, nonce: 1}"
```

> On Legion, prefix the `docker run` with `sudo -H unix:///var/run/docker.sock` (native
> daemon) — see the §5e warning.

---

## 8. Verification (on Legion)

| Check | Result |
|---|---|
| `colcon build` on `friday-os:sim` (Gazebo Harmonic 8.x) | clean |
| `kinematics` unit tests (straight / reverse / L+R turn / steer clamp) | ✅ pass (no ROS, no sim) |
| Spawns in Gazebo, settles **level** | `Model: mark1`, z = 0.070 m, roll/pitch ≈ 0, all 6 wheels grounded |
| Drives on command | **1.6 m** straight, body flat |
| **Corner-steers** | left arc to yaw **≈120°**, flat throughout — no tilt, no lifted wheel, no tip |
| **Real OS drives physics** (`sim_os.launch.py`) | `ACCEPT motion` (MARK1-CORE-001) → rover drives + arcs via the OS |
| **Safe-stop vs physics** | killed Core → **SAFE-STOP** (sim tolerance 0.6 s), rover halted, pose frozen 3 s later |
| **Live GUI** | Gazebo window on the Legion screen; drive + corner-steer + safe-stop watched in real time |
| **Command Center boundary** (`sim_cc.launch.py`) | signed command over a real MQTT broker → rover drove **2.19 m**; forged / expired / replay all **rejected**, no motion, each ACKed with its category |
| **Signed telemetry return path** | rover-signed odom/fault/ack verified by an independent subscriber — **66 odom + 2 ack + 1 fault, 0 bad**; tampered odom **rejected** |

---

## 9. What is intentionally NOT done yet

- ~~**Live GUI view**~~ — ✅ **Done**: runs on the Legion screen via the native Docker
  daemon (GPU + X passed in).
- ~~**The real OS path in sim**~~ — ✅ **Done** (`sim_os.launch.py`): the real Core
  Hub + Locomotion agent drive the physics rover; an authorized `MotionCommand` moves
  it and a Core death safe-stops it.
- **Passive rocker-bogie articulation** — deferred (it was unstable in turns; revisit
  with a cross-body differential + corner steering combined).
- **Cross-body differential** — a *closed kinematic loop*; URDF is a tree. Noted, not hidden.
- ~~**Telemetry → Command Center boundary into sim**~~ — ✅ **Done** (`sim_cc.launch.py`):
  a signed command over a real MQTT broker drives the rover; forged/expired/replay are
  rejected at the boundary. **Remaining:** connect to the *live* Command Center broker
  (mutual-TLS EMQX) with a real enrolled operator key — needs the FCC side to grant the
  rover an ACL rule + client cert (`mqtt_tls:=true` + ca/cert/key is already wired).
- **Uneven-terrain stress with the new model** — re-run the ridge/rock traverse on the
  rigid corner-steer chassis.
- **Sensors** (Stage 4: LiDAR/camera/IMU) and **Spark** (Stage 6) — later stages.

---

## 10. Where this goes next

- Connect `sim_cc` to the **live Command Center** broker (mutual-TLS EMQX) and drive
  the sim rover from the real operator console — the boundary + `mqtt_tls` params are
  done; it needs the FCC side to grant the rover an ACL rule + client cert + a real
  enrolled operator key.
- Re-run the **bumpy-terrain** traverse on the corner-steer chassis.
- Then **Stage 2+** of the sim-bringup procedure (lifecycle agents → closed loop →
  sensing → fault injection → Spark → headless CI).

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 4 — Safety](Phase 4 - Safety.md) ·
[Mark 1 sim build sheet](../../Mechanics/reference-models/perseverance/mark1_sim_spec.md) ·
[Mark 1 Index](../Mark 1 Index.md)
