from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class FrameImage:
    width: int
    height: int
    rgb_bytes: bytes
    source: str = "screen"


@dataclass(frozen=True)
class DetectionMark:
    x: int
    y: int
    width: int
    height: int
    label: str = ""
    confidence: float = 0.0
    color: str = "#00d18f"


@dataclass(frozen=True)
class RecognitionResult:
    marks: Tuple[DetectionMark, ...] = field(default_factory=tuple)
    note: str = ""
