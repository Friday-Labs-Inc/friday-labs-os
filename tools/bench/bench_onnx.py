"""Time an ONNX model with ONNX Runtime: latency percentiles over a sustained run.

Used for the CPU baselines (Pi 4B, Pi 5) and as a cross-check on Jetson
(CUDA / TensorRT execution providers). Accelerator-native numbers come
from the vendor tools named in the bench test plan (trtexec, hailortcli).

Run:  python bench_onnx.py model.onnx [--seconds 600] [--provider CPUExecutionProvider] [--csv out.csv]
Prints p50 / p99 / max latency (ms) and frames per second.
"""

import csv
import sys
import time

import numpy as np
import onnxruntime as ort


def arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> None:
    model = sys.argv[1]
    seconds = float(arg("--seconds", "600"))  # sustained: thermal throttling shows up after minutes
    provider = arg("--provider", "CPUExecutionProvider")
    session = ort.InferenceSession(model, providers=[provider])
    feeds = {i.name: np.random.rand(*i.shape).astype(np.float32) for i in session.get_inputs()}

    for _ in range(10):  # warm-up: first runs include allocation and kernel selection
        session.run(None, feeds)
    latencies, start = [], time.perf_counter()
    while time.perf_counter() - start < seconds:
        t = time.perf_counter()
        session.run(None, feeds)
        latencies.append((time.perf_counter() - t) * 1000)

    ms = np.array(latencies)
    p50, p99 = np.percentile(ms, [50, 99])
    print(f"{model} [{provider}] {len(ms)} runs  p50 {p50:.1f} ms  p99 {p99:.1f} ms  max {ms.max():.1f} ms  "
          f"{len(ms) / seconds:.1f} fps  budget(<=100 ms p99): {'PASS' if p99 <= 100 else 'FAIL'}")
    if "--csv" in sys.argv:
        with open(arg("--csv", "bench.csv"), "a", newline="") as f:
            csv.writer(f).writerow([model, provider, len(ms), round(p50, 2), round(p99, 2), round(ms.max(), 2)])


if __name__ == "__main__":
    main()
