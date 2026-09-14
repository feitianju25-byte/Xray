from pathlib import Path

from PIL import Image

from solder_mvp.inventory import scan_roots, stable_sample_id


def test_inventory_isolates_corrupt_and_missing_images(tmp_path: Path) -> None:
    root = tmp_path / "images"
    root.mkdir()
    good = root / "good.jpg"
    Image.new("L", (24, 16), 127).save(good)
    (root / "broken.jpg").write_bytes(b"not a jpeg")

    inventory = scan_roots(
        [("fixture", root), ("missing-root", tmp_path / "absent")],
        extra_paths=[("fixture", root, "missing.jpg")],
    )

    assert inventory["summary"]["ok"] == 1
    assert inventory["summary"]["error"] == 3
    good_record = next(record for record in inventory["records"] if record["status"] == "ok")
    assert good_record["width"] == 24
    assert good_record["height"] == 16
    assert Path(good_record["absolute_path"]) == good.resolve()
    errors = {record["error"].split(":", 1)[0] for record in inventory["records"] if record["status"] == "error"}
    assert {"root_not_found", "file_not_found"}.issubset(errors)


def test_sample_id_is_stable_across_root_location() -> None:
    first = stable_sample_id("data", "batch/image.jpg", 123)
    second = stable_sample_id("data", "batch\\image.jpg", 123)
    assert first == second

