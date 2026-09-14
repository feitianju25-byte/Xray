from __future__ import annotations

import json
import struct
import zlib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from .contract import FrameImage, RecognitionResult
from .settings import AppSettings


RecognitionReason = Literal["auto", "manual", "capture"]


class HistorySession:
    def __init__(self, settings: AppSettings, root_dir: Path | None = None) -> None:
        self.settings = settings
        base = root_dir or Path(settings.history.history_dir)
        if not base.is_absolute():
            base = Path(__file__).resolve().parents[1] / base
        now = datetime.now()
        self.session_id = now.strftime("session_%H%M%S")
        self.session_dir = base / now.strftime("%Y-%m-%d") / self.session_id
        self.screenshots_dir = self.session_dir / "screenshots"
        self.annotations_dir = self.session_dir / "annotations"
        self._index_path = self.session_dir / "detections.jsonl"
        self._counter = 0
        self._active = False

    def start(self) -> None:
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.annotations_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "session_id": self.session_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "settings": asdict(self.settings),
        }
        self._write_json(self.session_dir / "metadata.json", metadata)
        self._active = True

    def stop(self) -> None:
        if not self._active:
            return
        self._write_json(self.session_dir / "finished.json", {"finished_at": datetime.now().isoformat(timespec="seconds")})
        self._active = False

    def record(self, frame: FrameImage, result: RecognitionResult, reason: RecognitionReason, sequence_id: int) -> Path | None:
        if not self._active:
            return None
        if reason == "auto" and not result.marks and not self.settings.history.save_empty_results:
            return None

        self._counter += 1
        stem = f"{self._counter:06d}"
        screenshot_path = self.screenshots_dir / f"{stem}.png"
        annotation_path = self.annotations_dir / f"{stem}.json"
        if self.settings.history.save_screenshots:
            _write_png(frame, screenshot_path)
        else:
            screenshot_path = None

        record = {
            "id": stem,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "reason": reason,
            "sequence_id": sequence_id,
            "frame": {
                "width": frame.width,
                "height": frame.height,
                "source": frame.source,
                "screenshot": str(screenshot_path) if screenshot_path else "",
            },
            "result": {
                "note": result.note,
                "marks": [asdict(mark) for mark in result.marks],
            },
        }
        self._write_json(annotation_path, record)
        with self._index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        return annotation_path

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_png(frame: FrameImage, path: Path) -> None:
    rows = []
    stride = frame.width * 3
    for y in range(frame.height):
        start = y * stride
        rows.append(b"\x00" + frame.rgb_bytes[start : start + stride])
    payload = zlib.compress(b"".join(rows), level=3)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", frame.width, frame.height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", payload)
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
