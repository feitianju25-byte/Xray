from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contact_sheet import (
    apply_ranked_suggestions,
    render_contact_sheet,
    render_contact_sheet_batches,
    save_review_csv,
    save_review_manifest,
)
from .family_screen import rank_target_family, save_family_screen
from .inventory import save_inventory, scan_roots
from .io_utils import read_json
from .sampler import sample_inventory, save_sample


def _root_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("root must use ALIAS=PATH")
    alias, path = value.split("=", 1)
    if not alias.strip() or not path.strip():
        raise argparse.ArgumentTypeError("root must use non-empty ALIAS=PATH")
    return alias.strip(), Path(path.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solder-mvp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory", help="Scan image roots without copying images")
    inventory_parser.add_argument("--root", action="append", type=_root_spec, required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)

    sample_parser = subparsers.add_parser("sample", help="Create a deterministic stratified sample")
    sample_parser.add_argument("--manifest", type=Path, required=True)
    sample_parser.add_argument("--output", type=Path, required=True)
    sample_parser.add_argument("--limit", type=int, default=40)
    sample_parser.add_argument("--seed", type=int, default=20260914)
    sample_parser.add_argument("--include")
    sample_parser.add_argument("--reference", type=Path)

    screen_parser = subparsers.add_parser("screen-family", help="Rank candidates against a target component family")
    screen_parser.add_argument("--manifest", type=Path, required=True)
    screen_parser.add_argument("--output", type=Path, required=True)
    screen_parser.add_argument("--reference", type=Path, required=True)
    screen_parser.add_argument("--target-family", default="frontal-chip-internal-dot-grid-v1")
    screen_parser.add_argument("--limit", type=int, default=120)
    screen_parser.add_argument("--seed", type=int, default=20260915)
    screen_parser.add_argument("--include")
    screen_parser.add_argument("--duplicate-threshold", type=int, default=10)
    screen_parser.add_argument("--max-per-duplicate-group", type=int, default=1)

    sheet_parser = subparsers.add_parser("contact-sheet", help="Render candidates and initialize review JSON")
    sheet_parser.add_argument("--manifest", type=Path, required=True)
    sheet_parser.add_argument("--output", type=Path, required=True)
    sheet_parser.add_argument("--review-output", type=Path, required=True)
    sheet_parser.add_argument("--review-csv", type=Path)
    sheet_parser.add_argument("--columns", type=int, default=5)

    sheets_parser = subparsers.add_parser("contact-sheets", help="Render ranked candidates in review batches")
    sheets_parser.add_argument("--manifest", type=Path, required=True)
    sheets_parser.add_argument("--output-dir", type=Path, required=True)
    sheets_parser.add_argument("--review-output", type=Path, required=True)
    sheets_parser.add_argument("--review-csv", type=Path, required=True)
    sheets_parser.add_argument("--batch-size", type=int, default=40)
    sheets_parser.add_argument("--columns", type=int, default=5)

    suggestions_parser = subparsers.add_parser(
        "apply-suggestions", help="Apply a complete rank-to-label suggestion set to review outputs"
    )
    suggestions_parser.add_argument("--manifest", type=Path, required=True)
    suggestions_parser.add_argument("--suggestions", type=Path, required=True)
    suggestions_parser.add_argument("--review-output", type=Path, required=True)
    suggestions_parser.add_argument("--review-csv", type=Path, required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        result = scan_roots(args.root)
        save_inventory(result, args.output)
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "sample":
        result = sample_inventory(
            read_json(args.manifest),
            limit=args.limit,
            seed=args.seed,
            include_path_pattern=args.include,
            reference_path=args.reference,
        )
        save_sample(result, args.output)
        print(json.dumps(result["sampling"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "screen-family":
        result = rank_target_family(
            read_json(args.manifest),
            reference_path=args.reference,
            limit=args.limit,
            seed=args.seed,
            include_path_pattern=args.include,
            duplicate_threshold=args.duplicate_threshold,
            max_per_duplicate_group=args.max_per_duplicate_group,
            target_family=args.target_family,
        )
        save_family_screen(result, args.output)
        print(json.dumps(result["screening"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "contact-sheet":
        sample = read_json(args.manifest)
        sheet = render_contact_sheet(sample, args.output, columns=args.columns)
        review = save_review_manifest(sample, args.review_output)
        review_csv = save_review_csv(sample, args.review_csv) if args.review_csv else None
        print(
            json.dumps(
                {
                    "contact_sheet": str(sheet),
                    "review": str(review),
                    "review_csv": str(review_csv) if review_csv else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "contact-sheets":
        sample = read_json(args.manifest)
        sheets = render_contact_sheet_batches(
            sample,
            args.output_dir,
            batch_size=args.batch_size,
            columns=args.columns,
        )
        review = save_review_manifest(sample, args.review_output)
        review_csv = save_review_csv(sample, args.review_csv)
        print(
            json.dumps(
                {
                    "contact_sheets": [str(path) for path in sheets],
                    "review": str(review),
                    "review_csv": str(review_csv),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "apply-suggestions":
        annotated = apply_ranked_suggestions(read_json(args.manifest), read_json(args.suggestions))
        review = save_review_manifest(annotated, args.review_output)
        review_csv = save_review_csv(annotated, args.review_csv)
        counts = {decision: 0 for decision in ("keep", "other_component", "reject", "uncertain")}
        for record in annotated["records"]:
            counts[record["suggested_decision"]] += 1
        print(
            json.dumps(
                {"review": str(review), "review_csv": str(review_csv), "suggestion_counts": counts},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
