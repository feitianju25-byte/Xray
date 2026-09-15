from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from solder_mvp.labelme_export import export_labelme_annotation, export_region_analysis_to_labelme


def test_labelme_point_and_rectangle_export_can_be_loaded(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("L", (120, 90), 100).save(source)
    destination = export_labelme_annotation(
        source,
        tmp_path / "annotation.json",
        bbox=(10, 12, 100, 80),
        points=[{"x": 35, "y": 40, "row": 0, "col": 0}, [65, 40]],
    )
    loaded = json.loads(destination.read_text(encoding="utf-8"))
    assert loaded["imagePath"] == source.name
    assert (loaded["imageWidth"], loaded["imageHeight"]) == (120, 90)
    assert [shape["shape_type"] for shape in loaded["shapes"]] == ["rectangle", "point", "point"]
    assert loaded["shapes"][1]["points"] == [[35.0, 40.0]]

    analysis_path = export_region_analysis_to_labelme(
        {"source_path": str(source), "candidate_bbox": [10, 12, 100, 80], "centers": [{"x": 50, "y": 45}]},
        tmp_path / "analysis-labelme.json",
    )
    assert json.loads(analysis_path.read_text(encoding="utf-8"))["shapes"][0]["shape_type"] == "rectangle"
