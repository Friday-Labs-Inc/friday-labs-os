# Phase 4 — Safety (Walk-Through)

> 📘 **Chapter for Phase 4 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> Read [Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) first; this
> chapter makes the motion *safe*.
>
> **Status:** ✅ Authority enforcement + safe-stop + split-brain *failover*
> verified on Legion · **Branch:** `phase4/safety` · The HIL 100 ms p99 watchdog
> is the one remaining, hardware-gated part of Phase 4.

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
- **Failover** — if the Core brain really dies, the **Telemetry** node notices
  (using *two* independent signals, not one) and **takes over** command authority
  within ~2 s. When Core comes back, it *asks* for authority back and the two hand
  off cleanly. A counter called the **epoch** ticks up on every handover and
  guarantees the two can never both believe they're in charge.

Verified on Legion: an attacker's command is refused; a replay is refused; when
the Core is killed mid-drive the rover safe-stops in **112 ms**; Telemetry takes
authority in **~2 s**; and after Core restarts, authority hands back cleanly —
the holder/epoch sequence is `CORE@1 → TLM@2 → CORE@3`, never two holders at once.

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
| **Failover** | Telemetry taking over command authority when the Core brain dies. |
| **Self-promote** | Telemetry deciding, on its own, to become the authority holder. |
| **Observe-window** | A ~2.5 s "look before you leap" Core does on boot — is anyone already in charge? — before taking or asking for authority. |
| **RequestAuthority / ReleaseAuthority** | The "may I have it back?" / "you can have it" handshake messages for a clean hand-off. |
| **Quiet window** | A 500 ms gap during a hand-off where *neither* side commands, so the wheels never get two bosses at once. |

---

## 4. What changed

| Package | Change |
|---|---|
| `friday_msgs` | `AuthorityLease`, `EmergencyStop`, `FaultReport.CATEGORY_WATCHDOG` (enforcement); **+ `RequestAuthority.srv` and `ReleaseAuthority.msg`** for the hand-back handshake. |
| `friday_module_agent` | **New ROS-free `authority.py`** — `should_failover` (both signals), `accept_lease` (epoch-monotonic), `may_grant_return` (not-behind **and** stable). |
| `friday_core_hub` | Safety-supervisor: authority lease (500 ms) + **20 Hz safety pulse**. **+ a boot observe-window** — clean boot takes epoch 1; a rejoin *asks* for authority back instead of publishing a competing lease. |
| `friday_locomotion` | Enforces authority (`safety.authorize()`); **40 Hz** safe-stop watchdog. **+ an epoch gate** (`accept_lease`) that ignores a stale lower-epoch lease. |
| `friday_telemetry` | The Command-Center boundary. **+ failover** — watches Core's two signals → self-promotes; serves `RequestAuthority` and hands back cleanly. |

The decision rules live in **ROS-free** modules (`safety.py`, `authority.py`) so
they're unit-tested without a robot — **21 tests** covering every accept/reject and
failover/hand-back path.

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

### 5c. Split-brain failover (who's in charge when the brain dies)
The Core Hub is the brain. If it crashes, someone else must take command — but if
**two** nodes ever think they're in charge at the same time, the wheels get
contradictory orders. That's the *split-brain* problem. Three rules prevent it:

**1. Telemetry takes over — but only on two signals.** Telemetry watches the Core
for *two independent* signs of life: its **authority lease** (renewed every 500 ms,
good for 2 s) and its **safety pulse** (20×/second). Telemetry self-promotes only
when **both** go quiet — the lease expires **and** the pulse is silent ≥1.5 s. One
failing alone (a stuck renewer, a dropped pulse) is *not* enough; requiring both
avoids taking over from a Core that's actually fine. Worst case: ~2.5 s.

**2. The wheels trust the highest epoch, not the loudest voice.** Every lease
carries an **epoch** counter. When Telemetry takes over it bumps the epoch (1 → 2).
Locomotion's `accept_lease` ignores any lease whose epoch is *behind* the highest
it has seen. So if the old Core twitches back to life and publishes its stale
epoch-1 lease, the wheels simply ignore it — **the consumer can't be fooled into
obeying two bosses**, no matter who's shouting.

**3. Core asks for it back; it doesn't grab it.** When Core reboots it does a
2.5 s **observe-window**: *is anyone already holding authority?* If yes (Telemetry,
epoch 2), Core does **not** publish a competing lease — it sends `RequestAuthority`.
Telemetry grants only if the rover is **stable** (not mid-motion) and Core isn't
behind, then publishes `ReleaseAuthority` and stands down. A **500 ms quiet window**
follows where neither commands, and Core comes up at **epoch 3**. Clean handover.

```
# kill the Core mid-run →
CORE LOST (lease expired + safety pulse silent) — Telemetry self-promoting to authority at epoch 2
SAFE-STOP entered: safety pulse lost (103 ms)     # wheels safe-stop during the gap (correct)
ignoring stale authority lease: epoch 1 < 2 (from MARK1-CORE-001)   # old Core ignored

# restart the Core →
observe window: MARK1-TLM-001 holds authority (epoch 2) — requesting clean hand-back
RequestAuthority from MARK1-CORE-001 granted at epoch 3 — releasing and standing down
quiet window elapsed — Core resumes authority at epoch 3
```

The decision logic — `should_failover`, `accept_lease`, `may_grant_return` — is the
ROS-free `authority.py`, so every branch is unit-tested without a robot.

---

## 6. Decisions & why

| Decision | Why |
|---|---|
| **Authority = lease holder, not operator id** | The command-*router* (whichever brain holds the lease) issues the internal command as itself; the operator's identity is carried for audit, not authorization. So `source` on a valid `MotionCommand` is the holder (`MARK1-CORE-001`), not `OP-001`. |
| **Safety pulse separate from the 5 Hz heartbeat** | The heartbeat (200 ms) is *presence detection* for the supervisor; the safety pulse (50 ms) is the *watchdog* signal. Per the budget, they must be independent — a 1 s heartbeat can't catch a 1 m/s rover in time. |
| **Two safe-stop triggers, one safe-state** | Watchdog (the safety net) and EmergencyStop (the operator stop) both reach the *same* defined state — predictable behavior however it fires. |
| **No self-recovery** | A rover that un-stops itself after a glitch is dangerous; recovery is an explicit, supervised lifecycle transition. |
| **Nonce per source** | Replay protection is per sender, so one sender's sequence can't be wedged by another. |
| **Failover needs two signals** | A single failed signal (a wedged renewer, one dropped pulse) shouldn't strip a healthy Core of authority. Requiring lease-expiry *and* pulse-silence makes a false failover near-impossible. |
| **Epoch gate at the consumer, not just the publisher** | Even if two nodes both publish leases, Locomotion obeys only the highest epoch — so "no two bosses" holds *at the wheels*, regardless of the network. This is the keystone that makes a partition (S3) safe. |
| **Core asks, never grabs** | A rebooting Core that just started commanding could fight the node that took over. The observe-window + `RequestAuthority` handshake makes every handover deliberate and one-directional. |
| **Grant only if stable + not-behind** | Never hand authority back mid-motion, or to a node whose epoch view is behind — resolves the addendum's `last_known_epoch` question: grant **iff** requester epoch ≥ holder's. |
| **Authority is never written to disk** | A node that reboots must assume it holds nothing, or it could resume commanding without realising it was replaced. In-memory only, by design. |

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

# watchdog + failover: kill the Core. Locomotion safe-stops on pulse loss, and
# within ~2 s Telemetry self-promotes to authority (epoch 2).
pkill -f 'lib/friday_core_hub/core_hub'

# clean hand-back: bring Core back. It observes Telemetry holding, asks for
# authority, and resumes at epoch 3 after a 500 ms quiet window.
ros2 run friday_core_hub core_hub
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
| Telemetry never fails over (Core killed) | Only one of the two signals fired, or Core was never seen alive first. | Failover needs lease-expiry **and** pulse-silence ≥1.5 s; `ros2 topic echo /mark1/system/safety_pulse`. |
| Core won't take authority back after restart | Rover not stable (recent motion), or Core's epoch is behind. | Telemetry grants only if stable + not-behind; stop the rover and read the `RequestAuthority` denial reason. |
| Wheels obey an old Core after failover | The epoch gate isn't rejecting the stale lease. | Watch for "ignoring stale authority lease"; `accept_lease` needs incoming epoch ≥ highest seen. |
| A manual `ros2 topic pub` to `/authority` is ignored | Wrong QoS — `/authority` is `critical_reliable` (reliable + **transient_local**). | Publish with `--qos-reliability reliable --qos-durability transient_local`, or DDS drops it as incompatible. |

---

## 9. Verification (on Legion)

| Check | Result |
|---|---|
| `colcon build` (incl. `RequestAuthority` / `ReleaseAuthority`) | clean, 5 packages |
| Unit tests (`safety.authorize` + `authority.*`) | **42 / 42 pass** (incl. 11 new failover tests) |
| Authorized command | ACCEPT → moved (x=1.03) |
| Wrong-source / replay | REJECT `WRONG_SOURCE` / `REPLAY` |
| EmergencyStop | SAFE-STOP entered |
| Safety-pulse loss (Core killed) | SAFE-STOP at **112 ms**, motion → 0 |
| **S1** — kill Core → Telemetry self-promote | **~2.0 s** (≤ 2.5 s budget) |
| **S1** — gap behaviour | Locomotion safe-stops on pulse loss (no self-recovery) |
| **S3** — stale epoch-1 lease after failover | ignored at the consumer |
| **S4** — restart Core → clean hand-back | request → grant@3 → resume@3, Telemetry stood down |
| **Authority sequence across the run** | `CORE@1 → TLM@2 → CORE@3` — monotonic, never two holders |

---

## 10. What is intentionally NOT done yet

- ~~**Split-brain failover**~~ — ✅ **Done** (this chapter, commit `87d7604`):
  Telemetry self-promotes on Core loss (two independent signals), the
  epoch-monotonic gate blocks a stale Core *at the wheels*, and a rejoining Core
  asks for a clean hand-back. Verified S1 / S3 / S4 on Legion.
- **The true 100 ms p99** — that's the ESP32 hardware watchdog over a dedicated
  serial link, validated on hardware-in-the-loop. Sim validates the *logic* + the
  DDS EmergencyStop path; 112 ms here includes the sim watchdog tick.
- ~~**Command-router routing**~~ — ✅ **Done** (commit `4c8e7ae`): the Telemetry
  agent now re-issues a validated operator command *as the current lease holder*
  (durable monotonic nonce), so the end-to-end operator→rover path composes and is
  verified. The per-source nonce floor is also now persisted to disk (a reboot no
  longer resets replay protection).
- **Active holding torque** on a slope, and the **LoRa recovery beacon** — hardware.

---

## 11. Where this goes next

- **Phase 4 is complete in sim** — authority enforcement, safe-stop, **and** the
  split-brain failover are all verified (S1 / S3 / S4). The one remaining piece is
  the **HIL 100 ms p99 watchdog**, which is hardware-gated (ESP32 + serial link).
- **Stage 1 — Gazebo:** run all of this against a physics-simulated rocker-bogie.

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) ·
[Authority Lease Protocol](../addendums/Authority Lease Protocol.md) ·
[Safe-Stop Latency Budget](../addendums/Safe-Stop Latency Budget.md) ·
[Mark 1 Index](../Mark 1 Index.md)
