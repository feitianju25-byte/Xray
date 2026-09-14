from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO


DATASET = Path(r"D:\Xray\pcb_xray_annotation_workspace\void_roi_dataset")
PROJECT = DATASET / "runs"


def main() -> None:
    model = YOLO("yolo11n-cls.yaml")
    model.train(
        data=str(DATASET),
        epochs=80,
        imgsz=224,
        batch=32,
        device=0,
        project=str(PROJECT),
        name="void_roi_cls_baseline",
        patience=20,
        seed=42,
        workers=2,
    )


if __name__ == "__main__":
    main()
