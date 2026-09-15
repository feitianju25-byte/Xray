from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

from .io_utils import write_json


def create_labelme_annotation(
    source: str | Path,
    bbox: Iterable[float] | None = None,
    points: Iterable[dict | Iterable[float]] = (),
    bbox_label: str = "target_chip",
    point_label: str = "solder_center",
) -> dict:
    source_path = Path(source).resolve()
    with Image.open(source_path) as image:
        width, height = image.size
    shapes = []
    if bbox is not None:
        left, top, right, bottom = (float(value) for value in bbox)
        shapes.append(
            {
                "label": bbox_label,
                "points": [[left, top], [right, bottom]],
                "group_id": None,
                "description": "",
                "shape_type": "rectangle",
                "flags": {},
                "mask": None,
            }
        )
    for index, point in enumerate(points):
        if isinstance(point, dict):
            x = float(point.get("x", point.get("center", [0, 0])[0]))
            y = float(point.get("y", point.get("center", [0, 0])[1]))
            row, col = point.get("row"), point.get("col")
            suffix = f"_r{row}_c{col}" if row is not None and col is not None else f"_{index:03d}"
        else:
            x, y = (float(value) for value in point)
            suffix = f"_{index:03d}"
        shapes.append(
            {
                "label": point_label + suffix,
                "points": [[x, y]],
                "group_id": None,
                "description": "",
                "shape_type": "point",
                "flags": {},
                "mask": None,
            }
        )
    return {
        "version": "5.5.0",
        "flags": {},
        "shapes": shapes,
        "imagePath": source_path.name,
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
    }


def export_labelme_annotation(
    source: str | Path,
    output_path: str | Path,
    bbox: Iterable[float] | None = None,
    points: Iterable[dict | Iterable[float]] = (),
) -> Path:
    return write_json(output_path, create_labelme_annotation(source, bbox=bbox, points=points))


def export_region_analysis_to_labelme(analysis: dict, output_path: str | Path) -> Path:
    return export_labelme_annotation(
        analysis["source_path"],
        output_path,
        bbox=analysis.get("candidate_bbox"),
        points=analysis.get("centers", []),
    )
