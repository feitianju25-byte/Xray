from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

from solder_mvp.geometry_review import import_validation_geometry, prepare_validation_geometry


def test_geometry_pack_references_images_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("L", (64, 48), 100).save(source)
    split = {
        "target_family": "target-v1",
        "assignments": [{
            "sample_id": "a" * 20,
            "source_path": str(source),
            "split": "validation",
        }],
    }
    output_dir = tmp_path / "review-pack"
    result = prepare_validation_geometry(split, output_dir)

    with Path(result["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    annotation = json.loads(Path(rows[0]["labelme_json"]).read_text(encoding="utf-8"))
    assert annotation["imagePath"] == str(source.resolve())
    assert annotation["shapes"] == []
    assert Path(result["contact_sheet"]).exists()
    assert not list(output_dir.rglob("*.jpg"))


def test_completed_geometry_is_imported_from_labelme_and_csv(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("L", (64, 48), 100).save(source)
    sample_id = "c" * 20
    split = {
        "target_family": "target-v1",
        "assignments": [{"sample_id": sample_id, "source_path": str(source), "split": "validation", "rank": 3}],
    }
    review = {"items": [{
        "sample_id": sample_id,
        "array_bbox": None,
        "rows": None,
        "cols": None,
        "corners": [],
        "centers": [],
        "notes": "",
    }]}
    result = prepare_validation_geometry(split, tmp_path / "pack")
    csv_path = Path(result["csv"])
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    annotation_path = Path(rows[0]["labelme_json"])
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotation["shapes"] = [{
        "label": "target_chip",
        "points": [[10, 8], [50, 40]],
        "shape_type": "rectangle",
    }]
    annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
    rows[0]["rows"] = "4"
    rows[0]["cols"] = "5"
    rows[0]["review_status"] = "complete"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    merged = import_validation_geometry(review, split, csv_path)
    assert merged["geometry_review_status"]["completed"] == 1
    assert merged["items"][0]["array_bbox"] == [10.0, 8.0, 50.0, 40.0]
    assert merged["items"][0]["rows"] == 4
    assert merged["items"][0]["cols"] == 5
