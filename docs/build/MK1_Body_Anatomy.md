# Mark 1 body anatomy — measured from CAD

Source of truth: `Mechanics/mars-rover-perseverance-replica-howtomechatronics/Perseverance_Replica_Assembly.step`
(HowToMechatronics 1:4 Perseverance replica), measured 2026-07-17 with FreeCAD 1.1 headless.
The article never states these numbers — they come straight off the assembly geometry.
Caveat: the exported STEP has the right-side suspension branch floating out of pose; all
distances below were taken from the correctly-posed left side + the mirrored steering-mount
pair, whose midplane matches the frame centerline to <1 mm.

## The numbers that matter

| Measurement | Value | Notes |
|---|---|---|
| Wheelbase (front↔rear corner wheel centers) | **580 mm** | steering-pivot span 572 mm |
| Front axle → middle axle | **301 mm** | middles are NOT centered |
| Middle axle → rear axle | **278 mm** | (real Perseverance is asymmetric too) |
| Corner-wheel track (left↔right) | **536 mm** | |
| Middle-wheel track | **602 mm** | middles ride wider than corners |
| Steering-pivot track | **521 mm** | kingpin sits 7–8 mm inboard of wheel center |
| Wheel diameter (tire OD) | **133.6 mm** | radius 66.8 mm — sim uses 65 mm, true-up pending |
| Wheel width | **86.6 mm** | |
| Ground clearance (under frame) | **183 mm** | |
| Overall height (ground → mast top) | **≈614 mm** | |
| Footprint (incl. wheels) | ≈714 × 692 mm | wheelbase+wheel, mid-track+wheel |

## Ackermann inputs (the d-distances the article omits)

Relative to the middle-axle line and chassis centerline:
- half steering-pivot track: **260.5 mm**
- front pivot ahead of middle axle: **297 mm**
- rear pivot behind middle axle: **276 mm**
- half middle-wheel track: **301 mm**

## Frame + suspension cut list (from part labels in the STEP)

- 20×20 T-slot profile: **4× 382 mm + 6× 242 mm** (frame; the "10 pieces")
- Suspension arms (20 mm round tube): 4× rocker links + 4× bogie links
  (per-side: rocker ≈192 mm + ≈161 mm; bogie ≈123 mm + ≈111 mm — bounding-box
  lengths of posed parts; confirm against the cut diagram before sawing)
- Bearings (CAD count): **10× 608RS, 8× 626RS, 5× 625RS** — article text says 8× 608RS; CAD shows 10
- 2× M8 rod-end ball joints + 2× M8 50 mm threaded rod (differential linkage)

## Drivetrain layout (confirmed)

6 wheels, all driven (XD-37GB555 12 V gearmotors); only the 4 corners steer
(25 kg·cm servos); middle pair is drive-only and rides wider. Camera mast:
NEMA 17 pan + servo tilt (Mark 1 repurposes the mast for sensors — no FPV).
