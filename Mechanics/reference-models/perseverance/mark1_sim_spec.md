# Mark 1 — Stage 1 sim "build sheet"

The exact numbers to turn the scaled-Perseverance model into a Gazebo-ready rover
("puppet"). **All measured directly** from `converted/perseverance_rolling_chassis.blend`
(0.27× NASA Perseverance) in Blender 5.0.1 on Legion — not estimated.

> ⚠️ **Partly superseded (2026-06-30).** These are the 140 mm-era measurements off the
> *articulated* rocker-bogie Blender model. The build is now the **130 mm-wheel DIY replica**
> (in production; wheel radius **0.065**), and the live sim is the **rigid corner-steer** model
> (`src/friday_locomotion/.../kinematics.py` + `src/friday_description/urdf/mark1.urdf.xacro`),
> not the articulated joint-tree below. Treat the wheelbase/track/tree here as historical;
> re-derive geometry off the in-repo DIY CAD (`howtomechatronics-replica/`).

## Measurements (metres)
- **Wheel radius:** 0.065 *(was 0.070 — 130 mm DIY wheel, in production)*
- **Track** (left↔right): 0.722 · **Wheelbase** (front↔rear): 0.743
- **Body:** 0.413 (X, width) × 0.555 (Y, length) × 0.220 (Z, height)
- **Wheel centres** (axle height z = 0.070 = radius, so wheels rest on ground at z = 0):

  | wheel | x | y |
  |---|---|---|
  | L-front | −0.291 | +0.311 |
  | L-mid   | −0.323 | +0.024 |
  | L-rear  | −0.291 | −0.292 |
  | R-front | +0.291 | +0.311 |
  | R-mid   | +0.323 | +0.024 |
  | R-rear  | +0.291 | −0.292 |

  (mid wheels track 32 mm wider each side — authentic rocker-bogie geometry)

## Link tree (the "puppet" skeleton)
```
base_link  (body)
├─ rocker_left   (revolute, axis Y, on body)      → wheel_L_front (continuous, axis X)
│  └─ bogie_left (revolute, axis Y, on rocker)     → wheel_L_mid, wheel_L_rear (continuous, axis X)
├─ rocker_right  (revolute, axis Y, on body)      → wheel_R_front (continuous, axis X)
│  └─ bogie_right(revolute, axis Y, on rocker)     → wheel_R_mid, wheel_R_rear (continuous, axis X)
```
- 6 wheel joints (continuous, spin about X).
- Rocker differential (links L/R rockers across the body): model as a constraint, or omit in v1.

## Drive model (v1)
Skid / differential: left 3 wheels share one velocity, right 3 share another — maps
directly onto our existing unicycle `MotionCommand` (v, ω). Corner-wheel steering is
a later refinement.

## Mass budget (~10.5 kg total)
| part | qty | each | total |
|---|---|---|---|
| body | 1 | 6.0 | 6.0 |
| rocker | 2 | 0.7 | 1.4 |
| bogie | 2 | 0.4 | 0.8 |
| wheel | 6 | 0.38 | 2.3 |
| **≈ total** | | | **10.5** |

## Meshes
- `body.stl` exported (visual, ~137 KB). Wheels & suspension: use primitive cylinders/
  boxes for **collision + v1 visual** (never the raw 74 k-vert wheel mesh — kills sim
  perf); swap in split meshes later for visual polish.

## What Drift builds from this
A `friday_description` package: URDF with this link tree + these exact measurements +
masses, `ros2_control` (6 wheel-velocity), a flat-ground world, and a `ros_gz` Gazebo
launch — then we drive it with our existing `MotionCommand → Odometry` and run the
Phase 4 safety (authority + safe-stop) against physics.
