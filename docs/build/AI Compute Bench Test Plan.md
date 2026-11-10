# AI Compute Bench Test Plan

> How we choose the board that runs Mark 1's neural networks: what we test, how we measure it, and the rule that decides the winner, written down **before** any result exists. Step P0 of [Learned Perception and ML Pipeline](../addendums/Learned Perception and ML Pipeline.md).
> **Version:** Draft 0.1 · **Purpose:** Replace the stale Pi 5 + Coral decision in [AI Inference Location](../addendums/AI Inference Location.md) with a measured one.

## In Plain English

We will run the same neural networks on each candidate computer, under the same conditions, for long enough that heat becomes a problem, while the rest of the rover software is also running. We measure how fast (especially the slowest moments), how much power, how hot, and how painful the tools are. The board that passes every hard limit and costs least to own wins. The rule is fixed now, so the results cannot be bent to fit a favourite.

## Candidates

| ID | Board | Software | Approx. cost (Nov 2026) | Why it is in |
|---|---|---|---|---|
| **A** | Jetson Orin Nano Super 8 GB dev kit | JetPack 7.2.1 (Ubuntu 24.04, TensorRT 10.16), ROS 2 Jazzy native | $399 / **~₹47k incl. GST** (authorised: Tanna TechBiz) | Full GPU; runs the fusion network unmodified. |
| **B** | Raspberry Pi 5 8 GB + AI HAT+ 26 TOPS (Hailo-8) + Active Cooler | Ubuntu 24.04 + HailoRT 4.2x installed by hand; Raspberry Pi OS Trixie as reference | ~₹20k + ~₹10k + ~₹1.6k (cooler, PSU) ≈ **₹32k** | Lower price and power; needs the network split around a CPU step. |
| B′ | Same with AI HAT+ 13 TOPS (Hailo-8L) | as B | ~₹6.4k for the HAT | Only if B passes with large margin. |
| **C** | Raspberry Pi 4B 8 GB, CPU only (already owned) | Ubuntu 24.04 + ONNX Runtime | ₹0 | Baseline: shows what we have today. |

**Dropped:** Coral USB (official runtime abandoned since 2021 at Python 3.9; discontinued at DigiKey; 8 MB on-chip memory too small for fusion).
**Watch:** NVIDIA announced a Jetson Orin Nano 2 (~78 TOPS) for H1 2027 (single source). The ONNX model slot keeps that a drop-in.

## Workloads

All models are exported once on the workstation and the **same files** go to every board.

| ID | Model | Input | Role | Target |
|---|---|---|---|---|
| W1 | Proxy fusion network, width 2 (`tools/bench/proxy_fusion_model.py`): 1.3 M params, 9.2 GMAC | camera 3×256×448, depth 1×256×448, LiDAR BEV 1×120×80, memory 64×120×80 | Terrain map | **5 Hz, p99 ≤ 100 ms** end to end |
| W1-split | W1 as encoder + BEV head, `GridSample` on CPU between (`--split`) | same | Hailo path (B, B′) and an option on A | same |
| W1-lift | Proxy with depth-guided scatter instead of `GridSample` | same | Tests the GPU-friendly variant | same, A only |
| W1-w3 | Proxy width 3: 2.9 M params, 20.6 GMAC | same | Headroom: can the board grow with the model? | report only |
| W2 | RT-DETR v2 r18 (`PekingU/rtdetr_v2_r18vd`, Apache-2.0) | 640×640 | Person/vehicle detector | **≥ 15 fps, p99 ≤ 80 ms** (AI Inference Location) |
| W3 | Depth-Anything-V2-Small (Apache-2.0) | 224×224 and 256×448 | Optional depth densifier | report only |
| **W4** | **W1 at 5 Hz + W2 at 15 Hz together, while a recorded mission replays through `friday_terrain` + Nav2** | rosbag from the Baylands sim | The real rover load | **all W1/W2 targets still met** |

W4 decides the result; W1–W3 explain it.

## Measurements

| What | How | Notes |
|---|---|---|
| Latency p50 / p99 / max, fps | A: `trtexec --onnx=… --fp16` and `--int8 --percentile=50,99 --duration=1800`; B: `hailortcli benchmark` / `run` on the compiled HEF; C and all CPU steps: `tools/bench/bench_onnx.py --seconds 1800` | End to end includes pre-processing, the CPU warp (W1-split) and post-processing, timed in the ROS node for W4. |
| Sustained behaviour | 30 min continuous per workload | Heat throttling appears after minutes, not seconds. |
| Power | Inline logging meter on the supply: DC meter for the Jetson barrel jack, USB-C PD logging meter for the Pis; `tegrastats`/`jtop` and `vcgencmd pmic_read_adc` as secondary | Onboard sensors miss parts of the board; the inline meter is the number of record. Pi 4B has no `pmic_read_adc`. |
| Temperature and throttling | A: `tegrastats`; B/C: `vcgencmd measure_temp`, `vcgencmd get_throttled` every 5 s | Pi 5 throttles at 80 °C; Active Cooler fitted on B. |
| Heat stress | Repeat W4 at **~35 °C ambient** (outdoor Indian afternoon) or inside the closed electronics bay | A rover is not a lab desk. |
| CPU / RAM headroom | `top` sampling during W4 | Nav2 and safety nodes must keep ≥ 30 % CPU free. |
| Accuracy kept after INT8 | W1: compare INT8 vs FP32 outputs on the same 200 inputs (mean abs difference, sign agreement of cost); W2: COCO val 500-image subset mAP, FP32 vs board | Proxy weights are random, so W1 checks numerical fidelity, not usefulness. |
| Operator support | A: `trtexec` build log; B: `hailo parser onnx … --hw-arch hailo8` report: which ops fall back to CPU | A model that silently runs half on the CPU is a failure mode we want to see now. |
| Toolchain cost | Hours from unboxing to first W4 result; steps that needed workarounds | Hailo's compiler (DFC) runs only on x86 Ubuntu with Python 3.9–3.10: run it in Hailo's Docker image on the workstation. |

## Setup

1. **Workstation (Legion, RTX 3070):** export models (`proxy_fusion_model.py ipm|lift [--split] [--width 2|3]`, RT-DETR and Depth-Anything to ONNX opset 17); build INT8 calibration set of 64 frames from Baylands sim recordings; compile Hailo HEFs in the DFC Docker image.
2. **Board A:** flash JetPack 7.2.1; `sudo nvpmodel -m 2` (MAXN SUPER; the GUI may only show 7/15 W in 7.2) and repeat in 15 W mode; install ROS 2 Jazzy from Ubuntu packages; build `friday-labs-os`.
3. **Board B:** Ubuntu 24.04 for Pi 5; install HailoRT 4.2x `.deb` and Python wheel by hand; Active Cooler on; verify `hailortcli fw-control identify`; build `friday-labs-os`.
4. **Board C:** existing Pi 4B Core Hub image with ONNX Runtime.
5. Same power meters, same rosbag, same room temperature log for every board. Record software versions in the results.

## Decision Rule (fixed before testing)

1. **Hard gates. Fail any one and the board is out:**
   - W4: fusion p99 ≤ 100 ms at 5 Hz **and** detector ≥ 15 fps with p99 ≤ 80 ms, sustained 30 min, no throttling at room temperature.
   - W4 at ~35 °C: still meets the gates, possibly with throttling flags but no deadline misses > 1 %.
   - ≥ 30 % CPU headroom for the rest of the stack during W4.
   - Whole AI subsystem ≤ 15 W average during W4, so it fits the 50–75 W rover envelope in [Power Budget](../addendums/Power Budget.md).
   - Every model in W4 compiles with no unexpected CPU fallback beyond the planned warp.
2. **Among boards that pass, pick the cheapest** (board + accessories, INR). If two are within 20 % on price, pick the one with lower average W4 power (every watt is mission time on a 150 Wh battery). W1-w3 headroom breaks any remaining tie.
3. **If none pass:** shrink the model (width 1, smaller inputs) and re-run, rather than relaxing the gates.
4. **If only A passes:** A wins; record the cost gap as a product risk.

Results are kept in `docs/build/bench-results/` with raw logs; the [AI Inference Location](../addendums/AI Inference Location.md) addendum is then revised in its own PR.

## Shopping List

Authorised sellers where they exist (Raspberry Pi approved-reseller list; NVIDIA's India partners). Prices checked 10 Nov 2026, several from search snapshots; recheck at checkout.

| Item | For | Seller (authorised) | Approx. incl. GST |
|---|---|---|---|
| Jetson Orin Nano Super dev kit | A | Tanna TechBiz (NVIDIA partner, importer) or RP Tech India | ~₹47,200 |
| Raspberry Pi 5 8 GB | B | Thingbits / Aryabot / Robu | ~₹20,000 |
| Active Cooler | B | e2u / Silverline | ~₹400–450 |
| Official 27 W USB-C PSU (India plug) | B | Thingbits / Robocraze | ~₹1,000–1,200 |
| AI HAT+ 26 TOPS | B | Silverline / e2u / element14 | ~₹10,000 |
| M.2 HAT+ + 128 GB NVMe (or 64 GB A2 microSD) | B | e2u / Silverline (HAT); NVMe via marketplace | ~₹800 + ~₹2,600 |
| 128 GB NVMe (M.2 2280) | A | marketplace (no authorised channel at 128 GB) | ~₹2,600 |
| FNIRSI FNB58 (Bluetooth) USB-C logging meter | all | Fabtolab / ToolWorld (importers) | ~₹4,800–4,900 |

**Total ≈ ₹90k.** No logging DC meter for the Jetson's barrel jack is sold in India; instead power the Jetson from a 20 V USB-C PD charger through the FNB58 and a PD-trigger-to-5.5×2.5 mm barrel cable (confirm the devkit's input range before use), so one meter logs every board.

## Risks

- **Jetson stock and price** have moved twice in two years; quotes may change before purchase.
- **ONNX Runtime GPU wheels for JetPack 7.2** are community-built only; plan on TensorRT directly.
- **Hailo on Ubuntu 24.04** is a manual install, and Python 3.12 support is reported by users rather than stated by Hailo.
- **Proxy ≠ real model.** The proxy matches shapes and operations, not accuracy; re-run W4 with the first real fusion network before shipping.

## Glossary

- **p99 latency:** 99 % of frames finish faster than this. The slow 1 % is what makes a robot hesitate.
- **INT8 / FP16:** smaller number formats that make networks faster; INT8 needs a calibration set and can lose accuracy.
- **HEF / DFC:** Hailo's compiled model file / Hailo's compiler that makes it.
- **Proxy model:** a stand-in network with the right shape and operations but random weights.

## If This Breaks, Look Here

- Hailo compile fails: run `hailo parser onnx` alone and read which node it rejects; any `GridSample`/scatter belongs on the CPU (`--split`).
- Jetson only shows 7/15 W modes: known JetPack 7.2 GUI bug; set `nvpmodel -m 2` from the shell.
- Pi 5 numbers drift down after minutes: check `vcgencmd get_throttled`; the cooler or PSU is not keeping up.

## Related

[Learned Perception and ML Pipeline](../addendums/Learned Perception and ML Pipeline.md) · [AI Inference Location](../addendums/AI Inference Location.md) · [Power Budget](../addendums/Power Budget.md) · [Sensor Ownership](../addendums/Sensor Ownership.md) · [MK1 Electronics BOM](MK1_Electronics_BOM.md) · [Mark 1 Index](../Mark 1 Index.md)
