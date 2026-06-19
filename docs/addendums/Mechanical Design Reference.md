# Mechanical Design Reference

> Locks the NASA Perseverance rover as the mechanical-anatomy reference for [Mark 1](../architecture/Mark 1 Compute Architecture.md). Establishes which Perseverance features transfer to the Mark 1 prototype and which do not. Closes the chassis-design ambiguity in the dossier.
> **Version:** Draft 1.0 · **Purpose:** Lock the mechanical reference before chassis procurement or CAD work.

## Decision

The Mark 1 rover's mechanical anatomy is modeled on the **NASA Perseverance rover**, scaled to the [60-90 cm bench prototype envelope](Power Budget.md). This is not a mission-feature parity claim — Mark 1 is not a Mars science rover — it is a *chassis kinematics and proportions* reference. The Perseverance design has decades of JPL engineering behind it and an extensive open-source educational lineage.

## What Transfers from Perseverance

| Feature | How Mark 1 inherits it |
|---|---|
| **Six-wheel rocker-bogie suspension** | The iconic JPL pattern. Mechanical "averaging" keeps all six wheels in contact with uneven terrain without active suspension control. |
| **Independent wheel drive** | Each of the 6 wheels has its own motor. Allows differential speed control for turns and for the zero-radius Z-turn. |
| **Corner-only steering** | The 4 corner wheels (front-left, front-right, rear-left, rear-right) have steering servos. The 2 middle wheels are drive-only with no steering. This is the key Perseverance pattern and a revision to the dossier's earlier "all 6 steer" assumption. |
| **Body-mounted sensor mast** | Core's nav sensor (RealSense D435i) and the baseline camera (Arducam IMX477) live on a mast, analogous to Mastcam-Z on Perseverance. Elevation above ground clutter for nav and inspection. |
| **Box-shaped electronics body** | Compute and battery enclosed in the body. Insulation and active thermal control are not Mark 1 concerns at bench-prototype scale (Earth ambient vs Mars cold). |
| **Rear-mounted power compartment** | Battery (LiPo on Mark 1) at the rear, replacing Perseverance's MMRTG. |
| **General proportions** | Mast height, body length, wheelbase ratios scaled to ~25-30% of Perseverance's full size. |

## What Does NOT Transfer

| Perseverance feature | Why not |
|---|---|
| Multi-Mission Radioisotope Thermoelectric Generator (MMRTG) | Mark 1 uses LiPo battery per [Power Budget](Power Budget.md). Nuclear power not applicable. |
| Sample caching system | Out of scope. Mark 1 does not preserve samples for return. |
| Specific scientific instruments (SHERLOC, PIXL, MOXIE, SuperCam, Mastcam-Z, etc.) | Mark 1's payload is plug-and-play research sensors via the [Lab Deck](../modules/Adaptive Research Module.md), not specific Mars instruments. |
| Robotic arm with turret | Out of scope. Mark 1 does not manipulate samples. |
| Ingenuity helicopter | Replaced by **Spark** on Mark 1 — same role (aerial scout), different design. |
| Aluminum cleated wheels with grousers | Mark 1 uses commercially available rubber-tired wheels appropriate to bench testing. Cleat design may be revisited if outdoor traction becomes an issue. |
| Size and mass | Mark 1: 60-90 cm, ~5-10 kg. Perseverance: 3 m × 2.7 m × 2.2 m, 1025 kg. We scale proportions, not absolute dimensions. |
| Thermal protection (Mars cold) | Mark 1 operates in Earth ambient. Standard IP weather sealing only; no insulation. |
| Sky-crane landing system | We have legs and casters, no rocket sky-crane. |

## Actuator Count Implications

The Perseverance corner-only steering pattern gives Mark 1:

- **6 drive motors** (one per wheel, all driven independently).
- **4 corner steering servos** (one per corner wheel; middle wheels do not steer).
- **Total: 10 actuators** controlled by the [Locomotion Control Unit](../modules/Locomotion Control Unit.md).

This revises the original "12 actuators" assumption from the first Locomotion questionnaire pass. Saves $30 in servo BOM and 2 firmware PWM channels.

## Maneuvering Modes (All Four Inherited from Perseverance)

Mark 1 supports the same four locomotion modes Perseverance does:

| Mode | Corner steer position | Drive behavior |
|---|---|---|
| **Forward / reverse** | Corners straight | All 6 wheels in sync |
| **Ackermann turn** | Corners angled to define the arc | Outside wheels faster than inside |
| **Crab walk (lateral)** | All 4 corners at 90° in same direction | All wheels drive in unison; rover translates sideways |
| **Zero-radius Z-turn** | Corners angled inward toward rover center | Left side and right side counter-rotate; rover spins in place |

These four cover every maneuver Mark 1 needs: row navigation in agriculture, narrow forest paths, surveillance repositioning, and tight in-place reorientation. The middle wheels not steering does NOT reduce the maneuver set.

## Reference-Model Scaling

A NASA Perseverance 3D mesh is committed at `Mechanics/reference-models/perseverance/converted/` (via git-LFS) and loaded in Blender (BlenderMCP) for chassis/suspension study. To bring it to Mark 1 prototype scale, **anchor on the locked 130 mm wheel diameter** ([Locomotion Deck — Build Package](../build/Locomotion Deck - Build Package.md)).

- Real Perseverance wheel diameter: **525 mm** (Curiosity is 500 mm — verify against the model's source).
- Uniform scale factor: **130 / 525 = 0.2476** (≈ 1:4.04, ~25% — refines the "~25-30%" proportion note above).

| Dimension | Real Perseverance | Mark 1 at 0.2476× |
|---|---|---|
| Wheel diameter | 525 mm | **130 mm** (anchor) |
| Body length | ~3.0 m | ~743 mm |
| Width | ~2.7 m | ~668 mm |
| Height (mast top) | ~2.2 m | ~545 mm |

The ~743 × 668 mm footprint sits inside the [60-90 cm envelope](Power Budget.md) — confirming the 130 mm wheel and the prototype size are geometrically consistent.

**Applying it (Blender / CAD):** uniform scale X = Y = Z. The 0.2476 factor assumes the mesh imported at real-world scale; downloaded meshes often don't. Robust procedure:

1. Measure the model's current wheel diameter in its own units.
2. `scale = 130 / measured_wheel_mm` — 0.2476 if it reads 525 mm; scale *to* 0.130 if it reads 0.525 m; otherwise divide 130 by whatever the wheel measures.
3. Sanity-check: overall length should land ~743 mm. If it's wildly off, the mesh isn't true-proportion — re-anchor on body length and flag.

**Caveats:** confirm the 525 mm real-wheel figure against the model's source, and remember a decorative downloaded mesh may not be dimensionally faithful — measure, don't assume.

## Reference Designs to Evaluate

Open-source Perseverance-inspired rovers the team should evaluate before committing to custom CAD:

- **JPL Open Source Rover (OSR)** — NASA's official educational rover. ~$2,500 BOM. Mature, well-documented, runs ROS. Direct Perseverance lineage. Right scale; high cost.
- **Sawppy the Rover** (Roger Cheng) — Curiosity / Perseverance-style 6-wheel rocker-bogie. ~$500 BOM. 3D-printable. Accessible, well-trodden community path.
- **Curio Rover** — Perseverance-replica 3D-printable design (referenced in [Locomotion Control Unit](../modules/Locomotion Control Unit.md) open items). Educational-scale.

Recommendation: evaluate **Sawppy** or **Curio** first for cost reasons. Commit to OSR only if a specific feature is missing from those.

## Mast and Sensor Mounting

The Perseverance-inspired mast carries:

- Core's RealSense D435i nav sensor (mast head, tilted forward).
- Baseline Arducam IMX477 camera (mast head, forward).
- Optional pan/tilt servo for nav-camera sweeping (Mark 2).

The Lab Deck's research LiDAR (Slamtec RPLIDAR A3) mounts mid-body, lower than the mast, for ground-level scanning at agricultural row height.

Final mast height to be locked once the chassis kit is selected — proportionally ~30-40% of total rover height per Perseverance proportions.

## Open Items

- **Specific chassis kit selection** (Sawppy / Curio / OSR / custom CAD) — Phase 1 hardware.
- **Wheel design** (3D-printed Perseverance replica vs commercial rubber wheels) — terrain-dependent; commercial rubber for initial bench testing.
- **Mast height and exact sensor mounting layout** — refined during integration once chassis is in hand.
- **Whether to add a pan/tilt servo** at the mast head — defer to Mark 2 unless a specific mission needs it.
- **IP rating** for outdoor operation — locked once the body enclosure is selected.

## Acceptance Criteria

- The mechanical assembly performs all four locomotion modes (forward, Ackermann, crab walk, Z-turn) on bench, verified visually and by odometry trace.
- Rocker-bogie maintains all 6-wheel ground contact over a 5 cm step.
- Mast remains stable (no significant resonant vibration) at 1 m/s travel.
- Final dimensions fall within the 60-90 cm bench-prototype envelope from [Power Budget](Power Budget.md).

## Related

[Locomotion Control Unit](../modules/Locomotion Control Unit.md) · [Sensor Ownership](Sensor Ownership.md) · [Power Budget](Power Budget.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Simulation and Dev Environment](../architecture/Mark 1 Simulation and Dev Environment.md) · [Mark 1 Index](../Mark 1 Index.md)
