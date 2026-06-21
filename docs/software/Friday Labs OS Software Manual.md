# Friday Labs OS — Software Manual

> The **living manual** for the Mark 1 rover's software. It grows **one chapter
> per foundation phase**, written *as each phase is implemented* — never saved
> for the end. Built to be read by someone new to robotics: you should be able
> to **trace it, run it, and debug it** from this manual alone.
>
> **Status:** living · **Latest chapter:** Phase 2 — Walking Skeleton (✅) ·
> **Updated:** 2026-06-20

---

## How to read this manual

> 🌱 **Brand new, or want the origin story?** Read the genesis chapter first:
> **[Phase 0 — Genesis: The First Line of Code](Phase 0 - Genesis - The First Line of Code.md)**.
> It walks from an empty folder to Friday Labs' very first line of code and the
> first program that runs — no prior robotics knowledge needed. It's the single
> best starting point for anyone who picks up this manual cold.

1. **Start here** (Sections 1–6). This is the stuff that's the *same in every
   phase*: the big picture, where the code lives, how to build and run it, the
   debugging toolkit, and a plain-language glossary.
2. **Then read the chapters** in order (Section 7) — they're a story:
   **Phase 0 (Genesis)** → **Phase 2 (Walking Skeleton)** → **Phase 3 (Closed-Loop
   Motion)** → **Phase 4 (Safety)** → onward. Each chapter is a self-contained
   walk-through.
3. **New to ROS 2?** Every technical word is in the **Glossary** (Section 6).

Each chapter follows the same template, so once you've read one you know how to
read them all.

---

## 1. What Friday Labs OS is (one page)

Friday Labs OS is the **brain software** that runs on the rover's main computer
(the **Core Compute Hub**) and coordinates everything else.

The rover's body is split into **modules** (wheels, comms, lab/sensors, the drone
bay). Each module has a small program called an **agent**. One **Core Hub**
program is the coordinator. They all talk to each other over **ROS 2** using one
shared set of message shapes called **`friday_msgs`**.

```
                         ┌───────────────────────────┐
                         │   CORE COMPUTE HUB         │
                         │   = Friday Labs OS         │
                         │   (the brain / coordinator)│
                         └───────────┬───────────────┘
                                     │  ROS 2 + friday_msgs
        ┌──────────────┬─────────────┼─────────────┬──────────────┐
        ▼              ▼             ▼             ▼              ▼
   Telemetry      Locomotion   Adaptive Research  Aerial Bay   (+ Spark drone)
   (comms)        (wheels)     (sensors/lab)      (launch/dock)
```

Key idea: **offline-first.** The rover does its thinking on board; the internet
is optional and only reached through the Telemetry module.

---

## 2. The big architecture (how the whole thing fits)

- **One brain, many parts.** The Core Hub coordinates; each module agent does its
  own job. No single computer is a bottleneck or a single point of failure.
- **One shared language.** Every program speaks `friday_msgs`. Change the language
  in one place, everyone rebuilds against the same thing.
- **Every part is a "lifecycle node."** It can be told *configure → activate →
  deactivate* by the boss, so the rover starts up in a known order and shuts down
  safely. (This is the proven Nav2 pattern.)
- **Health by heartbeat.** Each part sends an "I'm alive" beep; the Core Hub
  notices instantly if one goes quiet.
- **The outside world is a separate door.** The Command Center (remote operator)
  link is *not* ROS 2 — the Telemetry module translates between the rover's
  internal ROS 2 world and the outside link.

For the full design rationale, see the dossier:
[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md),
[ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md),
[Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md).

---

## 3. Where the code lives (workspace map)

The software is a ROS 2 **colcon workspace**. Packages live in `src/`:

```
friday-labs-os/
├── src/
│   ├── friday_msgs/            the shared language (messages + services)
│   ├── friday_module_agent/    the reusable "part template" (ModuleAgent) + QoS rules
│   ├── friday_core_hub/        the boss (registry + health monitor + supervisor)
│   └── friday_locomotion/      the first part (wheels' brain — stub for now)
├── .devcontainer/              the Docker build/dev environment (ROS 2 Jazzy)
├── Makefile                    make build | test | run | clean
└── docs/software/              this manual + one chapter per phase
```

How the packages depend on each other (read the arrow as "is built on"):

```
friday_msgs  ←  friday_module_agent  ←  friday_core_hub
                       ↑                       (the boss)
                       └──  friday_locomotion  (a part)
```

So the **language** comes first, the **template** builds on it, and the **boss**
and **parts** build on the template. New modules are added at the bottom-right —
mostly copy `friday_locomotion`, rename, and fill in the real work.

---

## 4. Build, run, and the dev workflow (same for every phase)

> ⚠️ **ROS 2 Jazzy does not build on macOS.** We build inside a Docker container
> (Ubuntu 24.04 + ROS 2 Jazzy), defined in `.devcontainer/`.

**Heavy builds run on Legion** — a 16-core Linux box that is our build farm. The
loop is:

```
edit on the Mac  →  git push the branch  →  on Legion: git pull + build/run in Docker
```

The exact Legion build command and setup are recorded in the project memory note
`software-dev-legion-workflow`.

Inside the container (or on Legion), from the workspace root:

```bash
make build     # colcon build --symlink-install   (compiles everything)
make test      # runs the unit tests              (should say 0 failures)
make run       # ros2 launch friday_core_hub walking_skeleton.launch.py
```

VS Code users can "Reopen in Container" (`.devcontainer/`) to get the same
environment locally.

---

## 5. The debugging toolkit (works in every phase)

When something "should" work but doesn't, these commands let you *see* the live
system. Run them in a sourced ROS 2 shell while the system is running:

| Command | Answers |
|---|---|
| `ros2 node list` | Which programs are running? |
| `ros2 topic list` | What broadcast channels exist? |
| `ros2 topic echo <topic>` | What data is on a channel right now? |
| `ros2 topic hz <topic>` | How fast is a channel publishing? |
| `ros2 service list` | What request/answer "phone lines" exist? |
| `ros2 lifecycle get <node>` | What state is a part in (active/inactive)? |

**Golden rules of robot debugging:**
1. **If two parts won't talk, suspect a QoS mismatch first.** (QoS = the delivery
   rules. A mismatch fails *silently* — no error, just nothing arrives.)
2. **Best-effort channels need a best-effort listener.** To watch a heartbeat:
   `ros2 topic echo <topic> --qos-reliability best_effort --qos-durability volatile`.
3. **Logs live in `~/.ros/log/`.**
4. **Silence can be healthy** — the health monitor only logs when a part becomes
   DEGRADED or DEAD, so no news is good news.

Each chapter also has its own "**if this breaks, look here**" table for that
phase's specific failure modes.

---

## 6. Glossary (master)

| Word | Plain meaning |
|---|---|
| **ROS 2** | The robotics framework everything runs on (programs + messaging). |
| **Node** | One running program (e.g. `core_hub`). |
| **Package** | One small project in `src/` (e.g. `friday_msgs`). |
| **Topic** | A broadcast channel; anyone can listen. |
| **Service** | A one-time request/answer ("phone call"). |
| **Message** | The shape of data sent, defined in `friday_msgs`. |
| **Lifecycle node** | A node that can be told configure/activate/deactivate. |
| **Agent** | A module's program; in our code, a subclass of `ModuleAgent`. |
| **Registry** | The Core Hub's "phone book" of which parts are present. |
| **Heartbeat** | A tiny "I'm alive" message, sent 5×/second. |
| **QoS** | "Quality of Service" — a message's delivery rules (like postage class). |
| **Namespace** | A folder for a part's channels, e.g. `/mark1/locomotion/...`. |
| **colcon** | The tool that builds the workspace. |
| **micro-ROS** | The lightweight ROS used on tiny chips (ESP32), added later. |
| **Gazebo** | The 3-D physics simulator (used from Phase/Stage with a body model). |
| **MotionCommand** | Our message telling the wheels what to do (speed + turn rate). |
| **Odometry** | Standard ROS message: "here's where I am and how fast I'm going." |
| **odom frame** | The map-like coordinate system Locomotion reports position in. |
| **Motion model** | Math that turns a drive command into an updated position. |
| **Authority lease** | A rover-wide token; only its current holder may issue motion/stop commands. |
| **Safe-state** | The rover's defined stop: motors at zero, steering frozen. |
| **Watchdog** | A timer that trips a safe-stop if the brain's safety pulse goes quiet. |
| **EmergencyStop** | A message that forces safe-state immediately. |
| **Command Center** | The remote operator station that sends commands over the internet. |
| **Envelope** | The sealed, signed package every external command travels in. |
| **Ed25519 signature** | A tamper-proof "wax seal" proving who sent a command and that it's unchanged. |
| **Nonce** | A serial number that must always increase — stops replayed commands. |
| **mTLS** | Both sides prove identity with certificates before talking (production link). |

---

## 7. Foundation phases — the map

The software is built in foundation phases. Each **implemented** phase has a full
chapter below; planned phases show what they will prove. (These map onto the
dossier's 5-phase roadmap and the seven-stage sim bring-up.)

| Phase | What it proves | Status | Chapter |
|---|---|---|---|
| **0 — Genesis** | How the codebase begins: from an empty folder to the first line of code (`uint8 protocol_major`) to the first program that runs. Read this first. | ✅ Complete | [Phase 0 — Genesis: The First Line of Code](Phase 0 - Genesis - The First Line of Code.md) |
| **1 — Design foundation** | The architecture, the shared `friday_msgs` contract, QoS policy, and safety model — on paper, locked. | ✅ Complete | The dossier — start at [Mark 1 Index](../Mark 1 Index.md) |
| **2 — Walking skeleton** | Parts find each other, start up in order (lifecycle), and are watched by heartbeat. The spine everything bolts onto. | ✅ Complete | [Phase 2 — The Walking Skeleton](Phase 2 - Walking Skeleton.md) |
| **3 — Communication** | Closed-loop motion (`MotionCommand` → `Odometry`) **and** the guarded Command Center boundary (Ed25519-signed MQTT link; every command validated). | ✅ Complete | [Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) · [Command Center Boundary](Phase 3 - Command Center Boundary.md) |
| **4 — Safety** | **Authority enforcement** (only the lease holder may command; nonce + expiry) and the **safe-stop watchdog** (pulse-loss / e-stop → motors-off, verified 112 ms) ✅; split-brain failover + HIL 100 ms ⏳. | 🔄 In progress | [Phase 4 — Safety](Phase 4 - Safety.md) |
| **5 — Autonomy & missions** | Mission planning, sensor fusion, mapping, and Spark coordination. | ⏳ Planned | _added when implemented_ |

---

## 8. How this manual grows (the process)

When a foundation phase is finished, the **same pull request** that adds the code
also:

1. Adds a **chapter** in `docs/software/` using the standard template
   (30-second version → why this phase → glossary additions → architecture →
   what's in the box → step-by-step boot trace → decisions & why → run it →
   debugging guide → verification → not-done-yet → next).
2. Flips that phase's row in the **map** above to ✅ and links the chapter.
3. Adds any new terms to the **Glossary**.

Documentation is a **parallel deliverable**, part of every phase's definition of
done — written with the code, not after it.

---

**Related (dossier):**
[Mark 1 Index](../Mark 1 Index.md) ·
[Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) ·
[ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) ·
[Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) ·
[Phase 1 Implementation Kickoff](../onboarding/Phase 1 Implementation Kickoff.md)
