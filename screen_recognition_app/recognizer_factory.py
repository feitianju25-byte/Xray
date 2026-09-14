from __future__ import annotations

from .recognizer import RoiDefectClassifier, YoloRecognizer
from .settings import AppSettings


def build_recognizer(settings: AppSettings):
    backend_type = settings.backend.backend_type.lower()
    if backend_type == "roi_cls":
        return RoiDefectClassifier(device=settings.backend.device)
    if backend_type != "yolo":
        raise ValueError(f"Unsupported backend type: {settings.backend.backend_type}")
    return YoloRecognizer(
        model_path=settings.backend.model_path,
        confidence=settings.backend.confidence,
        iou=settings.backend.iou,
        device=settings.backend.device,
    )
