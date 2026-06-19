# Deck Layout, Sizing & Center of Gravity

> Proposed deck packaging for the Mark 1 body, an electronics-driven sizing check against the measured chassis, and an analytical center-of-gravity result. Closes the "deck footprint / stack order undocumented" open item flagged during the Blender study.
> **Version:** Draft 1.1 · **Status: PROPOSED.** Current baseline = **modular bolt-on enclosures with the battery centered** (see below) — this **supersedes the stacked-plate "Architecture A"** kept further down as history. Two earlier locked decisions are deliberately superseded by this pivot: the internal stacked-deck structure, and sealed-conduction cooling (now per-box fans). Blender modular re-model + CG re-confirmed: **CG centered (+0.5%), 205 mm — lower than the plate-stack** (see Verified below).

## Documented vs proposed

**Documented** (measured / locked): body envelope 743 × 722 × 596 mm; deck plate 555 × 413 × 220 mm; ground clearance ~180 mm; wheel 140 mm; what each module contains.
**Proposed here** (to validate): deck footprints, stack order, component positions, and the mass estimates feeding the CG.

## Deck Architecture — Modular Bolt-On Enclosures (current baseline)

Each module is a **self-contained sealed enclosure** (mini-PC casing style) — board screwed inside its own box, box bolted to the base plate, with one **blind-mate power+data connector** to the deck harness and its own small **fan + filtered vent**. Field repair = a box-swap, not a teardown. This is the physical form of the dossier's "each module owns its responsibility."

All boxes sit in a **single layer** on the 555 × 413 mm base plate. The battery is **centered** as the CG anchor.

| Module box | Size L×W×H (mm) | Position | Why |
|---|---|---|---|
| **Battery / Power** (4S Li-ion + BMS + contactor + fuses) | 200 × 150 × 95 | **Centered** | Heaviest box → CG anchor; balance becomes insensitive to the light boxes. **Top-loading** via a gasketed lid hatch + blind-mate base connector for hot-swap. (Supersedes the rear "RTG-analog" placement — central for balance.) |
| Locomotion | 210 × 140 × 60 | Rear | Motor/servo/pawl cabling drops to the drivetrain |
| Core Hub | 130 × 110 × 55 (+fan) | Front | Short USB to mast nav sensor |
| Telemetry | 150 × 110 × 55 | Front | Antenna leads to bulkhead + mast |
| Lab Deck | 140 × 110 × 55 | Front | (three compute boxes side-by-side across the front) |
| Mast (external) | — | Front roof, → z=596 | RealSense + Arducam + long-range LoRa antennas |
| Aerial Bay (Spark) | ~200 × 200 | Rear roof | Vertical launch clears the front mast |

### Sensor placement & Z headroom

The boxes occupy only the bottom **~95 mm** of the 220 mm internal height, leaving a **sensor bay** above (verified in the Blender re-model): **~122 mm above the central battery**, **~162 mm above the compute boxes**. The Perseverance-proportional body height is a *feature* here — vertical room for sensors without raising the CG (roof/headroom sensors are light).

| Sensor | Placement | Why |
|---|---|---|
| **RD-03D mmWave radar** | Front headroom, forward-facing, out a front aperture | ~22 mm thick; needs clear forward look |
| **RPLIDAR A3** | Roof (360°) | Unobstructed all-around view |
| **RealSense + camera** | Mast head | Elevated nav/inspection |
| Env sensors (BME280, gas) | Headroom / inner walls | Tiny; fit anywhere |
| Future sensors | The 122–162 mm headroom bay | Room to grow |

### Verified (Blender modular re-model, 2026-06-19) — `perseverance_modular.blend`

Stacked plates/standoffs/thermal-column removed; 5 sealed boxes single-layer on the base plate; battery centered with top-load hatch + blind-mate connector.

- Total **10.41 kg** (structure 2.74 kg).
- **CG (+3.0, 0.0, 205.1) mm = +0.5% wheelbase** → centered, and **lower (205 vs 217 mm of the plate-stack)** — a single low layer beats a stack.
- Tip angles: rear **56.1°** / fwd 55.5° / lat 56.5° — very stable, slightly better than the stack.
- Body 555 × 413 × 220 mm and overall 596 mm unchanged; full sensor headroom preserved.
- Renders: `/tmp/rover_study/60_modular_top.png`, `61_modular_side.png`, `62_modular_iso.png`.

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
- **CG brackets the same answer:** Blender (itemized 7.67 kg, no enclosure proxy) → CG **(−21.7, +0.5, 189) mm**. Analytical (with ~3 kg enclosure) → CG_z **~217 mm**. **Now RESOLVED:** the inter-deck structure (~3 kg) was modeled and verified inside the body → final full-build CG **(−15.2, +0.4, 217.1) mm** (see Inter-Deck Structure below) — landing on the analytical estimate.
- **Tip angles (Blender):** rearward **56.0°**, forward **59.7°**, lateral **58.6°** — all ≫ the 20° operating slope. Tip-over not a concern.
- **Rear-bias:** CG_x = **−3.6%** of wheelbase (battery at x=−150), well inside the −10% trigger. Sweep: x=−150→−3.6%, x=0→+0.5%, x=+100→+3.2% (perfect center ≈ x=−17). **Decision: battery stays rear — no move; Perseverance RTG-analog placement preserved, no dossier tension.**
- **Climb traction (Blender):** flat ≈46% front / 54% rear; on a 20° ascent ~11% transfers rearward → front still carries **~35%**. Front well-loaded; no pitch-back.
- Renders: `/tmp/rover_study/30_cg_side.png`, `31_cg_top.png` (CG marker + plumb line).

## Inter-Deck Structure (Architecture A — SUPERSEDED; kept as history)

> **Superseded 2026-06-19** by the modular bolt-on enclosure baseline above. Retained as history — its verified CG/mass numbers still validate that the chassis is stable and the electronics fit. The plate-stack is no longer the build approach.

Designed and modeled in `Mechanics/reference-models/perseverance/converted/perseverance_structure.blend`. Three options evaluated:

| Option | Verdict |
|---|---|
| **A — plates + standoffs** | **Recommended & modeled** — iterate-friendly bench-prototype choice; simplest thermal path. |
| B — side-rail cage + slide-in trays | Best serviceability/stiffness, highest build + cabling complexity. → Mark 2. |
| C — monocoque box w/ internal shelves | Stiffest, best-sealed, lightest potential; must re-fab to change. → Mark 2. |

**Architecture A (modeled):**
- Base plate 2.5 mm Al @ z=181 · mid/upper tray 2.5 mm @ z=269 · lid = conduction radiator 2.0 mm @ z=398 (full 400×540 top plate); all ~40% lightening cutouts.
- 6 standoffs (4 corner + 2 mid-side), base → lid.
- **Core→lid thermal column:** solid Al 22×22×58 mm carrying Core Hub heat (front-upper) to the lid radiator.
- Mast mount front-top; Spark-bay mount rear-top; mast-base gusset / front-bulkhead triangulation to kill mast resonance at 1 m/s.

**Final verified numbers:**
- Structure mass **~3.0 kg**.
- **Full-build total 10.61 kg.**
- **Full-build CG (−15.2, +0.4, 217.1) mm** — −2.5% rear (centered structure dilutes the bias), laterally centered. Lands on the analytical ~217 mm estimate.
- Tip angles: rear ~**53°** / fwd ~55° / lat ~55° — all ≫ 20° slope. Stable.
- **Height: structure sits z ≈ 181–401 mm, entirely INSIDE the 220 mm body** (z 179.9–400.3); lid flush with the body top (z=400). Overall rover height unchanged at 596 mm to mast top.

**Verified inside the envelope (2026-06-19).** An earlier x-ray render made the **roof payload** (mast + Spark bay + RPLIDAR, legitimately above z=400) plus a stray oversized reference plane read as a "cage stacked on top," suggesting doubled height. Numerical check + a clean re-render (body shown as orange wireframe) confirm the inter-deck structure is **entirely within the body** — the body did not grow. The stray reference plane was removed and the lid dropped flush. Render: `/tmp/rover_study/50_inside_side.png`.

**Constraints honored:** thermal (Al column Core→lid radiator); grommeted cable pass-throughs (corners RAW/SW + NC E-stop loop; center I2C/USB-CDC/BMS/PWR_FAIL); gasketed rear panel for battery hot-swap (pack slides out without lifting the upper tray); upper tray lifts off 6 standoff bolts for lower-deck access; 2.5 mm plates + 6 standoffs + mast gusset for stiffness; gasketed lid + rear panel for IP sealing; M12 bulkheads on rear + side walls.

Renders: `/tmp/rover_study/40_struct_side.png`, `41_struct_top.png`, `42_struct_iso.png`.

## Open Items

- ✅ **Modular re-model** (Blender) — done & verified: 5 bolt-on boxes, battery centered + top hatch; CG centered (+0.5%) and lower (205 mm). `perseverance_modular.blend`.
- ✅ **Drivetrain breakout** — done: 21 named objects; **wheelbase 603 mm, track 567/632 mm, wheel 140 mm confirmed**. **Rebuild markup sent** to Blender (functional wheels / common corner knuckle for 37D + DS3218 / middle motor brackets / structural arms + cable channels / functional diff-bar).
- ✅ **Chassis CG verification** — done; the wide, low stance is stable (tip 53–55° ≫ 20° slope).
- ✅ **Hub-center wheelbase / track** — measured (603 / 567–632 mm; see [Mechanical Design Reference](../addendums/Mechanical Design Reference.md)). **Rocker/bogie pivots still estimated** — confirm against real geometry before committing the functional suspension.
- **Per-box enclosure spec** — material, fan + filtered vent, blind-mate connector, gasket, mount pattern; folds into each module's electronics doc.
- **Real component masses** — replace estimates with measured/datasheet values once parts are in hand.

## Related

[Mechanical Design Reference](../addendums/Mechanical Design Reference.md) · [Power & E-stop Backbone — Build Package](Power and E-stop Backbone - Build Package.md) · [Locomotion Deck — Build Package](Locomotion Deck - Build Package.md) · [Power Budget](../addendums/Power Budget.md) · [Mark 1 Index](../Mark 1 Index.md)
