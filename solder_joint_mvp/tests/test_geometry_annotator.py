from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

from solder_mvp.geometry_annotator import (
    load_geometry_rows,
    read_saved_bbox,
    save_geometry_annotation,
    update_labelme_rectangle,
)
from solder_mvp.geometry_review import prepare_validation_geometry


def _pack(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    source = tmp_path / "source.png"
    Image.new("L", (100, 80), 120).save(source)
    split = {
        "target_family": "target-v1",
        "assignments": [{
            "rank": 9,
            "sample_id": "d" * 20,
            "source_path": str(source),
            "split": "validation",
        }],
    }
    result = prepare_validation_geometry(split, tmp_path / "pack")
    csv_path = Path(result["csv"])
    return csv_path, load_geometry_rows(csv_path)


def test_rectangle_replaces_only_existing_target_rectangle() -> None:
    annotation = {
        "shapes": [
            {"label": "target_chip", "shape_type": "rectangle", "points": [[0, 0], [1, 1]]},
            {"label": "solder_center_1", "shape_type": "point", "points": [[5, 5]]},
        ]
    }
    updated = update_labelme_rectangle(annotation, [10, 20, 90, 70])
    assert len(updated["shapes"]) == 2
    assert updated["shapes"][0]["label"] == "solder_center_1"
    assert updated["shapes"][1]["points"] == [[10.0, 20.0], [90.0, 70.0]]


def test_visual_annotation_saves_csv_labelme_and_backup(tmp_path: Path) -> None:
    csv_path, rows = _pack(tmp_path)
    save_geometry_annotation(csv_path, rows, 0, [10, 12, 88, 70], 4, 5, "checked")

    reloaded = load_geometry_rows(csv_path)
    assert reloaded[0]["review_status"] == "complete"
    assert reloaded[0]["rows"] == "4"
    assert reloaded[0]["cols"] == "5"
    assert read_saved_bbox(reloaded[0]) == [10.0, 12.0, 88.0, 70.0]
    assert csv_path.with_name(csv_path.name + ".backup").exists()
    annotation = json.loads(Path(reloaded[0]["labelme_json"]).read_text(encoding="utf-8"))
    assert annotation["shapes"][-1]["label"] == "target_chip"


def test_load_geometry_rows_preserves_all_fields(tmp_path: Path) -> None:
    csv_path, rows = _pack(tmp_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw = list(csv.DictReader(handle))
    assert rows == raw
