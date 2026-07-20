"""Pure-logic unit tests for the terrain classifier. No ROS needed."""
import numpy as np
import pytest

from friday_terrain.terrain_analysis_node import (
    CLS_FLAT, CLS_GENTLE, CLS_STEEP, CLS_ROUGH,
    CLS_LETHAL_STEP, CLS_LETHAL_SLOPE, CLS_LETHAL_CLIFF, CLS_UNKNOWN,
    COST_FREE, COST_GENTLE, COST_STEEP, COST_ROUGH, COST_LETHAL, COST_UNKNOWN,
    WHEEL_RADIUS_M, classify_grid,
)


def _seen_grid(shape=(6, 6)):
    """Helper: a 6x6 fully-observed grid at ground level."""
    return (np.zeros(shape, dtype=np.float32),
            np.zeros(shape, dtype=np.float32),
            np.ones(shape, dtype=np.int32))


def test_all_flat_ground_is_free():
    min_z, max_z, count = _seen_grid()
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert (g.classes == CLS_FLAT).all()
    assert (g.cost == COST_FREE).all()


def test_unseen_cells_are_unknown():
    min_z, max_z, count = _seen_grid()
    count[0, :] = 0  # a whole row unseen
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert (g.classes[0, :] == CLS_UNKNOWN).all()
    assert (g.cost[0, :] == COST_UNKNOWN).all()


def test_step_larger_than_wheel_is_lethal():
    min_z, max_z, count = _seen_grid()
    max_z[3, 3] = WHEEL_RADIUS_M + 0.01  # 7.7 cm step
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert g.classes[3, 3] == CLS_LETHAL_STEP
    assert g.cost[3, 3] == COST_LETHAL


def test_gentle_slope_is_gentle():
    # 15 deg slope over the whole grid: dz/dx = tan(15 deg) ≈ 0.268
    min_z = np.zeros((6, 6), dtype=np.float32)
    max_z = np.zeros((6, 6), dtype=np.float32)
    count = np.ones((6, 6), dtype=np.int32)
    for i in range(6):
        for j in range(6):
            min_z[i, j] = 0.268 * (j * 0.10)
            max_z[i, j] = min_z[i, j]
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    # Interior cells should be CLS_GENTLE (boundary cells might differ due to gradient edge)
    interior = g.classes[1:-1, 1:-1]
    assert (interior == CLS_GENTLE).all(), f"expected all gentle, got {np.unique(interior)}"


def test_steep_slope_is_steep():
    # 25 deg slope: dz/dx = tan(25 deg) ≈ 0.466
    min_z = np.zeros((6, 6), dtype=np.float32)
    max_z = np.zeros((6, 6), dtype=np.float32)
    count = np.ones((6, 6), dtype=np.int32)
    for i in range(6):
        for j in range(6):
            min_z[i, j] = 0.466 * (j * 0.10)
            max_z[i, j] = min_z[i, j]
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    interior = g.classes[1:-1, 1:-1]
    assert (interior == CLS_STEEP).all()


def test_lethal_slope_over_30deg():
    # 35 deg slope: dz/dx = tan(35 deg) ≈ 0.700
    min_z = np.zeros((6, 6), dtype=np.float32)
    max_z = np.zeros((6, 6), dtype=np.float32)
    count = np.ones((6, 6), dtype=np.int32)
    for i in range(6):
        for j in range(6):
            min_z[i, j] = 0.700 * (j * 0.10)
            max_z[i, j] = min_z[i, j]
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    interior = g.classes[1:-1, 1:-1]
    assert (interior == CLS_LETHAL_SLOPE).all()
    assert (g.cost[1:-1, 1:-1] == COST_LETHAL).all()


def test_cliff_below_rover_base_is_lethal():
    min_z, max_z, count = _seen_grid()
    min_z[2, 2] = -0.60  # true precipice: > 50 cm drop
    max_z[2, 2] = -0.60  # uniform depth, no step -> pure cliff
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert g.classes[2, 2] == CLS_LETHAL_CLIFF
    assert g.cost[2, 2] == COST_LETHAL


def test_rough_but_traversable():
    # 4 cm step (above rough threshold 3 cm, below lethal 6.68 cm), flat neighbours
    min_z, max_z, count = _seen_grid()
    max_z[3, 3] = 0.04
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert g.classes[3, 3] == CLS_ROUGH
    assert g.cost[3, 3] == COST_ROUGH


def test_lethal_priority_over_slope():
    # A cell that is BOTH steep and has a big step -> classified as LETHAL_STEP
    # (lethal precedence: step first)
    min_z = np.zeros((6, 6), dtype=np.float32)
    max_z = np.zeros((6, 6), dtype=np.float32)
    count = np.ones((6, 6), dtype=np.int32)
    for i in range(6):
        for j in range(6):
            min_z[i, j] = 0.5 * (j * 0.10)  # steep slope everywhere
            max_z[i, j] = min_z[i, j]
    max_z[2, 2] += 0.10  # big step at (2,2)
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    assert g.classes[2, 2] == CLS_LETHAL_STEP


def test_summary_shape():
    min_z, max_z, count = _seen_grid()
    g = classify_grid(min_z, max_z, count, cell_m=0.10)
    s = g.summary
    assert s['cells_total'] == 36
    assert s['cells_seen'] == 36
    assert s['coverage_pct'] == 100.0
    assert s['flat'] == 36
