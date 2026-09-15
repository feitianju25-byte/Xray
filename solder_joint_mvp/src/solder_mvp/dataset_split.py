from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import write_json


def _group_key(item: dict) -> str:
    return item.get("duplicate_group") or f"sample-{item['sample_id']}"


def find_duplicate_group_leakage(assignments: list[dict]) -> list[dict]:
    splits_by_group: dict[str, set[str]] = {}
    samples_by_group: dict[str, list[str]] = {}
    for assignment in assignments:
        split = assignment.get("split")
        if split not in {"development", "validation"}:
            continue
        group = assignment["duplicate_group"]
        splits_by_group.setdefault(group, set()).add(split)
        samples_by_group.setdefault(group, []).append(assignment["sample_id"])
    return [
        {"duplicate_group": group, "splits": sorted(splits), "sample_ids": sorted(samples_by_group[group])}
        for group, splits in sorted(splits_by_group.items())
        if len(splits) > 1
    ]


def freeze_review_split(review: dict, validation_count: int = 10, seed: int = 20260915) -> dict:
    """Freeze confirmed keep samples without splitting a near-duplicate group."""
    if validation_count < 1:
        raise ValueError("validation_count must be at least 1")
    keep_items = [dict(item) for item in review.get("items", []) if item.get("decision") == "keep"]
    if len(keep_items) < validation_count:
        raise ValueError(
            f"at least {validation_count} confirmed keep samples are required; found {len(keep_items)}"
        )

    groups: dict[str, list[dict]] = {}
    for item in keep_items:
        groups.setdefault(_group_key(item), []).append(item)
    ordered_groups = sorted(
        groups,
        key=lambda group: hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest(),
    )
    validation_groups: set[str] = set()
    validation_samples = 0
    for group in ordered_groups:
        if validation_samples >= validation_count:
            break
        validation_groups.add(group)
        validation_samples += len(groups[group])

    assignments = []
    for rank, item in enumerate(review.get("items", []), start=1):
        group = _group_key(item)
        if item.get("decision") != "keep":
            split = "excluded"
        elif group in validation_groups:
            split = "validation"
        else:
            split = "development"
        assignments.append(
            {
                "sample_id": item["sample_id"],
                "rank": rank,
                "source_path": item["source_path"],
                "decision": item.get("decision"),
                "duplicate_group": group,
                "split": split,
                "family_score": item.get("family_score"),
            }
        )

    leakage = find_duplicate_group_leakage(assignments)
    if leakage:
        raise AssertionError(f"duplicate groups leak across frozen splits: {leakage}")
    counts = {name: sum(item["split"] == name for item in assignments) for name in ("development", "validation", "excluded")}
    return {
        "schema_version": "1.0",
        "algorithm_version": review.get("algorithm_version", "unknown"),
        "target_family": review.get("target_family"),
        "seed": seed,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "validation_minimum": validation_count,
        "counts": counts,
        "duplicate_group_count": len(groups),
        "leakage": leakage,
        "assignments": assignments,
    }


def save_frozen_split(split: dict, output_path: str | Path) -> Path:
    return write_json(output_path, split)
