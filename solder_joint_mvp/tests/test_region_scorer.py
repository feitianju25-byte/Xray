from __future__ import annotations

import random

from solder_mvp.region_scorer import score_candidate_region


def _candidates(points: list[tuple[float, float]], radius: float = 7.0) -> list[dict]:
    return [{"x": x, "y": y, "radius": radius, "response": 0.9} for x, y in points]


def test_target_grid_scores_above_connector_random_and_linear_layouts() -> None:
    target = _candidates([(55 + column * 25, 48 + row * 28) for row in range(4) for column in range(5)])
    connector = _candidates([(30 + column * 16, 75 + row * 16) for row in range(2) for column in range(10)])
    linear = _candidates([(30 + index * 16, 90) for index in range(10)])
    randomizer = random.Random(20260915)
    random_points = _candidates([(randomizer.uniform(25, 175), randomizer.uniform(25, 155)) for _ in range(20)])
    bbox = (20.0, 20.0, 190.0, 165.0)

    target_score = score_candidate_region(target, (220, 190), bbox)
    negatives = [
        score_candidate_region(connector, (220, 190), bbox),
        score_candidate_region(linear, (220, 190), bbox),
        score_candidate_region(random_points, (220, 190), bbox),
    ]

    assert target_score["score"] > 0.70
    assert all(target_score["score"] > negative["score"] + 0.10 for negative in negatives)
    assert target_score["rejection_reasons"] == []
    assert "linear-or-narrow-layout" in negatives[0]["rejection_reasons"]
    assert "linear-or-narrow-layout" in negatives[1]["rejection_reasons"]
    assert "irregular-spacing" in negatives[2]["rejection_reasons"]


def test_points_on_package_border_are_penalized_as_other_structure() -> None:
    border = []
    for x in (25, 60, 95, 130, 165):
        border.extend([(x, 22), (x, 163)])
    for y in (55, 90, 125):
        border.extend([(22, y), (188, y)])

    result = score_candidate_region(_candidates(border), (220, 190), (20.0, 20.0, 190.0, 165.0))
    assert result["components"]["package"] < 0.65
    assert "package-or-view-mismatch" in result["rejection_reasons"]
