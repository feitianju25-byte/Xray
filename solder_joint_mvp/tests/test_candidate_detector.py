from __future__ import annotations

import math

from PIL import Image, ImageDraw

from solder_mvp.candidate_detector import detect_circular_candidates, normalize_grayscale


def _circle_array(background: int, foreground: int, radius: int) -> tuple[Image.Image, list[tuple[int, int]]]:
    image = Image.new("L", (220, 180), background)
    draw = ImageDraw.Draw(image)
    centers = [(45 + column * 55, 42 + row * 48) for row in range(3) for column in range(3)]
    for x, y in centers:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=foreground)
    return image, centers


def _matched_centers(result: dict, expected: list[tuple[int, int]], polarity: str, tolerance: float = 3.0) -> int:
    candidates = [candidate for candidate in result["candidates"] if candidate["polarity"] == polarity]
    return sum(
        any(math.hypot(candidate["x"] - x, candidate["y"] - y) <= tolerance for candidate in candidates)
        for x, y in expected
    )


def test_normalize_grayscale_preserves_geometry_and_range() -> None:
    image = Image.new("L", (1200, 600), 100)
    normalized = normalize_grayscale(image, max_side=300)
    assert normalized.original_size == (1200, 600)
    assert normalized.processing_size == (300, 150)
    assert normalized.scale_x == 4.0
    assert normalized.scale_y == 4.0
    assert normalized.pixels.min() == 0.0
    assert normalized.pixels.max() == 0.0


def test_multiscale_detector_finds_dark_and_bright_circle_arrays() -> None:
    dark_image, dark_centers = _circle_array(background=205, foreground=35, radius=7)
    bright_image, bright_centers = _circle_array(background=45, foreground=220, radius=11)

    dark = detect_circular_candidates(dark_image, radii=(5, 7, 10), min_contrast=0.08, max_candidates=60)
    bright = detect_circular_candidates(bright_image, radii=(7, 11, 15), min_contrast=0.08, max_candidates=60)

    assert _matched_centers(dark, dark_centers, "dark") == len(dark_centers)
    assert _matched_centers(bright, bright_centers, "bright") == len(bright_centers)


def test_detector_reports_original_coordinates_after_thumbnailing() -> None:
    image = Image.new("L", (800, 800), 180)
    draw = ImageDraw.Draw(image)
    draw.ellipse((360, 360, 440, 440), fill=20)

    result = detect_circular_candidates(image, radii=(18, 20, 22), max_side=400, min_contrast=0.08, max_candidates=20)
    dark = [candidate for candidate in result["candidates"] if candidate["polarity"] == "dark"]
    assert any(math.hypot(candidate["x"] - 400, candidate["y"] - 400) <= 5 for candidate in dark)
    assert result["processing_size"] == [400, 400]
    assert result["original_size"] == [800, 800]
