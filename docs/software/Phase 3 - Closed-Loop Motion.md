# Phase 3 — Closed-Loop Motion (Walk-Through)

> 📘 **Chapter for Phase 3 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> Read [Phase 2 — The Walking Skeleton](Phase 2 - Walking Skeleton.md) first; this
> chapter adds the first *moving* behavior on top of that spine.
>
> **Status:** ✅ Closed-loop motion verified · **Branch:** `phase3/communication` ·
> **Bring-up stage:** Stage 3 (closed loop). The Command Center boundary is the
> remaining part of foundation Phase 3 (Communication).

---

## 1. The 30-second version

In Phase 2 the rover could sign in and beep "I'm alive," but it couldn't *do*
anything. Now it can **take a drive command and report where it went.**

You send a `MotionCommand` ("go forward 0.5 m/s, turn 0.3 rad/s"); the Locomotion
agent runs a little **motion model** and publishes `Odometry` ("I'm now at x=1.36,
y=0.72, facing ~0.96 rad") 20 times a second. That's a **closed loop**: command
in → motion → position out.

It's still a *software* model — no real motors yet. But the messages are the real
ones, so when we later swap in Gazebo (or real wheels), nothing else changes.

---

## 2. Why this is the right next step

A rover that can't move isn't a rover. The first behavior to prove is the
**command-and-feedback spine**: can a command travel from the outside, cause
motion, and produce feedback the rest of the system can use (for mapping,
navigation, safety)? Everything later — autonomy, missions — rides on this loop.

**Design principle:** *prove the command→feedback loop with a stand-in model
before wiring real hardware.* The model is throwaway; the **contract** (the
messages and topics) is forever.

---

## 3. New words (glossary additions)

| Word | Plain meaning |
|---|---|
| **MotionCommand** | Our message that tells the wheels what to do (a speed + a turn rate). |
| **Odometry** | A standard ROS message: "here's where I am and how fast I'm going." |
| **Motion model** | Math that turns "drive at this speed" into "you're now here." |
| **Unicycle model** | The simplest such math: treat the rover as a dot with a forward speed and a turn rate. |
| **odom frame** | The map-like coordinate system Locomotion reports position in. |

---

## 4. What changed (just two things)

| Package | Change |
|---|---|
| `friday_msgs` | Added **`MotionCommand.msg`** — a velocity command (+ the contract's authority fields, see §6). |
| `friday_locomotion` | The agent now **subscribes** `MotionCommand`, runs a unicycle model, and **publishes** `nav_msgs/Odometry` at 20 Hz. Safe-state stops it. |

Nothing in `friday_core_hub` or `friday_module_agent` changed — the new behavior
slotted into the Locomotion agent through the base class's hardware hooks
(`configure_hardware`, `activate_hardware`, `enter_safe_state`). That's the
template paying off again.

---

## 5. Walk-through: a command becomes motion

New topics on the Locomotion namespace:

```
/mark1/locomotion/cmd_motion   (in)  — MotionCommand, QoS critical_reliable
/mark1/locomotion/odometry     (out) — nav_msgs/Odometry, QoS state_default
```

Step by step:

1. **Activate.** When Locomotion goes `active`, it resets its pose to (0, 0,
   facing 0) and starts a **20 Hz timer**. With no command, speed is 0 — odometry
   reads all zeros.
2. **A command arrives.** Someone publishes `MotionCommand {type: VELOCITY,
   linear_velocity: 0.5, angular_velocity: 0.3}`. The agent stores those two
   numbers (and logs the `source`).
3. **The model runs.** 20 times a second, the timer advances the pose a tiny step:
   ```
   theta += w · dt          # turn a little
   x     += v · cos(theta) · dt    # move forward a little, in the new direction
   y     += v · sin(theta) · dt
   ```
4. **Odometry goes out.** Each tick publishes where the rover now is (`odom`
   frame) and how fast it's going.
5. **Stop / safe-state.** A `STOP` or `SAFE_STOP` command (or the supervisor
   deactivating the node) zeroes the speed and halts integration.

Real verified output (after ~3 s of v=0.5, w=0.3):

```
frame_id: odom · child_frame_id: base_link
position:    x: 1.360   y: 0.721
orientation: z: 0.462   w: 0.887     → yaw ≈ 0.96 rad
twist:       linear.x: 0.5   angular.z: 0.3
```

The numbers check out: turning at 0.3 rad/s for ~3.2 s ≈ 0.96 rad; driving at
0.5 m/s along a curving path lands near (1.36, 0.72). The loop is closed.

---

## 6. Decisions & why

| Decision | Why |
|---|---|
| **Unicycle model** | Simplest model that captures "drive + turn." The real rover is a 6-wheel rocker-bogie, but for proving the *loop* the dot-with-heading is enough; Gazebo handles real physics later. |
| **`odom` frame, `base_link` child** | The locked frame convention: Locomotion owns `odom` (smooth, drifts); `base_link` is the rover body. Using the standard `nav_msgs/Odometry` means Nav2 and mapping tools work for free later. |
| **Commands are `critical_reliable`** | A drive command must not be dropped — it's reliable + latched. (Testing gotcha: `ros2 topic pub` must add `--qos-durability transient_local` to match, or the command silently won't arrive — the same QoS rule from Phase 2.) |
| **Authority fields present, not yet enforced** | `MotionCommand` carries `source / token_id / nonce / expires_at` per the contract (a command that can move the rover must be signable). Enforcement (reject unsigned/expired/replayed) lands in Phase 4 with the authority lease. We log `source` now so the wiring is visible. |
| **Motion lives in the agent, not the base** | Heartbeat/health/registration are universal (base class); driving is Locomotion-specific (subclass). Clean separation. |

---

## 7. Run it yourself

Build and launch as in Phase 2 (`make build` then `make run` in the dev
container / on Legion). Then, in another sourced shell:

```bash
# watch where the rover thinks it is
ros2 topic echo /mark1/locomotion/odometry

# drive it: forward 0.5 m/s, gentle left turn
ros2 topic pub --once \
  --qos-reliability reliable --qos-durability transient_local \
  /mark1/locomotion/cmd_motion friday_msgs/msg/MotionCommand \
  "{type: 1, linear_velocity: 0.5, angular_velocity: 0.3, source: OPERATOR-TEST}"

# stop
ros2 topic pub --once --qos-reliability reliable --qos-durability transient_local \
  /mark1/locomotion/cmd_motion friday_msgs/msg/MotionCommand "{type: 0}"
```

Watch the `position` in the odometry stream climb after the command, and freeze
after the stop.

---

## 8. Debugging guide — "if this breaks, look here"

| What you see | Likely cause | Where to look |
|---|---|---|
| Command sent but odometry never moves | **QoS mismatch** on the command (the classic). | Add `--qos-durability transient_local --qos-reliability reliable` to `ros2 topic pub`. The agent's sub uses `critical_reliable`. |
| Odometry topic missing entirely | Locomotion isn't `active` yet. | `ros2 lifecycle get /locomotion` — should be `active [3]`. The publisher is a *lifecycle* publisher (only emits when active). |
| Position jumps / drifts oddly | `dt` spikes (a stalled timer) or a huge velocity. | `_step()` in `locomotion_agent_node.py`; check the command values. |
| Odometry keeps moving after you wanted to stop | You sent `type: 1` with non-zero velocity, or never sent a stop. | Send `type: 0` (STOP) or deactivate the node. |
| `The passed message type is invalid` | Workspace not rebuilt after adding `MotionCommand`. | `make build`, re-`source install/setup.bash`. |

---

## 9. Verification

| Check | Result |
|---|---|
| `colcon build` (incl. `nav_msgs`) | clean, 4 packages |
| Lifecycle bring-up still works | ✅ registered + active + bring-up complete |
| Odometry at rest | x=0, y=0 |
| Odometry after a command | moved to (1.36, 0.72), yaw ≈ 0.96 rad, twist matches command |
| Frames | `odom` → `base_link` (per the locked convention) |

---

## 10. What is intentionally NOT done yet

- **No real drivers.** Still a software model — no motor/steer/encoder via the
  ESP32 (micro-ROS) and no firmware safe-stop. That's hardware-in-the-loop later.
- **Authority not enforced.** Commands aren't yet rejected for bad signature /
  nonce / expiry — Phase 4.
- **No Command Center boundary yet.** The other half of foundation Phase 3
  (modules ↔ OS ↔ remote operator over the non-ROS link) is still to come.
- **Velocity only.** `PATH_SEGMENT` / explicit corner-steer commands aren't wired.
- **No `sensor-fusion-manager`** consuming the odometry yet (Phase 5).

---

## 11. Where this goes next

- **Finish Phase 3:** the **Command Center boundary** — the Telemetry Node Agent
  translating `friday_msgs` ↔ the external (MQTT-class) protocol.
- **Phase 4 — Safety:** enforce the authority fields, wire heartbeat-loss →
  failover and the 100 ms safe-stop.
- **Stage 1 — Gazebo:** swap this model for `gz_ros2_control` publishing the same
  `Odometry` from a real rocker-bogie body.

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 2 — Walking Skeleton](Phase 2 - Walking Skeleton.md) ·
[ROS 2 Interface and Message Contract](../architecture/ROS 2 Interface and Message Contract.md) ·
[friday_msgs Schema Conventions](../addendums/friday_msgs Schema Conventions.md) ·
[Mark 1 Index](../Mark 1 Index.md)
