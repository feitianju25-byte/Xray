from __future__ import annotations

from PIL import Image

from solder_mvp.roi_exporter import crop_normalized_roi, extract_grid_rois


def test_normal_and_padded_edge_rois_have_identical_output_size() -> None:
    image = Image.new("L", (80, 60), 100)
    normal = crop_normalized_roi(image, (40, 30), (20, 22), output_size=(32, 32), boundary_policy="pad")
    edge = crop_normalized_roi(image, (2, 2), (20, 22), output_size=(32, 32), boundary_policy="pad")

    assert normal.image is not None and normal.image.size == (32, 32)
    assert edge.image is not None and edge.image.size == (32, 32)
    assert normal.metadata["padded"] is False
    assert edge.metadata["padded"] is True
    assert edge.metadata["status"] == "ok"


def test_out_of_bounds_and_missing_positions_can_be_skipped() -> None:
    image = Image.new("L", (50, 50), 120)
    edge = crop_normalized_roi(image, (1, 1), (20, 20), output_size=(24, 24), boundary_policy="skip")
    assert edge.image is None
    assert edge.metadata["status"] == "skipped_out_of_bounds"

    grid = {
        "column_spacing": 20.0,
        "row_spacing": 20.0,
        "cells": [
            {"row": 0, "col": 0, "x": 25.0, "y": 25.0, "status": "observed"},
            {"row": 0, "col": 1, "x": 45.0, "y": 25.0, "status": "missing"},
        ],
    }
    rois = extract_grid_rois(image, grid, output_size=(24, 24), missing_policy="skip")
    assert rois[0].image is not None and rois[0].image.size == (24, 24)
    assert rois[1].image is None
    assert rois[1].metadata["status"] == "skipped_missing"


def test_missing_position_can_be_extracted_for_anomaly_input() -> None:
    image = Image.new("L", (70, 70), 140)
    grid = {
        "column_spacing": 18.0,
        "row_spacing": 18.0,
        "cells": [{"row": 1, "col": 2, "x": 35.0, "y": 35.0, "status": "missing"}],
    }
    rois = extract_grid_rois(image, grid, output_size=(28, 28), missing_policy="extract")
    assert rois[0].image is not None and rois[0].image.size == (28, 28)
    assert rois[0].metadata["grid_status"] == "missing"
