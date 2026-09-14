from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=("bridge", "insufficient_through_solder"), required=True)
    parser.add_argument("--split", choices=("train", "val", "test"), default="test")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "pcb_xray_annotation_workspace" / f"{args.label}_roi_dataset"
    model = YOLO(str(root / "runs" / f"{args.label}_roi_cls_baseline" / "weights" / "best.pt"))
    output = root / f"{args.split}_predictions_categorized"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for true_label in (args.label, "normal"):
        for src in sorted((root / args.split / true_label).glob("*.jpg")):
            result = model.predict(source=str(src), imgsz=224, verbose=False)[0]
            pred = result.names[int(result.probs.top1)]; conf = float(result.probs.top1conf); correct = pred == true_label
            bucket = "correct" if correct else "wrong"
            dst = output / bucket / true_label / src.name
            draw(src, dst, true_label, pred, conf, correct)
            rows.append({"image": str(src), "true_label": true_label, "pred_label": pred, "confidence": f"{conf:.4f}", "correct": str(correct), "category": bucket, "output_image": str(dst)})
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    correct = sum(r["correct"] == "True" for r in rows)
    print(f"{args.label} {args.split}: {correct}/{len(rows)} accuracy={correct/len(rows):.4f}")
    print(f"Categorized output: {output}")


def draw(src: Path, dst: Path, true_label: str, pred: str, conf: float, correct: bool) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB"); d = ImageDraw.Draw(img); font = ImageFont.load_default(); text = f"true={true_label} pred={pred} conf={conf:.3f}"; box = d.textbbox((0, 0), text, font=font); d.rectangle((0, 0, box[2]+12, box[3]+12), fill=(0, 140, 0) if correct else (180, 0, 0)); d.text((6, 6), text, fill="white", font=font); dst.parent.mkdir(parents=True, exist_ok=True); img.save(dst, quality=95)


if __name__ == "__main__":
    main()
