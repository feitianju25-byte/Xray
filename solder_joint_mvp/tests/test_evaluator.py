from __future__ import annotations

import pytest

from solder_mvp.evaluator import (
    evaluate_center_localization,
    evaluate_family_predictions,
    evaluate_mvp,
    evaluate_usable_rois,
)


def test_known_family_center_and_roi_metrics() -> None:
    truth = [
        {"sample_id": "a", "decision": "keep"},
        {"sample_id": "b", "decision": "keep"},
        {"sample_id": "c", "decision": "keep"},
        {"sample_id": "d", "decision": "other_component"},
        {"sample_id": "e", "decision": "reject"},
    ]
    predictions = [
        {"sample_id": "a", "decision": "keep"},
        {"sample_id": "b", "decision": "keep"},
        {"sample_id": "c", "decision": "reject"},
        {"sample_id": "d", "decision": "keep"},
        {"sample_id": "e", "decision": "reject"},
    ]
    family = evaluate_family_predictions(predictions, truth)
    assert family["target_family_precision"]["value"] == pytest.approx(2 / 3)
    assert family["target_family_recall"]["value"] == pytest.approx(2 / 3)
    assert family["other_component_contamination"]["value"] == pytest.approx(1 / 3)
    assert family["false_positive_sample_ids"] == ["d"]

    centers = evaluate_center_localization([(1, 0), (22, 0), (100, 100)], [(0, 0), (20, 0), (40, 0)], 20, 0.25)
    assert centers["center_recall"]["value"] == pytest.approx(2 / 3)
    assert centers["relative_localization_error"]["value"] == pytest.approx(0.075)

    rois = evaluate_usable_rois(
        [{"roi_id": "1", "status": "ok"}, {"roi_id": "2", "status": "ok"}, {"roi_id": "3", "status": "skipped"}]
    )
    assert rois["usable_roi_ratio"]["value"] == pytest.approx(2 / 3)
    assert rois["failed_roi_ids"] == ["3"]


def test_missing_human_validation_is_reported_as_unavailable_not_zero() -> None:
    report = evaluate_mvp([], [], [], [], 20, [])
    assert report["family"]["target_family_precision"]["value"] is None
    assert report["family"]["target_family_precision"]["available"] is False
    assert report["centers"]["center_recall"]["value"] is None
    assert report["rois"]["usable_roi_ratio"]["value"] is None
