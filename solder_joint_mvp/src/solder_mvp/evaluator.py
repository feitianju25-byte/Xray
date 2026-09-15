from __future__ import annotations

import math
from typing import Iterable


def _metric(value: float | None, numerator: int, denominator: int, unavailable_reason: str | None = None) -> dict:
    return {
        "available": value is not None,
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "unavailable_reason": unavailable_reason if value is None else None,
    }


def evaluate_family_predictions(predictions: Iterable[dict], truth: Iterable[dict]) -> dict:
    prediction_by_id = {item["sample_id"]: item for item in predictions}
    truth_by_id = {item["sample_id"]: item for item in truth}
    predicted_keep = {
        sample_id
        for sample_id, item in prediction_by_id.items()
        if item.get("decision", item.get("suggested_decision")) == "keep"
    }
    true_keep = {sample_id for sample_id, item in truth_by_id.items() if item.get("decision") == "keep"}
    true_other = {sample_id for sample_id, item in truth_by_id.items() if item.get("decision") == "other_component"}
    true_positive = len(predicted_keep & true_keep)
    false_positive = sorted(predicted_keep - true_keep)
    other_mixed = len(predicted_keep & true_other)
    precision = true_positive / len(predicted_keep) if predicted_keep else None
    contamination = other_mixed / len(predicted_keep) if predicted_keep else None
    recall = true_positive / len(true_keep) if true_keep else None
    return {
        "target_family_precision": _metric(
            precision, true_positive, len(predicted_keep), "no predicted keep samples" if precision is None else None
        ),
        "target_family_recall": _metric(recall, true_positive, len(true_keep), "no confirmed keep samples" if recall is None else None),
        "other_component_contamination": _metric(
            contamination, other_mixed, len(predicted_keep), "no predicted keep samples" if contamination is None else None
        ),
        "false_positive_sample_ids": false_positive,
        "missing_prediction_sample_ids": sorted(set(truth_by_id) - set(prediction_by_id)),
    }


def evaluate_center_localization(
    predicted_centers: Iterable[Iterable[float]],
    truth_centers: Iterable[Iterable[float]],
    grid_spacing: float,
    tolerance_ratio: float = 0.25,
) -> dict:
    predicted = [tuple(float(value) for value in center) for center in predicted_centers]
    truth = [tuple(float(value) for value in center) for center in truth_centers]
    if not truth:
        return {
            "center_recall": _metric(None, 0, 0, "no verified truth centers"),
            "relative_localization_error": _metric(None, 0, 0, "no verified truth centers"),
            "matched_pairs": [],
            "tolerance_ratio": tolerance_ratio,
        }
    if grid_spacing <= 0:
        raise ValueError("grid_spacing must be positive")
    tolerance = grid_spacing * tolerance_ratio
    pairs = sorted(
        (
            math.hypot(predicted_x - truth_x, predicted_y - truth_y),
            predicted_index,
            truth_index,
        )
        for predicted_index, (predicted_x, predicted_y) in enumerate(predicted)
        for truth_index, (truth_x, truth_y) in enumerate(truth)
    )
    used_predicted: set[int] = set()
    used_truth: set[int] = set()
    matched = []
    for distance, predicted_index, truth_index in pairs:
        if distance > tolerance:
            break
        if predicted_index in used_predicted or truth_index in used_truth:
            continue
        used_predicted.add(predicted_index)
        used_truth.add(truth_index)
        matched.append(
            {
                "predicted_index": predicted_index,
                "truth_index": truth_index,
                "distance_pixels": distance,
                "distance_over_grid_spacing": distance / grid_spacing,
            }
        )
    recall = len(matched) / len(truth)
    relative_error = sum(pair["distance_over_grid_spacing"] for pair in matched) / len(matched) if matched else None
    return {
        "center_recall": _metric(recall, len(matched), len(truth)),
        "relative_localization_error": _metric(
            relative_error,
            len(matched),
            len(matched),
            "no centers matched within tolerance" if relative_error is None else None,
        ),
        "matched_pairs": matched,
        "tolerance_ratio": tolerance_ratio,
    }


def evaluate_usable_rois(records: Iterable[dict]) -> dict:
    records = list(records)
    usable = sum(record.get("status") == "ok" for record in records)
    ratio = usable / len(records) if records else None
    return {
        "usable_roi_ratio": _metric(ratio, usable, len(records), "no ROI records" if ratio is None else None),
        "failed_roi_ids": [record.get("roi_id") for record in records if record.get("status") != "ok"],
    }


def evaluate_mvp(
    predictions: Iterable[dict],
    truth: Iterable[dict],
    predicted_centers: Iterable[Iterable[float]],
    truth_centers: Iterable[Iterable[float]],
    grid_spacing: float,
    roi_records: Iterable[dict],
    tolerance_ratio: float = 0.25,
) -> dict:
    return {
        "family": evaluate_family_predictions(predictions, truth),
        "centers": evaluate_center_localization(
            predicted_centers, truth_centers, grid_spacing=grid_spacing, tolerance_ratio=tolerance_ratio
        ),
        "rois": evaluate_usable_rois(roi_records),
        "metric_config": {"center_tolerance_ratio": tolerance_ratio, "distance_normalizer": "grid_spacing"},
    }
