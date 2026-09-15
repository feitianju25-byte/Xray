from __future__ import annotations

import argparse
import csv
import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .geometry_review import GEOMETRY_FIELDS, _read_labelme_geometry
from .io_utils import write_json


def load_geometry_rows(csv_path: str | Path) -> list[dict[str, str]]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("geometry review CSV contains no rows")
    missing = [field for field in GEOMETRY_FIELDS if field not in rows[0]]
    if missing:
        raise ValueError(f"geometry review CSV is missing fields: {missing}")
    return rows


def read_saved_bbox(row: dict[str, str]) -> list[float] | None:
    names = ("bbox_left", "bbox_top", "bbox_right", "bbox_bottom")
    values = [(row.get(name) or "").strip() for name in names]
    if all(values):
        return [float(value) for value in values]
    labelme_path = (row.get("labelme_json") or "").strip()
    if labelme_path and Path(labelme_path).exists():
        bbox, _, _ = _read_labelme_geometry(labelme_path)
        return bbox
    return None


def update_labelme_rectangle(annotation: dict, bbox: list[float]) -> dict:
    updated = dict(annotation)
    shapes = [
        shape
        for shape in annotation.get("shapes", [])
        if not (shape.get("label") == "target_chip" and shape.get("shape_type") == "rectangle")
    ]
    left, top, right, bottom = bbox
    shapes.append(
        {
            "label": "target_chip",
            "points": [[float(left), float(top)], [float(right), float(bottom)]],
            "group_id": None,
            "description": "由验证集可视化标注器生成",
            "shape_type": "rectangle",
            "flags": {},
            "mask": None,
        }
    )
    updated["shapes"] = shapes
    return updated


def save_geometry_annotation(
    csv_path: str | Path,
    rows: list[dict[str, str]],
    index: int,
    bbox: list[float],
    row_count: int,
    col_count: int,
    notes: str = "",
) -> None:
    if not (0 <= index < len(rows)):
        raise IndexError("geometry row index is out of range")
    left, top, right, bottom = (float(value) for value in bbox)
    if right <= left or bottom <= top:
        raise ValueError("the chip rectangle must have positive width and height")
    if row_count < 2 or col_count < 3:
        raise ValueError("rows must be at least 2 and cols at least 3")

    row = rows[index]
    labelme_path = Path(row["labelme_json"])
    annotation = json.loads(labelme_path.read_text(encoding="utf-8"))
    write_json(labelme_path, update_labelme_rectangle(annotation, [left, top, right, bottom]))

    row.update(
        {
            "bbox_left": f"{left:.3f}",
            "bbox_top": f"{top:.3f}",
            "bbox_right": f"{right:.3f}",
            "bbox_bottom": f"{bottom:.3f}",
            "rows": str(int(row_count)),
            "cols": str(int(col_count)),
            "review_status": "complete",
            "notes": notes.strip(),
        }
    )

    destination = Path(csv_path)
    backup = destination.with_name(destination.name + ".backup")
    if not backup.exists():
        shutil.copy2(destination, backup)
    temporary = destination.with_name(destination.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GEOMETRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


class GeometryAnnotator:
    def __init__(self, root: tk.Tk, csv_path: str | Path) -> None:
        self.root = root
        self.csv_path = Path(csv_path).resolve()
        self.rows = load_geometry_rows(self.csv_path)
        self.index = next(
            (index for index, row in enumerate(self.rows) if row.get("review_status") != "complete"),
            0,
        )
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.bbox: list[float] | None = None
        self.drag_start: tuple[float, float] | None = None

        self.rank_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.progress_var = tk.StringVar()
        self.rows_var = tk.StringVar()
        self.cols_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.status_var = tk.StringVar(value="左键拖动框选芯片；滚轮缩放，滚动条平移")

        self._build_ui()
        self.root.update_idletasks()
        self._load_current()
        self.root.bind("<Control-s>", lambda _event: self._save())
        self.root.bind("<Left>", lambda _event: self._previous())
        self.root.bind("<Right>", lambda _event: self._next_without_save())
        self.root.bind("<Delete>", lambda _event: self._clear_box())

    def _build_ui(self) -> None:
        self.root.title("焊点阵列验证集轻量标注器")
        self.root.geometry("1400x900")
        self.root.minsize(900, 600)

        header = ttk.Frame(self.root, padding=8)
        header.pack(fill=tk.X)
        ttk.Label(header, textvariable=self.rank_var, font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.progress_var).pack(side=tk.RIGHT)
        ttk.Label(self.root, textvariable=self.path_var, padding=(8, 0), foreground="#555555").pack(fill=tk.X)

        form = ttk.Frame(self.root, padding=8)
        form.pack(fill=tk.X)
        ttk.Label(form, text="阵列行数：").pack(side=tk.LEFT)
        ttk.Entry(form, textvariable=self.rows_var, width=7).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(form, text="阵列列数：").pack(side=tk.LEFT)
        ttk.Entry(form, textvariable=self.cols_var, width=7).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(form, text="备注：").pack(side=tk.LEFT)
        ttk.Entry(form, textvariable=self.notes_var, width=42).pack(side=tk.LEFT, padx=(0, 12), fill=tk.X, expand=True)
        ttk.Button(form, text="缩小", command=lambda: self._zoom(0.8)).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="适应窗口", command=self._fit).pack(side=tk.LEFT, padx=2)
        ttk.Button(form, text="放大", command=lambda: self._zoom(1.25)).pack(side=tk.LEFT, padx=2)

        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#202020", highlightthickness=0, cursor="crosshair")
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self._start_box)
        self.canvas.bind("<B1-Motion>", self._drag_box)
        self.canvas.bind("<ButtonRelease-1>", self._finish_box)
        self.canvas.bind("<MouseWheel>", self._mousewheel)

        footer = ttk.Frame(self.root, padding=8)
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="上一张  ←", command=self._previous).pack(side=tk.LEFT, padx=3)
        ttk.Button(footer, text="清除框  Del", command=self._clear_box).pack(side=tk.LEFT, padx=3)
        ttk.Label(footer, textvariable=self.status_var, foreground="#1f5f8b").pack(side=tk.LEFT, padx=16)
        ttk.Button(footer, text="仅下一张  →", command=self._next_without_save).pack(side=tk.RIGHT, padx=3)
        ttk.Button(footer, text="保存并下一张  Ctrl+S", command=self._save_and_next).pack(side=tk.RIGHT, padx=3)
        ttk.Button(footer, text="保存", command=self._save).pack(side=tk.RIGHT, padx=3)

    def _load_current(self) -> None:
        row = self.rows[self.index]
        source = Path(row["source_path"])
        try:
            with Image.open(source) as image:
                self.image = image.convert("RGB")
        except OSError as error:
            messagebox.showerror("图片读取失败", f"{source}\n\n{error}")
            return
        self.bbox = read_saved_bbox(row)
        self.rows_var.set(row.get("rows", ""))
        self.cols_var.set(row.get("cols", ""))
        self.notes_var.set(row.get("notes", ""))
        self.rank_var.set(f"联系表 #{int(row['rank']):03d}    样本 {row['sample_id']}")
        self.path_var.set(str(source))
        self._update_progress()
        self._fit()

    def _update_progress(self) -> None:
        complete = sum(row.get("review_status") == "complete" for row in self.rows)
        self.progress_var.set(f"第 {self.index + 1}/{len(self.rows)} 张    已完成 {complete}/{len(self.rows)}")

    def _fit(self) -> None:
        if self.image is None:
            return
        width = max(100, self.canvas.winfo_width() - 8)
        height = max(100, self.canvas.winfo_height() - 8)
        self.scale = min(width / self.image.width, height / self.image.height)
        self._redraw()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _zoom(self, factor: float) -> None:
        if self.image is None:
            return
        center_x = self.canvas.canvasx(self.canvas.winfo_width() / 2) / self.scale
        center_y = self.canvas.canvasy(self.canvas.winfo_height() / 2) / self.scale
        max_scale = min(
            4.0,
            6000 / self.image.width,
            6000 / self.image.height,
            (40_000_000 / (self.image.width * self.image.height)) ** 0.5,
        )
        self.scale = min(max_scale, max(0.05, self.scale * factor))
        self._redraw()
        display_width = self.image.width * self.scale
        display_height = self.image.height * self.scale
        if display_width > self.canvas.winfo_width():
            self.canvas.xview_moveto(max(0.0, (center_x * self.scale - self.canvas.winfo_width() / 2) / display_width))
        if display_height > self.canvas.winfo_height():
            self.canvas.yview_moveto(max(0.0, (center_y * self.scale - self.canvas.winfo_height() / 2) / display_height))

    def _mousewheel(self, event: tk.Event) -> str:
        self._zoom(1.2 if event.delta > 0 else 1 / 1.2)
        return "break"

    def _redraw(self) -> None:
        if self.image is None:
            return
        display_size = (
            max(1, round(self.image.width * self.scale)),
            max(1, round(self.image.height * self.scale)),
        )
        resized = self.image.resize(display_size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW, tags="source")
        self.canvas.configure(scrollregion=(0, 0, display_size[0], display_size[1]))
        self._draw_box()

    def _draw_box(self) -> None:
        self.canvas.delete("bbox")
        if self.bbox is None:
            return
        left, top, right, bottom = self.bbox
        self.canvas.create_rectangle(
            left * self.scale,
            top * self.scale,
            right * self.scale,
            bottom * self.scale,
            outline="#00ff66",
            width=3,
            tags="bbox",
        )

    def _image_point(self, event: tk.Event) -> tuple[float, float]:
        if self.image is None:
            return 0.0, 0.0
        x = self.canvas.canvasx(event.x) / self.scale
        y = self.canvas.canvasy(event.y) / self.scale
        return min(max(x, 0.0), self.image.width), min(max(y, 0.0), self.image.height)

    def _start_box(self, event: tk.Event) -> None:
        self.drag_start = self._image_point(event)
        self.bbox = [*self.drag_start, *self.drag_start]
        self._draw_box()

    def _drag_box(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        current = self._image_point(event)
        self.bbox = [
            min(self.drag_start[0], current[0]),
            min(self.drag_start[1], current[1]),
            max(self.drag_start[0], current[0]),
            max(self.drag_start[1], current[1]),
        ]
        self._draw_box()

    def _finish_box(self, event: tk.Event) -> None:
        self._drag_box(event)
        self.drag_start = None
        if self.bbox and (self.bbox[2] - self.bbox[0] < 3 or self.bbox[3] - self.bbox[1] < 3):
            self.bbox = None
        self._draw_box()

    def _clear_box(self) -> None:
        self.bbox = None
        self._draw_box()
        self.status_var.set("已清除当前矩形，重新拖动即可")

    def _save(self) -> bool:
        if self.bbox is None:
            messagebox.showwarning("尚未框选", "请先用左键拖出目标芯片矩形。")
            return False
        try:
            row_count = int(self.rows_var.get().strip())
            col_count = int(self.cols_var.get().strip())
            save_geometry_annotation(
                self.csv_path,
                self.rows,
                self.index,
                self.bbox,
                row_count,
                col_count,
                self.notes_var.get(),
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("保存失败", str(error))
            return False
        self.status_var.set(f"已保存联系表 #{int(self.rows[self.index]['rank']):03d}")
        self._update_progress()
        return True

    def _save_and_next(self) -> None:
        if self._save():
            self._move(1)

    def _previous(self) -> None:
        self._move(-1)

    def _next_without_save(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        next_index = self.index + delta
        if not (0 <= next_index < len(self.rows)):
            complete = sum(row.get("review_status") == "complete" for row in self.rows)
            messagebox.showinfo("到达末尾", f"当前已完成 {complete}/{len(self.rows)} 张。")
            return
        self.index = next_index
        self._load_current()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw chip boxes and save validation geometry without hand-written coordinates")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "reviews" / "validation_geometry_2026-09-15" / "geometry_review.csv",
        help="Path to the prepared geometry_review.csv",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = tk.Tk()
    GeometryAnnotator(root, args.csv)
    root.mainloop()
    return 0
