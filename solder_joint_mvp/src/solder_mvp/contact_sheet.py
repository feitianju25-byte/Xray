from __future__ import annotations

import csv
import io
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .io_utils import write_json


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _short_source(record: dict, max_chars: int = 38) -> str:
    source = f"{record['root_alias']}:{record['source_dir']}"
    return source if len(source) <= max_chars else "..." + source[-(max_chars - 3) :]


DECISIONS = {"keep", "other_component", "reject", "uncertain"}
DEFAULT_TARGET_FAMILY = "frontal-chip-internal-dot-grid-v1"


def apply_ranked_suggestions(sample: dict, suggestions: dict) -> dict:
    """Attach one reproducible suggested decision to every ranked sample record."""
    records = [dict(record) for record in sample.get("records", [])]
    by_rank = {int(record.get("sample_rank", index + 1)): record for index, record in enumerate(records)}
    assigned: dict[int, str] = {}
    for decision, ranks in suggestions.get("labels", {}).items():
        if decision not in DECISIONS:
            raise ValueError(f"unsupported suggestion decision: {decision}")
        for raw_rank in ranks:
            rank = int(raw_rank)
            if rank not in by_rank:
                raise ValueError(f"suggestion rank is not present in sample: {rank}")
            if rank in assigned:
                raise ValueError(f"suggestion rank appears more than once: {rank}")
            assigned[rank] = decision

    missing = sorted(set(by_rank) - set(assigned))
    if missing:
        raise ValueError(f"suggestions do not cover all sample ranks: {missing}")

    reasons = {int(rank): reason for rank, reason in suggestions.get("reasons", {}).items()}
    for rank, record in by_rank.items():
        record["suggested_decision"] = assigned[rank]
        record["suggestion_notes"] = reasons.get(rank, "Codex 初审；等待用户确认。")

    annotated = dict(sample)
    annotated["records"] = records
    annotated["suggestion_review"] = {
        "reviewer": suggestions.get("reviewer", "codex"),
        "reviewed_at": suggestions.get("reviewed_at"),
        "criteria": suggestions.get("criteria"),
    }
    return annotated


def apply_ranked_confirmations(sample: dict, review: dict, confirmations: dict) -> dict:
    """Merge a partial set of user-confirmed rank decisions into a review manifest."""
    records = sample.get("records", [])
    sample_id_by_rank = {
        int(record.get("sample_rank", index + 1)): record["sample_id"] for index, record in enumerate(records)
    }
    items_by_id = {item["sample_id"]: dict(item) for item in review.get("items", [])}
    assigned: set[int] = set()
    reviewed_at = confirmations.get("reviewed_at") or datetime.now(timezone.utc).isoformat()
    notes = {int(rank): note for rank, note in confirmations.get("notes", {}).items()}

    for decision, ranks in confirmations.get("labels", {}).items():
        if decision not in DECISIONS:
            raise ValueError(f"unsupported confirmation decision: {decision}")
        for raw_rank in ranks:
            rank = int(raw_rank)
            if rank in assigned:
                raise ValueError(f"confirmation rank appears more than once: {rank}")
            sample_id = sample_id_by_rank.get(rank)
            if sample_id is None or sample_id not in items_by_id:
                raise ValueError(f"confirmation rank is not present in review: {rank}")
            item = items_by_id[sample_id]
            item["decision"] = decision
            item["reviewed_at"] = reviewed_at
            if rank in notes:
                item["notes"] = notes[rank]
            items_by_id[sample_id] = item
            assigned.add(rank)

    merged = dict(review)
    merged["items"] = [items_by_id[item["sample_id"]] for item in review.get("items", [])]
    merged["confirmation_status"] = {
        "confirmed_count": len(assigned),
        "pending_ranks": [int(rank) for rank in confirmations.get("pending_ranks", [])],
        "reviewed_at": reviewed_at,
    }
    return merged


def _read_review_csv(csv_path: str | Path) -> tuple[list[dict], str]:
    payload = Path(csv_path).read_bytes()
    decode_errors = []
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError as error:
            decode_errors.append(f"{encoding}: {error}")
            continue
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
        if rows and "sample_id" in rows[0]:
            return rows, encoding
    raise ValueError(f"could not decode review CSV; attempts={decode_errors}")


def merge_review_csv(review: dict, csv_path: str | Path, reviewed_at: str | None = None) -> dict:
    """Strictly merge human decisions edited in the review CSV back into JSON.

    The JSON remains the canonical geometry record.  Only ``decision`` and
    ``notes`` are accepted from CSV, so spreadsheet round-trips cannot silently
    replace source paths, duplicate groups, scores, or algorithm metadata.
    """
    timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()
    rows, source_encoding = _read_review_csv(csv_path)

    items = review.get("items", [])
    items_by_id = {item["sample_id"]: dict(item) for item in items}
    if len(items_by_id) != len(items):
        raise ValueError("review JSON contains duplicate sample IDs")

    rows_by_id: dict[str, dict] = {}
    for row in rows:
        sample_id = (row.get("sample_id") or "").strip()
        if not sample_id:
            raise ValueError("review CSV contains an empty sample_id")
        if sample_id in rows_by_id:
            raise ValueError(f"review CSV contains duplicate sample_id: {sample_id}")
        rows_by_id[sample_id] = row

    missing = sorted(set(items_by_id) - set(rows_by_id))
    unexpected = sorted(set(rows_by_id) - set(items_by_id))
    if missing or unexpected:
        raise ValueError(f"review CSV sample mismatch; missing={missing}, unexpected={unexpected}")

    changed_count = 0
    merged_items = []
    pending_ranks = []
    for rank, original in enumerate(items, start=1):
        item = items_by_id[original["sample_id"]]
        row = rows_by_id[original["sample_id"]]
        decision = (row.get("decision") or "").strip().lower()
        if decision not in DECISIONS:
            raise ValueError(f"unsupported CSV decision for {original['sample_id']}: {decision!r}")
        if decision != item.get("decision"):
            changed_count += 1
            item["reviewed_at"] = timestamp
        item["decision"] = decision
        if "notes" in row:
            item["notes"] = row.get("notes") or ""
        if decision == "uncertain":
            pending_ranks.append(rank)
        merged_items.append(item)

    merged = dict(review)
    merged["items"] = merged_items
    merged["manual_csv_import"] = {
        "source": str(Path(csv_path).resolve()),
        "source_encoding": source_encoding,
        "imported_at": timestamp,
        "changed_count": changed_count,
        "decision_counts": {decision: sum(item["decision"] == decision for item in merged_items) for decision in sorted(DECISIONS)},
        "pending_ranks": pending_ranks,
    }
    return merged


def create_review_manifest(sample: dict, target_family: str | None = None) -> dict:
    family = target_family or sample.get("target_family") or DEFAULT_TARGET_FAMILY
    return {
        "schema_version": "1.0",
        "algorithm_version": sample.get("algorithm_version", "0.2.0"),
        "target_family": family,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instructions": "核对 suggested_decision，再将 decision 改为 keep、other_component、reject 或 uncertain；可选填写 array_bbox、rows、cols、corners、centers。",
        "items": [
            {
                "sample_id": record["sample_id"],
                "source_path": record["absolute_path"],
                "target_family": family,
                "family_score": record.get("family_score"),
                "duplicate_group": record.get("duplicate_group"),
                "duplicate_representative": record.get("duplicate_representative"),
                "suggested_decision": record.get("suggested_decision", "uncertain"),
                "decision": "uncertain",
                "reviewed_at": None,
                "array_bbox": None,
                "rows": None,
                "cols": None,
                "corners": [],
                "centers": [],
                "notes": record.get("suggestion_notes", ""),
                "algorithm_version": sample.get("algorithm_version", "0.2.0"),
            }
            for record in sample.get("records", [])
        ],
    }


def migrate_review_manifest(review: dict, sample: dict | None = None, target_family: str | None = None) -> dict:
    sample_by_id = {record["sample_id"]: record for record in (sample or {}).get("records", [])}
    family = target_family or review.get("target_family") or (sample or {}).get("target_family") or DEFAULT_TARGET_FAMILY
    migrated = dict(review)
    migrated["schema_version"] = "1.0"
    migrated["algorithm_version"] = (sample or {}).get("algorithm_version", review.get("algorithm_version", "0.2.0"))
    migrated["target_family"] = family
    migrated_items = []
    for original in review.get("items", []):
        item = dict(original)
        record = sample_by_id.get(item.get("sample_id"), {})
        previous = item.get("decision", "uncertain")
        item["decision"] = previous if previous in DECISIONS else "uncertain"
        item.setdefault("suggested_decision", previous if previous in DECISIONS else "uncertain")
        item["target_family"] = family
        item.setdefault("family_score", record.get("family_score"))
        item.setdefault("duplicate_group", record.get("duplicate_group"))
        item.setdefault("duplicate_representative", record.get("duplicate_representative"))
        item["algorithm_version"] = migrated["algorithm_version"]
        migrated_items.append(item)
    migrated["items"] = migrated_items
    return migrated


def render_contact_sheet(
    sample: dict,
    output_path: str | Path,
    columns: int = 5,
    thumbnail_size: tuple[int, int] = (320, 220),
    label_height: int = 58,
) -> Path:
    records = sample.get("records", [])
    if not records:
        raise ValueError("sample manifest contains no records")
    columns = max(1, columns)
    rows = math.ceil(len(records) / columns)
    cell_width, image_height = thumbnail_size
    cell_height = image_height + label_height
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = _font(18)
    body_font = _font(13)

    for index, record in enumerate(records):
        row, column = divmod(index, columns)
        x, y = column * cell_width, row * cell_height
        try:
            with Image.open(record["absolute_path"]) as image:
                tile = ImageOps.contain(image.convert("RGB"), thumbnail_size, Image.Resampling.LANCZOS)
            offset_x = x + (cell_width - tile.width) // 2
            offset_y = y + (image_height - tile.height) // 2
            sheet.paste(tile, (offset_x, offset_y))
        except OSError:
            draw.rectangle((x, y, x + cell_width - 1, y + image_height - 1), fill="#dddddd")
            draw.text((x + 8, y + 8), "IMAGE ERROR", fill="red", font=title_font)

        draw.rectangle((x, y, x + cell_width - 1, y + cell_height - 1), outline="#555555", width=1)
        label_y = y + image_height + 4
        display_rank = int(record.get("sample_rank", index + 1))
        draw.text((x + 6, label_y), f"#{display_rank:03d}  {record['sample_id']}", fill="black", font=title_font)
        score = record.get("family_score")
        group = record.get("duplicate_group") or "no-group"
        score_text = f"score={score:.4f}" if isinstance(score, (int, float)) else "score=n/a"
        draw.text((x + 6, label_y + 24), f"{score_text}  group={group[-8:]}", fill="#222266", font=body_font)
        draw.text((x + 6, label_y + 43), _short_source(record), fill="#333333", font=body_font)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=True)
    return destination


def render_contact_sheet_batches(
    sample: dict,
    output_dir: str | Path,
    batch_size: int = 40,
    columns: int = 5,
    thumbnail_size: tuple[int, int] = (320, 220),
    label_height: int = 78,
) -> list[Path]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    records = sample.get("records", [])
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for start in range(0, len(records), batch_size):
        batch_records = records[start : start + batch_size]
        batch = dict(sample)
        batch["records"] = batch_records
        first_rank = int(batch_records[0].get("sample_rank", start + 1))
        last_rank = int(batch_records[-1].get("sample_rank", start + len(batch_records)))
        output = destination / f"contact_sheet_{first_rank:03d}_{last_rank:03d}.png"
        outputs.append(
            render_contact_sheet(
                batch,
                output,
                columns=columns,
                thumbnail_size=thumbnail_size,
                label_height=label_height,
            )
        )
    return outputs


def save_review_manifest(sample: dict, output_path: str | Path) -> Path:
    return write_json(output_path, create_review_manifest(sample))


def save_review_csv(sample: dict, output_path: str | Path, review: dict | None = None) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "sample_id",
        "family_score",
        "duplicate_group",
        "suggested_decision",
        "decision",
        "source_path",
        "source_dir",
        "notes",
    ]
    reviewed_by_id = {item["sample_id"]: item for item in (review or {}).get("items", [])}
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, record in enumerate(sample.get("records", []), start=1):
            reviewed = reviewed_by_id.get(record["sample_id"], {})
            writer.writerow(
                {
                    "rank": rank,
                    "sample_id": record["sample_id"],
                    "family_score": record.get("family_score"),
                    "duplicate_group": record.get("duplicate_group"),
                    "suggested_decision": record.get("suggested_decision", "uncertain"),
                    "decision": reviewed.get("decision", "uncertain"),
                    "source_path": record["absolute_path"],
                    "source_dir": f"{record['root_alias']}:{record['source_dir']}",
                    "notes": reviewed.get("notes", record.get("suggestion_notes", "")),
                }
            )
    return destination
