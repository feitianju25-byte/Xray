from __future__ import annotations

import csv
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(r"D:\Xray")
WORKSPACE = ROOT / "pcb_xray_annotation_workspace"
VOID_DIR = WORKSPACE / "images" / "void"
BRIDGE_DIR = WORKSPACE / "images" / "bridge"
THROUGH_DIR = WORKSPACE / "images" / "insufficient_through_solder"
RAW_ROOT = Path(r"D:\科研\Xray存档\X光图片20260330")
OUTPUT = WORKSPACE / "void_roi_dataset"

SEED = 42
PATCH_SIZE = 224
MIN_ROI_SIDE = 224
MAX_ROI_SIDE = 768
POSITIVE_SCALES = (3.0, 4.0, 5.0)
JITTER_RATIO = 0.12
NEGATIVES_PER_QUALIFIED_IMAGE = 2
NEGATIVES_PER_DEFECT_IMAGE = 2
TRAIN_RATIO = 0.70
VAL_RATIO = 0.20

EXCLUDE_NAMES = {
    "void_0014.jpg",
    "void_0059.jpg",
    "void_0061.jpg",
    "void_0072.jpg",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


def main() -> None:
    random.seed(SEED)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    for split in ("train", "val", "test"):
        for label in ("void", "normal"):
            (OUTPUT / split / label).mkdir(parents=True, exist_ok=True)

    positive_sources = collect_positive_sources()
    positive_split = split_paths(list(positive_sources))

    rows: list[dict[str, str]] = []
    roi_sides: list[int] = []
    for img_path, split in positive_split.items():
        boxes = load_void_boxes(img_path.with_suffix(".json"))
        made_rows, sides = make_positive_patches(img_path, boxes, split)
        rows.extend(made_rows)
        roi_sides.extend(sides)

    negative_side = int(sorted(roi_sides)[len(roi_sides) // 2]) if roi_sides else 384
    negative_sources = collect_negative_sources()
    negative_split = split_paths(negative_sources)

    for img_path, split in negative_split.items():
        per_image = NEGATIVES_PER_QUALIFIED_IMAGE if is_qualified_image(img_path) else NEGATIVES_PER_DEFECT_IMAGE
        rows.extend(make_negative_patches(img_path, split, negative_side, per_image))

    write_manifest(rows)
    write_summary(rows, positive_sources, negative_sources, negative_side)
    print(f"Prepared ROI classification dataset at: {OUTPUT}")


def collect_positive_sources() -> list[Path]:
    sources: list[Path] = []
    for img_path in sorted(VOID_DIR.iterdir()):
        if img_path.suffix.lower() not in IMAGE_EXTS:
            continue
        if img_path.name in EXCLUDE_NAMES:
            continue
        label_path = img_path.with_suffix(".json")
        if label_path.exists() and load_void_boxes(label_path):
            sources.append(img_path)
    return sources


def collect_negative_sources() -> list[Path]:
    sources: list[Path] = []
    sources.extend(
        p
        for p in RAW_ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and is_qualified_image(p)
    )
    for folder in (BRIDGE_DIR, THROUGH_DIR):
        sources.extend(p for p in sorted(folder.iterdir()) if p.suffix.lower() in IMAGE_EXTS)
    return sorted(dict.fromkeys(sources))


def is_qualified_image(path: Path) -> bool:
    return "合格" in str(path)


def split_paths(paths: list[Path]) -> dict[Path, str]:
    shuffled = paths[:]
    random.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)
    result: dict[Path, str] = {}
    for idx, path in enumerate(shuffled):
        if idx < n_train:
            split = "train"
        elif idx < n_train + n_val:
            split = "val"
        else:
            split = "test"
        result[path] = split
    return result


def load_void_boxes(label_path: Path) -> list[Box]:
    data = json.loads(label_path.read_text(encoding="utf-8"))
    boxes: list[Box] = []
    for shape in data.get("shapes") or []:
        if shape.get("label") != "void":
            continue
        points = shape.get("points") or []
        if len(points) < 2:
            continue
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        if x2 > x1 and y2 > y1:
            boxes.append(Box(x1, y1, x2, y2))
    return boxes


def make_positive_patches(img_path: Path, boxes: list[Box], split: str) -> tuple[list[dict[str, str]], list[int]]:
    rows: list[dict[str, str]] = []
    sides: list[int] = []
    with Image.open(img_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        for box_idx, box in enumerate(boxes):
            for scale_idx, scale in enumerate(POSITIVE_SCALES):
                side = int(max(max(box.width, box.height) * scale, MIN_ROI_SIDE))
                side = min(side, MAX_ROI_SIDE, width, height)
                sides.append(side)
                offsets = [(0.0, 0.0), (-JITTER_RATIO, 0.0), (JITTER_RATIO, 0.0), (0.0, -JITTER_RATIO), (0.0, JITTER_RATIO)]
                for jitter_idx, (jx, jy) in enumerate(offsets):
                    cx = box.cx + jx * side
                    cy = box.cy + jy * side
                    crop_box = square_crop_box(cx, cy, side, width, height)
                    out_name = f"{img_path.stem}_b{box_idx:02d}_s{scale_idx}_j{jitter_idx}.jpg"
                    out_path = OUTPUT / split / "void" / out_name
                    save_crop(img, crop_box, out_path)
                    rows.append(row(split, "void", out_path, img_path, crop_box, box))
    return rows, sides


def make_negative_patches(img_path: Path, split: str, side: int, count: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with Image.open(img_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            crop_side = min(side, width, height)
            if crop_side < 32:
                return rows
            for idx in range(count):
                x1 = random.randint(0, max(0, width - crop_side))
                y1 = random.randint(0, max(0, height - crop_side))
                crop_box = (x1, y1, x1 + crop_side, y1 + crop_side)
                source_key = safe_stem(img_path)
                out_name = f"{source_key}_n{idx:02d}.jpg"
                out_path = OUTPUT / split / "normal" / out_name
                save_crop(img, crop_box, out_path)
                rows.append(row(split, "normal", out_path, img_path, crop_box, None))
    except OSError:
        return rows
    return rows


def square_crop_box(cx: float, cy: float, side: int, width: int, height: int) -> tuple[int, int, int, int]:
    half = side / 2.0
    x1 = int(round(cx - half))
    y1 = int(round(cy - half))
    x1 = max(0, min(x1, width - side))
    y1 = max(0, min(y1, height - side))
    return x1, y1, x1 + side, y1 + side


def save_crop(img: Image.Image, crop_box: tuple[int, int, int, int], out_path: Path) -> None:
    patch = img.crop(crop_box).resize((PATCH_SIZE, PATCH_SIZE), Image.Resampling.LANCZOS)
    patch.save(out_path, quality=95)


def safe_stem(path: Path) -> str:
    token = abs(hash(path.as_posix())) % 1_000_000_000
    return f"{path.stem}_{token:09d}"


def row(
    split: str,
    label: str,
    out_path: Path,
    source_path: Path,
    crop_box: tuple[int, int, int, int],
    defect_box: Box | None,
) -> dict[str, str]:
    x1, y1, x2, y2 = crop_box
    result = {
        "split": split,
        "label": label,
        "patch_path": str(out_path),
        "source_path": str(source_path),
        "crop_x1": str(x1),
        "crop_y1": str(y1),
        "crop_x2": str(x2),
        "crop_y2": str(y2),
    }
    if defect_box:
        result.update(
            {
                "defect_x1": f"{defect_box.x1:.2f}",
                "defect_y1": f"{defect_box.y1:.2f}",
                "defect_x2": f"{defect_box.x2:.2f}",
                "defect_y2": f"{defect_box.y2:.2f}",
            }
        )
    else:
        result.update({"defect_x1": "", "defect_y1": "", "defect_x2": "", "defect_y2": ""})
    return result


def write_manifest(rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with (OUTPUT / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], positive_sources: list[Path], negative_sources: list[Path], negative_side: int) -> None:
    counts: dict[str, int] = {}
    for item in rows:
        key = f"{item['split']}/{item['label']}"
        counts[key] = counts.get(key, 0) + 1
    summary = {
        "patch_size": PATCH_SIZE,
        "min_roi_side": MIN_ROI_SIDE,
        "max_roi_side": MAX_ROI_SIDE,
        "positive_scales": POSITIVE_SCALES,
        "negative_crop_side_before_resize": negative_side,
        "positive_source_images": len(positive_sources),
        "negative_source_images": len(negative_sources),
        "patch_counts": counts,
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
