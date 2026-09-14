from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

from .io_utils import write_json

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}
SCHEMA_VERSION = "1.0"
ALGORITHM_VERSION = "0.1.0"


def stable_sample_id(root_alias: str, relative_path: str, file_size: int) -> str:
    normalized = relative_path.replace("\\", "/").casefold()
    payload = f"{root_alias.casefold()}\0{normalized}\0{file_size}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def _error_record(root_alias: str, root: Path, relative_path: str, error: str) -> dict:
    absolute_path = root / relative_path if relative_path != "." else root
    return {
        "sample_id": stable_sample_id(root_alias, relative_path, 0),
        "root_alias": root_alias,
        "relative_path": relative_path.replace("\\", "/"),
        "source_dir": Path(relative_path).parent.as_posix(),
        "absolute_path": str(absolute_path.resolve(strict=False)),
        "file_size": 0,
        "status": "error",
        "width": None,
        "height": None,
        "mode": None,
        "error": error,
    }


def inspect_image(root_alias: str, root: Path, path: Path) -> dict:
    relative_path = path.relative_to(root).as_posix()
    try:
        size = path.stat().st_size
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
        return {
            "sample_id": stable_sample_id(root_alias, relative_path, size),
            "root_alias": root_alias,
            "relative_path": relative_path,
            "source_dir": Path(relative_path).parent.as_posix(),
            "absolute_path": str(path.resolve()),
            "file_size": size,
            "status": "ok",
            "width": width,
            "height": height,
            "mode": mode,
            "error": None,
        }
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        record = _error_record(root_alias, root, relative_path, f"{type(exc).__name__}: {exc}")
        record["file_size"] = size
        record["sample_id"] = stable_sample_id(root_alias, relative_path, size)
        return record


def scan_roots(
    roots: Iterable[tuple[str, str | Path]],
    extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
    extra_paths: Iterable[tuple[str, str | Path, str | Path]] = (),
) -> dict:
    allowed = {extension.casefold() for extension in extensions}
    records: list[dict] = []
    root_descriptors: list[dict] = []

    for alias, root_value in roots:
        root = Path(root_value).resolve(strict=False)
        root_descriptors.append({"alias": alias, "path": str(root)})
        if not root.is_dir():
            records.append(_error_record(alias, root, ".", "root_not_found"))
            continue
        paths = sorted(
            (path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in allowed),
            key=lambda path: path.relative_to(root).as_posix().casefold(),
        )
        records.extend(inspect_image(alias, root, path) for path in paths)

    for alias, root_value, relative_value in extra_paths:
        root = Path(root_value).resolve(strict=False)
        path = root / Path(relative_value)
        if path.is_file():
            records.append(inspect_image(alias, root, path))
        else:
            records.append(_error_record(alias, root, Path(relative_value).as_posix(), "file_not_found"))

    status_counts = Counter(record["status"] for record in records)
    source_counts = Counter(
        f"{record['root_alias']}:{record['source_dir']}"
        for record in records
        if record["status"] == "ok"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roots": root_descriptors,
        "summary": {
            "total": len(records),
            "ok": status_counts.get("ok", 0),
            "error": status_counts.get("error", 0),
            "sources": dict(sorted(source_counts.items())),
        },
        "records": records,
    }


def save_inventory(inventory: dict, output_path: str | Path) -> Path:
    return write_json(output_path, inventory)

