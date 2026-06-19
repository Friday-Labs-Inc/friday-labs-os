# Spark Authority and friday-core-os Definition

> Two small clarifications: what authority the [Aerial Companion Bay](../architecture/Mark 1 Compute Architecture.md#module-5-aerial-companion-bay) actually has over **Spark** in flight, and what `friday-core-os` is as a software unit.
> **Version:** Draft 1.0 · **Purpose:** Closes two definitional gaps before the pending Aerial Companion Bay spec and any service implementation.

## Spark Flight Authority

### What the Bay Can Enforce

- Whether Spark is permitted to **launch** — preconditions: rover stationary, area clear, Spark battery > threshold, bay mechanism healthy.
- Whether Spark is permitted to **dock** — bay clear, docking lock available.
- Charging start/stop on the dock.
- Issuing a `RETURN` *request* to Spark.

### What the Bay Cannot Enforce

- **Mid-flight behavior.** Once Spark is airborne, Spark's own flight controller is the authority. The Bay cannot remotely lock controls, force a hover, or override Spark's onboard safety logic.
- **"Abort mid-flight"** in any meaningful sense. The Bay can request that Spark return immediately; Spark decides whether to honor the request based on its own state (battery, altitude, geofence).
- **No-fly enforcement.** Geofences are programmed into Spark's flight controller, not enforced from the rover.

### Implication for the Bay Spec

The Aerial Companion Bay spec (pending, to be written via the [module-spec](../../.claude/skills/module-spec/SKILL.md) skill) must be honest about this: the Bay is the **launch/dock physical interface and ground-side coordinator**, not the flight brain. `SparkMissionRequest` is a request to Spark, not a command — Spark is the source of truth for whether and how the mission proceeds.

### Pre-Launch Interlocks (Bay Authority)

The Bay's `bay-safety-checker` service holds these. Launch is refused unless all pass:

1. Rover is at zero velocity.
2. Rover is on stable ground (IMU tilt < threshold).
3. Bay is open and clear (no obstruction sensors triggered).
4. Spark is docked and locked.
5. Spark reports battery ≥ launch threshold (default 70%).
6. Spark reports system health OK.
7. No active fault on the Lab Deck (Spark relies on its sensor data for some missions).
8. Operator has explicitly authorized the launch (per-mission consent, not standing).

Any fail = launch refused, fault logged, operator notified.

## friday-core-os Definition

The original dossier names `friday-core-os` as a service but never defines what it is. Locking:

**`friday-core-os` is the systemd target** that owns the lifecycle of all Friday Labs OS services on the Core Compute Hub. It is not itself a service — it is the unit that brings the services up in the correct dependency order at boot and tears them down on shutdown.

```
friday-core-os.target
├── module-registry.service
├── system-health-manager.service
├── command-router.service
├── safety-supervisor.service
├── fault-manager.service
├── authority-lease-service.service
├── logging-service.service
├── mission-planner.service          (After=module-registry)
├── autonomy-manager.service          (After=mission-planner)
└── sensor-fusion-manager.service     (After=module-registry)
```

A Telemetry-side equivalent (`friday-telemetry-os.target`) owns the analogous service group on the Telemetry Command Node.

Each `.service` is a managed unit. systemd restarts on crash, subject to a crash-loop guard: 5 restarts in 60 s escalates to a `FaultReport` rather than continuing to thrash.

## Related

[Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Authority Lease Protocol](Authority Lease Protocol.md) · [module-spec](../../.claude/skills/module-spec/SKILL.md) · [Mark 1 Index](../Mark 1 Index.md)
