from __future__ import annotations

import pytest

from solder_mvp.dataset_split import find_duplicate_group_leakage, freeze_review_split


def _review() -> dict:
    items = []
    for index in range(14):
        items.append({
            "sample_id": f"{index:020x}",
            "source_path": f"D:/data/{index}.jpg",
            "decision": "keep" if index < 12 else "reject",
            "duplicate_group": "shared" if index in {0, 1} else f"group-{index}",
            "family_score": 1.0 - index / 100,
        })
    return {"algorithm_version": "0.3.0", "target_family": "target-v1", "items": items}


def test_frozen_split_is_deterministic_and_group_safe() -> None:
    first = freeze_review_split(_review(), validation_count=10, seed=42)
    second = freeze_review_split(_review(), validation_count=10, seed=42)
    assert [(item["sample_id"], item["split"]) for item in first["assignments"]] == [
        (item["sample_id"], item["split"]) for item in second["assignments"]
    ]
    assert first["counts"]["validation"] >= 10
    assert first["leakage"] == []
    shared = [item["split"] for item in first["assignments"] if item["duplicate_group"] == "shared"]
    assert len(set(shared)) == 1


def test_frozen_split_requires_enough_keeps() -> None:
    with pytest.raises(ValueError, match="confirmed keep"):
        freeze_review_split({"items": _review()["items"][:5]}, validation_count=10)


def test_leakage_detector_reports_cross_split_group() -> None:
    leakage = find_duplicate_group_leakage([
        {"sample_id": "a", "duplicate_group": "same", "split": "development"},
        {"sample_id": "b", "duplicate_group": "same", "split": "validation"},
    ])
    assert leakage[0]["duplicate_group"] == "same"
