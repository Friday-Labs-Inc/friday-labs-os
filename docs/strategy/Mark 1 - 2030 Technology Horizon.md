# Mark 1 — 2030 Technology Horizon (Forward-Looking Tech Bets)

> It is **2026**; Mark 1 **launches 2030**. A 7-expert forward-looking panel
> (application · system · connectivity · radio/RF · cloud · data lake · data
> pipeline) was briefed on the Friday Labs vision + Mark 1 product spec and asked:
> *what technology will be mature, available, and affordable at a 2030 launch — so
> the product ships current, not obsolete?* This is the comparative roadmap.
>
> Companion to the current-state [7-Expert Comparative Analysis](../command-center/Architecture Review - 7-Expert Comparative Analysis.md).

---

## The governing principle (all 7 converged on this)

> **Lock the contracts. Build the implementations as swappable slots.**

The **invariants to freeze now**: the `friday_msgs` schema + QoS contract, the
signed-envelope security contract (Ed25519 / nonce / expiry), the authenticated
`issued_at` event-time, and an Iceberg/Arrow-native column schema. **Everything
below them — transport, silicon, inference runtime, broker, sync engine — will
turn over 1–2× before 2030.** Design each as a slot with a stable interface, and
2030 technology drops in without a rebuild. *Build slots, not bets.*

This is the single most important takeaway: a 2026 architecture that obeys this
rule reaches 2030 by **swapping components, not rewriting**.

---

## The 2030 bet, per dimension

| Dimension | 2030 bet | Build-toward NOW (on-ramp, not throwaway) | Avoid (legacy by 2030) |
|---|---|---|---|
| **Application** | Local-first + **agentic ops console**: one human supervises a fleet; an LLM copilot **drafts**, the human **signs** (signing = the circuit-breaker). | CRDT edge control-plane cache (SQLite/libSQL); make telemetry/faults LLM-queryable; passkeys for login + PIV/PKCS#11 for signing. | Cloud-first ops console; Frappe **Desk** as the live UI; InfluxDB 1/2 at edge. |
| **System design** | **Foundation-model-steered** offline autonomy: VLA-class models on NPU-class edge silicon; Zenoh fabric; **digital twin as ground truth**. | Inference as a **swappable slot** (signed model → `DetectedObjectArray`); harden the schema registry; treat the Gazebo twin as a first-class deliverable. | Coral as the *permanent* inference target; Gazebo Classic; ROS-distro-locked coupling. |
| **Connectivity** | **Eclipse Zenoh** as the unified rover↔edge↔cloud fabric over 5G-Advanced/NTN; MQTT becomes a backward-compat shim. | Map MQTT topics → Zenoh **key-expressions** now; WireGuard tunnels on every bearer; NATS JetStream as the edge store-and-forward spine. | Cloud-hosted broker on the control path; **DDS-over-WAN**; LoRa as a commanded path. |
| **Radio & RF** | **3GPP NTN direct-to-device LEO** = global low-rate safety/beacon path; **sub-GHz cognitive SDR MANET** = primary 20–30 km NLoS link; firmware watchdog = the safe-stop. | Pluggable **radio module socket** (Iridium/Globalstar as the 2026 NTN proxy); power-gate bearers (10 W budget); commodity 900 MHz MANET prototype. | "Always-on LoRa" anything; 5 GHz as the general NLoS forest bearer; $3–8k defense-priced MANET as the cost baseline. |
| **Cloud & distributed** | Productized **CRDT sync engine** (ElectricSQL/PowerSync-class) over a **WASM/WASI** edge runtime; **Verifiable Credentials** replace passwords. | Event-sourced logs + **HLC**; NATS JetStream leaf nodes; design the SQLite edge cache to slide under a sync engine; K3s + GitOps fleet mgmt. | Lambda architecture; cloud-broker-first MQTT; Kafka at the edge. |
| **Data feeding & lake** | **Apache Iceberg REST catalog + Arrow-native everything** = the de-facto open lakehouse; build every boundary to speak Arrow/Iceberg. | QuestDB at edge (ship before Phase B); bag→Parquet ETL with `protocol_*`/`customer_id`/`issued_at` partitions; reserve a NULL `embedding` column. | InfluxDB OSS/Flux; **Kafka**; **Delta Lake** as primary format (vendor-governed). |
| **Data pipeline & AI** | **Time-series foundation models** (Moirai/Chronos/TimesFM-class) run **zero-shot on-device** → fulfills "catch failure before the customer" with **no labeled data needed to ship**. | Kappa spine (NATS + Bytewax + dbt + MLflow); **River** online features on the Pi; event-time watermark; **start accumulating the fleet failure corpus**. | Lambda; cloud-only anomaly inference; fixed-schema ingest without a registry. |

---

## Cross-cutting consensus (named independently by ≥3 experts)

1. **Zenoh is the convergence transport** [App · System · Connectivity · Cloud] — it collapses the stateful MQTT bridge into one routable pub/sub fabric. Keep MQTT as a shim now, prep the key-expression namespace, **eval 2027, migrate at Mark 2.** Don't commit DDS-over-WAN.
2. **NATS JetStream NOW** [Connectivity · System · Cloud · Pipeline · Data] — the durable store-and-forward spine that bridges to the Zenoh future and closes the P1 queue gap. Lighter than Kafka.
3. **A hardware-agnostic inference slot** [System · App · Pipeline] — Coral is today's *target*, a dead-end by 2029. Speak ONNX Runtime / TFLite-delegate so 2028–30 NPUs (Orin successor, Hailo, Qualcomm, RISC-V) drop in. Design models *for the future slot*, quantize down to Coral as the current deployment.
4. **NTN direct-to-device satellite is the field-link game-changer** [Radio · Connectivity] — by 2028–29 NTN NB-IoT in mainstream modules makes a global low-rate safety beacon nearly free-on-chip, and may displace MANET for some profiles. Build the **pluggable radio socket** now.
5. **The failure-prediction promise is fulfilled by time-series foundation models** [Pipeline · Data] — zero-shot, no labels. **But you must start collecting the labeled fleet-failure corpus in 2026** (every `FaultReport` + 60 s pre-fault window → Iceberg), or you reach 2029 with nothing to train/validate on. *This is the highest-leverage non-technical action.*
6. **Local-first / CRDT sync engine** [App · Cloud] — the productized 2030 answer to the edge↔cloud sync P0 gap; build the SQLite edge cache now, schema-ready to slide under ElectricSQL/PowerSync later.
7. **AI copilot + the human-signs circuit-breaker** [App · System · Pipeline] — the economics of "one operator → 10–20 rovers." The signing boundary future-proofs the liability story.
8. **Iceberg + Arrow as the durable data substrate** [Data · Cloud · Pipeline] — survives engine churn; the data outlives whichever query engine wins.
9. **Digital twin as a first-class moat** [System] — the OTA regression harness + training-data generator + fleet replay surface, not a dev convenience.

---

## The 2026 → 2030 timeline (gates)

```
2026  NO-REGRET (start now):  NATS JetStream spine · QuestDB edge · Iceberg+Arrow boundaries ·
      event-time watermark on issued_at · WireGuard on every bearer · hardware-agnostic
      inference slot · CRDT edge cache (SQLite) · schema registry · MQTT->Zenoh key-expr map ·
      pluggable radio socket · LLM-queryable telemetry + signing boundary ·
      ** START THE FLEET FAILURE-DATA CORPUS **
2027  Zenoh/rmw_zenoh eval (tier-1 RMW gate) · Iridium/Globalstar NTN proxy · NPU-successor eval
2028  NPU swap (Coral -> Orin-successor/Hailo) · NTN direct-to-device modems · WebXR 3D console ·
      ElectricSQL/PowerSync sync engine · Zenoh in the CC-side bridge
2029  Time-series FM anomaly (zero-shot) into the slot · Verifiable Credentials · VLA-assist
      autonomy advisor · confidential-compute/TEE for defense
2030  LAUNCH: Zenoh fabric (Mark 2) · FM predictive maintenance live · one-operator-many-rovers
      copilot · NTN global safety beacon
```

---

## No-regret moves to start in 2026 (pure on-ramps, zero lock-in)

These are endorsed across the panel and throw nothing away even if a bet misses:

1. **NATS JetStream** as the store-and-forward spine.
2. **QuestDB** at the edge; **Iceberg + Arrow** at every data boundary.
3. **Event-time on `issued_at`** with a 24 h watermark.
4. **Hardware-agnostic inference slot** (ONNX/TFLite delegate).
5. **CRDT edge control-plane cache** (SQLite/libSQL) — also closes the P0 nonce/allowlist gap.
6. **Schema registry** keyed on `protocol_major`.
7. **WireGuard** tunnels; **map MQTT topics to Zenoh key-expressions**.
8. **Pluggable radio socket** (NTN-ready).
9. **Start the fleet failure-data corpus** — the one thing you cannot backfill later.

---

## Moonshots worth a design socket (not a bet)

Spark as a **persistent tethered relay + Zenoh leaf node + aerial mapper**;
**on-device VLA** for natural-language mission specs; **confidential-compute TEE**
for provable defense data custody; **multimodal/vector fleet memory** over Iceberg
(semantic search of everything every rover has ever seen); **federated on-device
learning**; **free-space-optical** Spark uplink.

---

## Verdict

The architecture is **well-positioned for 2030 *if* Friday Labs adopts "lock
contracts, build slots" as an explicit, enforced design rule.** The interface-first
foundation already built (`friday_msgs`, signed envelopes, lifecycle agents) is
exactly the right invariant — it is the asset that lets everything else be swapped.

The biggest strategic action is **non-technical and time-sensitive: begin
accumulating the labeled fleet failure-data corpus in 2026.** The 2029
foundation-model predictive-maintenance capability — the literal "detect a failure
before the customer notices" promise — depends on data you can only gather by
running rovers in the field for years. Everything else can be bought or swapped in
2029; three years of field failures cannot.

---

**Related:** [7-Expert Comparative Analysis (current state)](../command-center/Architecture Review - 7-Expert Comparative Analysis.md) ·
[Command Center Application Blueprint](../command-center/Command Center Application Blueprint.md) ·
[Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) ·
[AI Inference Location](../addendums/AI Inference Location.md) ·
[Mark 1 Index](../Mark 1 Index.md)
