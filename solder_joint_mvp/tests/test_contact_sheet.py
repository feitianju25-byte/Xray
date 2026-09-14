from pathlib import Path

from PIL import Image

from solder_mvp.contact_sheet import create_review_manifest, render_contact_sheet, save_review_csv


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
    sample = {"algorithm_version": "0.1.0", "records": records}

    destination = render_contact_sheet(sample, tmp_path / "sheet.png", columns=2, thumbnail_size=(100, 80), label_height=40)
    with Image.open(destination) as sheet:
        assert sheet.size == (200, 240)

    review = create_review_manifest(sample)
    assert [item["sample_id"] for item in review["items"]] == [item["sample_id"] for item in records]
    assert [item["source_path"] for item in review["items"]] == [item["absolute_path"] for item in records]
    assert {item["decision"] for item in review["items"]} == {"uncertain"}

    csv_path = save_review_csv(sample, tmp_path / "review.csv")
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "rank,sample_id,decision,source_path,source_dir,notes" in csv_text
    assert "uncertain" in csv_text
