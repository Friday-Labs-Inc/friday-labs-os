# Phase 2 — The Walking Skeleton (Walk-Through)

> The first **running** software of Friday Labs OS. This doc is written so you
> can **trace it, run it, and debug it** even if you're new to ROS 2 — plain
> language first, details second. Read it top to bottom.
>
> **Status:** ✅ Complete & verified · **Branch:** `phase2/walking-skeleton` ·
> **Date:** 2026-06-20 · **Bring-up stage:** Stage 2 (lifecycle orchestration)

---

## 1. The 30-second version

We built the **smallest complete version of the rover's brain that actually
runs** — the *skeleton* that every future part bolts onto.

Two programs talk to each other:

- **Core Hub** — the boss. It keeps a list of every part of the rover, turns
  each part on in the right order, and listens for each part's "I'm alive" beep.
- **Locomotion agent** — one part (the wheels' brain, for now just a stub). It
  signs in with the boss, then beeps "I'm alive" 5 times a second.

No motors spin yet. That's on purpose. We proved the **skeleton works** first;
muscles come later.

> **Walking skeleton** = a tiny end-to-end build that exercises the *whole*
> architecture, so the risky parts are proven before we add features. (Term
> from Alistair Cockburn.) It's the opposite of building one finished corner and
> hoping the rest connects.

---

## 2. Why we did this first (the methodology)

The dossier rule is **"build the shared language first, behavior second"** — the
same way the professional ROS 2 navigation stack (Nav2) is built.

1. If the parts can't **find each other**, **start up in order**, and **notice
   when one dies**, nothing else matters. So we prove *that* first.
2. Everything else (motors, sensors, missions) then becomes "fill in the blank"
   on a spine we already trust.
3. It's **Stage 2** of the seven-stage sim bring-up (lifecycle orchestration).
   We skipped Stage 1 (the Gazebo 3-D model) on purpose — you don't need physics
   to prove the spine.

**Design principle:** *de-risk the architecture before adding features.*

---

## 3. Words you need (glossary)

| Word | In plain terms |
|---|---|
| **Node** | One running program in ROS 2 (e.g. `core_hub`). |
| **Topic** | A radio channel programs broadcast on. Anyone can listen. (Used for the heartbeat.) |
| **Service** | A phone call: one program asks, the other answers once. (Used for sign-in.) |
| **Message** | The shape of the data sent (defined in `friday_msgs`). |
| **Lifecycle node** | A node that can be told *configure → activate → deactivate*, instead of just running. Like an appliance with a proper power-on sequence. |
| **Registry** | The boss's phone book of all the parts. |
| **Heartbeat** | A tiny "I'm alive" message a part sends 5×/second. |
| **QoS** | "Quality of Service" — the *delivery rules* for a message (like postage class: registered mail vs. a postcard). |
| **Namespace** | A folder for a part's channels, e.g. `/mark1/locomotion/...`. |

---

## 4. The architecture (one picture)

```
            ┌──────────────────  CORE HUB  (node: core_hub)  ──────────────────┐
            │                                                                   │
            │   registry            health monitor           supervisor         │
            │   (who's here?)       (who's still alive?)      (turn parts on)    │
            └──▲───────────────────────▲───────────────────────────┬───────────┘
               │ 1. sign in            │ 3. heartbeat 5 Hz          │ 0. "configure,
               │   (service call)      │    (topic, best-effort)    │     then activate"
               │                       │                            │   (lifecycle service)
            ┌──┴───────────────────────┴────────────────────────────▼──────────┐
            │     LOCOMOTION AGENT  (node: locomotion)                          │
            │     a LifecycleNode that subclasses ModuleAgent                   │
            └───────────────────────────────────────────────────────────────────┘

        Everyone speaks the same language:  friday_msgs  (the shared message set)
```

**Design principle:** *one shared language (`friday_msgs`), one boss, many
identical-shaped parts.* Because every part is built from the same `ModuleAgent`
base, adding the next part (Telemetry, Research, Aerial Bay) is mostly copy +
rename.

---

## 5. What's in the box (the four packages)

A ROS 2 "workspace" is a folder of small projects called **packages**. Ours live
in `src/`:

| Package | What it is | Key files |
|---|---|---|
| **`friday_msgs`** | The shared language — the message/service shapes. Nothing runs without it. | `msg/*.msg`, `srv/RegisterModule.srv` |
| **`friday_module_agent`** | The reusable **part template** (`ModuleAgent`) + the delivery rules (`qos.py`). Every part inherits this. | `module_agent.py`, `qos.py`, `protocol.py` |
| **`friday_core_hub`** | The **boss**: registry + health monitor + supervisor. | `core_hub_node.py`, `registry.py`, `launch/walking_skeleton.launch.py` |
| **`friday_locomotion`** | The first **part** (wheels' brain, stub). Proves the template works. | `locomotion_agent_node.py` |

> Notice how small `friday_locomotion` is — that's the payoff of the template.
> The whole "be a proper rover part" behavior lives in `ModuleAgent`; the
> Locomotion file just says *who it is*.

---

## 6. Walk-through: exactly what happens when you run it

This is the real log from the verified run, line by line. Times are seconds from
start.

```
t=0.0  core_hub: Core Hub up — registry + health monitor + supervisor
t=3.0  core_hub: supervisor bringing up: ['locomotion']
t=3.0  core_hub: supervisor: locomotion -> configure
t=3.0  locomotion: [MARK1-LOCO-001] configuring
t=3.0  core_hub: supervisor: locomotion configure OK
t=3.0  core_hub: registered MARK1-LOCO-001 (locomotion) -> /mark1/locomotion caps=[drive, steer, safe_stop]
t=3.0  core_hub: monitoring heartbeat on /mark1/locomotion/heartbeat
t=3.0  core_hub: supervisor: locomotion -> activate
t=3.0  locomotion: [MARK1-LOCO-001] registered -> namespace /mark1/locomotion
t=3.0  core_hub: supervisor: locomotion activate OK
t=3.0  core_hub: supervisor: managed nodes ACTIVE — bring-up complete
```

What each step *means*:

1. **t=0 — Boss wakes up.** `core_hub` opens its sign-in phone line
   (`/mark1/system/register_module`) and arms a 3-second timer before it starts
   turning parts on. (The delay just gives the parts a moment to launch.)
2. **t=3 — Supervisor starts the line-up.** It reads its `managed_nodes` list
   (`['locomotion']`) and decides to bring each one up: first *configure*, then
   *activate*. This is the Nav2 pattern — a deterministic, ordered start.
3. **configure → Locomotion gets ready.** The boss tells Locomotion "configure."
   Locomotion creates its heartbeat + health broadcasters and its sign-in phone,
   then **calls the registry to sign in**.
4. **Registry checks the ID.** The boss verifies the part's **protocol major
   version** matches (so an out-of-date part can't half-join), writes it in the
   phone book, gives it the namespace `/mark1/locomotion`, and **subscribes to
   its heartbeat channel.**
5. **activate → Locomotion starts beeping.** The boss tells Locomotion
   "activate." Now Locomotion starts its **5 Hz heartbeat** and 1 Hz health
   report, and marks itself `ACTIVE`.
6. **Done.** All managed parts are `ACTIVE`. From here, the heartbeat just keeps
   flowing. The health monitor stays quiet *as long as everything is healthy* —
   **silence means OK** (it only logs when a part becomes DEGRADED or DEAD).

A real heartbeat we pulled off the wire:

```yaml
header:
  protocol_major: 0      # \
  protocol_minor: 1      #  > version of the language this part speaks (0.1.0)
  protocol_patch: 0      # /
  module_id: MARK1-LOCO-001
  stamp: { sec: ..., nanosec: ... }   # when it was sent
sequence: 26             # 26th beep — proves the 5 Hz timer is running
lifecycle_state: 3       # 3 = ACTIVE  (1=unconfigured 2=inactive 3=active 4=finalized)
```

---

## 7. Design decisions, and *why* (the principles)

| Decision | Why |
|---|---|
| **Python first (`rclpy`)** | Fast to write and read while we shape the architecture. The ESP32 firmware will be C (micro-ROS) later — same messages, different language. |
| **Every part is a lifecycle node** | So the boss can start the rover in a known order and shut it down safely. We never invent our own on/off logic — we use the ROS 2 standard (and the proven Nav2 supervisor pattern). |
| **Sign in on `configure`** | A part must be known to the system *before* it's allowed to act. Configure = "get known and get ready"; activate = "start doing your job." |
| **Packed version number (major.minor.patch as 3 fields)** | One small number can't safely hold three. The registry compares **major** to reject parts that speak an incompatible language. |
| **Heartbeat is "best-effort, newest-only"** | A heartbeat is a postcard, not registered mail. If one is lost, we don't want it re-sent late — we only ever care about the **latest** beep. |
| **The boss watches deadlines, doesn't poll** | The middleware tells us when a beep is late, instead of us constantly asking "you there?" Less work, faster detection. |
| **Registry stores data immutably** | When a part registers, we build a *new* phone book rather than editing the old one in place — fewer surprise bugs. |

### The bug we hit (a real debugging story)

On the **first** run, sign-in failed: `module-registry unavailable after 5.0s`.
The boss was right there — so why couldn't the part reach it?

- **Cause:** the part's sign-in phone (service *client*) was set to QoS
  `critical_reliable`, which includes **TRANSIENT_LOCAL durability**. The boss's
  phone (service *server*) used the **default** service QoS (**VOLATILE**). In
  DDS, a listener that demands TRANSIENT_LOCAL won't connect to a VOLATILE
  speaker — **so the two phones never matched.** No error, just silence.
- **Fix:** services use the **default service QoS** on both sides.
  `critical_reliable` is a profile for *command topics*, not services.
- **Lesson (write this on your wall):** QoS profiles are per-kind. A profile
  meant for a *topic* can quietly break a *service*. When two things "should"
  talk but don't, **suspect a QoS mismatch first.**

---

## 8. Run it yourself

> ⚠️ ROS 2 Jazzy **cannot build on macOS**. We build inside a Docker container
> (Ubuntu 24.04 + ROS 2 Jazzy). See `.devcontainer/`. Heavy builds run on the
> **Legion** box (16 cores) — see the memory note `software-dev-legion-workflow`.

Inside the dev container (or on Legion), from the workspace root:

```bash
make build        # colcon build --symlink-install
make test         # runs the unit tests (should say 0 failures)
make run          # ros2 launch friday_core_hub walking_skeleton.launch.py
```

To watch the heartbeat live (it's best-effort, so you must say so):

```bash
ros2 topic echo /mark1/locomotion/heartbeat \
  --qos-reliability best_effort --qos-durability volatile
```

To see the lifecycle state of any part:

```bash
ros2 lifecycle get /locomotion      # -> active [3]
```

---

## 9. Debugging guide — "if this breaks, look here"

| What you see | What it usually means | Where to look |
|---|---|---|
| `module-registry unavailable after 5.0s` | The boss isn't up yet, or a **QoS mismatch** on the service. | Is `core_hub` running? `ros2 service list \| grep register_module`. Check both sides use default service QoS (`module_agent.py` `_reg_client`). |
| `registration REJECTED: protocol major mismatch` | The part speaks a different **major** language version than the boss. | `protocol.py` `PROTOCOL_MAJOR` — rebuild both against the same `friday_msgs`. |
| Part never reaches `ACTIVE` | Supervisor couldn't reach `/<part>/change_state`. | Does the node **name** match `managed_nodes` in the launch file? `ros2 lifecycle nodes`. |
| You see **no** heartbeats with `ros2 topic echo` | Either the part isn't ACTIVE, or your listener used the wrong QoS. | Add `--qos-reliability best_effort --qos-durability volatile`. Confirm `lifecycle get` says active. |
| Boss logs `liveness -> DEGRADED` / `DEAD` | A part went slow or died (beeps stopped). | Is the part's process alive/CPU pegged? Thresholds: `core_hub_node.py` `DEGRADED_AGE_S` / `DEAD_AGE_S`. |
| `colcon build` fails on `friday_msgs` | Message generator missing in the image. | Ensure `ros-jazzy-rosidl-default-generators` is installed (`.devcontainer/Dockerfile`). |
| Nothing builds on your Mac | ROS 2 doesn't build natively on macOS. | Use the dev container / Legion (Section 8). |

**General tracing tips:** `ros2 node list` (who's running), `ros2 topic list`
(what channels exist), `ros2 topic echo <topic>` (see the data), `ros2 service
list` (what phone lines exist), `ros2 lifecycle get <node>` (what state a part
is in). Logs are at `~/.ros/log/`.

---

## 10. How we know it works (verification)

| Check | Result | What it proves |
|---|---|---|
| `colcon build` | 4 packages, clean | The shared language compiles (a dossier acceptance criterion). |
| `colcon test` | 7 tests, **0 failures** | The registry rules + version logic are correct. |
| `ros2 interface list \| grep friday` | all 5 show up | The messages/service were generated correctly. |
| Launch trace (Section 6) | configure → register → activate → complete | Lifecycle startup + sign-in + supervision all work. |
| Heartbeat echo | seq 26, `lifecycle_state: 3` | The 5 Hz alive-beep path works end-to-end. |

---

## 11. What is intentionally NOT done yet (honest scope)

- **No motion.** Locomotion is a stub — no `MotionCommand`, no wheel `Odometry`,
  no real 100 ms safe-stop wiring. (`enter_safe_state()` just logs for now.)
- **Health numbers are placeholders** (temperature/CPU report 0).
- **The "part died" path isn't demoed yet.** The monitor exists, but we haven't
  killed a part to watch DEGRADED → DEAD. That's Stage 5 (fault injection).
- **No Gazebo / 3-D** (Stage 1).
- **Strict style/lint + copyright headers** are deferred to keep the first build
  green. Tracked debt.

---

## 12. Where this goes next

Pick the next phase (each gets its own walk-through doc like this one):

- **Stage 3 — Closed loop:** add `MotionCommand` + a simple motion model so
  Locomotion actually "drives" and publishes `Odometry`.
- **Stage 1 — Gazebo:** the URDF rocker-bogie model + hand-driving (the visual
  sim).
- **Stage 5 — Fault injection:** kill the Core Hub / cut a part's comms and prove
  safe-stop + the split-brain handling.
- **Next module:** the Telemetry Command Node agent (same template).

---

## 13. The template (so every phase doc looks like this)

Each finished phase gets a doc with these sections: **1** 30-second version ·
**2** why this phase first · **3** glossary · **4** architecture picture · **5**
what's in the box · **6** step-by-step walk-through (with real logs) · **7**
decisions + why (+ any bug stories) · **8** run it yourself · **9** debugging
guide · **10** verification · **11** not-done-yet · **12** what's next.

Documentation is written **in parallel with the code, in the same PR** — never
saved for the end.

---

**Related:** [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) ·
[friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) ·
[Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) ·
[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) ·
[Mark 1 Index](../Mark 1 Index.md)
