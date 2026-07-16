# Mechanical Design Reference

> Locks the NASA Perseverance rover as the mechanical-anatomy reference for [Mark 1](../architecture/Mark 1 Compute Architecture.md). Establishes which Perseverance features transfer to the Mark 1 prototype and which do not. Closes the chassis-design ambiguity in the dossier.
> **Version:** Draft 1.2 · **Purpose:** Lock the mechanical reference before chassis procurement or CAD work.
> **1.2 (2026-06-30) — WHEEL REVERTED TO 130 mm.** The creator of the source rover
> (HowToMechatronics) confirmed the model was scaled to a **130 mm wheel diameter** and
> built around that wheel + the chosen servos/DC motors, with **no proportion calculations**.
> So the 1.1 "re-anchor to 743 mm / 140 mm / 0.2668×" (a Blender GLB re-measurement) is
> **dropped as over-derived**. The **dimensional source of truth is now the in-repo DIY CAD**
> (`../../Mechanics/reference-models/howtomechatronics-replica/` — STEP + 105 STLs; the parts
> being printed), with exact tube/profile dims to follow from the creator. Wheel = **130 mm**
> (the printed wheel STL measures ~133.6 mm outer incl. tread → use that as the rolling
> diameter for odometry); scale ≈ **0.247×**. Body/wheelbase/track below are the 140 mm-era
> figures rescaled ×130/140 — **confirm against the DIY CAD**, don't treat as exact.
> **1.1 (2026-06-19) — SUPERSEDED by 1.2.**

## Decision

The Mark 1 rover's mechanical anatomy is modeled on the **NASA Perseverance rover**, scaled to the [60-90 cm bench prototype envelope](Power Budget.md). This is not a mission-feature parity claim — Mark 1 is not a Mars science rover — it is a *chassis kinematics and proportions* reference. The Perseverance design has decades of JPL engineering behind it and an extensive open-source educational lineage.

**Locked build target:** the **HowToMechatronics Perseverance replica at its native size — 130 mm wheel** (creator-confirmed; scale ≈ **0.247×** of the real 526 mm wheel). Body envelope ≈ **690 × 670 × 553 mm** (the 140 mm-era 743 × 722 × 596 rescaled ×130/140 — **confirm off the in-repo DIY CAD**), within the [60-90 cm envelope](Power Budget.md). The JPL OSR is the rocker-bogie **mechanism donor**, but its compact native proportions are **not** adopted: holding true Perseverance proportions means a **partly-custom frame**, re-proportioned in CAD, rather than the stock OSR-kit dimensions. The scaled Perseverance mesh is therefore the build's dimensional reference (see [Reference-Model Scaling](#reference-model-scaling)).

## What Transfers from Perseverance

| Feature | How Mark 1 inherits it |
|---|---|
| **Six-wheel rocker-bogie suspension** | The iconic JPL pattern. Mechanical "averaging" keeps all six wheels in contact with uneven terrain without active suspension control. |
| **Independent wheel drive** | Each of the 6 wheels has its own motor. Allows differential speed control for turns and for the zero-radius Z-turn. |
| **Corner-only steering** | The 4 corner wheels (front-left, front-right, rear-left, rear-right) have steering servos. The 2 middle wheels are drive-only with no steering. This is the key Perseverance pattern and a revision to the dossier's earlier "all 6 steer" assumption. |
| **Body-mounted sensor mast** | Core's nav sensor (RealSense D435i) and the baseline camera (Arducam IMX477) live on a mast, analogous to Mastcam-Z on Perseverance. Elevation above ground clutter for nav and inspection. |
| **Box-shaped electronics body** | Compute and battery enclosed in the body. Insulation and active thermal control are not Mark 1 concerns at bench-prototype scale (Earth ambient vs Mars cold). |
| ~~Rear-mounted power compartment~~ **→ Centered battery** | **Superseded (2026-06-19):** the 4S Li-ion battery is **centered** as the CG anchor (top-loading hatch), not rear. Central placement makes the balance insensitive to the light modules; the rear-power = RTG-analog nod is dropped for balance. See [Deck Layout, Sizing & CG](../build/Deck Layout, Sizing and CG.md). |
| **General proportions** | Mast height, body length, wheelbase ratios held at **true Perseverance proportions, 0.2668× scale** (≈27%); see [Reference-Model Scaling](#reference-model-scaling). |

## What Does NOT Transfer

| Perseverance feature | Why not |
|---|---|
| Multi-Mission Radioisotope Thermoelectric Generator (MMRTG) | Mark 1 uses LiPo battery per [Power Budget](Power Budget.md). Nuclear power not applicable. |
| Sample caching system | Out of scope. Mark 1 does not preserve samples for return. |
| Specific scientific instruments (SHERLOC, PIXL, MOXIE, SuperCam, Mastcam-Z, etc.) | Mark 1's payload is plug-and-play research sensors via the [Lab Deck](../modules/Adaptive Research Module.md), not specific Mars instruments. |
| Robotic arm with turret | Out of scope. Mark 1 does not manipulate samples. |
| Ingenuity helicopter | Replaced by **Spark** on Mark 1 — same role (aerial scout), different design. |
| Aluminum cleated wheels with grousers | Mark 1 uses commercially available rubber-tired wheels appropriate to bench testing. Cleat design may be revisited if outdoor traction becomes an issue. |
| Absolute size and mass | Mark 1: **~74 cm body (0.2668× scale), ~11 kg**. Perseverance: 3 m × 2.7 m × 2.2 m, 1025 kg. We hold true proportions at 0.2668× scale, not absolute dimensions. |
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

A NASA Perseverance 3D mesh is committed at `Mechanics/reference-models/perseverance/converted/` (via git-LFS) and loaded in Blender (BlenderMCP). **Mark 1 holds true Perseverance proportions, so the scaled mesh is the build's dimensional reference — not just a study aid.** To bring it to Mark 1 prototype scale, **anchor on the locked 743 mm body length** — which yields a **140 mm wheel** (see below; cf. [Locomotion Deck — Build Package](../build/Locomotion Deck - Build Package.md)).

- Real Perseverance wheel diameter: **526 mm** (20.7 in, per NASA/JPL — **verified** against the GLB mesh, which measures 0.526 m; Curiosity is 500 mm).
- Measured Perseverance wheel-span on the GLB mesh: **2.785 m** (not the rounded 3.0 m once assumed).
- Uniform scale factor: **743 mm / 2785 mm = 0.2668** (≈ 1:3.75, ~27%), anchored on body length — yields a **140 mm wheel** (0.526 m × 0.2668).

> ⚠️ **Superseded by v1.2 (2026-06-30):** the build target is the **130 mm wheel** of the
> HowToMechatronics replica (creator-confirmed, no calculations). The 0.2668× / 743 mm / 140 mm
> derivation in this section is kept as history but is **NOT** the build size. Source of truth =
> the in-repo DIY CAD (`../../Mechanics/reference-models/howtomechatronics-replica/`).

| Dimension | Real Perseverance (GLB mesh) | Mark 1 at ≈0.247× (130 mm wheel) |
|---|---|---|
| Wheel diameter | 526 mm | **130 mm** (creator-confirmed; ~133.6 mm printed incl. tread) |
| Body length (wheel-span) | 2.785 m | ≈ **690 mm** (confirm off DIY CAD) |
| Width (track, outer) | 2.705 m | ≈ 670 mm (confirm off DIY CAD) |
| Height (mast top) | 2.232 m | ≈ 553 mm (confirm off DIY CAD) |

The ~743 × 722 mm footprint sits inside the [60-90 cm envelope](Power Budget.md) — confirming the 140 mm wheel and the prototype size are geometrically consistent.

**Applying it (resolved 2026-06-19).** The mesh was *measured* in Blender, not assumed: wheel Ø = 0.526 m (matches NASA's 526 mm — the mesh is dimensionally faithful) and wheel-span = 2.785 m. Anchoring on the **743 mm body-length** target gives uniform scale **0.2668×** (X = Y = Z), yielding a **140 mm wheel**.

**(Superseded — see v1.2 at the top.)** This paragraph argued for a *140 mm* wheel by anchoring on a 743 mm body from the GLB mesh. That is **dropped**: the creator confirms the source model is a **130 mm wheel** built around the wheel + servos/motors with **no proportion calculations**, so the in-repo DIY CAD — not a GLB-mesh re-scaling — is the size of record. Working file: `Mechanics/reference-models/perseverance/converted/perseverance_rolling_chassis.blend` (deck + rocker-bogie + 6 wheels; payload stripped).

**Derive the remaining build dimensions from the scaled mesh.** Because Mark 1 holds true proportions, there is no separate OSR dimension to reconcile against — the scaled model *is* the spec. Measured off the working file at 0.2668× (140 mm wheel):

| Build dimension | Value | Status |
|---|---|---|
| Overall envelope L × W × H | ≈ 690 × 670 × ~553 mm | 140mm-era 743×722×596 rescaled ×130/140 — confirm off DIY CAD |
| Deck plate (WEB body) L × W × H | ≈ 515 × 384 × 204 mm | 140mm-era 555×413×220 rescaled — confirm off DIY CAD |
| Wheel diameter | 130 mm | **creator-confirmed** (~133.6 mm printed incl. tread) |
| Wheelbase (front↔rear hub) | ≈ **560 mm** | 140mm-era 603 mm rescaled ×130/140 — confirm off DIY CAD |
| Track (hub-center) | ≈ **526 mm** front/rear · **587 mm** middle | 140mm-era 567/632 rescaled — confirm off DIY CAD |
| Hub centers (datum: WB-center @ ground) | front (±301.5, ±283.5, 70) · mid (+14.7, ±316.0, 70) · rear (∓301.5, ±283.5, 70) | **measured** |
| Ground clearance (deck underside) | ~180 mm | measured (suspension low point ~58 mm) |
| Rocker↔body / rocker↔bogie pivots | ≈ (−55, ±170, 295) / (−66, ±200, 244) | **estimated** — decorative arms are one fused blob; confirm vs real geometry before bearings |
| Mast height | mast removed from working model | TBD |

## Reference Designs to Evaluate

Open-source Perseverance-inspired rovers the team should evaluate before committing to custom CAD:

- **JPL Open Source Rover (OSR)** — NASA's official educational rover. ~$2,500 BOM. Mature, well-documented, runs ROS. Direct Perseverance lineage. Right scale; high cost.
- **Sawppy the Rover** (Roger Cheng) — Curiosity / Perseverance-style 6-wheel rocker-bogie. ~$500 BOM. 3D-printable. Accessible, well-trodden community path.
- **Curio Rover** — Perseverance-replica 3D-printable design (referenced in [Locomotion Control Unit](../modules/Locomotion Control Unit.md) open items). Educational-scale.

Recommendation: use these as the **rocker-bogie mechanism donor** (linkage design, pivots, drive/steer modules) — but because Mark 1 holds true Perseverance proportions (~74 cm body), **no stock kit fits dimensionally**; expect to re-space the rocker-bogie and scale the frame in CAD. **Sawppy / Curio** (3D-printed, parametric) are easiest to re-proportion; the OSR frame is more fixed. This is more custom work than a stock-kit build — the accepted cost of true-proportion fidelity.

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
