from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal

from .contract import FrameImage, RecognitionResult
from .history import HistorySession
from .screen_capture import capture_screen


CaptureFn = Callable[[], FrameImage]
RecognitionReason = Literal["auto", "manual", "capture"]


@dataclass(frozen=True)
class PipelineSnapshot:
    frame: FrameImage | None
    result: RecognitionResult
    capture_seq: int
    result_seq: int
    capture_fps: float
    inference_fps: float
    auto_enabled: bool
    paused: bool
    running: bool
    capture_note: str = ""


class RecognitionPipeline:
    def __init__(
        self,
        recognizer,
        capture_fn: CaptureFn = capture_screen,
        capture_interval: float = 0.08,
        idle_interval: float = 0.03,
    ) -> None:
        self.recognizer = recognizer
        self.capture_fn = capture_fn
        self.capture_interval = capture_interval
        self.idle_interval = idle_interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._frame_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._latest_frame: FrameImage | None = None
        self._latest_result = RecognitionResult(note="idle")
        self._capture_seq = 0
        self._result_seq = 0
        self._processed_seq = 0
        self._manual_requests: deque[RecognitionReason] = deque()
        self._auto_enabled = True
        self._paused = False
        self._capture_note = "idle"
        self._capture_times: deque[float] = deque(maxlen=32)
        self._inference_times: deque[float] = deque(maxlen=32)
        self._history: HistorySession | None = None

    def start(self) -> None:
        if self._threads:
            return
        self._stop_event.clear()
        self._threads = [
            threading.Thread(target=self._capture_loop, name="screen-capture", daemon=True),
            threading.Thread(target=self._recognition_loop, name="screen-recognition", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._frame_event.set()
        for thread in self._threads:
            thread.join(timeout=1.0)
        self._threads = []

    def set_recognizer(self, recognizer) -> None:
        with self._lock:
            self.recognizer = recognizer
            self._latest_result = RecognitionResult(note="recognizer updated")
            self._processed_seq = 0
        self._frame_event.set()

    def configure_timing(self, capture_interval: float, inference_interval: float) -> None:
        self.capture_interval = capture_interval
        self.idle_interval = inference_interval
        self._frame_event.set()

    def set_history_session(self, history: HistorySession | None) -> None:
        with self._lock:
            self._history = history

    def set_auto_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._auto_enabled = enabled
        self._frame_event.set()

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused
        self._frame_event.set()

    def request_recognition(self, reason: RecognitionReason = "manual") -> None:
        with self._lock:
            self._manual_requests.append(reason)
        self._frame_event.set()

    def set_simulation(self, enabled: bool) -> None:
        if hasattr(self.recognizer, "set_simulation"):
            self.recognizer.set_simulation(enabled)
        self._frame_event.set()

    def snapshot(self) -> PipelineSnapshot:
        with self._lock:
            capture_fps = self._fps(self._capture_times)
            inference_fps = self._fps(self._inference_times)
            return PipelineSnapshot(
                frame=self._latest_frame,
                result=self._latest_result,
                capture_seq=self._capture_seq,
                result_seq=self._result_seq,
                capture_fps=capture_fps,
                inference_fps=inference_fps,
                auto_enabled=self._auto_enabled,
                paused=self._paused,
                running=bool(self._threads),
                capture_note=self._capture_note,
            )

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.perf_counter()
            frame = self.capture_fn()
            with self._lock:
                self._latest_frame = frame
                self._capture_seq += 1
                self._capture_note = frame.source
                self._capture_times.append(time.perf_counter())
            self._frame_event.set()
            elapsed = time.perf_counter() - started
            if elapsed < self.capture_interval:
                self._stop_event.wait(self.capture_interval - elapsed)

    def _recognition_loop(self) -> None:
        while not self._stop_event.is_set():
            self._frame_event.wait(self.idle_interval)
            self._frame_event.clear()

            with self._lock:
                paused = self._paused
                auto_enabled = self._auto_enabled
                manual_reason = self._manual_requests.popleft() if self._manual_requests else None
                frame = self._latest_frame
                frame_seq = self._capture_seq
                recognizer = self.recognizer
                history = self._history

            if paused or frame is None:
                continue

            reason: RecognitionReason | None = None
            if manual_reason is not None:
                should_process = True
                reason = manual_reason
            else:
                should_process = auto_enabled and frame_seq != self._processed_seq
                if should_process:
                    reason = "auto"

            if not should_process:
                continue

            started = time.perf_counter()
            result = recognizer.recognize(frame)
            with self._lock:
                self._latest_result = result
                self._result_seq = frame_seq
                self._processed_seq = frame_seq
                self._inference_times.append(time.perf_counter())
            if history is not None and reason is not None:
                try:
                    history.record(frame, result, reason, frame_seq)
                except Exception:
                    pass
            elapsed = time.perf_counter() - started
            if elapsed < self.idle_interval:
                self._stop_event.wait(self.idle_interval - elapsed)

    @staticmethod
    def _fps(samples: deque[float]) -> float:
        if len(samples) < 2:
            return 0.0
        elapsed = samples[-1] - samples[0]
        if elapsed <= 0:
            return float(len(samples))
        return round((len(samples) - 1) / elapsed, 1)
