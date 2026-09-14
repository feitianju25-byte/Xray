from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contact_sheet import render_contact_sheet, save_review_csv, save_review_manifest
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

    sheet_parser = subparsers.add_parser("contact-sheet", help="Render candidates and initialize review JSON")
    sheet_parser.add_argument("--manifest", type=Path, required=True)
    sheet_parser.add_argument("--output", type=Path, required=True)
    sheet_parser.add_argument("--review-output", type=Path, required=True)
    sheet_parser.add_argument("--review-csv", type=Path)
    sheet_parser.add_argument("--columns", type=int, default=5)

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
    raise AssertionError(f"unhandled command: {args.command}")
