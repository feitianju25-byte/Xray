from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class GridGeometry:
    two_dimensionality: float
    orthogonality: float
    spacing_consistency: float
    balanced_extent: float
    primary_angle_degrees: float | None
    secondary_angle_degrees: float | None


def _candidate_value(candidate: object, name: str, default: float = 0.0) -> float:
    if isinstance(candidate, dict):
        return float(candidate.get(name, default))
    return float(getattr(candidate, name, default))


def _angle_distance(left: float, right: float) -> float:
    difference = abs(left - right) % math.pi
    return min(difference, math.pi - difference)


def _axis_distances(points: np.ndarray, angle: float, tolerance: float) -> tuple[np.ndarray, float]:
    direction = np.array([math.cos(angle), math.sin(angle)], dtype=np.float64)
    normal = np.array([-direction[1], direction[0]], dtype=np.float64)
    distances: list[float] = []
    supported = 0
    for index, point in enumerate(points):
        offsets = points - point
        along = np.abs(offsets @ direction)
        across = np.abs(offsets @ normal)
        valid = (along > 1e-6) & (across <= np.maximum(1.0, along * math.tan(tolerance)))
        if np.any(valid):
            distances.append(float(np.min(along[valid])))
            supported += 1
    return np.asarray(distances, dtype=np.float64), supported / max(1, len(points))


def estimate_grid_geometry(points: np.ndarray) -> GridGeometry:
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("points must have shape (n, 2)")
    if len(points) < 6:
        return GridGeometry(0.0, 0.0, 0.0, 0.0, None, None)

    offsets = points[None, :, :] - points[:, None, :]
    distances = np.linalg.norm(offsets, axis=2)
    np.fill_diagonal(distances, np.inf)
    neighbour_count = min(6, len(points) - 1)
    neighbour_indices = np.argpartition(distances, neighbour_count - 1, axis=1)[:, :neighbour_count]
    rows = np.arange(len(points))[:, None]
    vectors = offsets[rows, neighbour_indices].reshape(-1, 2)
    vector_lengths = np.linalg.norm(vectors, axis=1)
    angles = np.mod(np.arctan2(vectors[:, 1], vectors[:, 0]), math.pi)

    bins = 36
    histogram, edges = np.histogram(angles, bins=bins, range=(0.0, math.pi), weights=1.0 / np.maximum(vector_lengths, 1.0))
    primary_index = int(np.argmax(histogram))
    primary_angle = float((edges[primary_index] + edges[primary_index + 1]) / 2.0)
    eligible = [
        index
        for index in range(bins)
        if math.radians(55) <= _angle_distance(primary_angle, (edges[index] + edges[index + 1]) / 2.0) <= math.radians(125)
    ]
    if not eligible:
        return GridGeometry(0.0, 0.0, 0.0, 0.0, math.degrees(primary_angle), None)
    secondary_index = max(eligible, key=lambda index: histogram[index])
    secondary_angle = float((edges[secondary_index] + edges[secondary_index + 1]) / 2.0)

    separation = _angle_distance(primary_angle, secondary_angle)
    orthogonality = math.exp(-((separation - math.pi / 2.0) / math.radians(18)) ** 2)
    tolerance = math.radians(16)
    primary_distances, primary_support = _axis_distances(points, primary_angle, tolerance)
    secondary_distances, secondary_support = _axis_distances(points, secondary_angle, tolerance)

    def consistency(values: np.ndarray) -> float:
        if len(values) < max(3, len(points) // 3):
            return 0.0
        median = float(np.median(values))
        if median <= 1e-6:
            return 0.0
        robust_cv = float(np.median(np.abs(values - median))) / median
        return math.exp(-5.0 * robust_cv)

    spacing_consistency = math.sqrt(consistency(primary_distances) * consistency(secondary_distances))
    support = math.sqrt(primary_support * secondary_support)
    two_dimensionality = float(np.clip(orthogonality * support, 0.0, 1.0))

    primary_projection = points @ np.array([math.cos(primary_angle), math.sin(primary_angle)])
    secondary_projection = points @ np.array([math.cos(secondary_angle), math.sin(secondary_angle)])
    primary_span = float(np.ptp(primary_projection))
    secondary_span = float(np.ptp(secondary_projection))
    raw_balanced_extent = min(primary_span, secondary_span) / max(primary_span, secondary_span, 1e-6)
    balanced_extent = raw_balanced_extent * support

    return GridGeometry(
        two_dimensionality=two_dimensionality,
        orthogonality=orthogonality,
        spacing_consistency=spacing_consistency,
        balanced_extent=balanced_extent,
        primary_angle_degrees=math.degrees(primary_angle),
        secondary_angle_degrees=math.degrees(secondary_angle),
    )


def score_candidate_region(
    candidates: Iterable[object],
    image_size: tuple[int, int],
    package_bbox: tuple[float, float, float, float] | None = None,
) -> dict:
    """Score whether circular candidates form an internal, frontal two-dimensional chip grid."""
    candidates = list(candidates)
    points = np.asarray(
        [[_candidate_value(candidate, "x"), _candidate_value(candidate, "y")] for candidate in candidates],
        dtype=np.float64,
    )
    radii = np.asarray([_candidate_value(candidate, "radius", 1.0) for candidate in candidates], dtype=np.float64)
    width, height = image_size
    if len(points) == 0:
        return {
            "score": 0.0,
            "components": {},
            "candidate_count": 0,
            "package_bbox": None,
            "rejection_reasons": ["no-circular-candidates"],
        }

    median_radius = max(float(np.median(radii)), 1e-6)
    if package_bbox is None:
        padding = median_radius * 2.5
        package_bbox = (
            max(0.0, float(np.min(points[:, 0]) - padding)),
            max(0.0, float(np.min(points[:, 1]) - padding)),
            min(float(width), float(np.max(points[:, 0]) + padding)),
            min(float(height), float(np.max(points[:, 1]) + padding)),
        )
    left, top, right, bottom = package_bbox
    package_width = max(1.0, right - left)
    package_height = max(1.0, bottom - top)
    inside = (points[:, 0] >= left) & (points[:, 0] <= right) & (points[:, 1] >= top) & (points[:, 1] <= bottom)
    containment = float(np.mean(inside))

    geometry = estimate_grid_geometry(points)
    radius_cv = float(np.std(radii) / median_radius)
    radius_consistency = math.exp(-4.0 * radius_cv)
    aspect_score = min(package_width, package_height) / max(package_width, package_height)
    margins = np.column_stack(
        [points[:, 0] - left, right - points[:, 0], points[:, 1] - top, bottom - points[:, 1]]
    )
    positive_margins = np.maximum(np.min(margins, axis=1), 0.0)
    margin_ratio = float(np.median(positive_margins)) / min(package_width, package_height)
    interior_margin = float(np.clip(margin_ratio / 0.12, 0.0, 1.0))
    package_score = containment * (0.45 * aspect_score + 0.30 * interior_margin + 0.25 * geometry.balanced_extent)
    packing_density = float(len(points) * math.pi * median_radius**2 / (package_width * package_height))
    density_score = float(np.clip(packing_density / 0.05, 0.0, 1.0) * np.clip((0.55 - packing_density) / 0.20, 0.0, 1.0))
    count_score = float(np.clip((len(points) - 5) / 12.0, 0.0, 1.0))

    components = {
        "radius_consistency": radius_consistency,
        "two_dimensionality": geometry.two_dimensionality,
        "orthogonality": geometry.orthogonality,
        "spacing_consistency": geometry.spacing_consistency,
        "balanced_extent": geometry.balanced_extent,
        "package": package_score,
        "density": density_score,
        "count": count_score,
    }
    score = (
        0.14 * radius_consistency
        + 0.20 * geometry.two_dimensionality
        + 0.18 * geometry.spacing_consistency
        + 0.12 * geometry.balanced_extent
        + 0.20 * package_score
        + 0.08 * density_score
        + 0.08 * count_score
    )
    rejection_reasons = []
    if len(points) < 6:
        rejection_reasons.append("too-few-candidates")
    if geometry.two_dimensionality < 0.45:
        rejection_reasons.append("not-two-dimensional")
    if geometry.spacing_consistency < 0.45:
        rejection_reasons.append("irregular-spacing")
    if geometry.balanced_extent < 0.28:
        rejection_reasons.append("linear-or-narrow-layout")
    if package_score < 0.65:
        rejection_reasons.append("package-or-view-mismatch")
    if radius_consistency < 0.55:
        rejection_reasons.append("inconsistent-radius")

    return {
        "score": float(np.clip(score, 0.0, 1.0)),
        "components": components,
        "candidate_count": len(points),
        "package_bbox": [float(value) for value in package_bbox],
        "primary_angle_degrees": geometry.primary_angle_degrees,
        "secondary_angle_degrees": geometry.secondary_angle_degrees,
        "rejection_reasons": rejection_reasons,
    }
