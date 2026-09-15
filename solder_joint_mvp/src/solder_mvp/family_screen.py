from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import write_json
from .visual_features import assign_duplicate_groups, image_descriptors, compare_descriptors

ALGORITHM_VERSION = "0.2.0"
DEFAULT_TARGET_FAMILY = "frontal-chip-internal-dot-grid-v1"


def _seeded_key(sample_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{sample_id}".encode("utf-8")).hexdigest()


def rank_target_family(
    inventory: dict,
    reference_path: str | Path,
    limit: int = 120,
    seed: int = 20260915,
    include_path_pattern: str | None = None,
    duplicate_threshold: int = 10,
    max_per_duplicate_group: int = 1,
    target_family: str = DEFAULT_TARGET_FAMILY,
) -> dict:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if max_per_duplicate_group < 1:
        raise ValueError("max_per_duplicate_group must be at least 1")
    matcher = re.compile(include_path_pattern) if include_path_pattern else None
    candidates = [
        dict(record)
        for record in inventory.get("records", [])
        if record.get("status") == "ok"
        and (matcher is None or matcher.search(record.get("relative_path", "")))
    ]
    enriched = assign_duplicate_groups(candidates, threshold=duplicate_threshold)
    reference = image_descriptors(reference_path)[0]

    scored: list[dict] = []
    failures = 0
    for record in enriched:
        try:
            descriptors = image_descriptors(record["absolute_path"])
            comparisons = [compare_descriptors(reference, descriptor) for descriptor in descriptors]
            best_index = max(range(len(comparisons)), key=lambda index: comparisons[index][0])
            score, components = comparisons[best_index]
            record["family_score"] = score
            record["score_components"] = components
            record["best_rotation_degrees"] = int(descriptors[best_index]["rotation_degrees"])
            record["target_family"] = target_family
            scored.append(record)
        except (OSError, ValueError):
            failures += 1

    scored.sort(key=lambda item: (-item["family_score"], _seeded_key(item["sample_id"], seed)))
    group_counts: dict[str, int] = {}
    selected: list[dict] = []
    for record in scored:
        group_id = record["duplicate_group"]
        if group_counts.get(group_id, 0) >= max_per_duplicate_group:
            continue
        group_counts[group_id] = group_counts.get(group_id, 0) + 1
        record["sample_rank"] = len(selected) + 1
        record["sampling_source"] = f"{record['root_alias']}:{record['source_dir']}"
        selected.append(record)
        if len(selected) >= limit:
            break

    return {
        "schema_version": "1.0",
        "algorithm_version": ALGORITHM_VERSION,
        "target_family": target_family,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "screening": {
            "method": "global-multifeature-reference-ranking",
            "seed": seed,
            "limit": limit,
            "include_path_pattern": include_path_pattern,
            "reference_path": str(Path(reference_path).resolve()),
            "duplicate_hamming_threshold": duplicate_threshold,
            "max_per_duplicate_group": max_per_duplicate_group,
            "available_candidates": len(candidates),
            "scored": len(scored),
            "failed": failures,
            "selected": len(selected),
            "duplicate_groups": len({record["duplicate_group"] for record in enriched}),
        },
        "records": selected,
    }


def save_family_screen(result: dict, output_path: str | Path) -> Path:
    return write_json(output_path, result)

