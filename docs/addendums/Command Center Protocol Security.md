# Command Center Protocol Security

> Authentication, signing, and replay protection for the external link between the [Telemetry Command Node](../architecture/Telemetry Command Node.md) and the Command Center. Closes the only external attack surface in Mark 1.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 / Phase 2 security gap before any cellular field test.

## Decisions

| Parameter | Value |
|---|---|
| **Transport** | MQTT 5 over TLS 1.3 |
| **Authentication** | Mutual TLS (mTLS) with per-rover client certificates |
| **Per-command auth** | Ed25519 signature over `(payload \|\| nonce \|\| rover_id \|\| expiry)` |
| **Operator keys** | Per-operator signing key, allowlisted on each rover |
| **Replay protection** | Monotonic nonce per `(operator, rover)` pair, expiry on every command |
| **Payload encoding** | CBOR (compact, schema'd, smaller than JSON) |
| **Default command expiry** | 30 seconds |

## Why mTLS + Signing, Not Just TLS

TLS alone authenticates the transport. Signing authenticates the *command*. Both are required because:

- TLS is terminated at the MQTT broker — if the broker is compromised, TLS doesn't help.
- A misconfigured Telemetry Node could accept connections from the wrong Command Center.
- Operator-action audit needs a per-operator signature, not just a per-rover connection.

## Topic Structure

```
mark1/<rover_id>/cmd/<class>         operator → rover  (commands)
mark1/<rover_id>/tlm/<class>         rover → operator  (telemetry)
mark1/<rover_id>/dbg/<class>         rover → operator  (debug stream, deprioritized)
mark1/<rover_id>/ack/<msg_id>        rover → operator  (command acknowledgments)
```

Command classes are tied to the `friday_msgs` mapping in **Command Center Protocol Mapping** (to be drafted alongside `command-validation-service`).

## Payload Envelope

Every payload, in both directions, carries:

```
{
  protocol_version: { major, minor, patch },
  rover_id: string,
  sender_id: string,          # operator id (cmd) or "rover" (tlm)
  msg_id: uint64,             # monotonic per sender
  nonce: uint64,              # monotonic per (sender, rover) pair
  issued_at: timestamp,
  expires_at: timestamp,
  payload: <CBOR-encoded friday_msgs equivalent>,
  signature: bytes            # Ed25519 over the above
}
```

## Rejection Behavior

The Telemetry Node Agent rejects and logs any command where:

| Failure | Behavior |
|---|---|
| Invalid TLS client cert | Connection dropped, log + alert operator |
| `rover_id` mismatch | Drop, log, alert |
| Signature invalid | Drop, log as `FaultReport` with `category=SECURITY_AUTH`, alert |
| Nonce ≤ last seen for this `(operator, rover)` | Drop, log as `FaultReport` with `category=SECURITY_REPLAY`, alert |
| `expires_at` in the past | Drop, log, alert (likely network delay or clock skew) |
| Unknown `sender_id` (operator not in allowlist) | Drop, log, alert |
| Mismatched protocol major | Drop, log, alert |

Rejected commands are **never** executed, **never** queued for later, and **never** silently ignored.

## Key Management

### Rover-Side (Certificates and Allowlists)

- Each rover has a unique TLS client certificate, signed by a Friday Labs CA, with the rover's `module_id` in the CN.
- Each rover stores an allowlist of operator public keys (`/etc/mark1/operators.json`), signed by the CA.
- Allowlist updates are themselves signed commands and follow the normal rejection rules.

### Operator-Side

- Each operator has a personal Ed25519 keypair. The private key never leaves their workstation or HSM.
- Operator keys are registered with the CA and signed onto each rover's allowlist.

### Rotation

- **Rover TLS certs:** valid 2 years, rotate annually. Rotation is a signed command pushing a new cert + key to the rover.
- **Operator keys:** rotate annually, or immediately on suspected compromise.
- **CA root:** valid 10 years. Compromise = catastrophic; CA root stored offline.

### Revocation

- On suspected operator key compromise: a signed `RevokeOperator` command is pushed to all rovers. Each rover removes the key from its allowlist.
- A rover offline at revocation time receives the update on next reconnect, before processing any commands.
- Tracking which rovers have received the revocation is a Command Center responsibility, not a rover responsibility.

## LoRa Fallback

LoRa is a low-bandwidth channel and cannot carry full TLS handshakes. Emergency-stop authority via LoRa:

- Pre-shared symmetric key per rover, derived from the rover's TLS cert at provisioning time.
- Only a small whitelist of message types is permitted over LoRa: emergency_stop, status_ping, beacon.
- LoRa-delivered commands carry their own nonce + signature (HMAC-SHA256 with the pre-shared key).
- Replay protection is enforced separately for the LoRa channel (different nonce sequence).

## Debug Stream Isolation

The debug stream uses a separate topic class (`mark1/<rover>/dbg/...`) and a separate MQTT broker priority. Mission-critical traffic always preempts debug. Debug stream is signed and encrypted just like everything else — there are no "trusted" unauthenticated channels.

## Acceptance Criteria

- Replay attack test: capture a valid signed command, replay 60 s later. Must be rejected.
- Forged signature test: alter one byte of a valid command. Must be rejected.
- Wrong-rover test: send a command intended for `MARK1-002` to `MARK1-001`. Must be rejected at the rover.
- Revoked-operator test: revoke key, then attempt a command signed with it. Must be rejected.
- Performance: signature verification at the Telemetry Node Agent adds ≤ 5 ms p99 to command processing.

## Open Items

- Specific Friday Labs CA setup (provisioning workflow, hardware HSM for CA root).
- Operator workstation tooling for signing — a small CLI tool to wrap commands in the envelope.
- Whether to support hardware security keys (YubiKey class) for operator signing — recommended yes, deferred to Phase 2 implementation.

## Related

[Telemetry Command Node](../architecture/Telemetry Command Node.md) · [Authority Lease Protocol](Authority Lease Protocol.md) · [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
