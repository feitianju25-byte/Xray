from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


WORKSPACE = Path(__file__).resolve().parent / "pcb_xray_annotation_workspace"
IMAGE_ROOT = WORKSPACE / "images"
RAW_ROOT = Path(r"E:\Xray\X光图片20260330")
PATCH_SIZE = 224
MIN_ROI_SIDE = 224
MAX_ROI_SIDE = 768
POSITIVE_SCALES = (3.0, 4.0, 5.0)
JITTER_RATIO = 0.12
TRAIN_RATIO = 0.70
VAL_RATIO = 0.20
SEED = 42
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
EXCLUDE_VOID = {"void_0014.jpg", "void_0059.jpg", "void_0061.jpg", "void_0072.jpg"}


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


def load_boxes(path: Path, label: str) -> list[Box]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    result = []
    for shape in data.get("shapes") or []:
        if shape.get("label") != label or len(shape.get("points") or []) < 2:
            continue
        points = shape["points"]
        xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
        box = Box(min(xs), min(ys), max(xs), max(ys))
        if box.width > 0 and box.height > 0:
            result.append(box)
    return result


def split_paths(paths: list[Path], rng: random.Random) -> dict[Path, str]:
    paths = list(paths)
    rng.shuffle(paths)
    n_train, n_val = int(len(paths) * TRAIN_RATIO), int(len(paths) * VAL_RATIO)
    return {p: ("train" if i < n_train else "val" if i < n_train + n_val else "test") for i, p in enumerate(paths)}


def crop_box(cx: float, cy: float, side: int, width: int, height: int) -> tuple[int, int, int, int]:
    side = min(side, width, height)
    x1 = max(0, min(int(round(cx - side / 2)), width - side))
    y1 = max(0, min(int(round(cy - side / 2)), height - side))
    return x1, y1, x1 + side, y1 + side


def save_patch(img: Image.Image, box: tuple[int, int, int, int], out: Path) -> None:
    img.crop(box).resize((PATCH_SIZE, PATCH_SIZE), Image.Resampling.LANCZOS).save(out, quality=95)


def safe_stem(path: Path) -> str:
    digest = hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()[:10]
    return f"{path.stem}_{digest}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=("bridge", "insufficient_through_solder"), required=True)
    args = parser.parse_args()
    label = args.label
    output = WORKSPACE / f"{label}_roi_dataset"
    if output.exists():
        shutil.rmtree(output)
    for split in ("train", "val", "test"):
        for cls in (label, "normal"):
            (output / split / cls).mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    source_dir = IMAGE_ROOT / label
    positives = [p for p in source_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.with_suffix(".json").exists() and (label != "void" or p.name not in EXCLUDE_VOID) and load_boxes(p.with_suffix(".json"), label)]
    positive_split = split_paths(positives, rng)
    rows, sides = [], []
    for img_path, split in positive_split.items():
        with Image.open(img_path) as src:
            img = src.convert("RGB")
            w, h = img.size
            for bi, box in enumerate(load_boxes(img_path.with_suffix(".json"), label)):
                for si, scale in enumerate(POSITIVE_SCALES):
                    side = min(MAX_ROI_SIDE, w, h, max(MIN_ROI_SIDE, int(max(box.width, box.height) * scale)))
                    sides.append(side)
                    for ji, (jx, jy) in enumerate(((0, 0), (-JITTER_RATIO, 0), (JITTER_RATIO, 0), (0, -JITTER_RATIO), (0, JITTER_RATIO))):
                        cb = crop_box(box.cx + jx * side, box.cy + jy * side, side, w, h)
                        out = output / split / label / f"{img_path.stem}_b{bi:02d}_s{si}_j{ji}.jpg"
                        save_patch(img, cb, out)
                        rows.append({"split": split, "label": label, "patch_path": str(out), "source_path": str(img_path), "crop": str(cb)})

    # Unannotated images of the same defect class are deliberately excluded from normal.
    normal_sources = []
    if RAW_ROOT.exists():
        normal_sources.extend(p for p in RAW_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS and "合格" in str(p))
    for p in IMAGE_ROOT.iterdir():
        if p.name == label or not p.is_dir():
            continue
        normal_sources.extend(x for x in p.iterdir() if x.suffix.lower() in IMAGE_EXTS)
    normal_sources = list(dict.fromkeys(normal_sources))
    negative_side = int(sorted(sides)[len(sides) // 2]) if sides else 384
    for img_path, split in split_paths(normal_sources, rng).items():
        try:
            with Image.open(img_path) as src:
                img = src.convert("RGB"); w, h = img.size; side = min(negative_side, w, h)
                if side < 32: continue
                for i in range(2):
                    cb = (rng.randint(0, max(0, w-side)), rng.randint(0, max(0, h-side)), 0, 0)
                    cb = (cb[0], cb[1], cb[0]+side, cb[1]+side)
                    out = output / split / "normal" / f"{safe_stem(img_path)}_n{i:02d}.jpg"
                    save_patch(img, cb, out)
                    rows.append({"split": split, "label": "normal", "patch_path": str(out), "source_path": str(img_path), "crop": str(cb)})
        except OSError:
            continue
    with (output / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    counts = {}
    for r in rows: counts[f"{r['split']}/{r['label']}"] = counts.get(f"{r['split']}/{r['label']}", 0) + 1
    (output / "summary.json").write_text(json.dumps({"label": label, "positive_source_images": len(positives), "normal_source_images": len(normal_sources), "patch_counts": counts, "excluded_unannotated_same_class": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepared {label} ROI dataset at: {output}")


if __name__ == "__main__":
    main()
