from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class NormalizedGray:
    pixels: np.ndarray
    original_size: tuple[int, int]
    processing_size: tuple[int, int]
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class CircleCandidate:
    x: float
    y: float
    radius: float
    polarity: str
    response: float
    circularity: float
    processing_x: int
    processing_y: int
    processing_radius: float

    def to_dict(self) -> dict:
        return asdict(self)


def _load_grayscale(source: str | Path | Image.Image | np.ndarray) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.convert("L")
    if isinstance(source, np.ndarray):
        array = np.asarray(source)
        if array.ndim == 3:
            array = np.mean(array[..., :3], axis=2)
        if array.ndim != 2:
            raise ValueError("array source must be two-dimensional grayscale or RGB")
        if np.issubdtype(array.dtype, np.floating):
            maximum = float(np.nanmax(array)) if array.size else 0.0
            array = array * 255.0 if maximum <= 1.0 else array
        return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), mode="L")
    with Image.open(source) as image:
        return image.convert("L")


def normalize_grayscale(
    source: str | Path | Image.Image | np.ndarray,
    max_side: int = 768,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.0,
) -> NormalizedGray:
    """Load, resize and robustly normalize an image to float32 in [0, 1]."""
    if max_side < 32:
        raise ValueError("max_side must be at least 32")
    image = _load_grayscale(source)
    original_size = image.size
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    processing_size = image.size
    pixels = np.asarray(image, dtype=np.float32)
    low, high = np.percentile(pixels, [lower_percentile, upper_percentile])
    if high - low < 1e-6:
        minimum, maximum = float(np.min(pixels)), float(np.max(pixels))
        if maximum - minimum < 1e-6:
            normalized = np.zeros_like(pixels, dtype=np.float32)
        else:
            normalized = ((pixels - minimum) / (maximum - minimum)).astype(np.float32)
    else:
        normalized = np.clip((pixels - low) / (high - low), 0.0, 1.0).astype(np.float32)
    return NormalizedGray(
        pixels=normalized,
        original_size=original_size,
        processing_size=processing_size,
        scale_x=original_size[0] / processing_size[0],
        scale_y=original_size[1] / processing_size[1],
    )


def _gaussian(array: np.ndarray, sigma: float) -> np.ndarray:
    image = Image.fromarray(np.round(array * 255.0).astype(np.uint8), mode="L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=float(sigma)))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def _sample_nearest(array: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    xi = np.clip(np.rint(x).astype(int), 0, array.shape[1] - 1)
    yi = np.clip(np.rint(y).astype(int), 0, array.shape[0] - 1)
    return array[yi, xi]


def _refine_center(strength: np.ndarray, x: int, y: int, radius: float) -> tuple[int, int]:
    half = max(2, int(round(radius * 0.65)))
    left, right = max(0, x - half), min(strength.shape[1], x + half + 1)
    top, bottom = max(0, y - half), min(strength.shape[0], y + half + 1)
    patch = strength[top:bottom, left:right]
    floor = float(np.quantile(patch, 0.55))
    weights = np.maximum(patch - floor, 0.0)
    total = float(np.sum(weights))
    if total <= 1e-8:
        return x, y
    yy, xx = np.indices(patch.shape)
    refined_x = int(round(left + float(np.sum(xx * weights)) / total))
    refined_y = int(round(top + float(np.sum(yy * weights)) / total))
    return refined_x, refined_y


def _refine_intensity_center(
    array: np.ndarray, x: int, y: int, radius: float, polarity: str
) -> tuple[int, int]:
    half = max(3, int(round(radius * 1.35)))
    left, right = max(0, x - half), min(array.shape[1], x + half + 1)
    top, bottom = max(0, y - half), min(array.shape[0], y + half + 1)
    patch = array[top:bottom, left:right]
    baseline = float(np.median(patch))
    weights = np.maximum(baseline - patch, 0.0) if polarity == "dark" else np.maximum(patch - baseline, 0.0)
    yy, xx = np.indices(patch.shape)
    distance = np.hypot(xx - (x - left), yy - (y - top))
    weights = np.where(distance <= radius * 1.25, weights, 0.0)
    total = float(np.sum(weights))
    if total <= 1e-8:
        return x, y
    refined_x = int(round(left + float(np.sum(xx * weights)) / total))
    refined_y = int(round(top + float(np.sum(yy * weights)) / total))
    return refined_x, refined_y


def _circular_evidence(array: np.ndarray, x: int, y: int, radius: float, polarity: str) -> tuple[float, float]:
    angles = np.linspace(0.0, 2.0 * np.pi, 20, endpoint=False)
    inside = _sample_nearest(array, x + np.cos(angles) * radius * 0.45, y + np.sin(angles) * radius * 0.45)
    outside = _sample_nearest(array, x + np.cos(angles) * radius * 1.35, y + np.sin(angles) * radius * 1.35)
    directional = outside - inside if polarity == "dark" else inside - outside
    contrast = float(np.mean(directional))
    positive_fraction = float(np.mean(directional > 0.0))
    consistency = 1.0 - min(1.0, float(np.std(directional)) / (abs(contrast) + 1e-6))
    circularity = float(np.clip(0.65 * positive_fraction + 0.35 * consistency, 0.0, 1.0))
    return contrast, circularity


def _overlaps(candidate: CircleCandidate, accepted: CircleCandidate) -> bool:
    dx = candidate.processing_x - accepted.processing_x
    dy = candidate.processing_y - accepted.processing_y
    minimum_distance = 0.8 * max(candidate.processing_radius, accepted.processing_radius)
    return dx * dx + dy * dy < minimum_distance * minimum_distance


def detect_circular_candidates(
    source: str | Path | Image.Image | np.ndarray,
    radii: Iterable[float] = (4, 6, 9, 13, 18),
    max_side: int = 768,
    min_contrast: float = 0.06,
    min_circularity: float = 0.55,
    max_candidates: int = 500,
) -> dict:
    """Detect bright and dark near-circular blobs at several processing scales."""
    radii = tuple(float(radius) for radius in radii)
    normalized = normalize_grayscale(source, max_side=max_side)
    array = normalized.pixels
    proposals: list[CircleCandidate] = []

    for radius in radii:
        if radius < 2.0:
            raise ValueError("all radii must be at least 2 pixels")
        inner = _gaussian(array, max(0.8, radius * 0.32))
        outer = _gaussian(array, max(1.2, radius * 0.85))
        signed = inner - outer
        strength = np.abs(signed)
        median = float(np.median(strength))
        mad = float(np.median(np.abs(strength - median)))
        threshold = max(float(np.quantile(strength, 0.985)), median + 3.5 * mad, min_contrast * 0.25)
        ys, xs = np.nonzero(strength >= threshold)
        if not len(xs):
            continue
        order = np.argsort(strength[ys, xs])[::-1]
        border = int(np.ceil(radius * 1.5))
        per_scale_limit = min(len(order), max(max_candidates * 12, 600))
        for offset in order[:per_scale_limit]:
            x, y = int(xs[offset]), int(ys[offset])
            x, y = _refine_center(strength, x, y, radius)
            if x < border or y < border or x >= array.shape[1] - border or y >= array.shape[0] - border:
                continue
            polarity = "bright" if signed[y, x] > 0 else "dark"
            x, y = _refine_intensity_center(array, x, y, radius, polarity)
            contrast, circularity = _circular_evidence(array, x, y, radius, polarity)
            if contrast < min_contrast or circularity < min_circularity:
                continue
            scale_radius = radius * (normalized.scale_x * normalized.scale_y) ** 0.5
            proposals.append(
                CircleCandidate(
                    x=(x + 0.5) * normalized.scale_x - 0.5,
                    y=(y + 0.5) * normalized.scale_y - 0.5,
                    radius=scale_radius,
                    polarity=polarity,
                    response=float(contrast * circularity),
                    circularity=circularity,
                    processing_x=x,
                    processing_y=y,
                    processing_radius=radius,
                )
            )

    accepted: list[CircleCandidate] = []
    for candidate in sorted(proposals, key=lambda item: (item.response, item.circularity), reverse=True):
        if any(_overlaps(candidate, previous) for previous in accepted):
            continue
        accepted.append(candidate)
        if len(accepted) >= max_candidates:
            break

    return {
        "algorithm": "multiscale-difference-of-gaussians-v1",
        "original_size": list(normalized.original_size),
        "processing_size": list(normalized.processing_size),
        "radii": list(radii),
        "candidates": [candidate.to_dict() for candidate in accepted],
    }
