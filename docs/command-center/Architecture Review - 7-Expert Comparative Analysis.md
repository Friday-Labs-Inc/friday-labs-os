# Command Center — 7-Expert Architecture Review (Comparative Analysis)

> Seven senior system-architect agents independently reviewed the Command Center
> design (one per dimension: application, system design, connectivity, radio/RF,
> cloud/distributed, data lake, data pipeline). This is the comparative synthesis
> — what they agreed on, where they conflict, and the prioritized fix list.
>
> **Version:** Round 1 · **Verdict:** concept strong (~4/5), implementation detail
> thin (~2/5). The gaps cluster tightly — a few fixes close most of them.

---

## Scorecard

| Dimension | Maturity | Biggest single fix (the expert's words, condensed) |
|---|---|---|
| Application architecture | **3** | Define the **edge control-plane cache** (local allowlist/nonce/keys/audit) — until then "edge-first" is aspirational. |
| System design (holistic) | **3** | Define the **edge↔cloud sync protocol** — ordering/conflict rules for revocation & allowlist. A wrong merge is a security regression, not a bug. |
| Connectivity & network | **3** | Define **nonce persistence + MQTT session resumption** across bearer handover & rover reboot — else replay protection silently collapses. |
| Radio & RF telemetry | **2** | **Retire "always-on LoRa e-stop"** — duty-cycle-illegal & unnecessary; the firmware watchdog is the real RF-independent safe-stop, LoRa is a dead-man beacon. |
| Cloud & distributed systems | **2** | Implement the **reconnect handshake** that forces a rover to ACK the current revocation/allowlist bundle **before** accepting any command. |
| Data feeding & data lake | **2** | **Pick & deploy a concrete edge time-series store** before Phase B (recommend QuestDB) — "local time-series store" is a placeholder. |
| Data pipeline & analytics | **2** | Define **event-time watermarking** (use the authenticated `issued_at`) for backfill before any anomaly pipeline. |

**Average ~2.4.** The design *thinks* at a 4 and *specifies* at a 2. The weak band is the data + RF + cloud edge — exactly the parts the first blueprint hand-waved.

---

## Consensus gaps — ranked (what ≥2 experts independently hit)

These are the real priorities. The number in brackets = how many of the 7 raised it.

### P0 — security / safety correctness (fix before any field-connected build)

1. **Nonce durability is a hole. [3 — App, System, Connectivity]** The monotonic nonce per `(operator, rover)` is in-memory. A rover reboot, a bearer switch that resets the MQTT/TLS session, or a bridge restart resets it → either valid commands get rejected as replays, or replays get accepted. **Fix:** persist the nonce floor (fsync'd SQLite/file) on both the rover Telemetry agent and the bridge; resume MQTT 5 sessions with `Clean Start=false`.

2. **Revocation to an offline rover is asserted but unenforced. [3 — System, Cloud, App]** The spec promises "a revoked operator can't command an offline rover," but nothing enforces it. **Fix:** a reconnect handshake — the rover stays in `pending-sync` and refuses operator commands until it ACKs the current signed revocation/allowlist bundle (epoch E). This is the scariest defense gap.

3. **Edge↔cloud sync + conflict resolution is undesigned. [5 — App, System, Cloud, Connectivity, Data]** "Sync on reconnect" is named everywhere, specified nowhere. **Fix:** event-sourced append-only logs + a hybrid logical clock / vector clock. Per-stream consistency: telemetry/health = at-least-once, dedup on `msg_id`, order by `issued_at`; audit = append-only; **allowlist/revocation = CRDT (add-wins provision / remove-wins revoke) and security fields never auto-merge — they escalate to human ack.**

4. **The "edge control-plane cache" is the missing mechanism. [App]** A small local store (SQLite / libSQL) on the Local CC holding the allowlist snapshot, nonce floor, operator keys, audit tail — the bridge reads *this*, not cloud Frappe, on the hot path. This is what makes 1–3 actually work offline. **It's the keystone fix.**

5. **"Always-on LoRa e-stop" is physically/legally wrong. [2 — RF, Connectivity]** ISM duty cycle (~1%) forbids it; the **firmware watchdog (≤100 ms, RF-independent) is the real safe-stop.** LoRa is a low-rate dead-man beacon, not a stop channel. **Fix:** rename it everywhere; make sure no firmware safety dependency is built on LoRa. Cheap, important.

### P1 — architecture spine (needed before the data plane is built)

6. **Choose the time-series stores. [3 — Data, Pipeline, App]** Edge: **QuestDB** (low footprint, out-of-order inserts, SQL, InfluxDB-line ingest — both data experts named it). Cloud Fleet Health: **TimescaleDB** (Postgres familiarity) or **ClickHouse** (scale) + an **Iceberg + Parquet on S3/MinIO lakehouse** for fleet analytics. Lock before Phase B.

7. **Store-and-forward needs a real durable queue + shedding policy. [4 — Cloud, Data, System, Pipeline]** Bounded buffer, per-stream tiers (audit never dropped · health thinned after N hrs · odometry decimated under pressure), alert at 80% full. Don't let a 48-hr Starlink outage OOM the edge box.

8. **Backfill breaks analytics without event-time handling. [2 — Pipeline, Cloud]** Use the authenticated `issued_at` as event time + watermarks (≥24 hr tolerance) + dedup. Prefer **Kappa** over Lambda at this volume.

9. **Multi-tenant isolation needs an egress filter, not a promise. [2 — Cloud, Data]** Tag every `friday_msgs` field `@customer_private` / `@manufacturer_observable` / `@audit_required`; the bridge routes by tag. Otherwise "mission data stays with the customer" is unenforceable — a real defense risk.

10. **The bridge is stateful — split it (CQRS). [3 — App, Connectivity, Data]** A **command dispatcher** (stateful: signing + nonce + audit) and a **telemetry ingestor** (stateless, scalable). It also must strip the CBOR envelope: signature/nonce → audit (Frappe), payload → TSDB — an undocumented data-shaping responsibility today.

11. **RBAC is nominal, not specified. [App]** Draw the permission matrix (`rover:command:motion`, `:mission`, `:estop`, `fleet:manage`, `keys:provision`, `audit:read`) and note which need Frappe **row-level** User Permissions (operator X → rovers {R1,R2}) — before building DocTypes.

12. **No RF link budgets / power-gating / realistic relay. [RF]** Produce a one-page link budget per bearer/terrain before any radio purchase (≥15 dB fade margin). 900 MHz NLoS at 20 km through canopy needs **elevated relays (hilltop/tethered aerostat), not direct or Spark** (15–25 min flight ≠ persistent relay). Bearer selection must double as **power-gating** (MANET 12–15 W vs the 10 W telemetry budget). Defense needs **licensed bands / LPI-LPD**, not ISM.

### P2 — scale & resilience (before multi-site / fleet)

13. **Protocol versioning across an offline fleet. [2 — System, Data]** The CC must serve N and N-1; upgrade sequence = CC before rovers; add a **schema registry** (Avro/Protobuf keyed on `protocol_major`) at ingest.
14. **The edge box is a single point of failure. [3 — System, Connectivity, Cloud]** Broker/bridge/store/signing/UI on one node. Define HA (EMQX needs 3 for quorum; or 2-node active-passive) or an explicit degraded mode + RTO.
15. **Staged fault-detection ML. [2 — Pipeline, Data]** Stage 1 rules (ships v1) → Stage 2 unsupervised anomaly (Isolation Forest/HBOS on edge-computed features via **River**) → Stage 3 predictive (defer until labeled failure data). Avoids "need ML to ship" paralysis.

---

## Cross-dimension conflicts (tensions the experts flagged between areas)

- **Signing location ↔ laptop-edge.** A client-side signing daemon (YubiKey PIV) is fine on a manned workstation but changes the operator field kit — the App and Deployment docs decide this separately and don't cross-reference. Reconcile before locking.
- **Authority-lease 1.5 s ↔ bearer-handover convergence.** A transient bearer switch could exceed the lease heartbeat threshold and **false-trigger a Telemetry self-promote failover.** Compare the numbers explicitly.
- **30 s command expiry ↔ bearer latency + clock skew.** Over satellite/LoRa + GPS clock discipline gaps, a valid command (even an e-stop) can arrive with <2 s validity; a command replayed from the store-and-forward buffer after a clock-resync can fall outside expiry and be **silently voided.** Define a per-bearer skew budget.
- **Power budget 10 W ↔ MANET radio 12–15 W.** Bearer selection must be power-scheduled — only one high-power bearer transmits at peak.
- **Safe-stop 500 ms DDS path ↔ RF latency.** At 3-hop mesh or LoRa, the 500 ms p99 is unachievable by link physics. The watchdog (100 ms, RF-independent) is fine; the DDS e-stop path needs an RF-latency budget.

---

## Newer-tech consensus (Adopt / Evaluate)

| Tech | Verdict | For |
|---|---|---|
| **QuestDB** | Adopt | edge time-series store |
| **TimescaleDB / ClickHouse** | Adopt | cloud Fleet Health TSDB |
| **Apache Iceberg + Parquet (S3/MinIO)** | Adopt | HQ fleet-analytics lakehouse |
| **NATS JetStream** | Evaluate→likely | internal/cloud bus + store-and-forward leaf nodes [4 experts] |
| **WireGuard** | Adopt | edge→cloud tunnel / Starlink-CGNAT NAT traversal |
| **Event sourcing + HLC / CRDTs** | Adopt | edge↔cloud sync, audit, allowlist |
| **Schema registry (Apicurio/Confluent)** | Adopt | ingest schema evolution across firmware generations |
| **Bytewax/Flink + River + dbt + MLflow** | Evaluate | the staged anomaly/predictive pipeline |
| **DuckDB** | Evaluate | edge ad-hoc Parquet queries |
| **Local signing daemon (Tauri/Rust, localhost socket, YubiKey PIV)** | Adopt | client-side command signing |
| **Tethered aerostat / hilltop relay** | Adopt | persistent RF relay (vs Spark, which is burst-only) |
| **Zenoh / rmw_zenoh** | Defer (Mark 2) | rover↔cloud transport; removes the stateful bridge |

---

## Prioritized action plan

1. **P0 — write 3 short ADRs and one doc fix this week:**
   (a) the **edge control-plane cache** (what it holds, who writes it, how the bridge reads it offline) — closes nonce authority + offline allowlist;
   (b) the **edge↔cloud sync contract** (event-sourced logs + HLC; allowlist/revocation = CRDT + human-merge);
   (c) the **reconnect handshake** (rover `pending-sync` until revocation-bundle ACK);
   (d) **doc fix:** retire "always-on LoRa e-stop" → "dead-man beacon"; firmware watchdog is the safe-stop.
2. **P1 — lock the data spine before Phase B:** edge QuestDB + cloud TSDB/Iceberg; store-and-forward durable queue + shedding tiers; event-time/watermark rule; egress field-tagging; CQRS bridge split; RBAC matrix; one-page RF link budgets + power-gating.
3. **P2 — before multi-site:** protocol N/N-1 serving + schema registry; edge HA + RTO; staged fault-detection ML (ship Stage-1 rules in v1).

**One-line verdict:** the topology is right and the security primitives are right; what's missing is the **stateful glue of an intermittently-connected distributed system** — durable nonce/allowlist at the edge, an event-sourced sync contract, a real store-and-forward queue, and a concrete data spine. Close the five P0 items and the design jumps from ~2.4 to ~4.

---

**Related:** [Command Center Application Blueprint](Command Center Application Blueprint.md) ·
[Deployment, Connectivity & Fleet Monitoring](Deployment, Connectivity & Fleet Monitoring.md) ·
[Command Center Protocol Security](../addendums/Command Center Protocol Security.md) ·
[Mark 1 Index](../Mark 1 Index.md)
