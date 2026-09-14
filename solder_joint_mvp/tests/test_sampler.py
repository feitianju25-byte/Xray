from pathlib import Path

from solder_mvp.sampler import sample_inventory


def _record(index: int, source: str, path: Path) -> dict:
    return {
        "sample_id": f"{index:020x}",
        "root_alias": "fixture",
        "relative_path": f"未标注/{source}/{index}.jpg",
        "source_dir": f"未标注/{source}",
        "absolute_path": str(path),
        "status": "ok",
    }


def test_seeded_sampling_is_reproducible_and_limited(tmp_path: Path) -> None:
    records = []
    for index in range(12):
        source = "a" if index < 8 else "b"
        records.append(_record(index, source, tmp_path / f"{index}.jpg"))
    inventory = {"records": list(reversed(records))}

    first = sample_inventory(inventory, limit=6, seed=42, include_path_pattern="未标注")
    second = sample_inventory({"records": records}, limit=6, seed=42, include_path_pattern="未标注")

    assert [item["sample_id"] for item in first["records"]] == [item["sample_id"] for item in second["records"]]
    assert len(first["records"]) == 6
    assert {item["source_dir"] for item in first["records"]} == {"未标注/a", "未标注/b"}

