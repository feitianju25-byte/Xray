from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from solder_mvp.region_analysis import analyze_solder_region, render_region_overlay, save_region_analysis


def test_analysis_json_and_overlay_share_original_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "grid.png"
    image = Image.new("L", (260, 220), 205)
    draw = ImageDraw.Draw(image)
    expected = [(70 + column * 32, 68 + row * 34) for row in range(3) for column in range(4)]
    for x, y in expected:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=30)
    image.save(source)

    result = analyze_solder_region(
        source,
        package_bbox=(40, 35, 210, 180),
        radii=(6, 8, 11),
        max_side=260,
        min_contrast=0.08,
        max_candidates=80,
    )
    assert all(
        any(math.hypot(center["x"] - x, center["y"] - y) <= 3 for center in result["centers"])
        for x, y in expected
    )
    assert result["candidate_bbox"] == [40.0, 35.0, 210.0, 180.0]
    assert "confidence" in result
    assert "rejection_reasons" in result

    json_path = save_region_analysis(result, tmp_path / "analysis.json")
    overlay_path = render_region_overlay(source, result, tmp_path / "overlay.png")
    assert json_path.exists()
    with Image.open(overlay_path) as overlay:
        assert overlay.size == image.size
