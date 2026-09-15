from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .io_utils import write_json


@dataclass
class RoiCrop:
    image: Image.Image | None
    metadata: dict


def _open_image(source: str | Path | Image.Image) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.copy()
    with Image.open(source) as image:
        return image.copy()


def crop_normalized_roi(
    source: str | Path | Image.Image,
    center: tuple[float, float],
    grid_spacing: tuple[float, float],
    crop_ratio: float = 0.8,
    output_size: tuple[int, int] = (96, 96),
    boundary_policy: str = "pad",
    fill_value: int = 0,
) -> RoiCrop:
    if boundary_policy not in {"pad", "skip"}:
        raise ValueError("boundary_policy must be 'pad' or 'skip'")
    if crop_ratio <= 0:
        raise ValueError("crop_ratio must be positive")
    if min(output_size) < 1:
        raise ValueError("output_size must be positive")
    image = _open_image(source)
    crop_size = max(3, int(round(min(grid_spacing) * crop_ratio)))
    if crop_size % 2 == 0:
        crop_size += 1
    left = int(round(center[0] - crop_size / 2.0))
    top = int(round(center[1] - crop_size / 2.0))
    right, bottom = left + crop_size, top + crop_size
    outside = left < 0 or top < 0 or right > image.width or bottom > image.height
    metadata = {
        "center": [float(center[0]), float(center[1])],
        "crop_bbox": [left, top, right, bottom],
        "grid_spacing": [float(grid_spacing[0]), float(grid_spacing[1])],
        "crop_ratio": float(crop_ratio),
        "raw_size": [crop_size, crop_size],
        "output_size": [int(output_size[0]), int(output_size[1])],
        "boundary_policy": boundary_policy,
        "padded": outside,
    }
    if outside and boundary_policy == "skip":
        metadata["status"] = "skipped_out_of_bounds"
        return RoiCrop(None, metadata)

    if outside:
        crop = Image.new(image.mode, (crop_size, crop_size), color=fill_value)
        source_box = (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
        if source_box[2] > source_box[0] and source_box[3] > source_box[1]:
            visible = image.crop(source_box)
            crop.paste(visible, (source_box[0] - left, source_box[1] - top))
    else:
        crop = image.crop((left, top, right, bottom))
    normalized = crop.resize(output_size, Image.Resampling.LANCZOS)
    metadata["status"] = "ok"
    return RoiCrop(normalized, metadata)


def extract_grid_rois(
    source: str | Path | Image.Image,
    grid: dict,
    crop_ratio: float = 0.8,
    output_size: tuple[int, int] = (96, 96),
    boundary_policy: str = "pad",
    missing_policy: str = "skip",
    fill_value: int = 0,
) -> list[RoiCrop]:
    if missing_policy not in {"skip", "extract"}:
        raise ValueError("missing_policy must be 'skip' or 'extract'")
    spacing = (float(grid["column_spacing"]), float(grid["row_spacing"]))
    results = []
    for cell in grid.get("cells", []):
        if cell.get("status") == "missing" and missing_policy == "skip":
            crop_size = max(3, int(round(min(spacing) * crop_ratio)))
            if crop_size % 2 == 0:
                crop_size += 1
            left = int(round(float(cell["x"]) - crop_size / 2.0))
            top = int(round(float(cell["y"]) - crop_size / 2.0))
            results.append(
                RoiCrop(
                    None,
                    {
                        "row": int(cell["row"]),
                        "col": int(cell["col"]),
                        "center": [float(cell["x"]), float(cell["y"])],
                        "crop_bbox": [left, top, left + crop_size, top + crop_size],
                        "status": "skipped_missing",
                        "output_size": [int(output_size[0]), int(output_size[1])],
                    },
                )
            )
            continue
        crop = crop_normalized_roi(
            source,
            center=(float(cell["x"]), float(cell["y"])),
            grid_spacing=spacing,
            crop_ratio=crop_ratio,
            output_size=output_size,
            boundary_policy=boundary_policy,
            fill_value=fill_value,
        )
        crop.metadata.update({"row": int(cell["row"]), "col": int(cell["col"]), "grid_status": cell.get("status")})
        results.append(crop)
    return results


def _stable_roi_id(sample_id: str, array_id: str, row: int, col: int) -> str:
    digest = hashlib.sha1(f"{sample_id}|{array_id}|{row}|{col}".encode("utf-8")).hexdigest()[:12]
    return f"{array_id}-r{row:02d}-c{col:02d}-{digest}"


def _render_roi_overlay(source: str | Path, records: list[dict], output_path: Path) -> Path:
    with Image.open(source) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    for record in records:
        left, top, right, bottom = record["crop_bbox"]
        color = "#00e676" if record["status"] == "ok" else "#ff5252"
        draw.rectangle((left, top, right, bottom), outline=color, width=2)
        draw.text((left + 2, top + 2), f"r{record['row']}c{record['col']}", fill=color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)
    return output_path


def export_grid_rois(
    source: str | Path,
    grid: dict,
    output_dir: str | Path,
    sample_id: str,
    array_id: str,
    crop_ratio: float = 0.8,
    output_size: tuple[int, int] = (96, 96),
    boundary_policy: str = "pad",
    missing_policy: str = "skip",
    fill_value: int = 0,
    algorithm_version: str = "0.3.0",
) -> dict:
    destination = Path(output_dir)
    roi_dir = destination / "rois"
    roi_dir.mkdir(parents=True, exist_ok=True)
    crops = extract_grid_rois(
        source,
        grid,
        crop_ratio=crop_ratio,
        output_size=output_size,
        boundary_policy=boundary_policy,
        missing_policy=missing_policy,
        fill_value=fill_value,
    )
    records = []
    for crop in crops:
        row, col = int(crop.metadata["row"]), int(crop.metadata["col"])
        roi_id = _stable_roi_id(sample_id, array_id, row, col)
        output_path = None
        if crop.image is not None:
            output_path = roi_dir / f"{roi_id}.png"
            crop.image.save(output_path, format="PNG", optimize=True)
        skipped = crop.image is None
        records.append(
            {
                "roi_id": roi_id,
                "sample_id": sample_id,
                "source_path": str(Path(source).resolve()),
                "array_id": array_id,
                "row": row,
                "col": col,
                "crop_bbox": crop.metadata["crop_bbox"],
                "output_path": str(output_path.resolve()) if output_path else None,
                "status": "skipped" if skipped else "ok",
                "handling": "skipped" if skipped else ("padded" if crop.metadata.get("padded") else "none"),
                "grid_status": crop.metadata.get("grid_status", "missing" if skipped else "observed"),
                "error": None,
            }
        )
    config = {
        "crop_ratio": float(crop_ratio),
        "output_size": [int(output_size[0]), int(output_size[1])],
        "boundary_policy": boundary_policy,
        "missing_policy": missing_policy,
        "fill_value": fill_value,
    }
    manifest = {
        "schema_version": "1.0",
        "algorithm_version": algorithm_version,
        "config": config,
        "records": records,
    }
    manifest_path = write_json(destination / "roi_manifest.json", manifest)
    overlay_path = _render_roi_overlay(source, records, destination / "roi_overlay.png")
    return {"manifest": manifest, "manifest_path": manifest_path, "overlay_path": overlay_path}
