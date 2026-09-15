from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from solder_mvp.family_screen import rank_target_family
from solder_mvp.visual_features import assign_duplicate_groups, hash_distance, perceptual_hash, target_family_score


def _target_chip(path: Path, brightness: float = 1.0) -> Path:
    image = Image.new("L", (320, 200), 225)
    draw = ImageDraw.Draw(image)
    draw.rectangle((62, 30, 258, 170), fill=170, outline=80, width=5)
    for row in range(5):
        for col in range(7):
            x = 90 + col * 23
            y = 55 + row * 22
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=35)
    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    image.save(path)
    return path


def _connector(path: Path) -> Path:
    image = Image.new("L", (320, 200), 225)
    draw = ImageDraw.Draw(image)
    for row in range(2):
        for col in range(12):
            x = 25 + col * 24
            y = 75 + row * 35
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=35)
    image.save(path)
    return path


def _record(index: int, path: Path) -> dict:
    return {
        "sample_id": f"{index:020x}",
        "root_alias": "fixture",
        "relative_path": f"未标注/{path.name}",
        "source_dir": "未标注",
        "absolute_path": str(path),
        "status": "ok",
    }


def test_perceptual_duplicates_are_brightness_tolerant(tmp_path: Path) -> None:
    first = _target_chip(tmp_path / "first.png")
    second = _target_chip(tmp_path / "second.png", brightness=0.82)
    different = _connector(tmp_path / "different.png")
    assert hash_distance(perceptual_hash(first), perceptual_hash(second)) <= 10

    grouped = assign_duplicate_groups([_record(1, first), _record(2, second), _record(3, different)], threshold=10)
    assert grouped[0]["duplicate_group"] == grouped[1]["duplicate_group"]
    assert grouped[2]["duplicate_group"] != grouped[0]["duplicate_group"]
    assert sum(bool(item["duplicate_representative"]) for item in grouped[:2]) == 1


def test_target_family_scores_above_connector_and_ranks_globally(tmp_path: Path) -> None:
    reference = _target_chip(tmp_path / "reference.png")
    target = _target_chip(tmp_path / "target.png", brightness=0.9)
    connector = _connector(tmp_path / "connector.png")

    target_score = target_family_score(reference, target)["family_score"]
    connector_score = target_family_score(reference, connector)["family_score"]
    assert target_score > connector_score

    inventory = {"records": [_record(1, connector), _record(2, target)]}
    result = rank_target_family(inventory, reference, limit=2, duplicate_threshold=0)
    assert result["records"][0]["absolute_path"] == str(target)
    assert set(result["records"][0]["score_components"]) == {"whole", "center", "edge", "periodicity", "aspect"}

