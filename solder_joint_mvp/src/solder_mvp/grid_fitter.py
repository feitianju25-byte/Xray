from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class BasisEstimate:
    column: np.ndarray
    row: np.ndarray
    orthogonality: float


def _point(candidate: object) -> tuple[float, float]:
    if isinstance(candidate, dict):
        return float(candidate["x"]), float(candidate["y"])
    return float(getattr(candidate, "x")), float(getattr(candidate, "y"))


def _angle_distance(left: np.ndarray | float, right: float) -> np.ndarray:
    difference = np.abs(np.asarray(left) - right) % math.pi
    return np.minimum(difference, math.pi - difference)


def _refine_orientation(angles: np.ndarray, lengths: np.ndarray, initial: float) -> float:
    mask = _angle_distance(angles, initial) <= math.radians(12)
    selected = angles[mask]
    if not len(selected):
        return initial
    weights = 1.0 / np.maximum(lengths[mask], 1.0)
    doubled = np.sum(weights * np.exp(2j * selected))
    refined = (np.angle(doubled) / 2.0) % math.pi
    return float(refined)


def _basis_length(points: np.ndarray, angle: float) -> float:
    direction = np.array([math.cos(angle), math.sin(angle)])
    normal = np.array([-direction[1], direction[0]])
    candidates = []
    for point in points:
        offsets = points - point
        along = np.abs(offsets @ direction)
        across = np.abs(offsets @ normal)
        valid = (along > 2.0) & (across <= np.maximum(1.5, along * math.tan(math.radians(14))))
        if np.any(valid):
            candidates.append(float(np.min(along[valid])))
    if len(candidates) < 3:
        raise ValueError("not enough aligned neighbours to estimate grid spacing")
    return float(np.median(candidates))


def estimate_basis(points: np.ndarray) -> BasisEstimate:
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 6:
        raise ValueError("at least six points are required to fit a grid")
    offsets = points[None, :, :] - points[:, None, :]
    distances = np.linalg.norm(offsets, axis=2)
    np.fill_diagonal(distances, np.inf)
    neighbour_count = min(6, len(points) - 1)
    indices = np.argpartition(distances, neighbour_count - 1, axis=1)[:, :neighbour_count]
    rows = np.arange(len(points))[:, None]
    vectors = offsets[rows, indices].reshape(-1, 2)
    lengths = np.linalg.norm(vectors, axis=1)
    angles = np.mod(np.arctan2(vectors[:, 1], vectors[:, 0]), math.pi)
    histogram, edges = np.histogram(angles, bins=72, range=(0.0, math.pi), weights=1.0 / np.maximum(lengths, 1.0))
    first_index = int(np.argmax(histogram))
    first = float((edges[first_index] + edges[first_index + 1]) / 2.0)
    eligible = [
        index
        for index in range(len(histogram))
        if math.radians(55)
        <= float(_angle_distance((edges[index] + edges[index + 1]) / 2.0, first))
        <= math.radians(125)
    ]
    if not eligible:
        raise ValueError("could not find a second grid direction")
    second_index = max(eligible, key=lambda index: histogram[index])
    second = float((edges[second_index] + edges[second_index + 1]) / 2.0)
    first = _refine_orientation(angles, lengths, first)
    second = _refine_orientation(angles, lengths, second)

    first_length = _basis_length(points, first)
    second_length = _basis_length(points, second)
    first_vector = np.array([math.cos(first), math.sin(first)]) * first_length
    second_vector = np.array([math.cos(second), math.sin(second)]) * second_length
    separation = float(_angle_distance(first, second))
    orthogonality = math.exp(-((separation - math.pi / 2.0) / math.radians(18)) ** 2)

    vectors_by_angle = sorted((first_vector, second_vector), key=lambda vector: math.atan2(vector[1], vector[0]) % math.pi)
    return BasisEstimate(column=vectors_by_angle[0], row=vectors_by_angle[1], orthogonality=orthogonality)


def _phase(values: np.ndarray) -> float:
    circular = np.mean(np.exp(2j * math.pi * values))
    return float((np.angle(circular) / (2.0 * math.pi)) % 1.0)


def _largest_connected_cells(best_by_cell: dict[tuple[int, int], int]) -> list[int]:
    remaining = set(best_by_cell)
    components: list[set[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        frontier = [start]
        while frontier:
            column, row = frontier.pop()
            for neighbour in ((column - 1, row), (column + 1, row), (column, row - 1), (column, row + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    component.add(neighbour)
                    frontier.append(neighbour)
        components.append(component)
    largest = max(components, key=lambda component: (len(component), -min(sum(map(abs, cell)) for cell in component)))
    return [best_by_cell[cell] for cell in largest]


def fit_grid(candidates: Iterable[object], residual_tolerance: float = 0.32) -> dict:
    candidates = list(candidates)
    points = np.asarray([_point(candidate) for candidate in candidates], dtype=np.float64)
    basis = estimate_basis(points)
    matrix = np.column_stack([basis.column, basis.row])
    inverse = np.linalg.inv(matrix)
    coefficients = points @ inverse.T
    phases = np.array([_phase(coefficients[:, 0]), _phase(coefficients[:, 1])])
    lattice = np.rint(coefficients - phases).astype(int)

    origin = matrix @ phases
    for _ in range(3):
        predicted = origin + lattice @ matrix.T
        residuals = np.linalg.norm(points - predicted, axis=1)
        scale = max(1e-6, min(np.linalg.norm(matrix[:, 0]), np.linalg.norm(matrix[:, 1])))
        inliers = residuals <= residual_tolerance * scale
        if np.count_nonzero(inliers) < 6:
            raise ValueError("fewer than six grid inliers remain after robust fitting")
        design = np.column_stack([np.ones(np.count_nonzero(inliers)), lattice[inliers, 0], lattice[inliers, 1]])
        coefficients_xy, _, _, _ = np.linalg.lstsq(design, points[inliers], rcond=None)
        origin = coefficients_xy[0]
        matrix = np.column_stack([coefficients_xy[1], coefficients_xy[2]])
        inverse = np.linalg.inv(matrix)
        continuous = (points - origin) @ inverse.T
        lattice = np.rint(continuous).astype(int)

    predicted = origin + lattice @ matrix.T
    residuals = np.linalg.norm(points - predicted, axis=1)
    scale = max(1e-6, min(np.linalg.norm(matrix[:, 0]), np.linalg.norm(matrix[:, 1])))
    provisional = residuals <= residual_tolerance * scale
    best_by_cell: dict[tuple[int, int], int] = {}
    for index in np.flatnonzero(provisional):
        cell = int(lattice[index, 0]), int(lattice[index, 1])
        previous = best_by_cell.get(cell)
        if previous is None or residuals[index] < residuals[previous]:
            best_by_cell[cell] = int(index)
    inlier_indices = sorted(_largest_connected_cells(best_by_cell))
    if len(inlier_indices) < 6:
        raise ValueError("fewer than six unique grid cells remain after fitting")

    min_column = min(int(lattice[index, 0]) for index in inlier_indices)
    min_row = min(int(lattice[index, 1]) for index in inlier_indices)
    observed_cells = []
    inlier_set = set(inlier_indices)
    for index in inlier_indices:
        column = int(lattice[index, 0]) - min_column
        row = int(lattice[index, 1]) - min_row
        observed_cells.append(
            {
                "row": row,
                "col": column,
                "x": float(points[index, 0]),
                "y": float(points[index, 1]),
                "predicted_x": float(predicted[index, 0]),
                "predicted_y": float(predicted[index, 1]),
                "residual": float(residuals[index]),
                "confidence": float(math.exp(-((residuals[index] / scale) / residual_tolerance) ** 2)),
                "source_index": index,
                "status": "observed",
            }
        )
    observed_cells.sort(key=lambda cell: (cell["row"], cell["col"]))
    outliers = [
        {"source_index": index, "x": float(point[0]), "y": float(point[1]), "residual": float(residuals[index])}
        for index, point in enumerate(points)
        if index not in inlier_set
    ]
    row_count = max(cell["row"] for cell in observed_cells) + 1
    column_count = max(cell["col"] for cell in observed_cells) + 1
    observed_by_cell = {(cell["row"], cell["col"]): cell for cell in observed_cells}
    cells = []
    for row in range(row_count):
        for column in range(column_count):
            observed = observed_by_cell.get((row, column))
            if observed is not None:
                cells.append(observed)
                continue
            raw_lattice = np.array([column + min_column, row + min_row], dtype=np.float64)
            expected = origin + matrix @ raw_lattice
            cells.append(
                {
                    "row": row,
                    "col": column,
                    "x": float(expected[0]),
                    "y": float(expected[1]),
                    "predicted_x": float(expected[0]),
                    "predicted_y": float(expected[1]),
                    "residual": None,
                    "confidence": 0.0,
                    "source_index": None,
                    "status": "missing",
                }
            )
    mean_relative_residual = float(np.mean([cell["residual"] for cell in observed_cells]) / scale)
    occupancy = len(observed_cells) / (row_count * column_count)
    confidence = basis.orthogonality * occupancy * (len(observed_cells) / len(points)) * math.exp(-3.0 * mean_relative_residual)

    return {
        "algorithm": "robust-dual-basis-v1",
        "rows": row_count,
        "cols": column_count,
        "origin": [float(origin[0]), float(origin[1])],
        "column_basis": [float(matrix[0, 0]), float(matrix[1, 0])],
        "row_basis": [float(matrix[0, 1]), float(matrix[1, 1])],
        "column_spacing": float(np.linalg.norm(matrix[:, 0])),
        "row_spacing": float(np.linalg.norm(matrix[:, 1])),
        "orthogonality": basis.orthogonality,
        "confidence": float(np.clip(confidence, 0.0, 1.0)),
        "observed_count": len(observed_cells),
        "missing_count": len(cells) - len(observed_cells),
        "cells": cells,
        "outliers": outliers,
    }


def _bilinear_point(corners: np.ndarray, row: int, column: int, rows: int, cols: int) -> np.ndarray:
    vertical = row / max(1, rows - 1)
    horizontal = column / max(1, cols - 1)
    top = corners[0] * (1.0 - horizontal) + corners[1] * horizontal
    bottom = corners[3] * (1.0 - horizontal) + corners[2] * horizontal
    return top * (1.0 - vertical) + bottom * vertical


def _fit_review_geometry(candidates: list[object], corners: np.ndarray, rows: int, cols: int) -> dict:
    points = np.asarray([_point(candidate) for candidate in candidates], dtype=np.float64)
    column_basis = (corners[1] - corners[0]) / max(1, cols - 1)
    row_basis = (corners[3] - corners[0]) / max(1, rows - 1)
    column_spacing = float(np.linalg.norm(column_basis))
    row_spacing = float(np.linalg.norm(row_basis))
    tolerance = 0.38 * min(column_spacing, row_spacing)
    unused = set(range(len(points)))
    cells = []
    observed_residuals = []
    for row in range(rows):
        for column in range(cols):
            predicted = _bilinear_point(corners, row, column, rows, cols)
            selected = None
            residual = None
            if unused:
                selected = min(unused, key=lambda index: float(np.linalg.norm(points[index] - predicted)))
                residual = float(np.linalg.norm(points[selected] - predicted))
                if residual > tolerance:
                    selected = None
            if selected is None:
                cells.append({
                    "row": row,
                    "col": column,
                    "x": float(predicted[0]),
                    "y": float(predicted[1]),
                    "predicted_x": float(predicted[0]),
                    "predicted_y": float(predicted[1]),
                    "residual": None,
                    "confidence": 0.0,
                    "source_index": None,
                    "status": "missing",
                })
                continue
            unused.remove(selected)
            observed_residuals.append(residual)
            cells.append({
                "row": row,
                "col": column,
                "x": float(points[selected, 0]),
                "y": float(points[selected, 1]),
                "predicted_x": float(predicted[0]),
                "predicted_y": float(predicted[1]),
                "residual": residual,
                "confidence": float(math.exp(-((residual / max(tolerance, 1e-6)) ** 2))),
                "source_index": selected,
                "status": "observed",
            })
    observed_count = len(observed_residuals)
    occupancy = observed_count / (rows * cols)
    mean_relative_residual = float(np.mean(observed_residuals) / min(column_spacing, row_spacing)) if observed_residuals else 1.0
    cosine = abs(float(np.dot(column_basis, row_basis))) / max(column_spacing * row_spacing, 1e-6)
    orthogonality = float(np.clip(1.0 - cosine, 0.0, 1.0))
    return {
        "algorithm": "review-constrained-bilinear-v1",
        "rows": rows,
        "cols": cols,
        "origin": [float(corners[0, 0]), float(corners[0, 1])],
        "corners": corners.tolist(),
        "column_basis": column_basis.tolist(),
        "row_basis": row_basis.tolist(),
        "column_spacing": column_spacing,
        "row_spacing": row_spacing,
        "orthogonality": orthogonality,
        "confidence": float(np.clip(occupancy * orthogonality * math.exp(-3.0 * mean_relative_residual), 0.0, 1.0)),
        "observed_count": observed_count,
        "missing_count": rows * cols - observed_count,
        "cells": cells,
        "outliers": [
            {"source_index": index, "x": float(points[index, 0]), "y": float(points[index, 1])}
            for index in sorted(unused)
        ],
    }


def refit_grid_from_review(candidates: Iterable[object], review: dict, residual_tolerance: float = 0.32) -> dict:
    """Re-fit deterministically from an array box, ordered corners, dimensions or corrected centers."""
    candidates = list(candidates)
    corrected = [{"x": float(center[0]), "y": float(center[1]), "corrected": True} for center in review.get("centers", [])]
    working = candidates + corrected
    bbox = review.get("array_bbox")
    if bbox is not None:
        left, top, right, bottom = (float(value) for value in bbox)
        working = [candidate for candidate in working if left <= _point(candidate)[0] <= right and top <= _point(candidate)[1] <= bottom]

    rows = review.get("rows")
    cols = review.get("cols")
    corners = review.get("corners") or []
    if len(corners) == 4 and rows and cols:
        corner_array = np.asarray(corners, dtype=np.float64)
        result = _fit_review_geometry(working, corner_array, int(rows), int(cols))
    elif bbox is not None and rows and cols:
        left, top, right, bottom = (float(value) for value in bbox)
        corner_array = np.asarray([(left, top), (right, top), (right, bottom), (left, bottom)], dtype=np.float64)
        result = _fit_review_geometry(working, corner_array, int(rows), int(cols))
    else:
        result = fit_grid(working, residual_tolerance=residual_tolerance)
        if rows is not None and int(rows) != result["rows"]:
            result["dimension_warning"] = f"review rows={rows}, fitted rows={result['rows']}"
        if cols is not None and int(cols) != result["cols"]:
            result["dimension_warning"] = f"review cols={cols}, fitted cols={result['cols']}"
    result["review_constraints"] = {
        "array_bbox": bbox,
        "rows": rows,
        "cols": cols,
        "corners": corners,
        "corrected_center_count": len(corrected),
    }
    return result
