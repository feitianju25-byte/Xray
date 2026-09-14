from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO


ROOT = Path(r"D:\Xray\pcb_xray_annotation_workspace\yolo_void_dataset")
DATA_YAML = ROOT / "void_dataset.yaml"
WEIGHTS = Path(r"D:\Xray\yolo11n.pt")


def main() -> None:
    model = YOLO(str(WEIGHTS))
    model.train(
        data=str(DATA_YAML),
        epochs=60,
        imgsz=1280,
        batch=4,
        device=0,
        workers=4,
        cache=False,
        pretrained=True,
        patience=15,
        close_mosaic=10,
        single_cls=True,
        project=str(ROOT / "runs"),
        name="void_baseline",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
