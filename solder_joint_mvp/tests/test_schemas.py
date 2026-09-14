import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def test_minimal_examples_match_schemas() -> None:
    root = Path(__file__).resolve().parents[1]
    pairs = [
        ("inventory.schema.json", "minimal_inventory.json"),
        ("review.schema.json", "minimal_review.json"),
        ("array-grid.schema.json", "minimal_array_grid.json"),
        ("roi-manifest.schema.json", "minimal_roi_manifest.json"),
    ]
    for schema_name, example_name in pairs:
        schema = json.loads((root / "schemas" / schema_name).read_text(encoding="utf-8"))
        example = json.loads((root / "examples" / example_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)

