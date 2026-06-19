---
name: command-center-protocol
description: Author or validate the external Command Center protocol mapping that bridges `friday_msgs` to the Command Center over an MQTT-class transport. Use when designing the external boundary, validating auth/signing/replay protections, or reviewing a Telemetry Node Agent change. Refuses to specify a protocol that lacks authentication, nonces, or a defined behavior on unsigned commands.
---

# Command Center Protocol

The Command Center link is the only external attack surface in Mark 1. DDS is LAN-oriented and unsuited for public cellular; the Telemetry Node Agent is the translator. This skill keeps the boundary specification honest.

Reference: `Telemetry Command Node.md`; `ROS 2 Interface and Message Contract.md` (External Boundary section).

## Non-negotiable security controls

A spec without all of these is rejected by this skill:

1. **Mutual TLS** between Telemetry Node Agent and Command Center, with certificates pinned per rover identity (`MARK1-TEL-001` etc.).
2. **Command signing.** Every command from Command Center carries a signature over `(payload || nonce || rover_id || expiry)`, verified against an allowlisted operator key set on the Node.
3. **Monotonic nonces.** Per-operator, per-rover. Replay rejected.
4. **Expiry on every command.** Default 30 s; rejected past expiry. No "permanent" commands.
5. **Defined behavior on unsigned / invalid-signature commands.** Drop, log to `FaultReport`, alert operator. Never execute, never queue.
6. **SIM / modem security.** SIM PIN, APN-locked data path, IMEI allowlist on the carrier side where supported.

## Protocol shape

- Transport: MQTT 5 (or equivalent broker-based MQTT-class). Not raw TCP, not HTTP polling.
- Topic namespace: `mark1/<rover_id>/cmd/<class>` (operator → rover) and `mark1/<rover_id>/tlm/<class>` (rover → operator).
- Payload encoding: CBOR or Protobuf (compact, schema'd) — not JSON, not raw `friday_msgs` serialization.
- Each payload carries: `protocol_version`, `nonce`, `expiry`, `signature`, `payload`.

## Mapping to friday_msgs

The Telemetry Node Agent translates between the two vocabularies. Document each pair:

| Internal (`friday_msgs`) | External (CC protocol topic + payload) | Direction | Required signing |
|---|---|---|---|
| `EmergencyStop.msg` | `mark1/<id>/cmd/emergency_stop` | CC → rover | yes (separate operator key class) |
| `RecoveryCommand.msg` | `mark1/<id>/cmd/recovery` | CC → rover | yes |
| `MotionCommand.msg` (manual mode only) | `mark1/<id>/cmd/manual_motion` | CC → rover | yes |
| `MissionStatus.msg` | `mark1/<id>/tlm/mission` | rover → CC | rover-signed |
| `HealthStatus.msg` summary | `mark1/<id>/tlm/health` | rover → CC | rover-signed |
| `FaultReport.msg` | `mark1/<id>/tlm/fault` | rover → CC | rover-signed |
| Debug stream (separate endpoint) | `mark1/<id>/dbg/...` | rover → CC | rover-signed, lower priority |

If the operator proposes a mapping for a `friday_msgs` interface not in the table, ask whether the new entry needs a fresh operator-key class.

## Procedure

1. Enumerate every command class the spec proposes.
2. For each, confirm the six controls above.
3. Define the per-class authentication: which operator key signs it, what privilege class.
4. Walk a replay attack: capture a valid signed command, replay 60 s later. Spec must reject on expiry; if it does not, the spec is incomplete.
5. Walk a malformed-signature case: alter one byte. Spec must reject and log.
6. Walk a no-network case: command queue must drop expired entries without leaking memory.
7. Define the debug-stream endpoint as **isolated** from mission telemetry — separate topic class, deprioritized, never blocks critical alerts.

## Open questions the operator must answer before sign-off

- Key rotation schedule and procedure for both rover-side and operator-side keys.
- Revocation: how does the rover learn an operator key is revoked while offline?
- LoRa fallback for emergency-stop authority: how is signing handled on a low-bandwidth channel?
- Carrier-side controls available (IMEI allowlist, APN restriction).

## Acceptance

- Every command class in the spec maps to one of the six controls explicitly. No "TBD" on auth.
- Replay attack walk-through is in the spec, with the rejection step named.
- A "what happens with an unsigned command" subsection exists and answers: drop + log + alert.
- Debug stream is documented as isolated and deprioritized.

## What this skill refuses to do

- Write a spec with HTTPS polling instead of a broker — control-plane latency will be wrong.
- Write a spec that punts auth to "Phase 2."
- Write a spec where the same operator key signs both routine telemetry pulls and emergency-stop / reboot commands.
- Use JSON for the wire format and call it "future-proof."
