# Phase 3 — Command Center Boundary (Walk-Through)

> 📘 **Chapter for Phase 3 of the [Friday Labs OS Software Manual](Friday Labs OS Software Manual.md).**
> The companion to [Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md).
> Together they complete foundation Phase 3 (Communication). Read the
> closed-loop chapter first.
>
> **Status:** ✅ Verified (all security checks live) · **Branch:** `phase3/communication`

---

## 1. The 30-second version

So far everything happened *inside* the rover. Now a **remote operator** (the
"Command Center") can send commands to the rover over the internet — safely.

The catch: the internet is hostile. So every command travels in a **sealed,
signed envelope**, and the rover's **Telemetry agent** checks every seal before
acting. A real command drives the wheels; a forged, expired, or replayed command
is **rejected and logged** — never executed.

The rover's internal world stays ROS 2; the outside link is **not** ROS 2 (ROS 2
isn't built for the public internet). The Telemetry agent is the **translator**
between the two.

---

## 2. Why a guarded door, and why here

The external link is the rover's **only** attack surface. If someone could forge
a drive command, they could steal or crash the rover. So the boundary is built
**security-first**, before any real field test. One module — the Telemetry
Command Node — owns this door, so there's exactly one place to get right.

**Design principle:** *one guarded door, and trust nothing that comes through it
until it's proven.*

---

## 3. New words (glossary additions)

| Word | Plain meaning |
|---|---|
| **Command Center** | The remote operator's station. |
| **Envelope** | The sealed package every command travels in (data + proof of who sent it). |
| **Ed25519 signature** | A tamper-proof wax seal: math that proves *who* signed and that *nothing was changed*. |
| **Allowlist** | The guest list — operators the rover will even consider commands from. |
| **Nonce** | A ticket number that must always go **up**. A repeat or lower number = a replay → rejected. |
| **Expiry** | A "use by" time on every command (30 s). Too late = rejected. |
| **CBOR** | A compact binary format (like JSON, but smaller). |
| **mTLS** | Both sides show ID cards (certificates) before talking — production transport security. |

---

## 4. The envelope (what's in a command)

Every command — and every reply — is wrapped like this (from the security spec):

```
{ protocol_version, rover_id, sender_id, msg_id, nonce,
  issued_at, expires_at, payload (CBOR), signature (Ed25519) }
```

Think of it as a sealed letter: the **address** (rover_id), **who sent it**
(sender_id), a **serial number that only goes up** (nonce), a **use-by date**
(expires_at), the **message** (payload), and a **wax seal** (signature) over all
of it. Change one byte and the seal breaks.

---

## 5. The seven checks (how the door decides)

When a command arrives, the Telemetry agent runs these in order. **All** must
pass, or the command is dropped and logged:

1. **Right language?** protocol major matches.
2. **Right rover?** rover_id is *this* rover.
3. **Known operator?** sender_id is on the allowlist.
4. **Real seal?** Ed25519 signature verifies against that operator's public key.
5. **Still fresh?** expires_at hasn't passed.
6. **Not a replay?** nonce is strictly higher than the last one we accepted from
   this operator.
7. (Production) **Valid certificate?** mTLS at the transport.

A rejected command **never executes, never queues, and never silently
disappears** — it's logged as a `FaultReport` (with a security category) and
ACK'd back as rejected.

---

## 6. Walk-through: a command's journey

```
Operator                MQTT broker            Telemetry agent           Locomotion
   |  sign envelope         |                       |                        |
   |---- cmd/motion ------->|---- deliver --------->| 7 checks               |
   |                        |                       |  pass -> MotionCommand-+--> drives
   |<------------------- ack (accepted) ------------|                        |
```

- The operator signs the envelope with their **private** key and publishes it to
  `mark1/<rover>/cmd/motion`.
- The Telemetry agent receives it **on the network thread**, runs the seven
  checks, and hands the result to the **ROS thread** (so DDS is only touched from
  one place).
- **Accepted** → it builds a `friday_msgs/MotionCommand` (carrying the operator's
  id + nonce as authority provenance) and publishes it internally; Locomotion
  drives.
- **Rejected** → it publishes a `FaultReport` and ACKs the rejection with the
  reason.

---

## 7. Decisions & why

| Decision | Why |
|---|---|
| **Sign the command, not just the connection** | TLS only protects the *pipe* and is terminated at the broker. The signature protects the *command* end-to-end, and ties each action to a specific operator (audit). |
| **Ed25519** | Fast, tiny (64-byte) signatures, modern and hard to misuse. |
| **Nonce + expiry** | Together they kill replay attacks: an old captured command is either too old (expiry) or a number we've already seen (nonce). |
| **Reject advances nothing** | A rejected command must not consume the nonce sequence, or an attacker could wedge the door. Verified by a unit test. |
| **Validate on the network thread, publish on the ROS thread** | DDS publishers aren't meant to be poked from random threads; a queue + a ROS timer keeps it clean. |
| **CBOR payload** | Smaller than JSON on a metered cellular link. |
| **mTLS deferred to transport config** | The command-authority security (the part that stops forged commands) is fully implemented and tested now; mTLS is a transport wrapper added with real certs at field-test time. |

---

## 8. Run it yourself

Inside the dev container / on Legion:

```bash
# 1. make an operator keypair + the rover's allowlist
ros2 run friday_telemetry mock_command_center provision \
  --operator-id OP-001 --key-file /tmp/op.key --allowlist /tmp/operators.json

# 2. start a broker
printf 'listener 1883 0.0.0.0\nallow_anonymous true\n' > /tmp/mosq.conf
mosquitto -c /tmp/mosq.conf -d

# 3. launch the whole system (Core Hub + Locomotion + Telemetry)
ros2 launch friday_core_hub command_center.launch.py operators_file:=/tmp/operators.json

# 4. (other shell) send commands — try each mode
ros2 run friday_telemetry mock_command_center send \
  --key-file /tmp/op.key --operator-id OP-001 --rover MARK1-001 --nonce 1 --mode valid
#   modes: valid | forged | expired | replay ;  wrong-rover = different --rover
```

Each `send` prints the rover's **ACK** (`accepted: true/false`, and the reason).

---

## 9. Debugging guide — "if this breaks, look here"

| What you see | Likely cause | Where to look |
|---|---|---|
| Every command rejected as `UNKNOWN_SENDER` | The allowlist the rover loaded doesn't contain your operator key. | Launch arg `operators_file`; re-run `provision`; check the `--operator-id` matches. |
| `ACK: (none received)` | Telemetry isn't connected to the broker, or isn't active. | Is `mosquitto` running on `mqtt_host`? `ros2 lifecycle get /telemetry` → active? Check `/tmp/run.log`. |
| Valid command rejected as `SECURITY_AUTH` | Key mismatch (allowlist pub key ≠ signing priv key) or payload tampered. | Re-`provision` so `/tmp/op.key` and `/tmp/operators.json` are a matched pair. |
| Valid command rejected as `SECURITY_REPLAY` | You reused or lowered the `--nonce`. | Always send a higher `--nonce` than last time. |
| Valid command rejected as `EXPIRED` | Big clock skew between operator and rover, or `--mode expired`. | Check clocks; default expiry is 30 s. |
| Command accepted but rover doesn't move | The internal `MotionCommand` QoS or Locomotion isn't active. | See the closed-loop chapter's debug table. |

---

## 10. Verification (live, on Legion)

| Test | Result |
|---|---|
| `colcon build` (incl. `friday_telemetry`) | clean, 5 packages |
| Security unit tests | **9 / 9 pass** (forged, replay, expired, wrong-rover, unknown-operator, protocol-mismatch, nonce-not-consumed-on-reject) |
| Live: valid command | `ACK accepted: True` → ACCEPTED, rover drove (odometry x = 0.597) |
| Live: forged command | `ACK accepted: False · SECURITY_AUTH` |
| Live: expired command | `ACK accepted: False · EXPIRED` |
| Live: replay (nonce reused) | `ACK accepted: False · SECURITY_REPLAY` |
| The forged `v=9.5` | never reached the wheels (rover moved at the last *valid* speed, 0.4) |

---

## 11. What is intentionally NOT done yet

- **No real mTLS/certs in the demo** — plaintext localhost MQTT + full app-layer
  signing. Real client certificates + a CA come at field-test provisioning.
- **Telemetry outbound is minimal** — the rover→operator health/telemetry stream
  and the `dbg/` debug channel are stubs.
- **Authority not yet enforced *internally*** — the operator id rides on the
  internal `MotionCommand`, but Locomotion doesn't yet reject on it. That's
  **Phase 4** (authority lease + internal enforcement).
- **No LoRa fallback** path yet (emergency-stop over the low-bandwidth channel).
- **CA / key rotation / revocation** workflows are designed (spec) but not built.

---

## 12. Where this goes next

Foundation **Phase 3 (Communication) is now complete**: internal closed-loop
motion + the guarded external boundary. Next is **Phase 4 — Safety**: enforce the
authority fields end-to-end, wire heartbeat-loss → failover, and the 100 ms
safe-stop.

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 3 — Closed-Loop Motion](Phase 3 - Closed-Loop Motion.md) ·
[Command Center Protocol Security](../addendums/Command Center Protocol Security.md) ·
[Telemetry Command Node](../architecture/Telemetry Command Node.md) ·
[Authority Lease Protocol](../addendums/Authority Lease Protocol.md) ·
[Mark 1 Index](../Mark 1 Index.md)
