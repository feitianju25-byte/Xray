from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageOps


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32, copy=False)
    low, high = np.percentile(values, [2, 98])
    if high - low < 1e-6:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def load_gray(path: str | Path, size: int = 64) -> tuple[np.ndarray, float]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        gray = ImageOps.grayscale(image)
        fitted = ImageOps.fit(gray, (size, size), method=Image.Resampling.BILINEAR)
        values = np.asarray(fitted, dtype=np.float32)
    return _normalize(values), width / max(height, 1)


def perceptual_hash(path: str | Path, hash_size: int = 16) -> str:
    with Image.open(path) as image:
        gray = ImageOps.grayscale(ImageOps.exif_transpose(image))
        resized = ImageOps.fit(
            gray,
            (hash_size + 1, hash_size),
            method=Image.Resampling.BILINEAR,
        )
        pixels = np.asarray(resized, dtype=np.int16)
    differences = pixels[:, 1:] >= pixels[:, :-1]
    packed = np.packbits(differences.reshape(-1).astype(np.uint8))
    return packed.tobytes().hex()


def hash_distance(first: str, second: str) -> int:
    if len(first) != len(second):
        raise ValueError("hashes must have the same length")
    return (int(first, 16) ^ int(second, 16)).bit_count()


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first: int, second: int) -> None:
        root_first = self.find(first)
        root_second = self.find(second)
        if root_first != root_second:
            self.parent[max(root_first, root_second)] = min(root_first, root_second)


def assign_duplicate_groups(records: Iterable[dict], threshold: int = 10) -> list[dict]:
    enriched = [dict(record) for record in records]
    hashes: list[str | None] = []
    for record in enriched:
        try:
            value = perceptual_hash(record["absolute_path"])
        except (OSError, ValueError):
            value = None
        hashes.append(value)
        record["visual_hash"] = value

    groups = _DisjointSet(len(enriched))
    # Sixteen 16-bit bands guarantee at least one shared band for hashes whose
    # Hamming distance is <= 15, while avoiding an all-pairs scan.
    band_indexes: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(16)]
    for index, value in enumerate(hashes):
        if value is None:
            continue
        integer = int(value, 16)
        for band in range(16):
            key = (integer >> (band * 16)) & 0xFFFF
            for other in band_indexes[band][key]:
                other_hash = hashes[other]
                if other_hash is not None and hash_distance(value, other_hash) <= threshold:
                    groups.union(index, other)
            band_indexes[band][key].append(index)

    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(enriched)):
        members[groups.find(index)].append(index)

    for indexes in members.values():
        representative_index = min(indexes, key=lambda item: enriched[item]["sample_id"])
        representative = enriched[representative_index]
        group_seed = representative["sample_id"]
        group_id = "dup-" + hashlib.sha256(group_seed.encode("utf-8")).hexdigest()[:12]
        representative_hash = hashes[representative_index]
        for index in indexes:
            enriched[index]["duplicate_group"] = group_id
            enriched[index]["duplicate_representative"] = index == representative_index
            enriched[index]["duplicate_group_size"] = len(indexes)
            enriched[index]["duplicate_distance"] = (
                hash_distance(hashes[index], representative_hash)
                if hashes[index] is not None and representative_hash is not None
                else None
            )
    return enriched


def _unit_vector(values: np.ndarray) -> np.ndarray:
    flattened = values.astype(np.float32, copy=False).reshape(-1)
    flattened = flattened - float(flattened.mean())
    norm = float(np.linalg.norm(flattened))
    return flattened / norm if norm > 1e-8 else np.zeros_like(flattened)


def _edge_map(values: np.ndarray) -> np.ndarray:
    dx = np.zeros_like(values)
    dy = np.zeros_like(values)
    dx[:, 1:] = np.abs(values[:, 1:] - values[:, :-1])
    dy[1:, :] = np.abs(values[1:, :] - values[:-1, :])
    return _normalize(dx + dy)


def _periodicity(values: np.ndarray, bins: int = 16) -> np.ndarray:
    row_projection = values.mean(axis=1)
    column_projection = values.mean(axis=0)
    row_spectrum = np.abs(np.fft.rfft(row_projection - row_projection.mean()))[1 : bins + 1]
    column_spectrum = np.abs(np.fft.rfft(column_projection - column_projection.mean()))[1 : bins + 1]
    return _unit_vector(np.concatenate([row_spectrum, column_spectrum]))


def descriptor_from_array(values: np.ndarray, aspect_ratio: float) -> dict[str, np.ndarray | float]:
    size = values.shape[0]
    margin = max(1, round(size * 0.16))
    center = values[margin:-margin, margin:-margin]
    return {
        "whole": _unit_vector(values),
        "center": _unit_vector(center),
        "edge": _unit_vector(_edge_map(values)),
        "periodicity": _periodicity(center),
        "aspect_ratio": float(aspect_ratio),
    }


def image_descriptors(path: str | Path, size: int = 64) -> list[dict[str, np.ndarray | float]]:
    values, aspect_ratio = load_gray(path, size=size)
    descriptors = []
    for quarter_turns in range(4):
        rotated = np.rot90(values, quarter_turns)
        rotated_aspect = aspect_ratio if quarter_turns % 2 == 0 else 1.0 / max(aspect_ratio, 1e-8)
        descriptor = descriptor_from_array(rotated, rotated_aspect)
        descriptor["rotation_degrees"] = quarter_turns * 90.0
        descriptors.append(descriptor)
    return descriptors


def _cosine(first: np.ndarray, second: np.ndarray) -> float:
    if not np.any(first) or not np.any(second):
        return 0.0
    return float(np.clip(np.dot(first, second), -1.0, 1.0) * 0.5 + 0.5)


def compare_descriptors(reference: dict, candidate: dict) -> tuple[float, dict[str, float]]:
    aspect_difference = abs(np.log(max(float(candidate["aspect_ratio"]), 1e-8) / max(float(reference["aspect_ratio"]), 1e-8)))
    components = {
        "whole": _cosine(reference["whole"], candidate["whole"]),
        "center": _cosine(reference["center"], candidate["center"]),
        "edge": _cosine(reference["edge"], candidate["edge"]),
        "periodicity": _cosine(reference["periodicity"], candidate["periodicity"]),
        "aspect": float(np.exp(-2.0 * aspect_difference)),
    }
    score = (
        0.38 * components["whole"]
        + 0.26 * components["center"]
        + 0.16 * components["edge"]
        + 0.15 * components["periodicity"]
        + 0.05 * components["aspect"]
    )
    return float(np.clip(score, 0.0, 1.0)), components


def target_family_score(reference_path: str | Path, candidate_path: str | Path) -> dict:
    reference = image_descriptors(reference_path)[0]
    candidates = image_descriptors(candidate_path)
    comparisons = [compare_descriptors(reference, candidate) for candidate in candidates]
    best_index = max(range(len(comparisons)), key=lambda index: comparisons[index][0])
    score, components = comparisons[best_index]
    return {
        "family_score": score,
        "score_components": components,
        "best_rotation_degrees": int(candidates[best_index]["rotation_degrees"]),
    }

