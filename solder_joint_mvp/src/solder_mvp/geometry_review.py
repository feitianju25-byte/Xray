from __future__ import annotations

import csv
import json
from pathlib import Path

from .contact_sheet import render_contact_sheet
from .io_utils import write_json
from .labelme_export import create_labelme_annotation


GEOMETRY_FIELDS = [
    "rank",
    "sample_id",
    "source_path",
    "labelme_json",
    "bbox_left",
    "bbox_top",
    "bbox_right",
    "bbox_bottom",
    "rows",
    "cols",
    "review_status",
    "notes",
]


def prepare_validation_geometry(split: dict, output_dir: str | Path) -> dict:
    """Create a no-image-copy LabelMe/CSV review pack for frozen validation samples."""
    destination = Path(output_dir)
    labelme_dir = destination / "labelme"
    labelme_dir.mkdir(parents=True, exist_ok=True)
    assignments = [item for item in split.get("assignments", []) if item.get("split") == "validation"]
    if not assignments:
        raise ValueError("frozen split contains no validation samples")

    rows = []
    for index, item in enumerate(assignments, start=1):
        source = Path(item["source_path"]).resolve()
        annotation = create_labelme_annotation(source)
        annotation["imagePath"] = str(source)
        annotation["sample_id"] = item["sample_id"]
        annotation["target_family"] = split.get("target_family")
        annotation["review_instructions"] = (
            "Draw one rectangle named target_chip. Optionally add corner_tl/corner_tr/corner_br/corner_bl "
            "or solder_center points. Fill rows and cols in geometry_review.csv."
        )
        rank = int(item.get("rank", index))
        labelme_path = labelme_dir / f"rank_{rank:03d}_{item['sample_id']}.json"
        write_json(labelme_path, annotation)
        rows.append(
            {
                "rank": rank,
                "sample_id": item["sample_id"],
                "source_path": str(source),
                "labelme_json": str(labelme_path.resolve()),
                "bbox_left": "",
                "bbox_top": "",
                "bbox_right": "",
                "bbox_bottom": "",
                "rows": "",
                "cols": "",
                "review_status": "pending",
                "notes": "",
            }
        )

    contact_records = [
        {
            "sample_id": item["sample_id"],
            "sample_rank": int(item.get("rank", index)),
            "root_alias": "validation",
            "source_dir": Path(item["source_path"]).parent.name,
            "absolute_path": item["source_path"],
            "family_score": item.get("family_score"),
            "duplicate_group": item.get("duplicate_group"),
        }
        for index, item in enumerate(assignments, start=1)
    ]
    contact_sheet = render_contact_sheet(
        {"records": contact_records},
        destination / "validation_contact_sheet.png",
        columns=5,
        label_height=78,
    )

    csv_path = destination / "geometry_review.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GEOMETRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    instructions_path = destination / "README.txt"
    instructions_path.write_text(
        "验证集轻量几何复核\n\n"
        "每个样本必须完成：\n"
        "1. 用 LabelMe 打开 labelme 目录中的 JSON；原图通过绝对路径引用，没有复制。\n"
        "2. 给目标芯片画一个矩形，标签必须为 target_chip；保存 JSON。\n"
        "3. 在 geometry_review.csv 填写 rows、cols，并把 review_status 改为 complete。\n"
        "4. 如果矩形难以覆盖透视阵列，可增加 corner_tl、corner_tr、corner_br、corner_bl 四个点；\n"
        "   少量人工确认圆心可使用 solder_center 开头的点标签。\n"
        "也可以不使用 LabelMe，直接填写 CSV 的四个 bbox 坐标和 rows、cols。\n",
        encoding="utf-8",
    )
    return {
        "csv": str(csv_path),
        "instructions": str(instructions_path),
        "contact_sheet": str(contact_sheet),
        "count": len(rows),
    }


def _optional_float(row: dict, name: str) -> float | None:
    value = (row.get(name) or "").strip()
    return float(value) if value else None


def _read_labelme_geometry(path: str | Path) -> tuple[list[float] | None, list[list[float]], list[list[float]]]:
    annotation = json.loads(Path(path).read_text(encoding="utf-8"))
    bbox = None
    corners_by_name: dict[str, list[float]] = {}
    centers = []
    for shape in annotation.get("shapes", []):
        label = str(shape.get("label", ""))
        points = shape.get("points", [])
        if label == "target_chip" and shape.get("shape_type") == "rectangle" and len(points) == 2:
            (x1, y1), (x2, y2) = points
            bbox = [min(float(x1), float(x2)), min(float(y1), float(y2)), max(float(x1), float(x2)), max(float(y1), float(y2))]
        elif label in {"corner_tl", "corner_tr", "corner_br", "corner_bl"} and points:
            corners_by_name[label] = [float(points[0][0]), float(points[0][1])]
        elif label.startswith("solder_center") and points:
            centers.append([float(points[0][0]), float(points[0][1])])
    corners = [corners_by_name[name] for name in ("corner_tl", "corner_tr", "corner_br", "corner_bl") if name in corners_by_name]
    return bbox, corners, centers


def import_validation_geometry(review: dict, split: dict, csv_path: str | Path) -> dict:
    """Merge completed geometry rows and their LabelMe shapes into review JSON."""
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows_by_id = {row["sample_id"].strip(): row for row in rows}
    validation_ids = {
        item["sample_id"] for item in split.get("assignments", []) if item.get("split") == "validation"
    }
    if set(rows_by_id) != validation_ids:
        raise ValueError("geometry CSV sample IDs do not exactly match the frozen validation set")

    items_by_id = {item["sample_id"]: dict(item) for item in review.get("items", [])}
    completed = []
    incomplete = []
    for sample_id in sorted(validation_ids):
        row = rows_by_id[sample_id]
        try:
            rows_count = int((row.get("rows") or "").strip())
            cols_count = int((row.get("cols") or "").strip())
        except ValueError:
            incomplete.append({"sample_id": sample_id, "reason": "rows/cols must be integers"})
            continue
        csv_bbox_values = [_optional_float(row, name) for name in ("bbox_left", "bbox_top", "bbox_right", "bbox_bottom")]
        csv_bbox = [float(value) for value in csv_bbox_values] if all(value is not None for value in csv_bbox_values) else None
        labelme_bbox, corners, centers = _read_labelme_geometry(row["labelme_json"])
        bbox = csv_bbox or labelme_bbox
        status = (row.get("review_status") or "").strip().lower()
        if status != "complete":
            incomplete.append({"sample_id": sample_id, "reason": "review_status is not complete"})
            continue
        if rows_count < 2 or cols_count < 3 or (bbox is None and len(corners) != 4):
            incomplete.append({"sample_id": sample_id, "reason": "requires rows>=2, cols>=3 and bbox or four corners"})
            continue
        item = items_by_id[sample_id]
        item["array_bbox"] = bbox
        item["rows"] = rows_count
        item["cols"] = cols_count
        item["corners"] = corners
        item["centers"] = centers
        item["notes"] = (row.get("notes") or item.get("notes") or "").strip()
        items_by_id[sample_id] = item
        completed.append(sample_id)

    merged = dict(review)
    merged["items"] = [items_by_id[item["sample_id"]] for item in review.get("items", [])]
    merged["geometry_review_status"] = {
        "required": len(validation_ids),
        "completed": len(completed),
        "completed_sample_ids": completed,
        "incomplete": incomplete,
    }
    return merged
