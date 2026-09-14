from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=("bridge", "insufficient_through_solder"), required=True)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "pcb_xray_annotation_workspace" / f"{args.label}_roi_dataset"
    model = YOLO("yolo11n-cls.yaml")
    model.train(data=str(root), epochs=80, imgsz=224, batch=32, device=args.device, project=str(root / "runs"), name=f"{args.label}_roi_cls_baseline", patience=20, seed=42, workers=2)


if __name__ == "__main__":
    main()
