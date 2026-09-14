from __future__ import annotations

from pathlib import Path

from .contract import DetectionMark, FrameImage, RecognitionResult


class PlaceholderRecognizer:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate

    def set_simulation(self, enabled: bool) -> None:
        self.simulate = enabled

    def recognize(self, frame: FrameImage) -> RecognitionResult:
        if not self.simulate:
            return RecognitionResult()

        width = max(1, frame.width)
        height = max(1, frame.height)
        marks = (
            DetectionMark(
                x=int(width * 0.18),
                y=int(height * 0.22),
                width=max(80, int(width * 0.22)),
                height=max(60, int(height * 0.12)),
                label="demo-1",
                confidence=0.88,
            ),
            DetectionMark(
                x=int(width * 0.54),
                y=int(height * 0.58),
                width=max(100, int(width * 0.18)),
                height=max(70, int(height * 0.15)),
                label="demo-2",
                confidence=0.76,
                color="#ffb020",
            ),
        )
        return RecognitionResult(marks=marks, note="simulated")


class YoloRecognizer:
    def __init__(
        self,
        model_path: str | Path = "yolo11n.pt",
        confidence: float = 0.25,
        iou: float = 0.45,
        device: str = "auto",
    ) -> None:
        self.model_path = str(model_path)
        self.confidence = confidence
        self.iou = iou
        self.device_preference = device
        self.simulate = False
        self._placeholder = PlaceholderRecognizer(simulate=True)
        self._model = None
        self._device = None

    def set_simulation(self, enabled: bool) -> None:
        self.simulate = enabled

    def _load_model(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO
        import torch

        if self.device_preference == "auto":
            self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self._device = self.device_preference
        self._model = YOLO(self.model_path)
        return self._model

    def warmup(self) -> None:
        self._load_model()

    def recognize(self, frame: FrameImage) -> RecognitionResult:
        if self.simulate:
            return self._placeholder.recognize(frame)

        try:
            import numpy as np

            image = np.frombuffer(frame.rgb_bytes, dtype=np.uint8).reshape((frame.height, frame.width, 3))
            model = self._load_model()
            results = model.predict(
                image,
                conf=self.confidence,
                iou=self.iou,
                device=self._device,
                verbose=False,
            )
            if not results:
                return RecognitionResult(note="yolo")

            result = results[0]
            names = result.names
            marks: list[DetectionMark] = []
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    label = str(names.get(cls_id, cls_id))
                    marks.append(
                        DetectionMark(
                            x=max(0, int(x1)),
                            y=max(0, int(y1)),
                            width=max(1, int(x2 - x1)),
                            height=max(1, int(y2 - y1)),
                            label=label,
                            confidence=conf,
                            color="#00d18f",
                        )
                    )
            return RecognitionResult(marks=tuple(marks), note=f"yolo:{self._device}")
        except Exception as exc:
            return RecognitionResult(note=f"yolo error: {exc}")


class RoiDefectClassifier:
    """Classify an already-cropped ROI with the three trained defect models.

    This is intentionally separate from :class:`YoloRecognizer`: ROI classifiers
    answer whether the supplied crop contains a particular defect, but they do
    not localize a defect inside the crop.
    """

    DEFAULT_MODELS = {
        "void": Path(__file__).resolve().parents[1]
        / "pcb_xray_annotation_workspace"
        / "void_roi_dataset"
        / "runs"
        / "void_roi_cls_baseline"
        / "weights"
        / "best.pt",
        "bridge": Path(__file__).resolve().parents[1]
        / "pcb_xray_annotation_workspace"
        / "bridge_roi_dataset"
        / "runs"
        / "bridge_roi_cls_baseline"
        / "weights"
        / "best.pt",
        "insufficient_through_solder": Path(__file__).resolve().parents[1]
        / "pcb_xray_annotation_workspace"
        / "insufficient_through_solder_roi_dataset"
        / "runs"
        / "insufficient_through_solder_roi_cls_baseline"
        / "weights"
        / "best.pt",
    }

    def __init__(self, model_paths: dict[str, str | Path] | None = None, device: str = "auto") -> None:
        self.model_paths = {**self.DEFAULT_MODELS, **(model_paths or {})}
        self.device_preference = device
        self._models: dict[str, object] = {}
        self._device: str | None = None

    def _load_models(self) -> None:
        if self._models:
            return
        from ultralytics import YOLO
        import torch

        self._device = "cuda:0" if self.device_preference == "auto" and torch.cuda.is_available() else self.device_preference
        for label, path in self.model_paths.items():
            model_path = Path(path)
            if not model_path.exists():
                raise FileNotFoundError(f"ROI model not found for {label}: {model_path}")
            self._models[label] = YOLO(str(model_path))

    def classify_frame(self, frame: FrameImage) -> dict[str, dict[str, object]]:
        import numpy as np

        self._load_models()
        image = np.frombuffer(frame.rgb_bytes, dtype=np.uint8).reshape((frame.height, frame.width, 3))
        results: dict[str, dict[str, object]] = {}
        for defect_label, model in self._models.items():
            prediction = model.predict(image, imgsz=224, device=self._device, verbose=False)[0]
            probs = prediction.probs
            names = prediction.names
            positive_index = next((int(index) for index, name in names.items() if str(name) == defect_label), None)
            if positive_index is None:
                positive_index = int(probs.top1)
            probability = float(probs.data[positive_index].item())
            has_defect = probability >= 0.5
            results[defect_label] = {
                "has_defect": has_defect,
                # Confidence must correspond to the reported label. For a
                # normal prediction this is the normal probability, not the
                # (low) positive-defect probability.
                "confidence": probability if has_defect else 1.0 - probability,
                "defect_probability": probability,
                "label": defect_label if has_defect else "normal",
                "device": self._device or "auto",
            }
        return results

    def classify_image_path(self, image_path: str | Path) -> dict[str, dict[str, object]]:
        from PIL import Image

        path = Path(image_path)
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            frame = FrameImage(width=rgb.width, height=rgb.height, rgb_bytes=rgb.tobytes(), source="roi")
        return self.classify_frame(frame)
