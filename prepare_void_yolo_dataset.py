from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(r"D:\Xray")
WORKSPACE = ROOT / "pcb_xray_annotation_workspace"
OUTPUT = WORKSPACE / "yolo_void_dataset"
SEED = 42
TRAIN_RATIO = 0.7
VAL_RATIO = 0.2

VOID_DIR = WORKSPACE / "images" / "void"
BRIDGE_DIR = WORKSPACE / "images" / "bridge"
THROUGH_DIR = WORKSPACE / "images" / "insufficient_through_solder"

EXCLUDE_NAMES = {
    "void_0014.jpg",
    "void_0059.jpg",
    "void_0061.jpg",
    "void_0072.jpg",
}


@dataclass
class Item:
    source: Path
    label_path: Path | None
    label_id: int | None
    split: str = ""


def main() -> None:
    random.seed(SEED)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    images_dir = OUTPUT / "images"
    labels_dir = OUTPUT / "labels"
    for split in ("train", "val", "test"):
        (images_dir / split).mkdir(parents=True, exist_ok=True)
        (labels_dir / split).mkdir(parents=True, exist_ok=True)

    positives = collect_positives()
    negatives = collect_negatives()

    split_items(positives)
    split_items(negatives)

    for item in positives + negatives:
        out_img = images_dir / item.split / item.source.name
        shutil.copy2(item.source, out_img)
        out_lbl = labels_dir / item.split / f"{item.source.stem}.txt"
        if item.label_path and item.label_id is not None:
            out_lbl.write_text(convert_labelme_to_yolo(item.label_path, item.label_id), encoding="utf-8")
        else:
            out_lbl.write_text("", encoding="utf-8")

    write_yaml()
    write_manifest(positives, negatives)
    print(f"Prepared YOLO dataset at: {OUTPUT}")


def collect_positives() -> list[Item]:
    items: list[Item] = []
    for img in sorted(VOID_DIR.glob("*.jpg")):
        if img.name in EXCLUDE_NAMES:
            continue
        label = img.with_suffix(".json")
        if not label.exists():
            continue
        items.append(Item(source=img, label_path=label, label_id=0))
    return items


def collect_negatives() -> list[Item]:
    items: list[Item] = []
    for folder in (BRIDGE_DIR, THROUGH_DIR):
        for img in sorted(folder.glob("*.jpg")):
            items.append(Item(source=img, label_path=None, label_id=None))
    return items


def split_items(items: list[Item]) -> None:
    random.shuffle(items)
    n = len(items)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)
    for idx, item in enumerate(items):
        if idx < n_train:
            item.split = "train"
        elif idx < n_train + n_val:
            item.split = "val"
        else:
            item.split = "test"


def convert_labelme_to_yolo(label_path: Path, label_id: int) -> str:
    data = json.loads(label_path.read_text(encoding="utf-8"))
    shapes = data.get("shapes") or []
    if not shapes:
        return ""
    lines: list[str] = []
    width = float(data["imageWidth"])
    height = float(data["imageHeight"])
    for shape in shapes:
        if shape.get("shape_type") != "rectangle":
            continue
        pts = shape.get("points") or []
        if len(pts) != 2 and len(pts) != 4:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        xc = ((x1 + x2) / 2.0) / width
        yc = ((y1 + y2) / 2.0) / height
        bw = (x2 - x1) / width
        bh = (y2 - y1) / height
        lines.append(f"{label_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return "\n".join(lines)


def write_yaml() -> None:
    yaml_text = "\n".join(
        [
            f"path: {OUTPUT.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:",
            "  0: void",
        ]
    )
    (OUTPUT / "void_dataset.yaml").write_text(yaml_text, encoding="utf-8")


def write_manifest(positives: list[Item], negatives: list[Item]) -> None:
    rows = [
        "split,label,image_path,label_path",
    ]
    for item in positives + negatives:
        rows.append(
            ",".join(
                [
                    item.split,
                    "void" if item.label_id == 0 else "background",
                    item.source.as_posix(),
                    (item.label_path.as_posix() if item.label_path else ""),
                ]
            )
        )
    (OUTPUT / "manifest.csv").write_text("\n".join(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
