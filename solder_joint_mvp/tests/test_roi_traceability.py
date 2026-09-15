from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from PIL import Image

from solder_mvp.roi_exporter import export_grid_rois


def test_exported_roi_traces_to_source_array_and_grid_cell(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("L", (90, 70), 130).save(source)
    grid = {
        "column_spacing": 24.0,
        "row_spacing": 22.0,
        "cells": [
            {"row": 0, "col": 0, "x": 30.0, "y": 30.0, "status": "observed"},
            {"row": 0, "col": 1, "x": 54.0, "y": 30.0, "status": "missing"},
        ],
    }
    result = export_grid_rois(
        source,
        grid,
        tmp_path / "export",
        sample_id="0123456789abcdef0123",
        array_id="array-001",
        output_size=(32, 32),
        missing_policy="skip",
        algorithm_version="test-v1",
    )

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    schema_path = Path(__file__).parents[1] / "schemas" / "roi-manifest.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(manifest)
    first, second = manifest["records"]
    assert Path(first["source_path"]) == source.resolve()
    assert first["array_id"] == "array-001" and (first["row"], first["col"]) == (0, 0)
    assert Path(first["output_path"]).exists()
    assert first["status"] == "ok"
    assert second["status"] == "skipped" and second["output_path"] is None
    assert Path(result["overlay_path"]).exists()
