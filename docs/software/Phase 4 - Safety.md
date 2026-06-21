# Phase 4 — Safety (Walk-Through)

> 📘 **Chapter for Phase 4 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> Read [Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) first; this
> chapter makes the motion *safe*.
>
> **Status:** ✅ Authority enforcement + safe-stop verified · **Branch:**
> `phase4/safety` · The split-brain *failover* and the HIL 100 ms validation are
> the remaining parts of Phase 4.

---

## 1. The 30-second version

Until now, anything that published a `MotionCommand` could drive the rover, and
nothing stopped it if the brain died. Phase 4 fixes both:

- **Authority** — the rover now obeys a command *only* from whoever holds the
  `authority` lease, and only if the command is fresh and not a replay. A command
  from the wrong sender, or a repeated one, is **rejected and logged**.
- **Safe-stop** — a watchdog watches a fast "I'm alive" pulse from the brain. If
  that pulse stops (brain died / comms cut), or someone hits emergency-stop, the
  rover **halts itself** — motors to zero, steering frozen — within ~100 ms.

Verified on Legion: an attacker's command is refused; a replay is refused; and
when the Core is killed mid-drive, the rover safe-stops in **112 ms**.

---

## 2. Why these two, and why now

A rover that *moves* near people, livestock, and property is only acceptable if
two things are guaranteed: **only an authorized brain can command it**, and **it
stops the instant it loses its brain.** Everything past here (autonomy, missions)
is only safe to build on top of this floor.

**Design principle:** *safety is independent of the thing it protects against.*
The safe-stop must fire even when the software that's supposed to issue commands
has crashed — so it's a separate watchdog, not a feature of the command path.

---

## 3. New words (glossary additions)

| Word | Plain meaning |
|---|---|
| **Authority lease** | A rover-wide token; only its current **holder** may send motion/stop commands. |
| **Holder** | The node that currently has authority (Core Hub by default). |
| **Epoch** | A counter that ticks up every time authority changes hands (used to settle split-brain). |
| **Safety pulse** | A fast "I'm alive" beat from the brain that the wheels' watchdog listens for. |
| **Watchdog** | A timer that trips a safe-stop if the safety pulse goes quiet. |
| **Safe-state** | Motors at zero, steering frozen — the rover's defined "stopped and holding" state. |
| **EmergencyStop** | A message that forces safe-state immediately (the operator's big red button). |

---

## 4. What changed

| Package | Change |
|---|---|
| `friday_msgs` | New `AuthorityLease` (holder + epoch + 2 s expiry) and `EmergencyStop` (categories); `FaultReport` gains `CATEGORY_WATCHDOG`. |
| `friday_core_hub` | Acts as the **safety-supervisor**: publishes the authority lease (renewed every 500 ms) and a **20 Hz safety pulse**. |
| `friday_locomotion` | Enforces authority on every command (pure `safety.authorize()`); a **40 Hz watchdog** trips safe-state on pulse-loss / e-stop / authority-loss. |

The enforcement rules live in a **ROS-free** module (`safety.py`) so they're unit-
tested without a robot — 10 tests covering every accept/reject path.

---

## 5. Walk-through

### 5a. Authority enforcement (the command path)
Every `MotionCommand` carries `source`, `nonce`, and `expires_at`. Before obeying
it, Locomotion runs `safety.authorize()`, which checks, in order:

1. **Not safe-stopped?** (a safe-stopped rover obeys nothing.)
2. **Valid authority?** a lease exists and hasn't expired.
3. **Right sender?** `source` == the current lease holder.
4. **Still fresh?** the command's own expiry hasn't passed.
5. **Not a replay?** `nonce` strictly increases for that sender.

Pass → drive. Fail → publish a `FaultReport` and drop it. Real trace:

```
ACCEPT motion src=MARK1-CORE-001 nonce=1 v=0.50 w=0.30      # authorized → moves
REJECT motion: WRONG_SOURCE (src=ATTACKER nonce=2)          # not the lease holder
REJECT motion: REPLAY (src=MARK1-CORE-001 nonce=1)          # reused nonce
```

### 5b. Safe-stop (the watchdog path)
The Core Hub beats a **safety pulse** 20×/second. Locomotion's watchdog checks
40×/second: *has it been >100 ms since the last pulse?* If yes → **safe-state**.
Same safe-state is reached three ways — **watchdog (pulse lost)**, **EmergencyStop**,
or a lifecycle **deactivate**. One safe-state, three triggers.

```
# kill the Core mid-drive → its pulse stops →
SAFE-STOP entered: safety pulse lost (112 ms) (latency 112 ms)
odom twist x: 0.0     # motion halted
```

Recovery is deliberate: the rover does **not** un-stop itself. The safety-
supervisor must walk it back through the lifecycle (`inactive → active`).

---

## 6. Decisions & why

| Decision | Why |
|---|---|
| **Authority = lease holder, not operator id** | The command-*router* (whichever brain holds the lease) issues the internal command as itself; the operator's identity is carried for audit, not authorization. So `source` on a valid `MotionCommand` is the holder (`MARK1-CORE-001`), not `OP-001`. |
| **Safety pulse separate from the 5 Hz heartbeat** | The heartbeat (200 ms) is *presence detection* for the supervisor; the safety pulse (50 ms) is the *watchdog* signal. Per the budget, they must be independent — a 1 s heartbeat can't catch a 1 m/s rover in time. |
| **Two safe-stop triggers, one safe-state** | Watchdog (the safety net) and EmergencyStop (the operator stop) both reach the *same* defined state — predictable behavior however it fires. |
| **No self-recovery** | A rover that un-stops itself after a glitch is dangerous; recovery is an explicit, supervised lifecycle transition. |
| **Nonce per source** | Replay protection is per sender, so one sender's sequence can't be wedged by another. |

---

## 7. Run it yourself

```bash
make build && make run     # Core Hub now publishes authority + safety pulse

# authorized drive
ros2 topic pub --once --qos-reliability reliable --qos-durability transient_local \
  /mark1/locomotion/cmd_motion friday_msgs/msg/MotionCommand \
  "{type: 1, linear_velocity: 0.5, angular_velocity: 0.3, source: MARK1-CORE-001, nonce: 1}"

# try an unauthorized one → watch it get rejected
ros2 topic pub --once --qos-reliability reliable --qos-durability transient_local \
  /mark1/locomotion/cmd_motion friday_msgs/msg/MotionCommand \
  "{type: 1, linear_velocity: 0.9, source: ATTACKER, nonce: 2}"

# emergency stop
ros2 topic pub --once --qos-reliability reliable --qos-durability transient_local \
  /mark1/locomotion/emergency_stop friday_msgs/msg/EmergencyStop "{category: 0, reason: test}"

# watchdog: kill the Core and watch Locomotion safe-stop on pulse loss
pkill -f 'lib/friday_core_hub/core_hub'
```

---

## 8. Debugging guide — "if this breaks, look here"

| What you see | Likely cause | Where to look |
|---|---|---|
| Every command `REJECT NO_AUTHORITY` | Locomotion isn't receiving the lease (QoS mismatch) or the Core isn't publishing it. | Authority is `critical_reliable` both sides; `ros2 topic echo /mark1/system/authority`. |
| Authorized command `REJECT WRONG_SOURCE` | Your `source` != the lease holder. | Use `source: MARK1-CORE-001` (the `authority_holder` param), or check who holds it. |
| Command `REJECT REPLAY` | Reused/lower `nonce` for that source. | Send a higher nonce. |
| Rover safe-stops immediately on activate | Safety pulse not arriving (QoS mismatch / Core down). | Pulse is `best_effort`; `ros2 topic echo /mark1/system/safety_pulse`. |
| Rover won't move after a safe-stop | It's safe-stopped; it does not self-recover. | Re-activate: `ros2 lifecycle set /locomotion deactivate` then `activate`. |

---

## 9. Verification (on Legion)

| Check | Result |
|---|---|
| `colcon build` (incl. new interfaces) | clean, 5 packages |
| Authority unit tests (`safety.authorize`) | **10 / 10 pass** |
| Authorized command | ACCEPT → moved (x=1.03) |
| Wrong-source / replay | REJECT `WRONG_SOURCE` / `REPLAY` |
| EmergencyStop | SAFE-STOP entered |
| Safety-pulse loss (Core killed) | SAFE-STOP at **112 ms**, motion → 0 |

---

## 10. What is intentionally NOT done yet

- **Split-brain failover** — the Telemetry node *self-promoting* to take the lease
  when the Core dies (and the clean hand-back when it returns) is the next slice;
  this chapter covers authority *enforcement*, not the *failover* protocol.
- **The true 100 ms p99** — that's the ESP32 hardware watchdog over a dedicated
  serial link, validated on hardware-in-the-loop. Sim validates the *logic* + the
  DDS EmergencyStop path; 112 ms here includes the sim watchdog tick.
- **Command-router routing** — so a Command Center operator command is re-issued
  internally *as the lease holder* (today the Phase 3 telemetry path stamps the
  operator id, which Phase 4 would reject — they're integrated in the next slice).
- **Active holding torque** on a slope, and the **LoRa recovery beacon** — hardware.

---

## 11. Where this goes next

- **Finish Phase 4:** the Telemetry self-promote **failover** + clean authority
  hand-back (the split-brain protocol), exercised by the `fault-injection` scenarios.
- **Stage 1 — Gazebo:** run all of this against a physics-simulated rocker-bogie.

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) ·
[Authority Lease Protocol](../addendums/Authority Lease Protocol.md) ·
[Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) ·
[Mark 1 Index](../Mark 1 Index.md)
