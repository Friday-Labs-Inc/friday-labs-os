---
name: module-spec
description: Generate a standalone module spec in the house style of the existing Telemetry Command Node doc. Use to fill the gap of the missing Locomotion Control Unit, Adaptive Research Module, or Aerial Companion Bay specs. Produces a draft that matches the section order, depth, and discipline of the existing dossier.
---

# Module Spec Generator

The Mark 1 dossier has standalone specs for the Telemetry Command Node, the OS, the compute architecture, the interface contract, and the sim environment. The three module specs marked pending in [Mark 1 Index.md](Mark 1 Index.md) — Locomotion Control Unit, Adaptive Research Module, Aerial Companion Bay — need to be written in the same house style.

Reference (read before generating): `Telemetry Command Node.md` — it is the model for tone, depth, and section order.

## House style rules

- **First line is a blockquote** describing the doc's role in the dossier, with backlinks to `Mark 1 Compute Architecture` and `Friday Labs OS Architecture`.
- **Version/purpose/reports-to** on the second line of the blockquote.
- Sections in this order: Role · Hardware Direction · Core Principle · Internal Layers · Module-specific responsibilities · Software Services · Failover Behavior · Message Types Handled · Provisioning · Open Design Areas · Related links.
- Use the `[[Wiki Link]]` Obsidian convention for inter-doc links — match the existing dossier.
- No emoji. No marketing language. Engineering register.
- Prefer prose over bulleted-fragments where the prose reads cleanly; bullets when listing capabilities/responsibilities.
- Close with `---` and a `Related:` line listing the immediate neighbors in the dossier.

## Inputs

Ask before generating:

1. **Which module:** Locomotion Control Unit | Adaptive Research Module | Aerial Companion Bay
2. **Any locked decisions** the spec must reflect (board choice, sensor list, real-time guarantees).
3. **Any open questions** that should land in the Open Design Areas section vs. be resolved inline.

## Per-module checklists — sections the spec must cover

### Locomotion Control Unit

- Real-time motor/steering/encoder/IMU control loop
- Independent firmware watchdog for safe-stop (the doc must call this out as primary, not a fallback)
- Lost-comms behavior — clamp motors, lock brake, hold steering, continue heartbeats at degraded rate
- micro-ROS / Micro XRCE-DDS bindings to `friday_msgs` (note bridge-independence for safe-stop)
- Movement commands accepted: MOVE, STOP, TURN, SET_VELOCITY, SET_STEER, PATH_SEGMENT, SAFE_STOP
- Odometry publication rate + frame conventions (`base_link`, `odom`)
- Wheel-stall and traction-monitoring outputs
- Power-state coordination with the Core Hub

### Adaptive Research Module / Lab Deck

- Plug-and-play sensor discovery protocol (this is currently a documented open question — surface it)
- Sensor ownership model: which sensors does the Lab Deck own, which does Core Hub borrow via stream, which are dedicated to nav?
- Local processing pipeline: capture → preprocess → derive decision-level outputs (`MapSegment`, `DetectedObjectArray`, `CoverageProgress`)
- Local research-data logging (volume, retention, when to stream up)
- Hot-swap policy: can sensors swap mid-mission? If yes, how does the registry update?
- Failure mode if Lab Deck dies: does Core navigation degrade gracefully? (This is a known design gap — call it out.)

### Aerial Companion Bay

- Physical interface only — flight authority lives on Spark itself
- Launch / dock / charge / secure state machine
- Pre-launch safety interlocks (rover stationary, area clear, Spark battery > threshold)
- Relays `SparkMissionRequest` to Spark; reports `SparkStatus` to Core Hub
- Reject rover-motion while Spark is mid-launch or mid-dock
- Mid-air abort: what can the Bay actually enforce? (Likely nothing — be honest in the spec.)

## Procedure

1. Read `Telemetry Command Node.md` end-to-end to internalize the style.
2. Confirm the locked-decisions and open-questions inputs from the operator.
3. Draft each section in order, cross-linking to `friday_msgs` interfaces where relevant.
4. End with a candid Open Design Areas section — under-specifying is fine; pretending things are resolved is not.
5. Add the `Related:` line.

## Acceptance

- Section count and order match the Telemetry Command Node doc.
- All cross-references use `[[Wiki Link]]` syntax.
- Every claim about a `friday_msgs` interface points to a message that actually exists (or flags one that must be added).
- Open design questions are stated as questions, not as solutions.

## What this skill refuses to do

- Generate a spec that omits the Open Design Areas section.
- Make up a sensor list, motor controller, or board for the operator without asking.
- Use the words "robust", "best-in-class", "cutting-edge" — engineering register only.
