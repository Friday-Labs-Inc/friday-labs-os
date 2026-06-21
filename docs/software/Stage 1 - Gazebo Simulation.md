# Stage 1 — Gazebo Simulation (Walk-Through)

> 📘 **Chapter for Stage 1 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> Read [Phase 4 — Safety](Phase 4 - Safety.md) first. Until now the rover OS was
> tested in a *node sim* — the logic ran, but nothing had a body. Stage 1 gives
> Mark 1 a **physical body in a physics world**.
>
> **Status:** ✅ rover spawns, **self-levels** on its rocker-bogie, drives in
> physics, **traverses bumpy terrain** (over ridges + a rock, staying upright),
> **and the real OS drives it** — an authorized `MotionCommand` moves the Gazebo
> rover and a Core death safe-stops it at ~107 ms (Phase 4 against physics).
> Verified on Legion. **Branch:** `stage1/gazebo`. A live GUI view is the open item.

---

## 1. The 30-second version

We gave Mark 1 a body in **Gazebo** (a physics simulator). It has a real chassis,
six wheels, the rocker-bogie suspension, gravity, friction, and contact. We can now
watch it **stand up, drive, and (next) climb** — and **record everything** it does
to a file we can replay. No real hardware needed yet.

Verified on Legion: the rover **spawns**, **settles and stands** stably (body at a
steady height, not sinking or wobbling), **drives** a straight 1.9 m on command,
and a **10k-message recording** captures the whole run.

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
| **URDF / xacro** | The robot's blueprint — its links, joints, sizes, and weights. `xacro` is the blueprint with reusable macros. |
| **Gazebo Harmonic** | The physics simulator — gravity, contact, friction, the lot. |
| **Rocker-bogie** | The six-wheel **passive** suspension (two arms per side) that keeps all wheels on the ground over bumps. |
| **ros2_control / diff_drive** | The wheel controller: takes a speed command, spins the wheels, and reports odometry. |
| **Bag (MCAP)** | The black-box recording of every message during a run — replayable later. |

---

## 4. What we built

| Piece | What it is |
|---|---|
| `friday_description` package | The rover blueprint (URDF), a ground **world**, the wheel **controllers**, and a **launch**. |
| `.devcontainer/Dockerfile.sim` | The sim environment (Gazebo Harmonic + `ros_gz` + `ros2_control`) — built on the farm as `friday-os:sim`, keeping the lean dev image Gazebo-free. |

The model is **measured, not guessed** — straight from the scaled-Perseverance
model (see `Mechanics/reference-models/perseverance/mark1_sim_spec.md`): 6 wheels of
**7 cm** radius, track **0.72 m**, body **0.41 × 0.55 × 0.22 m**, total **~10.5 kg**.

---

## 5. Walk-through

### 5a. From blueprint to a standing robot
The launch turns the `xacro` blueprint into a URDF, starts headless Gazebo with the
ground world, **spawns** the rover, then loads the controllers. Under gravity the
rover drops a few cm and **settles** onto its wheels. Real trace: settled body
height **z = 0.097 m**, and identical 3 s later — *stable*, not sinking or bouncing.

### 5b. The rocker-bogie (why it's not just six wheels on a box)
The suspension is the real passive linkage, per side:
```
base_link → rocker (front wheel) → bogie (mid wheel + rear wheel)
```
The rocker and bogie are **passive** revolute joints (damped, limited) — no motors,
no springs. Like the real rover, they level by **geometry + gravity**: when one
wheel rides up a rock, the arms rotate so the others stay planted and the body stays
flatter than a rigid chassis would. (First-light started rigid to prove the pipeline;
then we swapped in the articulated linkage.)

### 5c. Driving + recording
The six wheels are velocity-driven by `diff_drive_controller` in **skid steer** —
the 3 left wheels share one speed, the 3 right another. Send a `Twist` (a speed +
turn) and it drives; it publishes `odom` back. A `ros2 bag` records the whole run to
MCAP. Real trace: commanded 0.3 m/s → odom **0 → 1.90 m** straight, body stayed
upright (z unchanged), **11,294 messages** captured.

### 5d. The real OS driving the physics rover (`sim_os.launch.py`)
The whole point of interface-first: the **same OS** runs the node-sim *and* the
physics rover. `sim_os.launch.py` brings up the physics layer **plus** the real
**Core Hub** (authority lease + safety pulse + lifecycle supervisor) and the real
**Locomotion agent**. The Locomotion agent keeps all its Phase 4 logic — it obeys a
`MotionCommand` only from the authority holder, and runs the safe-stop watchdog —
and a `wheel_cmd_topic` param makes its accepted, safe-stop-gated `(v, w)` flow to
the wheels. So:

```
ACCEPT motion src=MARK1-CORE-001 nonce=1 v=0.30   →  physics rover drives -0.08 → 1.56 m
# kill the Core →
SAFE-STOP entered: safety pulse lost (107 ms)     →  rover halts at 1.65 m, frozen 3 s later
```

An *authorized* command moves the physical body; the instant the brain (Core) dies,
the watchdog stops it. Phase 4 safety, proven against physics — not just logic.

---

## 6. Decisions & why

| Decision | Why |
|---|---|
| **Rigid first-light, then articulate** | Prove the whole pipeline (spawn → stand → drive → record) with the fewest moving parts, *then* add the suspension. Fewer variables when something breaks. |
| **Passive rocker-bogie (no springs)** | Faithful to the real rover — it levels by geometry + gravity. |
| **Cross-body differential omitted (for now)** | The differential bar is a *closed kinematic loop*; URDF is a tree. On flat ground the body settles level; on rough ground it rolls a touch more than the real coupled rover. Noted, not hidden. |
| **Separate `friday-os:sim` image** | Gazebo is ~GBs; keep the everyday dev image lean and add sim weight only where it's needed. |
| **diff_drive skid steer** | Maps directly onto the unicycle `MotionCommand` (v, ω) the OS already speaks. |

---

## 7. Run it yourself

```bash
# on the sim image (friday-os:sim), in the workspace:
colcon build --packages-select friday_description && source install/setup.bash
ros2 launch friday_description sim.launch.py        # headless Gazebo + rover + control

# drive it (separate shell):
ros2 topic pub -r 20 /diff_drive_controller/cmd_vel geometry_msgs/msg/TwistStamped \
  "{twist: {linear: {x: 0.3}}}"

# record a run:
ros2 bag record -s mcap -o run /clock /joint_states /diff_drive_controller/odom /tf
```

---

## 8. Verification (on Legion)

| Check | Result |
|---|---|
| `check_urdf` parses the articulated tree | base → rocker → {front, bogie → {mid, rear}} ×2 ✅ |
| `colcon build` on `friday-os:sim` (Gazebo Harmonic 8.x) | clean |
| Spawns in Gazebo | `Model: mark1` present |
| Settles & **self-levels** | z = 0.070 m, **roll/pitch ≈ 0** (rocker pivot raised above the body CoM) |
| Drives on command | odom 0 → **1.90 m** straight; stays upright |
| **Bumpy terrain** | drove **6.1 m** over 2 ridges + an offset rock; upright throughout (max tilt ~3°); no flip / stall / joint runaway |
| Data collection | MCAP bag, **11,294** (flat) / **25,720** (bumpy) messages |
| **Real OS drives physics** (`sim_os.launch.py`) | authorized `MotionCommand` (MARK1-CORE-001) → rover moved 1.6 m |
| **Safe-stop vs physics** | killed Core → **SAFE-STOP at 107 ms**, rover halted (pose frozen 3 s later) |

---

## 9. What is intentionally NOT done yet

- ~~**Uneven-terrain stress**~~ — ✅ **Done**: the rover self-levels (the rocker
  pivot was raised above the body CoM) and drove **6.1 m over two ridges + an offset
  rock**, staying upright (max tilt ~3°), no flip/stall. (Found + fixed a bug where
  the passive arms collapsed to their limit, pitching the body ~21–39°.)
- **Live GUI view** — the headless sim is fully verified; opening the Gazebo *window*
  on a real screen (through Docker Desktop + Wayland) is being handled on the Legion PC.
- **Command-topic name** — the wheels currently listen on
  `/diff_drive_controller/cmd_vel`; rename/route to `/mark1/locomotion/cmd_vel`.
- ~~**The real OS path in sim**~~ — ✅ **Done** (`sim_os.launch.py`): the real Core
  Hub + Locomotion agent drive the physics rover; an authorized `MotionCommand`
  moves it and a Core death safe-stops it at 107 ms. (Next: route the full chain
  through the Telemetry Command Center boundary into sim.)
- **Sensors** (Stage 4: LiDAR/camera/IMU) and **Spark** (Stage 6) — later stages.

---

## 10. Where this goes next

- **Live GUI** on a screen (in progress on the Legion PC), and route the full command
  chain through the Telemetry Command Center boundary into sim.
- Then **Stage 2+** of the sim-bringup procedure (lifecycle agents → closed loop →
  sensing → fault injection → Spark → headless CI).

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 4 — Safety](Phase 4 - Safety.md) ·
[Mark 1 sim build sheet](../../Mechanics/reference-models/perseverance/mark1_sim_spec.md) ·
[Mark 1 Index](../Mark 1 Index.md)
