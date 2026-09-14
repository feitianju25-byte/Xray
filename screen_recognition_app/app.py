from __future__ import annotations

import argparse
import ctypes
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog
from tkinter import ttk

from .contract import DetectionMark, FrameImage, RecognitionResult
from .history import HistorySession
from .pipeline import PipelineSnapshot, RecognitionPipeline
from .recognizer_factory import build_recognizer
from .settings import AppSettings, BackendSettings, HistorySettings, RuntimeSettings, load_settings, save_settings


TRANSPARENT_COLOR = "#ff00ff"
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WDA_EXCLUDEFROMCAPTURE = 0x11
LWA_COLORKEY = 0x00000001
TRANSPARENT_COLORREF = 0x00FF00FF


def _user32():
    return ctypes.windll.user32


def _set_exclude_from_capture(hwnd: int) -> bool:
    try:
        return bool(_user32().SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def _set_click_through(hwnd: int) -> bool:
    try:
        user32 = _user32()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        return bool(user32.SetLayeredWindowAttributes(hwnd, TRANSPARENT_COLORREF, 0, LWA_COLORKEY))
    except Exception:
        return False


class MainWindow(ttk.Frame):
    def __init__(
        self,
        master: tk.Tk,
        on_start,
        on_toggle_auto,
        on_settings,
        on_open_roi,
        status_var: tk.StringVar,
        auto_enabled: bool = True,
    ) -> None:
        super().__init__(master, padding=24)
        self.on_start = on_start
        self.on_toggle_auto = on_toggle_auto
        self.on_settings = on_settings
        self.on_open_roi = on_open_roi
        self.status_var = status_var
        self.auto_enabled = auto_enabled
        self._build()

    def _build(self) -> None:
        style = ttk.Style(self)
        style.layout("Primary.TButton", style.layout("TButton"))
        style.configure("Primary.TButton", padding=12, font=("Segoe UI", 11, "bold"))
        style.configure("Secondary.TButton", padding=10, font=("Segoe UI", 10))

        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Screen Recognition UI", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 18)
        )
        ttk.Label(
            self,
            text="Start recognition to hide this window and draw detection marks over the live desktop.",
            wraplength=780,
        ).grid(row=1, column=0, sticky="w", pady=(0, 18))

        controls = ttk.Frame(self)
        controls.grid(row=2, column=0, sticky="ew")
        for index in range(2):
            controls.columnconfigure(index, weight=1)

        buttons = [
            ("Start Recognition", self._start_recognition, "Primary.TButton"),
            ("Auto Detect", self._toggle_auto, "Secondary.TButton"),
            ("Capture", lambda: self._placeholder("Capture"), "Secondary.TButton"),
            ("Save", lambda: self._placeholder("Save"), "Secondary.TButton"),
            ("Settings", self.on_settings, "Secondary.TButton"),
            ("Open ROI Image", self.on_open_roi, "Secondary.TButton"),
            ("About", lambda: self._placeholder("About"), "Secondary.TButton"),
        ]
        for index, (text, command, style_name) in enumerate(buttons):
            row = index // 2
            column = index % 2
            button = ttk.Button(controls, text=text, command=command, style=style_name)
            if text == "Start Recognition":
                button.configure(width=30)
            button.grid(row=row, column=column, sticky="ew", padx=6, pady=6, ipady=6)

        ttk.Label(self, textvariable=self.status_var, anchor="w").grid(row=3, column=0, sticky="ew", pady=(14, 0))

    def _start_recognition(self) -> None:
        self.status_var.set("Hiding launcher and entering click-through overlay mode.")
        self.on_start()

    def _toggle_auto(self) -> None:
        self.auto_enabled = not self.auto_enabled
        self.on_toggle_auto(self.auto_enabled)
        self.status_var.set(f"Auto detect {'enabled' if self.auto_enabled else 'disabled'}.")

    def _placeholder(self, name: str) -> None:
        self.status_var.set(f"{name} is reserved for a later workflow step.")


class DetectionOverlay(tk.Toplevel):
    def __init__(self, master: tk.Tk, pipeline: RecognitionPipeline, settings: AppSettings, status_callback) -> None:
        super().__init__(master)
        self.pipeline = pipeline
        self.settings = settings
        self.status_callback = status_callback
        self._running = True
        self._click_through_set = False
        self._affinity_set = False

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.configure(bg=TRANSPARENT_COLOR)

        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        self.geometry(f"{width}x{height}+0+0")
        self.canvas = tk.Canvas(self, bg=TRANSPARENT_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.after(50, self._finish_window_setup)

    def _finish_window_setup(self) -> None:
        self.update_idletasks()
        hwnd = self.winfo_id()
        self._affinity_set = _set_exclude_from_capture(hwnd)
        self._click_through_set = _set_click_through(hwnd)
        self.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self._tick()

    def set_auto_detect(self, enabled: bool) -> None:
        self.pipeline.set_auto_enabled(enabled)

    def set_paused(self, paused: bool) -> None:
        self.pipeline.set_paused(paused)

    def recognize_now(self) -> None:
        self.pipeline.request_recognition("manual")

    def save_capture(self) -> None:
        self.pipeline.request_recognition("capture")

    def _tick(self) -> None:
        if not self._running:
            return
        snapshot = self.pipeline.snapshot()
        self._render(snapshot)
        self.after(50, self._tick)

    def _render(self, snapshot: PipelineSnapshot) -> None:
        self.canvas.delete("overlay")
        frame = snapshot.frame
        result = snapshot.result
        if frame is None:
            return
        scale_x = self.winfo_screenwidth() / max(1, frame.width)
        scale_y = self.winfo_screenheight() / max(1, frame.height)
        for mark in result.marks:
            self._draw_mark(mark, scale_x, scale_y)
        status = (
            f"{frame.width} x {frame.height} | "
            f"{len(result.marks)} marks | "
            f"cap {snapshot.capture_fps:.1f} fps | inf {snapshot.inference_fps:.1f} fps"
        )
        if result.note:
            status += f" | {result.note}"
        if frame.source == "fallback":
            status += " | fallback capture"
        if snapshot.paused:
            status += " | paused"
        if snapshot.auto_enabled:
            status += " | auto"
        else:
            status += " | manual"
        if snapshot.capture_note:
            status += f" | {snapshot.capture_note}"
        if not self._click_through_set:
            status += " | click-through unavailable"
        if not self._affinity_set:
            status += " | capture affinity unavailable"
        self.status_callback(status)

    def _draw_mark(self, mark: DetectionMark, scale_x: float, scale_y: float) -> None:
        x1 = int(mark.x * scale_x)
        y1 = int(mark.y * scale_y)
        x2 = int((mark.x + mark.width) * scale_x)
        y2 = int((mark.y + mark.height) * scale_y)
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=mark.color, width=3, tags=("overlay",))
        self.canvas.create_text(
            x1,
            max(0, y1 - 6),
            anchor="sw",
            fill=mark.color,
            font=("Segoe UI", 11, "bold"),
            text=self._mark_text(mark),
            tags=("overlay",),
        )

    def _mark_text(self, mark: DetectionMark) -> str:
        parts: list[str] = []
        if self.settings.runtime.show_labels:
            parts.append(mark.label or "mark")
        if self.settings.runtime.show_confidence:
            parts.append(f"{mark.confidence:.2f}")
        return " ".join(parts) if parts else ""

    def stop(self) -> None:
        self._running = False
        self.destroy()


class OverlayControls(tk.Toplevel):
    def __init__(self, master: tk.Tk, overlay: DetectionOverlay, pipeline: RecognitionPipeline, on_exit) -> None:
        super().__init__(master)
        self.overlay = overlay
        self.pipeline = pipeline
        self.on_exit = on_exit
        self.title("Recognition Controls")
        self.attributes("-topmost", True)
        self.geometry("+24+24")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.exit)

        frame = ttk.Frame(self, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Button(frame, text="Recognize Now", command=overlay.recognize_now).grid(row=0, column=0, padx=4)
        ttk.Button(frame, text="Save Capture", command=overlay.save_capture).grid(row=0, column=1, padx=4)

        self.auto_var = tk.BooleanVar(value=pipeline.snapshot().auto_enabled)
        ttk.Checkbutton(frame, text="Auto Detect", variable=self.auto_var, command=self._toggle_auto).grid(
            row=0, column=2, padx=4
        )
        self.demo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Demo Marks", variable=self.demo_var, command=self._toggle_demo).grid(
            row=0, column=3, padx=4
        )
        self.pause_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Pause", variable=self.pause_var, command=self._toggle_pause).grid(
            row=0, column=4, padx=4
        )
        ttk.Button(frame, text="Exit", command=self.exit).grid(row=0, column=5, padx=4)

        self.status_var = tk.StringVar(value="Live monitor active.")
        ttk.Label(frame, textvariable=self.status_var).grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))
        self.after(50, lambda: _set_exclude_from_capture(self.winfo_id()))

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _toggle_auto(self) -> None:
        self.overlay.set_auto_detect(bool(self.auto_var.get()))

    def _toggle_demo(self) -> None:
        self.pipeline.set_simulation(bool(self.demo_var.get()))
        self.overlay.recognize_now()

    def _toggle_pause(self) -> None:
        self.overlay.set_paused(bool(self.pause_var.get()))

    def exit(self) -> None:
        self.on_exit()


class ScreenRecognitionApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Screen Recognition UI")
        self.root.geometry("1120x720")
        self.root.minsize(900, 620)
        self.settings = load_settings()
        self.status_var = tk.StringVar(value=self._main_status())
        self.recognizer = build_recognizer(self.settings)
        self.pipeline = RecognitionPipeline(
            self.recognizer,
            capture_interval=self.settings.runtime.capture_interval,
            idle_interval=self.settings.runtime.inference_interval,
        )
        self.auto_detect = self.settings.runtime.auto_detect
        self.history_session: HistorySession | None = None
        self.overlay: DetectionOverlay | None = None
        self.controls: OverlayControls | None = None
        self.roi_classifier = None
        self.main_window = MainWindow(
            self.root,
            on_start=self._start_recognition,
            on_toggle_auto=self._set_auto_detect,
            on_settings=self._open_settings,
            on_open_roi=self._open_roi_image,
            status_var=self.status_var,
            auto_enabled=self.auto_detect,
        )
        self.main_window.pack(fill="both", expand=True)

    def _set_auto_detect(self, enabled: bool) -> None:
        self.auto_detect = enabled
        self.settings = replace(self.settings, runtime=replace(self.settings.runtime, auto_detect=enabled))
        save_settings(self.settings)
        if self.overlay is not None:
            self.overlay.set_auto_detect(enabled)

    def _start_recognition(self) -> None:
        if self.overlay is not None:
            return
        self.root.withdraw()
        self.root.after(250, self._show_overlay)

    def _show_overlay(self) -> None:
        if self.overlay is not None:
            return
        self._start_history_session()
        self.pipeline.start()
        self.pipeline.set_auto_enabled(self.auto_detect)
        self.overlay = DetectionOverlay(self.root, self.pipeline, self.settings, status_callback=self._set_overlay_status)
        self.controls = OverlayControls(self.root, self.overlay, self.pipeline, self._close_overlay)

    def _set_overlay_status(self, text: str) -> None:
        if self.controls is not None:
            self.controls.set_status(text)

    def _close_overlay(self) -> None:
        overlay = self.overlay
        controls = self.controls
        self.overlay = None
        self.controls = None
        if overlay is not None:
            overlay.stop()
        if controls is not None and controls.winfo_exists():
            controls.destroy()
        self.pipeline.stop()
        self._stop_history_session()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.status_var.set("Returned to launcher.")

    def _open_settings(self) -> None:
        SettingsDialog(self.root, self.settings, self._apply_settings)

    def _open_roi_image(self) -> None:
        image_path = filedialog.askopenfilename(
            parent=self.root,
            title="Open cropped ROI image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All files", "*.*")],
        )
        if not image_path:
            return
        try:
            from .recognizer import RoiDefectClassifier

            self.status_var.set("Loading ROI models and classifying image...")
            if self.roi_classifier is None:
                self.roi_classifier = RoiDefectClassifier(device=self.settings.backend.device)
            results = self.roi_classifier.classify_image_path(image_path)
            RoiResultWindow(self.root, image_path, results)
            summary = "; ".join(
                f"{label}: {'defect' if item['has_defect'] else 'normal'} ({float(item['confidence']):.2f})"
                for label, item in results.items()
            )
            self.status_var.set(f"ROI result: {summary}")
        except Exception as exc:
            self.status_var.set(f"ROI classification failed: {exc}")

    def _apply_settings(self, new_settings: AppSettings) -> tuple[bool, str]:
        old_recognizer = self.recognizer
        try:
            recognizer = build_recognizer(new_settings)
            recognizer.warmup()
        except Exception as exc:
            self.recognizer = old_recognizer
            return False, f"Model load failed: {exc}"

        self.settings = new_settings
        self.recognizer = recognizer
        self.auto_detect = new_settings.runtime.auto_detect
        save_settings(new_settings)
        self.pipeline.set_recognizer(recognizer)
        self.pipeline.configure_timing(new_settings.runtime.capture_interval, new_settings.runtime.inference_interval)
        self.pipeline.set_auto_enabled(new_settings.runtime.auto_detect)
        if self.overlay is not None:
            self.overlay.settings = new_settings
        self.status_var.set(self._main_status())
        return True, "Settings saved."

    def _start_history_session(self) -> None:
        self._stop_history_session()
        if not self.settings.history.enabled:
            self.pipeline.set_history_session(None)
            return
        self.history_session = HistorySession(self.settings)
        self.history_session.start()
        self.pipeline.set_history_session(self.history_session)

    def _stop_history_session(self) -> None:
        if self.history_session is not None:
            self.history_session.stop()
        self.history_session = None
        self.pipeline.set_history_session(None)

    def _main_status(self) -> str:
        return (
            f"Ready. backend={self.settings.backend.backend_type} "
            f"model={self.settings.backend.model_path} "
            f"conf={self.settings.backend.confidence:.2f} iou={self.settings.backend.iou:.2f}"
        )

    def run(self) -> int:
        self.root.mainloop()
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Screen recognition desktop UI prototype.")
    parser.add_argument("--smoke-test", action="store_true", help="Initialize and exit after validating core objects.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        app = ScreenRecognitionApp()
        frame = FrameImage(width=1280, height=720, rgb_bytes=b"\x00" * (1280 * 720 * 3))
        result = app.recognizer.recognize(frame)
        assert isinstance(result, RecognitionResult)
        app.root.after(200, app.root.destroy)
        app.run()
        return 0
    app = ScreenRecognitionApp()
    return app.run()


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, settings: AppSettings, on_apply) -> None:
        super().__init__(master)
        self.settings = settings
        self.on_apply = on_apply
        self.title("Settings")
        self.geometry("620x520")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._vars: dict[str, tk.Variable] = {}
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self._entry(frame, "Backend", "backend_type", self.settings.backend.backend_type, 0)
        self._entry(frame, "Model path", "model_path", self.settings.backend.model_path, 1, browse=True)
        self._entry(frame, "Confidence", "confidence", str(self.settings.backend.confidence), 2)
        self._entry(frame, "IoU", "iou", str(self.settings.backend.iou), 3)
        self._entry(frame, "Device", "device", self.settings.backend.device, 4)
        self._entry(frame, "Capture interval", "capture_interval", str(self.settings.runtime.capture_interval), 5)
        self._entry(frame, "Inference interval", "inference_interval", str(self.settings.runtime.inference_interval), 6)
        self._check(frame, "Auto detect", "auto_detect", self.settings.runtime.auto_detect, 7)
        self._check(frame, "Show labels", "show_labels", self.settings.runtime.show_labels, 8)
        self._check(frame, "Show confidence", "show_confidence", self.settings.runtime.show_confidence, 9)
        self._check(frame, "Save history", "history_enabled", self.settings.history.enabled, 10)
        self._check(frame, "Save screenshots", "save_screenshots", self.settings.history.save_screenshots, 11)
        self._check(frame, "Save empty auto results", "save_empty_results", self.settings.history.save_empty_results, 12)
        self._entry(frame, "History dir", "history_dir", self.settings.history.history_dir, 13)

        self.status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status_var).grid(row=14, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=15, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(actions, text="Save", command=self._save).grid(row=0, column=1, padx=4)

    def _entry(self, parent, label: str, key: str, value: str, row: int, browse: bool = False) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        var = tk.StringVar(value=value)
        self._vars[key] = var
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        if browse:
            ttk.Button(parent, text="Browse", command=lambda: self._browse_model(var)).grid(
                row=row, column=2, padx=(8, 0), pady=4
            )

    def _check(self, parent, label: str, key: str, value: bool, row: int) -> None:
        var = tk.BooleanVar(value=value)
        self._vars[key] = var
        ttk.Checkbutton(parent, text=label, variable=var).grid(row=row, column=0, columnspan=3, sticky="w", pady=4)

    def _browse_model(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Select YOLO model",
            filetypes=[("PyTorch weights", "*.pt"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _save(self) -> None:
        try:
            settings = AppSettings(
                backend=BackendSettings(
                    backend_type=str(self._vars["backend_type"].get()),
                    model_path=str(self._vars["model_path"].get()),
                    confidence=float(self._vars["confidence"].get()),
                    iou=float(self._vars["iou"].get()),
                    device=str(self._vars["device"].get()),
                ),
                runtime=RuntimeSettings(
                    auto_detect=bool(self._vars["auto_detect"].get()),
                    capture_interval=float(self._vars["capture_interval"].get()),
                    inference_interval=float(self._vars["inference_interval"].get()),
                    show_labels=bool(self._vars["show_labels"].get()),
                    show_confidence=bool(self._vars["show_confidence"].get()),
                ),
                history=HistorySettings(
                    enabled=bool(self._vars["history_enabled"].get()),
                    save_screenshots=bool(self._vars["save_screenshots"].get()),
                    save_empty_results=bool(self._vars["save_empty_results"].get()),
                    history_dir=str(self._vars["history_dir"].get()),
                ),
            )
        except ValueError as exc:
            self.status_var.set(f"Invalid setting: {exc}")
            return
        ok, message = self.on_apply(settings)
        self.status_var.set(message)
        if ok:
            self.destroy()


class RoiResultWindow(tk.Toplevel):
    def __init__(self, master: tk.Tk, image_path: str, results: dict[str, dict[str, object]]) -> None:
        super().__init__(master)
        self.title("ROI Classification Result")
        self.geometry("980x680")
        self.minsize(760, 520)
        self.transient(master)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="ROI 分类结果", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text=image_path, wraplength=920).pack(anchor="w", pady=(4, 12))

        content = ttk.Frame(frame)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        image_frame = ttk.LabelFrame(content, text="已打开的 ROI 图片", padding=8)
        image_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        self._image_label = ttk.Label(image_frame, anchor="center")
        self._image_label.grid(row=0, column=0, sticky="nsew")
        self._load_preview(image_path)

        result_frame = ttk.LabelFrame(content, text="检测结果（左上区域）", padding=12)
        result_frame.grid(row=0, column=1, sticky="new")
        for label, item in results.items():
            has_defect = bool(item["has_defect"])
            confidence = float(item["confidence"])
            text = f"{label}: {'有缺陷' if has_defect else '正常'}\n置信度：{confidence:.3f}"
            defect_probability = float(item.get("defect_probability", confidence))
            text += f"\n缺陷概率：{defect_probability:.3f}"
            color = "#b00020" if has_defect else "#087f23"
            ttk.Label(result_frame, text=text, foreground=color, font=("Segoe UI", 12, "bold"), justify="left").pack(anchor="w", pady=(0, 14))

        ttk.Label(
            frame,
            text="说明：三个模型分别判断当前裁剪 ROI 是否包含 void、bridge 或透锡不足；结果为分类判断，不提供缺陷框定位。",
            wraplength=920,
        ).pack(anchor="w", pady=(12, 8))
        ttk.Button(frame, text="关闭", command=self.destroy).pack(anchor="e", pady=(12, 0))

    def _load_preview(self, image_path: str) -> None:
        try:
            from PIL import Image, ImageTk
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                image.thumbnail((590, 500), Image.Resampling.LANCZOS)
                self._preview_image = ImageTk.PhotoImage(image)
            self._image_label.configure(image=self._preview_image, text="")
        except Exception as exc:
            self._image_label.configure(text=f"图片预览失败：{exc}", anchor="center", justify="center")
