from pathlib import Path

import pytest
from PIL import Image

from solder_mvp.contact_sheet import (
    apply_ranked_suggestions,
    create_review_manifest,
    migrate_review_manifest,
    render_contact_sheet,
    render_contact_sheet_batches,
    save_review_csv,
)


def test_contact_sheet_and_review_preserve_ids_and_sources(tmp_path: Path) -> None:
    records = []
    for index in range(3):
        path = tmp_path / f"source-{index}.png"
        Image.new("L", (80, 60), 60 + index * 40).save(path)
        records.append(
            {
                "sample_id": f"{index:020x}",
                "root_alias": "fixture",
                "source_dir": f"batch-{index}",
                "absolute_path": str(path),
            }
        )
    sample = {"algorithm_version": "0.2.0", "target_family": "target-v1", "records": records}

    destination = render_contact_sheet(sample, tmp_path / "sheet.png", columns=2, thumbnail_size=(100, 80), label_height=40)
    with Image.open(destination) as sheet:
        assert sheet.size == (200, 240)

    review = create_review_manifest(sample)
    assert [item["sample_id"] for item in review["items"]] == [item["sample_id"] for item in records]
    assert [item["source_path"] for item in review["items"]] == [item["absolute_path"] for item in records]
    assert {item["decision"] for item in review["items"]} == {"uncertain"}
    assert {item["target_family"] for item in review["items"]} == {"target-v1"}
    assert {item["suggested_decision"] for item in review["items"]} == {"uncertain"}

    csv_path = save_review_csv(sample, tmp_path / "review.csv")
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "rank,sample_id,family_score,duplicate_group,suggested_decision,decision,source_path,source_dir,notes" in csv_text
    assert "uncertain" in csv_text

    batches = render_contact_sheet_batches(sample, tmp_path / "batches", batch_size=2, columns=2)
    assert [path.name for path in batches] == ["contact_sheet_001_002.png", "contact_sheet_003_003.png"]


def test_apply_ranked_suggestions_requires_complete_unique_coverage(tmp_path: Path) -> None:
    path = tmp_path / "source.png"
    Image.new("L", (80, 60), 90).save(path)
    sample = {
        "records": [{
            "sample_id": "0" * 20,
            "sample_rank": 1,
            "root_alias": "fixture",
            "source_dir": "batch",
            "absolute_path": str(path),
        }]
    }
    annotated = apply_ranked_suggestions(
        sample,
        {"reviewer": "codex", "labels": {"keep": [1], "other_component": [], "reject": [], "uncertain": []}},
    )
    assert annotated["records"][0]["suggested_decision"] == "keep"

    with pytest.raises(ValueError, match="more than once"):
        apply_ranked_suggestions(sample, {"labels": {"keep": [1], "uncertain": [1]}})


def test_old_review_manifest_migrates_without_losing_decisions() -> None:
    old = {
        "schema_version": "1.0",
        "algorithm_version": "0.1.0",
        "created_at": "2026-09-14T00:00:00+00:00",
        "items": [{
            "sample_id": "0123456789abcdef0123",
            "source_path": "D:/data/image.jpg",
            "decision": "keep",
            "reviewed_at": None,
            "array_bbox": None,
            "rows": None,
            "cols": None,
            "corners": [],
            "centers": [],
            "notes": "old decision",
            "algorithm_version": "0.1.0",
        }],
    }
    migrated = migrate_review_manifest(old, target_family="target-v1")
    assert migrated["target_family"] == "target-v1"
    assert migrated["items"][0]["decision"] == "keep"
    assert migrated["items"][0]["suggested_decision"] == "keep"
