# Deck Layout, Sizing & Center of Gravity

> Proposed deck packaging for the Mark 1 body, an electronics-driven sizing check against the measured chassis, and an analytical center-of-gravity result. Closes the "deck footprint / stack order undocumented" open item flagged during the Blender study.
> **Version:** Draft 1.0 · **Status: PROPOSED — not yet locked.** Footprints, positions, and component masses are estimates pending real part data + Blender 3D verification.

## Documented vs proposed

**Documented** (measured / locked): body envelope 743 × 722 × 596 mm; deck plate 555 × 413 × 220 mm; ground clearance ~180 mm; wheel 140 mm; what each module contains.
**Proposed here** (to validate): deck footprints, stack order, component positions, and the mass estimates feeding the CG.

## Proposed deck allocation

| Module | Level | Footprint (proposed) | Position | Why |
|---|---|---|---|---|
| Power (4S Li-ion + BMS + contactor + fuses) | Lower | ~185 × 413 mm | Rear third | Heavy → low CG; rear = Perseverance RTG analog; rear hot-swap |
| Locomotion Control Unit (PCB) | Lower | ~340 × 413 mm | Front ⅔, low | Motor/servo/pawl cabling drops to the wheels |
| Core Compute Hub | Upper | ~150 × 90 mm | Front, under lid | Conduction path to lid radiator; short USB to mast nav sensor |
| Telemetry Node | Upper | ~160 × 100 mm | Mid | Antenna leads to bulkhead + mast |
| Lab Deck | Upper | ~150 × 90 mm | Rear-upper | RPLIDAR cable to roof; radar faces forward |
| Mast (external) | Top | — | Front roof, +196 mm | RealSense + Arducam + long-range LoRa antennas |
| Aerial Bay (Spark cradle) | Top | ~200 × 200 mm | Rear roof | Vertical launch clears the front mast |

## Electronics-driven sizing check

Sizing bottom-up from real component footprints (Pi 85×56, MDD10A ~75×55 ×3, 21700 4S3P pack ~90×65, etc.) vs the measured 555 × 413 × 220 deck:

| Level | Footprint used | % of deck area | Height needed |
|---|---|---|---|
| Upper (3 compute modules) | ~520 × 100 mm | ~23% | ~40 mm |
| Lower (Locomotion + power) | ~460 × 160 mm | ~28% | ~80 mm (power-driven) |
| **Height stack** (lid + upper + gap + lower + base) | — | — | **~160 / 220 mm** |

**Result:** the electronics use <30% of each level's area and ~73% of the height. The Perseverance-proportional deck is *oversized* for the electronics — they fit comfortably; **proportions drive the deck size, not the electronics.** Tightest items: the Locomotion carrier (~220 × 160, three MDD10A drivers) and the power-compartment height (~80 mm — 21700 pack + contactor). Height is the axis to watch as boards finalize.

## Center of Gravity (analytical)

Datum: origin at wheelbase center, ground level; +X forward, +Y left, +Z up. Wheelbase ~603 mm (axles at ±302); track ~620 mm (half ±310); deck underside z=180, top z=400.

| Component | mass (g) | x | y | z |
|---|---|---|---|---|
| Battery 4S3P + BMS/contactor/fuses | 1250 | −150 | 0 | 220 |
| Locomotion PCB | 280 | +120 | 0 | 215 |
| Core Hub | 180 | +150 | 0 | 320 |
| Telemetry | 130 | 0 | +90 | 320 |
| Lab Deck | 130 | −150 | −60 | 320 |
| RPLIDAR A3 (roof) | 190 | 0 | 0 | 430 |
| Mast (post + RealSense + camera + ant) | 280 | +250 | 0 | 540 |
| Aerial Bay + Spark (rear roof) | 450 | −200 | 0 | 440 |
| 6 drive gearmotors | 1290 | 0 (axle mean) | 0 | 70 |
| 4 steering servos | 240 | 0 | 0 | 90 |
| 6 wheels | 750 | 0 | 0 | 70 |
| Rocker-bogie frame | 2000 | 0 | 0 | 150 |
| 4 pawl solenoids | 200 | 0 | 0 | 90 |
| Wiring / misc | 300 | 0 | 0 | 200 |
| Enclosure / structure / fasteners | 3000 | 0 | 0 | 290 |
| **Total** | **10,670** | | | |

CG = Σ(m·pos)/Σm:

| Axis | Result | Interpretation |
|---|---|---|
| CG_x | **−16 mm** (~5% of half-wheelbase, rear of center) | well balanced fore/aft |
| CG_y | **+0.4 mm** | centered left/right |
| CG_z | **~217 mm** (just above deck underside) | low |
| θ_tip longitudinal | atan(286 / 217) ≈ **53°** | vs 20° climb — huge margin |
| θ_tip lateral | atan(310 / 217) ≈ **55°** | vs 15° hold — huge margin |

**Verdict:** very stable. The wide, low stance makes tip-over a non-issue at the design slopes. The forward mast + Core Hub offset the rear battery + Spark, so net fore/aft bias is only ~16 mm — **no need to move the battery forward; the rear (RTG-analog) placement holds.** CG_z is dominated by the ~3 kg enclosure/structure estimate; a ±30 mm error there still leaves tip angles >49°, so the verdict is robust.

## 3D verification & mass reconciliation (Blender, 2026-06-19)

Mass proxies placed in `perseverance_rolling_chassis.blend` and CG computed in the same datum — **confirms the analytical result and the verdict.**

- **Mass reconciliation:** the itemized component list sums to **7.67 kg** (the "≈9.7 kg" total quoted in the original CG brief to Blender was a mis-add — caught by this pass). The path to the locked ~11 kg is the **enclosure / structure / fasteners** (~3 kg @ body-center z≈290), which is a row in the table above but was omitted from the Blender brief. So: itemized **7.67 kg** + structure **~3 kg** ≈ **10.7 kg** → ~11 kg with hardware/margin.
- **CG brackets the same answer:** Blender (itemized 7.67 kg, no enclosure proxy) → CG **(−21.7, +0.5, 189) mm**. Analytical (with ~3 kg enclosure) → CG_z **~217 mm**. Real value sits between; both **low, centered (+0.5 mm), stable.**
- **Tip angles (Blender):** rearward **56.0°**, forward **59.7°**, lateral **58.6°** — all ≫ the 20° operating slope. Tip-over not a concern.
- **Rear-bias:** CG_x = **−3.6%** of wheelbase (battery at x=−150), well inside the −10% trigger. Sweep: x=−150→−3.6%, x=0→+0.5%, x=+100→+3.2% (perfect center ≈ x=−17). **Decision: battery stays rear — no move; Perseverance RTG-analog placement preserved, no dossier tension.**
- **Climb traction (Blender):** flat ≈46% front / 54% rear; on a 20° ascent ~11% transfers rearward → front still carries **~35%**. Front well-loaded; no pitch-back.
- Renders: `/tmp/rover_study/30_cg_side.png`, `31_cg_top.png` (CG marker + plumb line).

## Open Items (blocked on the Blender session)

- ✅ **3D CG verification** — done (above); battery-rear confirmed.
- **Add the ~3 kg enclosure/structure proxy** to the Blender model so its 3D CG (189 mm, itemized-only) matches the full-build ~217 mm — minor; verdict unchanged.
- **Hub-center wheelbase / track** — exact axle-center measurement (wheels are one merged mesh).
- **Rocker / bogie pivot positions** — measurement pass.
- **Real component masses** — replace the estimates above with measured/datasheet values once parts are in hand (especially the enclosure/structure 3 kg, which drives CG_z).

## Related

[Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [Power & E-stop Backbone — Build Package](Power and E-stop Backbone - Build Package.md) · [Locomotion Deck — Build Package](Locomotion Deck - Build Package.md) · [Power Budget](../addendums/Power Budget.md) · [Mark 1 Index](../Mark 1 Index.md)
