from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .io_utils import write_json


def _seeded_key(sample_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{sample_id}".encode("utf-8")).hexdigest()


def image_signature(path: str | Path, size: int = 48) -> np.ndarray:
    with Image.open(path) as image:
        gray = ImageOps.grayscale(image)
        fitted = ImageOps.fit(gray, (size, size), method=Image.Resampling.BILINEAR)
        values = np.asarray(fitted, dtype=np.float32).reshape(-1)
    values -= float(values.mean())
    deviation = float(values.std())
    if deviation > 1e-6:
        values /= deviation
    return values


def _similarity(record: dict, reference: np.ndarray | None) -> float | None:
    if reference is None:
        return None
    try:
        signature = image_signature(record["absolute_path"], size=int(reference.size**0.5))
    except (OSError, ValueError):
        return None
    denominator = float(np.linalg.norm(signature) * np.linalg.norm(reference))
    if denominator <= 1e-9:
        return 0.0
    return float(np.dot(signature, reference) / denominator)


def sample_inventory(
    inventory: dict,
    limit: int,
    seed: int,
    include_path_pattern: str | None = None,
    reference_path: str | Path | None = None,
) -> dict:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    matcher = re.compile(include_path_pattern) if include_path_pattern else None
    candidates = [
        dict(record)
        for record in inventory.get("records", [])
        if record.get("status") == "ok"
        and (matcher is None or matcher.search(record.get("relative_path", "")))
    ]

    reference = image_signature(reference_path) if reference_path else None
    for record in candidates:
        record["reference_similarity"] = _similarity(record, reference)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in candidates:
        key = f"{record['root_alias']}:{record['source_dir']}"
        grouped[key].append(record)

    queues: dict[str, deque[dict]] = {}
    for source, records in grouped.items():
        records.sort(
            key=lambda item: (
                -(item["reference_similarity"] if item["reference_similarity"] is not None else -2.0),
                _seeded_key(item["sample_id"], seed),
            )
        )
        queues[source] = deque(records)

    selected: list[dict] = []
    source_order = sorted(queues, key=lambda source: _seeded_key(source, seed))
    while source_order and len(selected) < limit:
        next_round: list[str] = []
        for source in source_order:
            queue = queues[source]
            if queue and len(selected) < limit:
                record = queue.popleft()
                record["sample_rank"] = len(selected) + 1
                record["sampling_source"] = source
                selected.append(record)
            if queue:
                next_round.append(source)
        source_order = next_round

    method = "reference_similarity_stratified" if reference_path else "seeded_stratified"
    return {
        "schema_version": "1.0",
        "algorithm_version": "0.1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sampling": {
            "method": method,
            "seed": seed,
            "limit": limit,
            "include_path_pattern": include_path_pattern,
            "reference_path": str(Path(reference_path).resolve()) if reference_path else None,
            "available_candidates": len(candidates),
            "selected": len(selected),
        },
        "records": selected,
    }


def save_sample(sample: dict, output_path: str | Path) -> Path:
    return write_json(output_path, sample)

