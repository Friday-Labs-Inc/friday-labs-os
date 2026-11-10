# Learned Perception and ML Pipeline

> How Mark 1 adds neural networks without weakening its safety core: where learned models plug in, where they may never plug in, how they are trained and proven, and what has to be re-decided first. Proposes a re-engineering of the AI layer; nothing here is locked until reviewed.
> **Version:** Draft 0.1 (proposal) · **Purpose:** Plan the learned-perception layer for Phase 5 and record the evidence behind it.

## In Plain English

Mark 1 already drives the way NASA's Perseverance does: **geometry keeps it safe**. The bumper depth camera measures slope, steps and cliffs (`friday_terrain`), Nav2 plans around them (`friday_nav_layers`), and the ESP32 watchdog stops the wheels if the brain goes quiet. None of that uses a neural network, and that is correct.

What Mark 1 cannot do yet is *understand* what it sees: sand versus grass versus mud, a person versus a bush. That is where small neural networks help. This addendum says they may **add information** (raise the cost of a patch of ground, report a person) but may **never command the motors** and may **never overrule geometry**. It also sets up a separate training pipeline so every model that reaches the rover has been tested honestly first.

## Evidence Behind This Plan

From the `rover` learning sandbox (Donkey simulator, RTX 3070, Nov 2026) and two cited research reports (`reports/Small rover driving model methods.md`, `reports/LLMs writing neural networks.md` in that sandbox):

| Finding | Number | What it means for Mark 1 |
|---|---|---|
| Perseverance AutoNav drove > 90 % of 45 km with no learned control; JPL places ML *before* its geometric check, never instead of it | Verma 2023; Abcouwer 2021 | Keep `friday_terrain` as the final gate. |
| Copying an instructor *without* recovery data | 48 crashes vs 0–1 with recovery data | Training data must include mistakes and recoveries. |
| Model trained on one track, tested on an unseen one | 17 crashes; 5-track training: mean 1.8 | Variety of scenery matters more than model size. Off-road segmentation also transfers badly across datasets (≈15 mIoU, GOOSE-Ex 2024). |
| Same recipe, different random seed | 0 vs 17 crashes | Never judge a model on one training run. |
| Lower validation loss, worse driving | clean-data model scored better offline, crashed 48× | Judge models by closed-loop driving, not loss. |
| Reinforcement learning (hybrid, 40k steps) vs imitation | mean 38 vs 1.8 crashes | RL is research-only for Mark 1; not on the product path. |
| LLM-written ML code | deep-learning code correct ~31 % first try (Deep-Bench 2025); silent bugs and score-gaming are the main failure modes | Sanity checks and a protected evaluation set are mandatory, whoever writes the code. |

## Decisions (proposed)

| Parameter | Proposal |
|---|---|
| **Role of learned models** | Perception only: they publish costs and detections. No learned output reaches `MotionCommand`. |
| **Final safety authority** | Geometric classifier (`friday_terrain`) + Nav2 + ESP32 watchdog, unchanged. |
| **Fusion rule in TerrainLayer** | `cost = max(geometric_cost, learned_cost)`. A model can make ground *more* expensive; it can never make geometrically lethal ground passable. Learned cost is capped below `LETHAL` unless a second, independent source agrees. |
| **First models** | (1) terrain-type segmentation, (2) person/vehicle detection with on-device face blurring. |
| **New ROS package** | `friday_perception`: lifecycle inference nodes, `model_version` in `HealthStatus`, `FaultReport` on accelerator loss (as [AI Inference Location](AI Inference Location.md) already requires). |
| **Training lives elsewhere** | New repo `friday-ml`: datasets, training, evaluation, signed model export. Heavy ML dependencies never enter `friday-core-os`. |
| **Model format** | ONNX as the exchange format; compiled per target (TensorRT, Hailo, LiteRT) at release time. Matches the "hardware-agnostic inference slot" in [Mark 1 - 2030 Technology Horizon](../strategy/Mark 1 - 2030 Technology Horizon.md). |
| **Cloud** | Training and labelling help only. Never on the rover's decision path. |

## Hard Rules

- **No neural network output may command a motor, steer, or bypass the authority lease.**
- **Learned costs can only raise cost.** Geometry alone decides lethal unless two independent sources agree.
- **Every model ships with its exam results**: closed-loop scores from at least 3 training seeds on a held-out world it never trained on, plus a real-field test set. A model without them does not get signed.
- **The held-out exam data is never used for training, tuning, or picking the winner.** Picking on the exam set is itself a form of cheating.
- **Inference stays within the existing budget**: > 100 ms per frame is not allowed on the navigation path.
- **Privacy before storage**: faces are blurred on the rover before any frame is logged or uploaded. No face recognition.

## Step 0: Re-decide the AI Compute (blocks everything else)

The [AI Inference Location](AI Inference Location.md) addendum locks **Pi 5 + Coral USB**. Reality and the market have moved:

- The Core Hub actually built is a **Pi 4B** with no accelerator (see [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md)).
- The 2030 Horizon document already calls Coral "a dead-end by 2029".
- The Jetson price used to reject it ($500) is out of date: **Jetson Orin Nano Super is $249** (Dec 2024).
- **To verify before buying:** whether the Coral Edge TPU Python runtime supports Python 3.12, which ROS 2 Jazzy on Ubuntu 24.04 uses.

| Option | Approx. cost | AI throughput | Power | Notes |
|---|---|---|---|---|
| Pi 4B + Coral USB | ~$60 (Coral) | 4 TOPS | +1–2 W | Small models only; runtime support risk. |
| Pi 5 + Hailo AI HAT+ | ~$80 + $70–110 | 13–26 TOPS | ~5–8 W | No CUDA; good for detection and segmentation. |
| Jetson Orin Nano Super | $249 | 67 TOPS (sparse) | 7–25 W | CUDA/TensorRT; Isaac ROS supported on Humble only (not Jazzy) on Orin as of 2026. |

**Proposal:** run the acceptance test from the AI Inference Location addendum (≥ 15 fps, p99 ≤ 80 ms) on Pi 5 + Hailo and on Orin Nano Super with the same exported model, then revise that addendum. Prices are from 2024–2026 sources and must be re-checked in INR at purchase.

## Architecture

```
 bumper RGB-D ─┬─► friday_terrain (geometry) ──────────┐
               │                                        ├─► TerrainLayer: max(geo, learned) ─► Nav2 ─► MotionCommand ─► lease + watchdog
 mast camera ──┴─► friday_perception/terrain_seg ──────┘
 mast camera ────► friday_perception/detect + blur ───► DetectedObjectArray ─► mission / telemetry
```

`friday_perception` nodes follow the `lifecycle-node-scaffold` skill and the four locked QoS profiles; detections use `state_default`.

## The Training Pipeline (`friday-ml`)

1. **Collect.** `ros2 bag` recordings from the real rover (per [Mission Logging and Replay](Mission Logging and Replay.md)) plus public datasets: AI4Mars (35k Mars terrain images), RUGD and RELLIS-3D (off-road).
2. **Label.** Humans label a small, trusted set; machine pre-labels speed up the rest (see [TypeSafe / Jev](#typesafe--jev-in-the-pipeline)). A human-reviewed test set is never machine-labelled.
3. **Train** on the RTX 3070 workstation, with the sanity checks that caught bugs in the sandbox: a trivial baseline to beat, a starting loss check, and the network memorising one small batch.
4. **Exam in closed loop.** Gazebo worlds (`arena`, `bumpy`, `baylands`) run the full OS with the model in the loop. One world is held out as the final exam. Metrics: interventions, autonomy %, mean distance between interventions. At least 3 seeds per recipe.
5. **Exam on real data.** Gazebo images are too plain to judge vision, so perception accuracy (mIoU, detection mAP) is measured on real held-out field frames.
6. **Release.** ONNX → target compile → sign → OTA per [OTA Update Strategy](OTA Update Strategy.md), with `model_version` pinned per mission.

Later, **self-supervised traversability**: the rover labels its own experience by comparing commanded motion with actual motion (slip), as in Wild Visual Navigation (RSS 2023). No human labelling needed.

## TypeSafe / Jev in the Pipeline

Jev (TypeSafe's System One model) answers typed questions about text and images: Choice, Score, Noul (yes/no probability) and Box (locate a region). It is a hosted cloud API, so it belongs in `friday-ml` and the Command Center, **never on the rover**.

| Use | Primitive | Guardrail |
|---|---|---|
| Pre-label people and vehicles in rover frames | Box | Low-confidence boxes go to a human; the test set is human-only. |
| Weak terrain labels per image patch (sand / grass / rock / mud / water / none) | Choice | Used as training hints, not ground truth; checked against human labels before use. |
| Screen frames (blurred, occluded, duplicate, useful?) | Noul | Thresholds tuned on a labelled sample. |
| Sort `FaultReport` + mission logs into failure categories | Choice | Starts the fleet failure corpus the 2030 Horizon document asks for. |
| Operator request → typed mission parameters | Choice + function-calling | Command Center side; the operator still signs every command. |

**Conditions before use:** blur faces on the rover before any frame leaves it (DPDP); confirm TypeSafe's terms allow using outputs as training labels; measure accuracy and cost on our own frames first. Calibrated probabilities are not guaranteed in a new domain.

## Where Imitation and RL Fit

- **Behavioural cloning:** only for a narrow, opt-in mode (for example trail following), proposing velocities that still pass through Nav2 and the lease. Not the default driver.
- **Reinforcement learning:** simulation research only. In the sandbox it lost to imitation by ~20×.
- **Large driving / vision-language-action models:** reading only for Mark 1. They do not fit the power or compute budget.

## Phases and Acceptance

| Phase | Deliverable | Done when |
|---|---|---|
| P0 | Revised AI Inference Location addendum | Bench test of the chosen board meets ≥ 15 fps, p99 ≤ 80 ms with a real exported model. |
| P1 | `friday-ml` repo + data recording | 3 field sessions recorded and versioned; human-labelled test set exists. |
| P2 | Terrain segmentation in `friday_perception` + TerrainLayer fusion | In the held-out Gazebo world, interventions do not increase vs geometry-only; on real test frames, mIoU reported per class. |
| P3 | Detection + on-device blurring | Detection mAP on real test frames; no unblurred face in any stored frame (audit). |
| P4 | Self-supervised traversability (research) | Beats geometry-only cost on the field test set without increasing interventions. |

## Open Items

- Board choice (P0) and the Coral runtime check.
- Licence for the detector (Ultralytics YOLO is AGPL unless licensed; alternatives with permissive licences).
- Whether `terrain_seg` runs on the Core Hub or the Lab Deck, given [Sensor Ownership](Sensor Ownership.md) (nav perception must stay on Core).
- New `friday_msgs` types for terrain semantics, per [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md).

## Glossary

- **Costmap:** a grid the planner uses; each cell has a cost from 0 (free) to 254 (lethal).
- **Segmentation:** labelling every pixel of an image (sand, grass, rock…).
- **Seed:** the random starting point of training; different seeds can give very different models.
- **Closed-loop exam:** the model drives and its mistakes affect what it sees next, unlike scoring on recorded data.
- **ONNX:** a common file format for trained models that many accelerators can import.
- **Behavioural cloning / RL:** learning by copying a teacher / by trial and error with rewards.

## If This Breaks, Look Here

- Rover avoids ground that looks fine: check `learned_cost` vs `geometric_cost` in the TerrainLayer; the model may be raising cost wrongly. Lower its weight or roll back `model_version`.
- Rover drives onto something dangerous: this should be impossible from the learned layer. Check the geometric classifier and the fusion rule first.
- `ACCELERATOR_LOST` fault: inference node falls back per [AI Inference Location](AI Inference Location.md).

## Related

[AI Inference Location](AI Inference Location.md) · [Sensor Ownership](Sensor Ownership.md) · [Mission Logging and Replay](Mission Logging and Replay.md) · [OTA Update Strategy](OTA Update Strategy.md) · [friday_msgs Schema Conventions](friday_msgs Schema Conventions.md) · [mmWave Human Detection](mmWave Human Detection.md) · [Mark 1 - 2030 Technology Horizon](../strategy/Mark 1 - 2030 Technology Horizon.md) · [Mark 1 Index](../Mark 1 Index.md)
