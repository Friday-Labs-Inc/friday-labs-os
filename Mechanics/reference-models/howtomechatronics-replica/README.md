# HowToMechatronics — Mars Perseverance Replica (Mark 1 mechanical reference)

The **canonical mechanical / CAD reference** for the Mark 1 rover body. Mark 1's
mechanical anatomy *is* this replica, scaled to the locked build target (≈140 mm
wheel / 743 mm body, ~0.267× the real Perseverance). The parts being 3D-printed for
the prototype come from here.

**Source:** HowToMechatronics — "DIY Mars Perseverance Rover Replica with Arduino"
<https://howtomechatronics.com/projects/diy-mars-perseverance-rover-replica-with-arduino/>
(CAD by Dejan Nedelkovski / HowToMechatronics, published 2023-11-30).

## Contents

| File / folder | What it is |
|---|---|
| `Perseverance_Replica_Assembly.step` | Full assembly, STEP (neutral format — opens in FreeCAD) |
| `Perseverance_Replica_SOLIDWORKS.zip` | Original editable SOLIDWORKS source CAD |
| `stl/Main Functional Parts/` | **28** build-critical printed parts |
| `stl/Cameras Unit/` | 20 camera-unit parts |
| `stl/Accessories - Not functional parts/` | 57 cosmetic / shell parts |

(The redundant `STL Files.zip` from the download was intentionally not committed —
the `stl/` folder is the same parts, individually browsable.)

## How it maps to Mark 1

The mechanism Mark 1 inherits from this replica (see
[Mechanical Design Reference](../../../docs/addendums/Mechanical%20Design%20Reference.md)):

- **6-wheel rocker-bogie** + 3-piece **differential bar** (`Differential Bar p1/p2`,
  `Diff bar link`, `Bracker for dif bar`, `Rocker Joint*`, `Bogie Joint*`).
- **4-corner steering** — `Wheel 1/3/4/6 Joint Servo Mount` are the steered corners;
  `Wheel 2/5 ... motor mount` are the drive-only middle wheels. Matches the OS
  `kinematics.drive_and_steer` (Ackermann corner steer).
- `Rim` + `Rim and DC Motor Coupler` + `Servo coupler` — the drivetrain couplers.
- `Electronics holder p1/p2` — the original single-Arduino bay; Mark 1 replaces this
  with the modular hub enclosures (Core / Telemetry / Mobility / Research) and the
  signed Command Center, but keeps this mechanical base.

## ⚠️ Licensing

These CAD files are **HowToMechatronics' work**, included here as a build reference.
Before any redistribution or commercial use, confirm the original author's license
terms. Treat as reference-only unless cleared.
