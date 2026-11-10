"""Proxy terrain-fusion network for the AI compute bench test.

The real fusion network does not exist yet. This proxy has the agreed
shapes and the same *kinds* of operations, with random weights, so each
candidate board can be timed before we commit to one. Accuracy is not
measured here; speed, memory and operator support are.

Inputs (one frame):
  camera   1x3x256x448   wide-angle RGB, downscaled
  depth    1x1x256x448   depth image aligned to the camera
  lidar    1x1x120x80    2D LiDAR scan rasterised to the BEV grid in code
  prev     1x(32w)x120x80 last BEV features, already shifted by odometry in code
Output:
  bev      1x8x120x80    cost, confidence, 6 terrain classes
BEV grid: 10 cm cells, x -2..10 m (120), y -4..4 m (80).

Two variants differ only in how camera features reach the BEV grid:
  ipm   fixed ground-plane sampling (GridSample)   -> NPU-friendly
  lift  depth-guided scatter into cells (ScatterElements) -> GPU-friendly

Sizes: --width 1 = 0.3M params, 2.3 GMAC; 2 (default) = 1.3M, 9.2 GMAC; 3 = 2.9M, 20.6 GMAC.

Hailo cannot run GridSample (or, likely, scatter), so --split exports the
network in two halves that run on the NPU, with the camera-to-BEV step done
on the CPU in between (see warp_on_cpu):
  <name>_encoder.onnx   camera, depth          -> feats  (1x(32w)x32x56)
  <name>_bevhead.onnx   camera_bev, lidar, prev -> bev

Run:  python proxy_fusion_model.py [ipm|lift] [out.onnx] [--width 2] [--split]
"""

import sys

import torch
from torch import nn

BEV_H, BEV_W = 120, 80


def block(cin: int, cout: int, stride: int = 1) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(cin, cout, 3, stride, 1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))


class ProxyFusion(nn.Module):
    def __init__(self, variant: str = "ipm", width: int = 2) -> None:
        super().__init__()
        self.variant, w = variant, width
        self.c = C = 32 * w
        self.image = nn.Sequential(  # RGB-D -> (64w) x 32 x 56 (stride 8)
            block(4, 32 * w, 2), block(32 * w, 32 * w), block(32 * w, 64 * w, 2), block(64 * w, 64 * w),
            block(64 * w, 64 * w, 2), block(64 * w, 64 * w), block(64 * w, 64 * w))
        self.to_bev = nn.Conv2d(64 * w, C, 1)
        # fixed ground-plane lookup: where in the image each BEV cell falls (calibration in the real model)
        self.register_buffer("grid", torch.rand(1, BEV_H, BEV_W, 2) * 2 - 1)
        # fixed cell index per image feature pixel (from depth + calibration in the real model)
        self.register_buffer("cell", torch.randint(0, BEV_H * BEV_W, (32 * 56,)))
        self.bev = nn.Sequential(block(C + 1 + C, 64 * w), block(64 * w, 64 * w), block(64 * w, 64 * w), block(64 * w, 64 * w))
        self.head = nn.Conv2d(64 * w, 8, 1)

    def camera_to_bev(self, feats: torch.Tensor) -> torch.Tensor:
        if self.variant == "ipm":
            return nn.functional.grid_sample(feats, self.grid, align_corners=False)
        flat = feats.flatten(2)  # 1 x C x (32*56)
        bev = torch.zeros(1, self.c, BEV_H * BEV_W, device=feats.device, dtype=feats.dtype)
        bev = bev.index_add(2, self.cell, flat)
        return bev.view(1, self.c, BEV_H, BEV_W)

    def forward(self, camera, depth, lidar, prev):
        feats = self.to_bev(self.image(torch.cat([camera, depth], 1)))
        bev = torch.cat([self.camera_to_bev(feats), lidar, prev], 1)
        return self.head(self.bev(bev))


class Encoder(nn.Module):
    """First half for NPUs: camera + depth -> image features."""

    def __init__(self, full: ProxyFusion) -> None:
        super().__init__()
        self.image, self.to_bev = full.image, full.to_bev

    def forward(self, camera, depth):
        return self.to_bev(self.image(torch.cat([camera, depth], 1)))


class BevHead(nn.Module):
    """Second half for NPUs: BEV features + LiDAR + memory -> terrain map."""

    def __init__(self, full: ProxyFusion) -> None:
        super().__init__()
        self.bev, self.head = full.bev, full.head

    def forward(self, camera_bev, lidar, prev):
        return self.head(self.bev(torch.cat([camera_bev, lidar, prev], 1)))


def warp_on_cpu(feats, grid):
    """The step Hailo cannot run: sample image features at each BEV cell (numpy or torch on the CPU)."""
    return nn.functional.grid_sample(torch.as_tensor(feats), torch.as_tensor(grid), align_corners=False)


def example_inputs(width: int = 2):
    return (torch.rand(1, 3, 256, 448), torch.rand(1, 1, 256, 448), torch.rand(1, 1, BEV_H, BEV_W),
            torch.rand(1, 32 * width, BEV_H, BEV_W))


if __name__ == "__main__":
    width = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 2
    split = "--split" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--width", str(width), "--split")]
    variant = args[0] if args else "ipm"
    out = args[1] if len(args) > 1 else f"proxy_fusion_{variant}_w{width}.onnx"
    model = ProxyFusion(variant, width).eval()
    camera, depth, lidar, prev = example_inputs(width)
    if split:
        stem = out.removesuffix(".onnx")
        torch.onnx.export(Encoder(model), (camera, depth), f"{stem}_encoder.onnx", opset_version=17, dynamo=False,
                          input_names=["camera", "depth"], output_names=["feats"])
        camera_bev = warp_on_cpu(Encoder(model)(camera, depth).detach(), model.grid)
        torch.onnx.export(BevHead(model), (camera_bev, lidar, prev), f"{stem}_bevhead.onnx", opset_version=17,
                          dynamo=False, input_names=["camera_bev", "lidar", "prev"], output_names=["bev"])
        print(f"exported {stem}_encoder.onnx and {stem}_bevhead.onnx (CPU warp in between)")
    else:
        torch.onnx.export(model, (camera, depth, lidar, prev), out, opset_version=17, dynamo=False,
                          input_names=["camera", "depth", "lidar", "prev"], output_names=["bev"])
        print(f"exported {out} ({sum(p.numel() for p in model.parameters()):,} parameters)")
