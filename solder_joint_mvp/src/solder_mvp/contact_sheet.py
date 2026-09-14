from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .io_utils import write_json


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _short_source(record: dict, max_chars: int = 38) -> str:
    source = f"{record['root_alias']}:{record['source_dir']}"
    return source if len(source) <= max_chars else "..." + source[-(max_chars - 3) :]


def create_review_manifest(sample: dict) -> dict:
    return {
        "schema_version": "1.0",
        "algorithm_version": sample.get("algorithm_version", "0.1.0"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instructions": "将 decision 改为 keep、reject 或 uncertain；可选填写 array_bbox、rows、cols、corners、centers。",
        "items": [
            {
                "sample_id": record["sample_id"],
                "source_path": record["absolute_path"],
                "decision": "uncertain",
                "reviewed_at": None,
                "array_bbox": None,
                "rows": None,
                "cols": None,
                "corners": [],
                "centers": [],
                "notes": "",
                "algorithm_version": sample.get("algorithm_version", "0.1.0"),
            }
            for record in sample.get("records", [])
        ],
    }


def render_contact_sheet(
    sample: dict,
    output_path: str | Path,
    columns: int = 5,
    thumbnail_size: tuple[int, int] = (320, 220),
    label_height: int = 58,
) -> Path:
    records = sample.get("records", [])
    if not records:
        raise ValueError("sample manifest contains no records")
    columns = max(1, columns)
    rows = math.ceil(len(records) / columns)
    cell_width, image_height = thumbnail_size
    cell_height = image_height + label_height
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = _font(18)
    body_font = _font(13)

    for index, record in enumerate(records):
        row, column = divmod(index, columns)
        x, y = column * cell_width, row * cell_height
        try:
            with Image.open(record["absolute_path"]) as image:
                tile = ImageOps.contain(image.convert("RGB"), thumbnail_size, Image.Resampling.LANCZOS)
            offset_x = x + (cell_width - tile.width) // 2
            offset_y = y + (image_height - tile.height) // 2
            sheet.paste(tile, (offset_x, offset_y))
        except OSError:
            draw.rectangle((x, y, x + cell_width - 1, y + image_height - 1), fill="#dddddd")
            draw.text((x + 8, y + 8), "IMAGE ERROR", fill="red", font=title_font)

        draw.rectangle((x, y, x + cell_width - 1, y + cell_height - 1), outline="#555555", width=1)
        label_y = y + image_height + 4
        draw.text((x + 6, label_y), f"#{index + 1:02d}  {record['sample_id']}", fill="black", font=title_font)
        draw.text((x + 6, label_y + 25), _short_source(record), fill="#333333", font=body_font)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=True)
    return destination


def save_review_manifest(sample: dict, output_path: str | Path) -> Path:
    return write_json(output_path, create_review_manifest(sample))


def save_review_csv(sample: dict, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = ["rank", "sample_id", "decision", "source_path", "source_dir", "notes"]
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, record in enumerate(sample.get("records", []), start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "sample_id": record["sample_id"],
                    "decision": "uncertain",
                    "source_path": record["absolute_path"],
                    "source_dir": f"{record['root_alias']}:{record['source_dir']}",
                    "notes": "",
                }
            )
    return destination
