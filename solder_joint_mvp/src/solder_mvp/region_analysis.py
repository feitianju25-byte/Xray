from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .candidate_detector import detect_circular_candidates
from .io_utils import write_json
from .region_scorer import score_candidate_region


def _select_internal_grid(candidates: list[dict], package_bbox: tuple[float, float, float, float]) -> tuple[list[dict], dict]:
    left, top, right, bottom = package_bbox
    margin_x = (right - left) * 0.07
    margin_y = (bottom - top) * 0.07
    internal = [
        candidate
        for candidate in candidates
        if left + margin_x <= candidate["x"] <= right - margin_x
        and top + margin_y <= candidate["y"] <= bottom - margin_y
    ]
    if not internal:
        return [], score_candidate_region([], (int(right), int(bottom)), package_bbox)

    radius_anchors = sorted({round(float(candidate["radius"]), 3) for candidate in internal})
    groups: list[tuple[list[dict], dict]] = []
    for polarity in ("dark", "bright"):
        for radius in radius_anchors:
            group = [
                candidate
                for candidate in internal
                if candidate["polarity"] == polarity and 0.72 * radius <= candidate["radius"] <= 1.38 * radius
            ]
            if len(group) < 6:
                continue
            groups.append((group, score_candidate_region(group, (int(right), int(bottom)), package_bbox)))
    if not groups:
        score = score_candidate_region(internal, (int(right), int(bottom)), package_bbox)
        return internal, score
    return max(groups, key=lambda item: (item[1]["score"], len(item[0])))


def analyze_solder_region(
    source: str | Path,
    package_bbox: tuple[float, float, float, float] | None = None,
    **detector_options: object,
) -> dict:
    detection = detect_circular_candidates(source, **detector_options)
    candidates = detection["candidates"]
    raw_candidate_count = len(candidates)
    if package_bbox is not None:
        left, top, right, bottom = package_bbox
        candidates = [
            candidate
            for candidate in candidates
            if left <= candidate["x"] <= right and top <= candidate["y"] <= bottom
        ]
        candidates, score = _select_internal_grid(candidates, package_bbox)
    else:
        score = score_candidate_region(candidates, tuple(detection["original_size"]), package_bbox)
    return {
        "schema_version": "1.0",
        "algorithm_version": "0.3.0",
        "source_path": str(Path(source).resolve()),
        "processing_size": detection["processing_size"],
        "raw_candidate_count": raw_candidate_count,
        "candidate_bbox": score["package_bbox"],
        "confidence": score["score"],
        "score_components": score["components"],
        "rejection_reasons": score["rejection_reasons"],
        "centers": candidates,
    }


def save_region_analysis(result: dict, output_path: str | Path) -> Path:
    return write_json(output_path, result)


def render_region_overlay(source: str | Path, result: dict, output_path: str | Path) -> Path:
    with Image.open(source) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    bbox = result.get("candidate_bbox")
    if bbox:
        draw.rectangle(tuple(bbox), outline="#ffd400", width=max(2, round(min(canvas.size) / 300)))

    for candidate in result.get("centers", []):
        x, y = float(candidate["x"]), float(candidate["y"])
        radius = max(2.0, float(candidate["radius"]))
        color = "#00d8ff" if candidate.get("polarity") == "dark" else "#ff4fd8"
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=2)
        draw.line((x - 3, y, x + 3, y), fill=color, width=1)
        draw.line((x, y - 3, x, y + 3), fill=color, width=1)

    confidence = float(result.get("confidence", 0.0))
    reasons = ", ".join(result.get("rejection_reasons", [])) or "accepted"
    label = f"confidence={confidence:.3f}  centers={len(result.get('centers', []))}  {reasons}"
    font = ImageFont.load_default()
    label_box = draw.textbbox((0, 0), label, font=font)
    label_width = label_box[2] - label_box[0] + 12
    label_height = label_box[3] - label_box[1] + 10
    draw.rectangle((0, 0, label_width, label_height), fill="black")
    draw.text((6, 5), label, fill="white", font=font)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)
    return destination
