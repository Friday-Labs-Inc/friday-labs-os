# Phase 1 Implementation Kickoff

> Day-zero onboarding for any engineer joining the Mark 1 build. The 4-week ramp from "haven't read the dossier" to "contributing code against the locked spec." Works whether you're the founder, a hire in month 6, or yourself coming back after a break.
> **Version:** Draft 1.0 · **Purpose:** Make Phase 1 startable by anyone, not just the dossier's author.

## Before You Write A Single Line of Code

Read the dossier. All of it. The architecture is locked; if you start coding before you've read it, you'll waste two weeks rebuilding decisions that are already written down.

**The 6 originals** — the system:
1. [Mark 1 Index](../Mark 1 Index.md) — the map. Start here.
2. [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) — five modules, who does what.
3. [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) — brain software on the Core Hub.
4. [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) — the shared vocabulary. **Build this first.**
5. [Telemetry Command Node](../architecture/Telemetry Command Node.md) — comms, recovery, internet gateway.
6. [Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) — how to prove it works before hardware.

**The 14 addendums** — the locked decisions (read in any order):

Authority and safety: [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) · [Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) · [Sensor Ownership](../addendums/Sensor Ownership.md) · [Stage 5 Acceptance Criteria](../addendums/Stage 5 Acceptance Criteria.md)

Hardware: [Power Budget](../addendums/Power Budget.md) · [AI Inference Location](../addendums/AI Inference Location.md) · [Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [mmWave Human Detection](../addendums/mmWave Human Detection.md)

Contract and infrastructure: [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) · [Command Center Protocol Security](../addendums/Command Center Protocol Security.md) · [OTA Update Strategy](../addendums/OTA Update Strategy.md) · [Mission Logging and Replay](../addendums/Mission Logging and Replay.md) · [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md)

**The 3 module specs** — the implementations:
[Locomotion Control Unit](../modules/Locomotion Control Unit.md) · [Adaptive Research Module](../modules/Adaptive Research Module.md) · [Aerial Companion Bay](../modules/Aerial Companion Bay.md)

**Total reading time:** ~3-4 hours. Take notes on anything that feels off — by week's end you'll have caught issues the author missed, and that's how the dossier improves.

## Workstation Setup (Days 3-4)

Install in this order. Don't skip the validation step at the end.

### Required

| Tool | Purpose |
|---|---|
| **Ubuntu 24.04 LTS** | Base OS. VM or dual-boot. Not WSL — DDS discovery is unreliable across the WSL boundary. |
| **ROS 2 Jazzy** | The robotics middleware. `apt install ros-jazzy-desktop-full`. |
| **Gazebo Harmonic** | Simulator. `apt install gz-harmonic`. |
| **ros_gz** bridge | ROS 2 ↔ Gazebo bridge. `apt install ros-jazzy-ros-gz`. |
| **Foxglove Studio** | Live data visualization. Free download. Far better than RViz2 for debugging streams. |
| **VS Code** + ROS extension | Editor. The extension knows about launch files and message types. |
| **colcon** + **rosdep** | Workspace build tools. Bundled with ROS 2 install. |
| **Git** | Source control. Configure your name and email. |

### Validate

Three checks. If any fails, debug before continuing — every later step assumes these work.

1. **Hello world.** Two terminals. Terminal 1: `ros2 run demo_nodes_cpp talker`. Terminal 2: `ros2 run demo_nodes_cpp listener`. Listener prints "Hello World" messages. ✅
2. **Turtlesim.** `ros2 run turtlesim turtlesim_node`, then in another terminal `ros2 run turtlesim turtle_teleop_key`. Drive the turtle with arrow keys. ✅
3. **Gazebo.** `gz sim shapes.sdf` opens a 3D world. ✅

If you've never used ROS 2 before, do the official 5 beginner tutorials before Week 1 — about 4 hours. Don't fake it; the rest of the build assumes you know what a publisher, subscriber, and lifecycle node are.

## Week 1 — friday_msgs (Phase 1 Foundation)

The contract before the code. Nothing else can be built until `friday_msgs` exists and is frozen at v0.1.0.

### Tasks (in order)

1. **Create the package.** `ros2 pkg create --build-type ament_cmake friday_msgs --dependencies builtin_interfaces lifecycle_msgs std_msgs geometry_msgs sensor_msgs nav_msgs`.
2. **Define every message** in [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) + [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) (`AuthorityLease`, `RequestAuthority`, `ReleaseAuthority`) + [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) (mandatory headers, packed semver, category enums).
3. **Use the [friday-msgs-author](../../.claude/skills/friday-msgs-author/SKILL.md) skill** for every message. It enforces the rules — bounded arrays, frame_id, command auth fields, etc. Don't author by hand; the skill exists so you can't forget the discipline.
4. **Define the `UploadMission.action`** for missions entering the system.
5. **Run [qos-audit](../../.claude/skills/qos-audit/SKILL.md)** against a test publisher/subscriber pair to confirm the four QoS profiles work as documented.
6. **Tag v0.1.0** and write a CHANGELOG entry.

### Done means

- `colcon build --packages-select friday_msgs` is clean on both Ubuntu (rclcpp/rclpy) and via Micro-XRCE-DDS-Gen for the ESP32 target.
- `ros2 interface show friday_msgs/msg/Heartbeat` lists every field with correct types.
- Another developer can `apt install`-style consume the package and not need to read the schema doc to use it correctly.

## Week 2 — Lifecycle + Authority

Now build the spine. Three Core Hub services + the authority lease.

### Read first

Nav2's `lifecycle_manager` source code is the working reference for `safety-supervisor`. Spend 30 minutes reading it before implementing. (`github.com/ros-navigation/navigation2/tree/main/nav2_lifecycle_manager` — but version against the current Jazzy branch.)

### Tasks

1. **`module-registry`** — Pi rclpy lifecycle node. Implements `RegisterModule.srv`. Tracks which modules are present and their capabilities. Use [lifecycle-node-scaffold](../../.claude/skills/lifecycle-node-scaffold/SKILL.md).
2. **`system-health-manager`** — Pi rclpy lifecycle node. Subscribes to all heartbeat topics with the documented Deadline QoS. Raises events when a deadline is missed.
3. **`safety-supervisor`** — Pi rclpy lifecycle node. Drives child lifecycle nodes via `change_state` / `get_state`. Nav2 pattern.
4. **`authority-lease-service`** — Pi rclpy lifecycle node. Implementation matches the protocol in [Authority Lease Protocol](../addendums/Authority Lease Protocol.md) exactly — 2 s lease, 500 ms renewal, epoch counter, in-memory only.
5. **Wire it up** — services start in dependency order via systemd target `friday-core-os.target` per [Spark Authority and friday-core-os Definition](../addendums/Spark Authority and friday-core-os Definition.md).

### Done means

- `ros2 lifecycle list` shows all four services.
- `ros2 lifecycle set /mark1/system/authority-lease-service activate` succeeds, and the lease holder is reported.
- A second mock node can request the lease and observe the documented handoff.
- Killing the lease holder process triggers Telemetry's self-promotion within 2.5 s in a mock test.

## Week 3 — Sim Bring-Up

Stand up Gazebo and get a rocker-bogie model moving with `MotionCommand`.

### Tasks

1. **URDF/SDF for the rover** — Perseverance-pattern per [Mechanical Design Reference](../addendums/Mechanical Design Reference.md). 6 driven wheels, 4 corner-steered.
2. **Run [sim-bringup](../../.claude/skills/sim-bringup/SKILL.md) Stage 1** — model + teleop. Drive the rover by keyboard in Gazebo.
3. **Run [sim-bringup](../../.claude/skills/sim-bringup/SKILL.md) Stage 2** — lifecycle orchestration. The sim agents are lifecycle nodes that register with `module-registry`.
4. **Run [sim-bringup](../../.claude/skills/sim-bringup/SKILL.md) Stage 3** — closed loop. Core publishes `MotionCommand`, sim Locomotion publishes `Odometry`, you can drive the rocker-bogie in a square via code.
5. **Set up CI** to run Stages 1-3 headlessly on every commit. `gz sim --headless-rendering ...`.

### Done means

- Headless CI green on a clean main.
- A sim Locomotion agent accepts MotionCommand and publishes Odometry that closes the autonomy loop.
- Foxglove (or RViz2) shows the rover driving, with health and authority topics live.

## Week 4 — Fault Injection (Stage 5)

The most important stage of bring-up. This is where bugs in the safety chain surface.

### Tasks

1. **Run [fault-injection](../../.claude/skills/fault-injection/SKILL.md) scenario S1** — kill Core process. Confirm Telemetry detects within 1.5 s. Confirm sim Locomotion safe-stops within 100 ms of heartbeat loss.
2. **Run S2** — cut Locomotion comms (`tc qdisc add` to drop packets). Confirm motors-zero within 200 ms.
3. **Run S3** — network partition between Core and Telemetry. Confirm zero conflicting motion commands.
4. **Run S4** — Core restart during recovery. Confirm clean handoff per [Authority Lease Protocol](../addendums/Authority Lease Protocol.md).
5. **Run S5** — both Pis killed. Confirm sim ESP32 backup beacons within 5 s.
6. **Run S6** — Lab Deck killed mid-mission. Confirm Core nav continues with its own sensor.
7. **Wire all six into CI.** Every commit re-runs them. p99 budgets per [Stage 5 Acceptance Criteria](../addendums/Stage 5 Acceptance Criteria.md).

### Done means

- Headless CI runs S1-S6 every commit. All six green at p99 budget.
- Any regression on the safety path is caught on push, not in the field.

## After Week 4 — Three Parallel Tracks

By now the framework is proven in sim. Open three workstreams that can run independently:

**Track A — Locomotion firmware** ([Locomotion Control Unit](../modules/Locomotion Control Unit.md)). ESP32-S3 + USB CDC + hardware Task WDT + motor + steering loops. Use [lifecycle-node-scaffold](../../.claude/skills/lifecycle-node-scaffold/SKILL.md) for the ESP32 variant. Validate against [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) before any motor spins on real hardware.

**Track B — Lab Deck services** ([Adaptive Research Module](../modules/Adaptive Research Module.md)). Pi 5 + sensor drivers (LiDAR, camera, environmental, mmWave radar). Plug-and-play discovery. Each driver is its own lifecycle node.

**Track C — Telemetry + CC Protocol** ([Command Center Protocol Security](../addendums/Command Center Protocol Security.md)). Pi 4 + mTLS + per-operator Ed25519 + nonce/expiry. Build against a mock Command Center first; real broker integration last.

When all three tracks pass [fault-injection](../../.claude/skills/fault-injection/SKILL.md) in sim AND [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) on bench, you're ready for [Stage 7 headless CI](../architecture/Mark 1 Simulation and Dev Environment.md) and hardware integration.

## Decision Authority

Clarity on what you decide alone vs. with the team.

| Scope | You decide alone | Team review | Addendum update |
|---|---|---|---|
| Code style, file names, internal interfaces | ✅ | | |
| Choice of test framework, formatter, linter | ✅ | | |
| Variable names, log formats, error messages | ✅ | | |
| Adding a new `friday_msgs` message | | ✅ (use [friday-msgs-author](../../.claude/skills/friday-msgs-author/SKILL.md)) | If breaking change |
| Changing a QoS profile | | ✅ | ✅ |
| Adding hardware not in the BOM | | | ✅ (write a new addendum) |
| Changing anything in the 14 locked addendums | | | ✅ (revise the addendum first, then code) |
| Disabling a [Stage 5 scenario](../addendums/Stage 5 Acceptance Criteria.md) | | | Hard no — fix the bug |

The default: **if the dossier and the code disagree, the dossier wins.** Update the dossier first, then the code. The dossier is the spec.

## Eight Discipline Rules

Read these every Monday. They're the lessons the dossier already paid for; they exist because someone (the dossier's author, or NASA, or me, or you) already got burned learning them.

1. **The dossier is the spec.** Code that contradicts the dossier is wrong; fix the doc first, then the code.
2. **Every line of code traces to a decision.** No drive-by changes. No "while I'm here." If you can't link it to a section of the dossier, don't write it.
3. **Every Mark 1-specific message has the mandatory header.** No exceptions per [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md).
4. **Every command source is validated against the [authority lease](../addendums/Authority Lease Protocol.md).** Unsigned or stale commands are dropped with `FaultReport`, not silently ignored.
5. **Every ESP32 with motion authority uses the hardware Task WDT.** Never a FreeRTOS soft timer for safety. [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) refuses to pass otherwise.
6. **Tests that claim "pass" report a p99 number.** Vibes don't pass CI. See [Stage 5 Acceptance Criteria](../addendums/Stage 5 Acceptance Criteria.md).
7. **Never merge to main with a failing Stage 5.** No exceptions, including "just for the demo."
8. **Read the dossier on Monday, write code Tuesday-Friday.** Drift between the dossier and the code accumulates fast; checking weekly catches it cheap.

## Tools You Have

Eight skills are in `.claude/skills/`:

| Skill | When to use |
|---|---|
| [friday-msgs-author](../../.claude/skills/friday-msgs-author/SKILL.md) | Any time you add or change a `friday_msgs` interface |
| [lifecycle-node-scaffold](../../.claude/skills/lifecycle-node-scaffold/SKILL.md) | Any time you create a new module agent (Pi or ESP32) |
| [sim-bringup](../../.claude/skills/sim-bringup/SKILL.md) | Bringing Gazebo up clean; onboarding a developer |
| [fault-injection](../../.claude/skills/fault-injection/SKILL.md) | Running Stage 5; verifying safety regressions caught |
| [safe-stop-audit](../../.claude/skills/safe-stop-audit/SKILL.md) | Before any field test; after Locomotion firmware change |
| [module-spec](../../.claude/skills/module-spec/SKILL.md) | Drafting a new module spec in house style |
| [qos-audit](../../.claude/skills/qos-audit/SKILL.md) | After any new node ships; before integration test |
| [command-center-protocol](../../.claude/skills/command-center-protocol/SKILL.md) | Working on the external link or the Telemetry Node Agent |

Each skill refuses unsafe patterns by design — FreeRTOS soft timers for safe-stop, unbounded arrays on RELIABLE QoS, unsigned commands, JSON wire formats, etc. They're how the discipline survives between sessions. Use them.

## Hardware Procurement

Don't order hardware in Week 1. The first 4 weeks are pure sim. Procurement happens after the sim foundation is green — that way you don't discover a wrong BOM choice with parts on the bench.

When you're ready, the locked BOM is in [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) and the per-module specs ([Locomotion Control Unit](../modules/Locomotion Control Unit.md), [Adaptive Research Module](../modules/Adaptive Research Module.md), [Aerial Companion Bay](../modules/Aerial Companion Bay.md)).

Rough total: **~$2,045-2,450** excluding the Spark drone. See [Power Budget](../addendums/Power Budget.md) for the envelope rationale.

## Where to Get Help

- **Dossier ambiguity** — the addendum or module spec is the answer. If the answer isn't there, propose a new addendum. Don't decide in code.
- **ROS 2 questions** — `discourse.ros.org` is the official forum. Stack Overflow has answered most of what you'll hit.
- **Nav2 questions** — `github.com/ros-navigation/navigation2/discussions` is the right venue. Their lifecycle manager is our reference.
- **Hardware-specific debugging** — `forum.arduino.cc` and the ESP32 part of `esp32.com` for firmware issues; `forums.raspberrypi.com` for Pi-side.
- **Stuck for >30 minutes** — stop, write down what you tried, ask. The session limit is 30 minutes alone, not 4 hours.

## Related

[Mark 1 Index](../Mark 1 Index.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) · [Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) · [Stage 5 Acceptance Criteria](../addendums/Stage 5 Acceptance Criteria.md) · [friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md)
