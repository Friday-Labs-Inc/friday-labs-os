"""Boustrophedon (lawnmower) survey planner.

Pure function — no ROS, no state — so it is easy to unit-test and safe to
call from any thread or callback group.

Given a rectangular zone [x0, y0, x1, y1] in map-frame metres and a lane
spacing, produces an ordered list of (x, y) waypoints that cover the zone
in a serpentine (boustrophedon) pattern:

  Lane 0 ↑  |  Lane 1 ↓  |  Lane 2 ↑  …
  ──────────────────────────────────────
  The rover drives each lane end-to-end; adjacent lanes alternate direction
  so turns are tight and coverage is seamless.

  lane_count = ceil(width / lane_spacing_m)   (matches task spec)
  waypoints  = 2 × lane_count  (one start + one end per lane)
"""

from __future__ import annotations

import math


def plan_survey(zone: list[float],
                lane_spacing_m: float) -> list[tuple[float, float]]:
    """Return ordered (x, y) waypoints for a boustrophedon sweep of *zone*.

    Args:
        zone: [x0, y0, x1, y1] — any corner pair, normalised internally.
        lane_spacing_m: distance between parallel lane centrelines (m).

    Returns:
        List of (x, y) waypoints in drive order.  Empty when zone is
        degenerate (zero area) or spacing ≤ 0.
    """
    if lane_spacing_m <= 0:
        return []

    x0, y0, x1, y1 = zone
    xmin, xmax = min(x0, x1), max(x0, x1)
    ymin, ymax = min(y0, y1), max(y0, y1)

    width = xmax - xmin
    height = ymax - ymin
    if width <= 0 or height <= 0:
        return []

    n_lanes = math.ceil(width / lane_spacing_m)

    waypoints: list[tuple[float, float]] = []
    for i in range(n_lanes):
        # Clamp last lane to zone boundary (avoids overshooting by <spacing)
        x = min(xmin + i * lane_spacing_m, xmax)
        if i % 2 == 0:          # even lane: bottom → top
            waypoints.append((x, ymin))
            waypoints.append((x, ymax))
        else:                   # odd lane: top → bottom (serpentine)
            waypoints.append((x, ymax))
            waypoints.append((x, ymin))

    return waypoints
