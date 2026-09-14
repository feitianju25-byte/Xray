#!/usr/bin/env python3
"""Draw predicted and ground-truth rotated ellipses for PCB X-ray results."""

import argparse
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont


DEFAULT_DATASET_JSON = Path("/Qwen3.6/LlamaFactory/data/pcb_xray_test.json")
DEFAULT_RESULTS_DIR = Path("/Qwen3.6/Test2/results")
TYPE_COLORS = {
    "多余物": (230, 57, 70),
    "焊点少锡": (29, 112, 184),
    "焊点桥连": (42, 157, 143),
    "焊点空洞": (131, 56, 236),
    "过锡不良": (244, 162, 97),
}
ASCII_LABELS = {
    "多余物": "foreign_object",
    "焊点少锡": "insufficient_solder",
    "焊点桥连": "solder_bridge",
    "焊点空洞": "solder_void",
    "过锡不良": "excess_solder",
}
FONT_CANDIDATES = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
)


def write_json(value: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ellipse_points(ellipse: dict[str, Any], segments: int = 72) -> list[tuple[float, float]]:
    center_x = float(ellipse["center_x"])
    center_y = float(ellipse["center_y"])
    radius_x = float(ellipse["diameter_x"]) / 2
    radius_y = float(ellipse["diameter_y"]) / 2
    angle = math.radians(float(ellipse["angle"]))
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    points = []
    for index in range(segments):
        theta = 2 * math.pi * index / segments
        x = radius_x * math.cos(theta)
        y = radius_y * math.sin(theta)
        points.append(
            (
                round(center_x + x * cos_angle - y * sin_angle, 6),
                round(center_y + x * sin_angle + y * cos_angle, 6),
            )
        )
    return points


def ellipse_iou(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_points = ellipse_points(first, segments=180)
    second_points = ellipse_points(second, segments=180)
    all_points = first_points + second_points
    left = math.floor(min(point[0] for point in all_points))
    top = math.floor(min(point[1] for point in all_points))
    right = math.ceil(max(point[0] for point in all_points))
    bottom = math.ceil(max(point[1] for point in all_points))
    size = (max(1, right - left + 1), max(1, bottom - top + 1))

    masks = []
    for points in (first_points, second_points):
        mask = Image.new("1", size, 0)
        shifted = [(x - left, y - top) for x, y in points]
        ImageDraw.Draw(mask).polygon(shifted, fill=1)
        masks.append(mask)

    intersection = ImageChops.logical_and(masks[0], masks[1])
    union = ImageChops.logical_or(masks[0], masks[1])
    intersection_area = intersection.histogram()[255]
    union_area = union.histogram()[255]
    return intersection_area / union_area if union_area else 0.0


def match_annotations(
    prediction: dict[str, Any] | None,
    ground_truth: dict[str, Any],
    iou_threshold: float,
) -> list[float]:
    if prediction is None or prediction.get("defect_type") != ground_truth.get("defect_type"):
        return []

    predicted = prediction.get("ellipses", [])
    expected = ground_truth.get("ellipses", [])
    overlaps = [[ellipse_iou(pred, truth) for truth in expected] for pred in predicted]
    adjacency = [
        sorted(
            ((overlap, truth_index) for truth_index, overlap in enumerate(row) if overlap >= iou_threshold),
            reverse=True,
        )
        for row in overlaps
    ]
    truth_matches: dict[int, int] = {}

    def find_match(prediction_index: int, visited: set[int]) -> bool:
        for _, truth_index in adjacency[prediction_index]:
            if truth_index in visited:
                continue
            visited.add(truth_index)
            previous = truth_matches.get(truth_index)
            if previous is None or find_match(previous, visited):
                truth_matches[truth_index] = prediction_index
                return True
        return False

    for prediction_index in range(len(predicted)):
        find_match(prediction_index, set())

    return [overlaps[prediction_index][truth_index] for truth_index, prediction_index in truth_matches.items()]


def evaluate_records(
    records: list[dict[str, Any]],
    ground_truth: dict[str, tuple[Path, dict[str, Any]]],
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    ground_truth_count = 0
    prediction_count = 0
    matched_ious = []
    parse_failures = 0
    class_correct_images = 0
    correctly_detected_images = 0
    per_image = []
    seen_ids = set()

    for record in records:
        sample_id = record["sample_id"]
        if sample_id in seen_ids:
            raise ValueError(f"Duplicate prediction sample id: {sample_id}")
        if sample_id not in ground_truth:
            raise KeyError(f"Prediction sample not found in test dataset: {sample_id}")
        seen_ids.add(sample_id)

        expected = ground_truth[sample_id][1]
        prediction = record.get("prediction")
        expected_count = len(expected.get("ellipses", []))
        predicted_count = len(prediction.get("ellipses", [])) if prediction is not None else 0
        image_ious = match_annotations(prediction, expected, iou_threshold)
        class_correct = prediction is not None and prediction.get("defect_type") == expected.get("defect_type")
        if record.get("parse_failed", prediction is None):
            parse_failures += 1
        if class_correct:
            class_correct_images += 1
        if image_ious:
            correctly_detected_images += 1

        ground_truth_count += expected_count
        prediction_count += predicted_count
        matched_ious.extend(image_ious)
        per_image.append(
            {
                "sample_id": sample_id,
                "class_correct": class_correct,
                "ground_truth_ellipses": expected_count,
                "predicted_ellipses": predicted_count,
                "matched_ellipses": len(image_ious),
                "accuracy": len(image_ious) / expected_count if expected_count else 0.0,
                "matched_ious": image_ious,
            }
        )

    matched_count = len(matched_ious)
    accuracy = matched_count / ground_truth_count if ground_truth_count else 0.0
    precision = matched_count / prediction_count if prediction_count else 0.0
    recall = accuracy
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "iou_threshold": iou_threshold,
        "evaluated_images": len(records),
        "parse_failures": parse_failures,
        "class_correct_images": class_correct_images,
        "correctly_detected_images": correctly_detected_images,
        "ground_truth_ellipses": ground_truth_count,
        "predicted_ellipses": prediction_count,
        "matched_ellipses": matched_count,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_matched_iou": sum(matched_ious) / matched_count if matched_count else 0.0,
        "per_image": per_image,
    }


def load_font(font_path: Path | None, size: int = 22) -> tuple[Any, bool]:
    candidates = ([font_path] if font_path is not None else []) + list(FONT_CANDIDATES)
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return ImageFont.truetype(candidate.as_posix(), size=size), True
    return ImageFont.load_default(), False


def draw_annotation(
    image_path: Path,
    annotation: dict[str, Any] | None,
    output_path: Path,
    title: str,
    font_path: Path | None = None,
) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font, supports_chinese = load_font(font_path)
    if annotation is not None:
        defect_type = str(annotation.get("defect_type", "unknown"))
        color = TYPE_COLORS.get(defect_type, (255, 0, 0))
        label = defect_type if supports_chinese else ASCII_LABELS.get(defect_type, defect_type)
        for ellipse in annotation.get("ellipses", []):
            points = ellipse_points(ellipse)
            draw.line(points + [points[0]], fill=color, width=5)
            label_x = max(0, int(float(ellipse["center_x"]) - float(ellipse["diameter_x"]) / 2))
            label_y = max(0, int(float(ellipse["center_y"]) - float(ellipse["diameter_y"]) / 2) - 25)
            draw.text((label_x, label_y), label, fill=color, font=font, stroke_width=1, stroke_fill=(0, 0, 0))
    draw.text((8, 8), title, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def read_ground_truth(dataset_json: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    records = json.loads(dataset_json.read_text(encoding="utf-8"))
    index = {}
    for record in records:
        image_path = Path(record["images"][0])
        sample_id = image_path.stem
        if sample_id in index:
            raise ValueError(f"Duplicate test sample id: {sample_id}")
        annotation = json.loads(record["messages"][1]["content"])
        index[sample_id] = (image_path, annotation)
    return index


def render_results(
    dataset_json: Path,
    results_dir: Path,
    font_path: Path | None = None,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    ground_truth = read_ground_truth(dataset_json)
    rendered: dict[str, int] = {}
    model_metrics = {}
    inferred_ids = set()
    for model_name in ("before_lora", "after_lora"):
        predictions_path = results_dir / model_name / "predictions.json"
        if not predictions_path.is_file():
            continue
        records = json.loads(predictions_path.read_text(encoding="utf-8"))
        model_metrics[model_name] = evaluate_records(records, ground_truth, iou_threshold)
        count = 0
        for record in records:
            sample_id = record["sample_id"]
            if sample_id not in ground_truth:
                raise KeyError(f"Prediction sample not found in test dataset: {sample_id}")
            image_path, _ = ground_truth[sample_id]
            draw_annotation(
                image_path,
                record.get("prediction"),
                results_dir / model_name / "images" / f"{sample_id}.jpg",
                model_name,
                font_path,
            )
            inferred_ids.add(sample_id)
            count += 1
        rendered[model_name] = count

    ground_truth_dir = results_dir / "ground_truth"
    for sample_id in sorted(inferred_ids):
        image_path, annotation = ground_truth[sample_id]
        write_json(annotation, ground_truth_dir / "json" / f"{sample_id}.json")
        draw_annotation(
            image_path,
            annotation,
            ground_truth_dir / "images" / f"{sample_id}.jpg",
            "ground_truth",
            font_path,
        )
    rendered["ground_truth"] = len(inferred_ids)
    summary = {
        "dataset_json": dataset_json.as_posix(),
        "results_dir": results_dir.as_posix(),
        "rendered": rendered,
        "metrics_file": (results_dir / "metrics.json").as_posix(),
    }
    metrics = {
        "definition": "class matches and rotated ellipse IoU is at least the threshold",
        "accuracy_definition": "matched_ellipses / ground_truth_ellipses",
        "iou_threshold": iou_threshold,
        "models": model_metrics,
    }
    write_json(metrics, results_dir / "metrics.json")
    write_json(summary, ground_truth_dir / "summary.json")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draw PCB X-ray ellipse predictions and ground truth.")
    parser.add_argument("--dataset-json", type=Path, default=DEFAULT_DATASET_JSON)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--font", type=Path, default=None, help="Optional CJK TrueType/OpenType font.")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = render_results(args.dataset_json, args.results_dir, args.font, args.iou_threshold)
    print(f"Drawing complete: {json.dumps(summary['rendered'], ensure_ascii=False)}")
    print(f"Results saved to {args.results_dir}")


if __name__ == "__main__":
    main()
