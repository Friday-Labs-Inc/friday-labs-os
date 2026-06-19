# AI Inference Location

> Where AI inference runs on Mark 1, what hardware powers it, and what this means for the offline-first autonomy claim. Locks the Core Compute Hub SBC choice for the bench prototype.
> **Version:** Draft 1.0 · **Purpose:** Closes a Phase 1 hardware-design gap before SBC procurement.

## Decisions

| Parameter | Value |
|---|---|
| **Inference location** | Local, on the Core Compute Hub. No cloud dependency for any safety- or autonomy-critical task. |
| **Core Hub SBC** | Raspberry Pi 5 (8 GB) |
| **Neural accelerator** | Google Coral USB Accelerator (Edge TPU, 4 TOPS) |
| **Typical power** | ~6 W (Pi 5 ~5 W + Coral ~1 W under load) |
| **Cost** | ~$140 combined |
| **Cloud role** | Optional augmentation only: heavy AI model retraining, batch post-mission analytics, map pre-fetch. Never on the autonomy critical path. |

## Why Local, Not Cloud

The dossier promises "offline-first autonomy — Mark 1 must complete a mission with zero internet." Cloud inference breaks that promise for any vision-driven task. The rover's use cases — agriculture, forestry, environmental research, surveillance — all involve operating in areas where cellular signal is poor or absent. AI features that fail in the field are worse than no AI features.

Local inference also concentrates the safety story in one place: if the Core Hub board is alive, perception is alive. There is no "did the upload reach the cloud?" question on the critical path.

## Why Pi 5 + Coral, Not Jetson

The Jetson Orin Nano is the better AI board on raw performance. It is the wrong board for a first prototype:

- **Cost:** $500 vs $140 — a ~3.5x premium that's hard to justify before you know what models you actually need.
- **Power:** 15 W vs 6 W — eats 15-25% of your typical-power budget, cutting effective mission runtime.
- **Ecosystem:** Pi 5 has the largest beginner-friendly ROS 2 community; Jetson is more specialist.

The Pi 5 + Coral combination runs all the model classes Mark 1 needs at the bench-prototype stage:

- YOLOv8-nano / YOLOv5-nano (object and person detection) at 15-30 fps
- MobileNet, EfficientNet-Lite (image classification) at 30+ fps
- DeepLabV3 lite (semantic segmentation) at 5-10 fps
- Small custom-trained classifiers (weed detection, crop stage) at 30+ fps

Models that don't fit: full vision transformers, large LLMs, dense 3D reasoning. None of these are required for Mark 1's stated missions.

When Mark 2 needs heavier models, the **architecture does not change**. The Core Hub gets swapped for a Jetson; all `friday_msgs` interfaces and the autonomy stack stay identical. No throwaway code.

## Model Pipeline

- **Training:** off-rover, on a development workstation or cloud GPU. Quantize to int8 TFLite for Edge TPU.
- **Deployment:** TFLite models pushed to Core Hub via OTA (see future OTA addendum). Versioned and signed.
- **Inference runtime:** `tflite_runtime` on Pi 5, delegated to Coral via the Edge TPU runtime.
- **ROS 2 integration:** inference nodes are lifecycle nodes, publishing `DetectedObjectArray` and similar via `friday_msgs`. QoS profile `state_default` for detection outputs.
- **Failure mode:** if the Coral USB is disconnected or fails, the inference node publishes a `FaultReport` with `category=ACCELERATOR_LOST` and either falls back to CPU inference at reduced rate or declares perception loss (mission-dependent).

## Hard Rules

- **No autonomy decision depends on cloud inference.** Cloud is optional augmentation only.
- **No model loads on the autonomy critical path that exceeds Coral's memory** (8 MB SRAM, 1-2 MB practical model size after quantization). Bigger models live on the Lab Deck or wait for Mark 2.
- **Inference timing is bounded.** Any model that takes > 100 ms per frame is treated as unsuitable for the navigation perception pipeline (use it for slower research-class tasks instead).
- **Model updates are versioned.** Each deployed model carries `model_version` reported in `HealthStatus`. A mismatched model version vs. the expected one for the loaded mission triggers a fault.

## Migration Path

| Stage | Core Hub | Trigger to upgrade |
|---|---|---|
| Mark 1 prototype | Pi 5 + Coral | — |
| Mark 1.5 (if needed) | Pi 5 + Coral or RK3588 NPU board | Coral memory limit hit by required models |
| Mark 2 production | Jetson Orin Nano or successor | Full transformer-class models required, or power budget grows |

`friday_msgs` and the autonomy stack are unchanged across this path.

## Acceptance Criteria

- A YOLOv8-nano model running on Coral processes Core's nav-sensor stream at ≥ 15 fps sustained, with inference latency p99 ≤ 80 ms per frame, in bench testing.
- Unplugging the Coral USB triggers `FaultReport` within 1 s and the documented fallback behavior fires.
- A mission with vision-based detection enabled runs offline (cellular disabled) end-to-end with no degraded behavior compared to online operation.

## Open Items

- Specific model list per mission class — locked during Phase 5 (mission planner build).
- Whether to add a secondary Coral accelerator if a mission needs more than one model running in parallel — defer.
- LLM-class on-device inference for natural-language mission interpretation — explicitly out of scope for Mark 1.

## Related

[Authority Lease Protocol](Authority Lease Protocol.md) · [Safe-Stop Latency Budget](Safe-Stop Latency Budget.md) · [Sensor Ownership](Sensor Ownership.md) · [Power Budget](Power Budget.md) · [Friday Labs OS Architecture](../architecture/Friday Labs OS Architecture.md) · [Mark 1 Compute Architecture](../architecture/Mark 1 Compute Architecture.md) · [Mark 1 Index](../Mark 1 Index.md)
