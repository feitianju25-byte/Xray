from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "screen_recognition_app_config.json"


@dataclass(frozen=True)
class BackendSettings:
    backend_type: str = "yolo"
    model_path: str = "yolo11n.pt"
    confidence: float = 0.25
    iou: float = 0.45
    device: str = "auto"


@dataclass(frozen=True)
class RuntimeSettings:
    auto_detect: bool = True
    capture_interval: float = 0.08
    inference_interval: float = 0.03
    show_labels: bool = True
    show_confidence: bool = True


@dataclass(frozen=True)
class HistorySettings:
    enabled: bool = True
    save_screenshots: bool = True
    save_empty_results: bool = False
    history_dir: str = "runs"


@dataclass(frozen=True)
class AppSettings:
    backend: BackendSettings = field(default_factory=BackendSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    history: HistorySettings = field(default_factory=HistorySettings)


def load_settings(path: Path = CONFIG_PATH) -> AppSettings:
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return AppSettings()
        return _settings_from_dict(data)
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def _settings_from_dict(data: dict[str, Any]) -> AppSettings:
    defaults = AppSettings()
    backend_data = data.get("backend") if isinstance(data.get("backend"), dict) else {}
    runtime_data = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    history_data = data.get("history") if isinstance(data.get("history"), dict) else {}

    backend = BackendSettings(
        backend_type=_str(backend_data.get("backend_type"), defaults.backend.backend_type),
        model_path=_str(backend_data.get("model_path"), defaults.backend.model_path),
        confidence=_clamp_float(backend_data.get("confidence"), defaults.backend.confidence, 0.01, 1.0),
        iou=_clamp_float(backend_data.get("iou"), defaults.backend.iou, 0.01, 1.0),
        device=_str(backend_data.get("device"), defaults.backend.device),
    )
    runtime = RuntimeSettings(
        auto_detect=_bool(runtime_data.get("auto_detect"), defaults.runtime.auto_detect),
        capture_interval=_clamp_float(
            runtime_data.get("capture_interval"), defaults.runtime.capture_interval, 0.01, 5.0
        ),
        inference_interval=_clamp_float(
            runtime_data.get("inference_interval"), defaults.runtime.inference_interval, 0.0, 5.0
        ),
        show_labels=_bool(runtime_data.get("show_labels"), defaults.runtime.show_labels),
        show_confidence=_bool(runtime_data.get("show_confidence"), defaults.runtime.show_confidence),
    )
    history = HistorySettings(
        enabled=_bool(history_data.get("enabled"), defaults.history.enabled),
        save_screenshots=_bool(history_data.get("save_screenshots"), defaults.history.save_screenshots),
        save_empty_results=_bool(history_data.get("save_empty_results"), defaults.history.save_empty_results),
        history_dir=_str(history_data.get("history_dir"), defaults.history.history_dir),
    )
    return AppSettings(backend=backend, runtime=runtime, history=history)


def _str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))
