# Command Center Boundary — The Locked Contract (v0.1.0)

> 📘 **The single source of truth for the rover ↔ Command Center external boundary.**
> Builds on [Phase 3 — Command Center Boundary](Phase 3 - Command Center Boundary.md)
> (the first working version of the guarded door) and locks the *full* contract that
> both sides now implement against.
>
> **Status:** 🔒 **Contract LOCKED 2026-06-30** (negotiated architect-to-architect,
> rover ↔ FCC). Wire shape empirically verified with a golden test vector. Some
> clauses are **live** today, some are **agreed-but-pending** — each section says which.
> The Command Center (FCC) keeps a mirrored authoritative copy of this contract.

---

## 1. The 30-second version

The rover talks to a **remote operator station** (the Command Center) over the open
internet. The internet is hostile, so the rule is simple: **trust nothing that comes
through the door until it's proven.**

Three things make that work:

1. **Every command is signed by a *person*.** Not by "the Command Center" — by the
   individual human operator who sent it. The rover keeps a guest list (the
   **allowlist**) of which operators it will obey, and checks the signature against
   *that person's* key. A forged, expired, or replayed command is **rejected and
   logged — never executed.**
2. **The rover keeps its head when it loses contact.** If the rover can't reach the
   Command Center for a while, it doesn't freeze and it doesn't blindly trust old
   permissions. It keeps doing safe things, refuses dangerous ones, always honors a
   stop, and eventually coasts to a hold. This is the **stale-trust** rule.
3. **The seal can't be faked across three programming languages.** The signature math
   only works if the browser (JavaScript), the Command Center (Python), and the rover
   (C++/ROS) all package the bytes *identically*. We pin that with a shared **golden
   test vector** so the three can never silently drift apart.

---

## 2. Two keys, two jobs (don't confuse them)

| Key | Who holds it | What it proves |
|---|---|---|
| **Operator key** | each human operator (private key in their own OS keychain) | "*This specific person* sent this command." Commands are signed with it. |
| **Rover key** | the rover (`rover_key_file`) | "This telemetry really came from *this rover* and wasn't faked." Telemetry is signed with it. |

There is **no single "Command Center master key."** The Command Center bridge holds
**zero** private keys — it only relays. That means a stolen key burns *one* operator (or
*one* rover), never the whole fleet.

A separate **mTLS certificate** secures the *transport pipe* at the broker. Keep it
mentally separate: mTLS proves "this machine may connect"; the Ed25519 signature proves
"this command is genuine." The signature is the real authority — the broker can be
bypassed, so the rover's own signature check is the gate that matters.

---

## 3. New words (glossary additions)

| Word | Plain meaning |
|---|---|
| **Operator allowlist** | The rover's guest list: which operators it will obey, each stamped with an `epoch` (version number). |
| **Fleet-root key** | A master key kept **offline** (in a safe/HSM). It doesn't sign commands — it vouches for the short-lived keys that sign the guest list. |
| **Intermediate key** | A short-lived (≤ 24 h) key the Command Center uses day-to-day to sign guest lists. The fleet-root vouches for it, so the root can stay offline. |
| **Snapshot** | One signed copy of the guest list, with an `epoch`. The rover only accepts a newer epoch than it's already seen (no going backwards). |
| **Stale-trust** | The rover's posture when its guest list is too old (it's been offline a while). It degrades *safely* instead of failing hard. |
| **Opaque byte-string (bstr)** | The command's actual content, sealed as raw bytes that nobody re-packages. This is what keeps the seal identical across languages. |
| **Golden vector** | A fixed example envelope + its expected signature, checked into both repos, so any packaging drift is caught instantly. |
| **epoch-ms** | Time as a plain whole number of milliseconds since 1970 (UTC). Whole numbers encode the same everywhere; decimals don't. |

---

## 4. The envelope (what's on the wire)

Same idea as Phase 3 — a sealed letter — with two changes that the lock-in nailed down:
**timestamps are whole milliseconds**, and **the content rides as an opaque byte-string**.

**Command (operator → rover):**
```
{ protocol_version{major,minor,patch}, rover_id, sender_id, msg_id,
  nonce, issued_at, expires_at, payload:bstr, signature }
```
**Telemetry (rover → Command Center):**
```
{ rover_id, kind, nonce, issued_at, data:bstr, sig }
```

- **`payload`/`data` are an opaque CBOR byte-string.** The sender packs the content
  **once**; those exact bytes travel and are what the signature covers. The receiver
  checks the signature over the bytes it received and **only then** unpacks them. Nobody
  ever re-packs the content — which is why floats inside it (a pose, a velocity setpoint)
  can't break the seal. ⏳ *pending — see §8.*
- **`issued_at`/`expires_at` are int64 epoch-ms (UTC).** Whole numbers, never decimals.
  ⏳ *pending — currently floats; see §8.*
- **`nonce`** is a ticket number that only goes **up** (see §6).
- Everything outside the byte-string is a simple type (number or text), so the
  **canonical packaging** (RFC 8949 §4.2: sorted keys, definite lengths, smallest
  integers) only has to agree on the boring fields.

---

## 5. The door checks (how a command is judged)

All must pass, in order, or the command is **rejected + logged, never executed**
(`friday_telemetry/protocol.py::CommandValidator`):

1. **Right language?** `protocol_version` matches — pre-1.0, exact `(major, minor)`
   (✅ major live; ⏳ minor pending).
2. **Right rover?** `rover_id` is this rover. ✅
3. **Known operator?** `sender_id` is on the allowlist. ✅
4. **Real seal?** Ed25519 signature verifies against *that operator's* public key. ✅
5. **Still fresh?** `now ≤ expires_at + 5 s` skew (⏳ ±5 s skew pending; expiry live). ✅/⏳
6. **Not a replay?** `nonce > floor` for this operator — strictly higher, **gaps allowed**
   (the floor is durable, survives reboot). ✅
7. **(Production) Valid certificate?** mTLS at the transport. ⏳

> **Why `nonce > floor`, not `floor + 1`:** the Command Center's durable counter can leave
> gaps after a reconcile, so demanding consecutive numbers would wrongly reject. Strictly
> increasing still kills replays.

---

## 6. Replay protection (nonce + time)

- **Nonce is the hard guarantee.** Per-(operator) for commands and per-(rover, kind) for
  telemetry, the rover keeps a durable **floor** and accepts only a strictly higher number.
  Survives reboot, so a captured old command can't be replayed across a power cycle.
- **The timestamp is a soft freshness gate.** 30 s expiry window + **±5 s skew**, because a
  field rover's clock drifts (no guaranteed internet time sync). If the clock is hopeless,
  the nonce floor *still* blocks replays.
- **Fault nonces are dense (1, 2, 3, …)** so the Command Center can tell a fault went
  missing and ask for it back (§9). Streaming `odom` keeps gap-tolerant nonces.

---

## 7. Stale-trust — keeping a safe head when offline

The rover can't phone home for the guest list mid-mission (it's often offline). So the
guest list is delivered as a **signed snapshot** it can carry and trust:

**The trust chain:** offline **fleet-root** → short-lived **intermediate** (≤ 24 h,
pre-signed in quarterly batches so the root stays offline) → **live-signed snapshot** of
the allowlist. The rover ships with the root's public key + an initial allowlist baked in
at provisioning. It accepts a new snapshot only if: the chain verifies **and** the `epoch`
is higher than the last one it saw **and** the intermediate is inside its validity window.
The rover remembers the highest epoch *and* intermediate serial it has ever seen (in
non-volatile memory) so nobody can roll it back to an old list.

**When the list goes stale (rover offline too long), commands are sorted into three tiers
— the rule is: stale trust may never GRANT authority or CLEAR a safety latch, but must
always allow a SAFE-DIRECTION action:**

| Tier | Examples | When stale |
|---|---|---|
| **ALWAYS** | e-stop **engage** / halt; *tightening* a geofence; *lowering* a speed cap | **Honored** — stopping and getting safer never needs fresh trust. |
| **NORMAL** | incremental motion setpoints, pause, hold, status queries | **Honored** within the cached list (raises a `STALE_AUTHZ` fault), until hard-stale (below). |
| **HIGH-AUTHORITY** | teleop handoff/takeover, e-stop **clear**, mission load/start, *relaxing* a geofence or speed cap, OTA/firmware, key/config push | **Refused** until a fresh snapshot arrives. |

**Two-stage staleness** (both numbers are per-deployment-profile config; the Command Center
stamps the active freshness lifetime into each snapshot so the rover reads one authoritative
number):

- **fresh → stale-grace** at the snapshot's freshness lifetime (default **1 h**).
- **stale-grace → hard-stale** at `T_hard` (default **4 h**): NORMAL motion now also
  degrades to **auto-HOLD** (stop taking new setpoints, coast to a hold — *not* an e-stop).
  ALWAYS-tier and safe-direction actions stay honored at every stage.

A high-security profile can set `1 h / 1 h`. The rover owns the **tighten-vs-relax**
decision (only it knows its current live envelope).

**Two field-ops realities (runbook, not wire contract):**
- A rover that e-stops and *then* goes stale **cannot self-clear** (e-stop clear is
  HIGH-AUTHORITY) — recovery needs connectivity. That's the correct trade-off.
- An autonomous mission authorized while trust was fresh **keeps running** through later
  staleness (honoring prior authority; aborting mid-maneuver is itself a hazard). On
  reconnect, if its authorizing operator was revoked, the rover raises a `STALE_AUTHZ`
  fault for a human to disposition rather than auto-aborting.

---

## 8. The golden vector — proving the seal across three languages

The whole signing scheme only works if the browser (JS), Command Center (Python), and rover
(C++/ROS) package the signed bytes **byte-for-byte identically**. We pin that with a fixed
**golden vector**: a known keypair + one command + one telemetry envelope + their expected
signing-bytes and signatures, checked into both repos
(`friday_telemetry/test/test_protocol_golden.py` here, `bridge/tests/test_golden_vector.py`
on FCC). **Neither side merges if its vector test is red.**

The trick that makes a stable vector possible is **opaque-bstr signing** (§4): because the
content is never re-packed, floats inside it (which different CBOR libraries shrink to
different widths) never touch the signature path. Only the simple outer fields need to match.

> **Verified 2026-06-30:** the agreed vector was independently checked — keys derive from
> seeds, both signatures verify, and an independent canonical re-encode of the outer map
> matched byte-for-byte. *Caveat:* that check used the same CBOR library family on both
> sides (2-of-3). The genuinely independent leg is the rover's **C++/rclpy** encoder
> asserting the same constants — which is the **acceptance gate on the implementing PR**.

---

## 9. Delivery & QoS (so a fault is never silently lost)

- **Topic scheme:** commands in on `mark1/{rover}/cmd/{class}`; telemetry out on
  `mark1/{rover}/tlm/…`; acks on `mark1/{rover}/ack/…`.
- **Per-class QoS:** `fault` + `ack` → **QoS 1 + persistent session** (expiry 300 s);
  `odom` → **QoS 0** (high-rate and self-healing — making it reliable would let it
  head-of-line-block a `fault`).
- **The real durability guarantee lives on the rover, not the broker.** The rover keeps a
  durable **fault journal** (MCAP). On reconnect it reads the Command Center's
  `get_fault_cursor(rover)` (highest *contiguous* fault nonce received) and **republishes
  every fault above it**; the Command Center de-duplicates by `(rover, nonce)`. The rover
  trims its journal only at/below that cursor, so a >5 min outage never drops a fault.

---

## 10. Rover-side build order (this repo)

Each step is gated by the golden vector + its own tests. ⏳ = not yet built.

1. ⏳ **Envelope change:** int64 epoch-ms timestamps + payload-as-bstr signing
   (the wire change the golden-vector test ships with). *Breaking — lands in lockstep with FCC.*
2. ⏳ **Operator-allowlist verify:** root→intermediate→snapshot chain, durable epoch +
   serial in NVM, baked-in provisioning state.
3. ⏳ **Stale-trust posture:** `STALE_AUTHZ` fault + class→authority-tier map + two-stage
   staleness + tighten-vs-relax direction split.
4. ⏳ **Telemetry replay fields:** `nonce` + `issued_at`, persisted floor; dense fault nonce.
5. ✅/⏳ **Command replay verify:** persisted per-operator nonce floor (✅ logic;
   durability + ±5 s skew ⏳).
6. ⏳ **Per-class QoS publishers** + verify topic scheme byte-for-byte.
7. ⏳ **Fault journal + reconnect replay** responder.
8. ⏳ **Golden-vector assertion test** (the C++/rclpy acceptance gate).

**Post-lock backlog:** a single **CDDL schema** that generates the JS/Python/C++ encoders,
so the wire format isn't hand-maintained in three places. The golden vector guards us until
then; afterwards it becomes a CI check on the generated code.

---

## 11. Debugging guide — "if this breaks, look here"

| What you see | Likely cause | Where to look |
|---|---|---|
| Valid command rejected `SECURITY_AUTH` after the bstr change | Encoder re-packed the payload instead of signing the received bytes verbatim. | `protocol.py::_signing_bytes` — payload must be an opaque bstr, not re-encoded. Run the golden-vector test. |
| Golden-vector test red on one side only | One language's CBOR encoder diverged on the **outer** map (key order, integer width, float in a timestamp). | Diff your `signing_bytes` hex against the vector; the differing field is the bug. Timestamps must be int epoch-ms, not float. |
| Command rejected `EXPIRED` with clocks "close enough" | Clock skew beyond the ±5 s window, or skew not implemented yet. | Check both clocks; confirm the ±5 s skew clause is built (step 5). |
| Rover refuses a teleop/mission command it used to accept | The allowlist snapshot is stale → HIGH-AUTHORITY refused. | `ros2` log for `STALE_AUTHZ`; check snapshot epoch/age vs. the freshness lifetime; reconnect to refresh. |
| Rover coasts to HOLD on its own while offline | Hit `T_hard` (hard-stale) — NORMAL motion degraded by design. | Snapshot age ≥ `T_hard`; reconnect for a fresh snapshot, or adjust the deployment profile. |
| A fault never showed up at the Command Center | QoS 0 path, or gateway was down past the 300 s session expiry. | Confirm `fault` publishes at QoS 1; check the reconnect fault-journal replay (§9) ran. |

---

## 12. What is intentionally NOT done yet

- The **bstr + int-ms wire change** (step 1) is the first implementing PR; until it lands the
  live code still re-encodes the whole payload and uses float timestamps.
- The **offline trust chain, stale-trust posture, fault journal/replay, and per-class QoS**
  (steps 2–4, 6–7) are designed and locked here but not yet built.
- **mTLS / real certificates** still come at field-test provisioning.
- **CDDL codegen** is post-lock backlog.

---

**Related:** [Software Manual](Friday Labs OS Software Manual.md) ·
[Phase 3 — Command Center Boundary](Phase 3 - Command Center Boundary.md) ·
[Phase 4 — Safety](Phase 4 - Safety.md) ·
[Command Center Protocol Security](../addendums/Command Center Protocol Security.md) ·
[Telemetry Command Node](../architecture/Telemetry Command Node.md)
