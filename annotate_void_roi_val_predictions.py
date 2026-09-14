from __future__ import annotations

import csv
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


DATASET = Path(r"D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset")
MODEL = DATASET / "runs" / "void_roi_cls_baseline" / "weights" / "best.pt"

def main() -> None:
    args = parse_args()
    split_dir = DATASET / args.split
    output = DATASET / f"{args.split}_predictions_annotated"

    model = YOLO(str(MODEL))
    if output.exists():
        for p in output.rglob("*"):
            if p.is_file():
                p.unlink()
    output.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for true_label in ("void", "normal"):
        for img_path in sorted((split_dir / true_label).glob("*.jpg")):
            result = model.predict(source=str(img_path), imgsz=224, verbose=False)[0]
            probs = result.probs
            names = result.names
            pred_idx = int(probs.top1)
            pred_label = names[pred_idx]
            conf = float(probs.top1conf)
            correct = pred_label == true_label
            out_dir = output / ("correct" if correct else "wrong") / true_label
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / img_path.name
            draw_prediction(img_path, out_path, true_label, pred_label, conf, correct)
            rows.append(
                {
                    "image": str(img_path),
                    "true_label": true_label,
                    "pred_label": pred_label,
                    "confidence": f"{conf:.4f}",
                    "correct": str(correct),
                    "output_image": str(out_path),
                }
            )

    with (output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    correct = sum(1 for r in rows if r["correct"] == "True")
    total = len(rows)
    print(f"Annotated {total} {args.split} images, accuracy={correct/total:.4f}")
    print(f"Output: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("train", "val", "test"), default="val")
    return parser.parse_args()


def draw_prediction(
    src: Path,
    out: Path,
    true_label: str,
    pred_label: str,
    conf: float,
    correct: bool,
) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        text = f"true={true_label}  pred={pred_label}  conf={conf:.3f}"
        padding = 6
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        rect = [0, 0, tw + padding * 2, th + padding * 2]
        bg = (0, 140, 0) if correct else (180, 0, 0)
        draw.rectangle(rect, fill=bg)
        draw.text((padding, padding), text, fill=(255, 255, 255), font=font)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, quality=95)


if __name__ == "__main__":
    main()
