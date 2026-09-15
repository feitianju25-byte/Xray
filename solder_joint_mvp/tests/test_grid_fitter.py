from __future__ import annotations

import math
import random

import pytest

from solder_mvp.grid_fitter import fit_grid, refit_grid_from_review


def _transformed_grid(angle_degrees: float, scale: float, perspective: float, seed: int) -> tuple[list[dict], int]:
    randomizer = random.Random(seed)
    angle = math.radians(angle_degrees)
    column = (scale * 24 * math.cos(angle), scale * 24 * math.sin(angle))
    row = (-scale * 28 * math.sin(angle), scale * 28 * math.cos(angle))
    candidates = []
    for grid_row in range(4):
        for grid_column in range(5):
            cross = perspective * grid_row * grid_column
            x = 140 + grid_column * column[0] + grid_row * row[0] + cross * math.cos(angle)
            y = 110 + grid_column * column[1] + grid_row * row[1] + cross * math.sin(angle)
            candidates.append({
                "x": x + randomizer.uniform(-0.35, 0.35),
                "y": y + randomizer.uniform(-0.35, 0.35),
                "truth": (grid_row, grid_column),
            })
    for _ in range(5):
        candidates.append({"x": randomizer.uniform(20, 330), "y": randomizer.uniform(20, 300)})
    randomizer.shuffle(candidates)
    return candidates, 20


@pytest.mark.parametrize(
    ("angle", "scale", "perspective"),
    [(0.0, 1.0, 0.0), (27.0, 0.75, 0.0), (-38.0, 1.35, 0.18)],
)
def test_robust_grid_numbering_survives_rotation_scale_perspective_and_outliers(
    angle: float, scale: float, perspective: float
) -> None:
    candidates, expected_cells = _transformed_grid(angle, scale, perspective, seed=20260915)
    result = fit_grid(candidates)

    assert len(result["cells"]) == expected_cells
    assert sorted((result["rows"], result["cols"])) == [4, 5]
    assert len({(cell["row"], cell["col"]) for cell in result["cells"]}) == expected_cells
    assert len(result["outliers"]) == 5
    assert result["confidence"] > 0.65
    assert result["orthogonality"] > 0.85


def test_missing_positions_are_inferred_without_renumbering_observed_cells() -> None:
    full_candidates, _ = _transformed_grid(24.0, 1.0, 0.08, seed=20260915)
    full = fit_grid(full_candidates)
    full_numbering = {
        full_candidates[cell["source_index"]]["truth"]: (cell["row"], cell["col"])
        for cell in full["cells"]
        if cell["status"] == "observed" and "truth" in full_candidates[cell["source_index"]]
    }

    removed_truth = {(1, 2), (2, 3)}
    partial_candidates = [candidate for candidate in full_candidates if candidate.get("truth") not in removed_truth]
    partial = fit_grid(partial_candidates)
    partial_numbering = {
        partial_candidates[cell["source_index"]]["truth"]: (cell["row"], cell["col"])
        for cell in partial["cells"]
        if cell["status"] == "observed" and "truth" in partial_candidates[cell["source_index"]]
    }

    assert partial["missing_count"] == 2
    assert sum(cell["status"] == "missing" for cell in partial["cells"]) == 2
    assert partial_numbering == {truth: index for truth, index in full_numbering.items() if truth not in removed_truth}


def test_review_corners_dimensions_and_corrected_center_reproduce_same_grid() -> None:
    corners = [(40.0, 35.0), (190.0, 48.0), (184.0, 148.0), (48.0, 155.0)]
    rows, cols = 3, 4
    candidates = []
    missing = (1, 2)
    for row in range(rows):
        for col in range(cols):
            if (row, col) == missing:
                continue
            vertical = row / (rows - 1)
            horizontal = col / (cols - 1)
            top = tuple(corners[0][axis] * (1 - horizontal) + corners[1][axis] * horizontal for axis in (0, 1))
            bottom = tuple(corners[3][axis] * (1 - horizontal) + corners[2][axis] * horizontal for axis in (0, 1))
            candidates.append({
                "x": top[0] * (1 - vertical) + bottom[0] * vertical,
                "y": top[1] * (1 - vertical) + bottom[1] * vertical,
            })
    corrected_center = [135.0, 98.0]
    review = {
        "array_bbox": [35.0, 30.0, 195.0, 160.0],
        "rows": rows,
        "cols": cols,
        "corners": [list(point) for point in corners],
        "centers": [corrected_center],
    }

    first = refit_grid_from_review(candidates, review)
    second = refit_grid_from_review(candidates, review)
    assert first == second
    assert first["algorithm"] == "review-constrained-bilinear-v1"
    assert first["rows"] == rows
    assert first["cols"] == cols
    assert first["observed_count"] == rows * cols
    assert first["missing_count"] == 0
    assert first["review_constraints"]["corrected_center_count"] == 1
