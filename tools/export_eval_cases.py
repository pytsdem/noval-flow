from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.romance.case_exporter import HistoricalCaseExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export standardized historical chapter cases for eval and self-improvement.")
    parser.add_argument("--source", default="db", choices=["db"], help="Historical case source.")
    parser.add_argument("--db", default="data/novel_flow.db", help="SQLite database path.")
    parser.add_argument("--output-dir", default="evals/romance/exported_cases/latest", help="Output directory for exported case JSON files.")
    parser.add_argument("--limit", type=int, default=20, help="Number of cases to export.")
    parser.add_argument(
        "--sample-mode",
        "--mode",
        dest="sample_mode",
        default="latest",
        choices=["latest", "low_score", "high_cost", "tagged"],
        help="Sampling strategy used to select historical cases.",
    )
    parser.add_argument("--book-id", default="", help="Optional book id filter.")
    parser.add_argument("--chapter-id", default="", help="Optional chapter id filter.")
    parser.add_argument("--run-id", default="", help="Optional run id filter.")
    parser.add_argument("--tags", nargs="*", default=None, help="Optional tag filters used with tagged sampling.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.source != "db":
        raise ValueError(f"Unsupported source: {args.source}")
    exporter = HistoricalCaseExporter(args.db)
    summary = exporter.export(
        output_dir=Path(args.output_dir),
        limit=args.limit,
        sample_mode=args.sample_mode,
        book_id=args.book_id or None,
        chapter_id=args.chapter_id or None,
        run_id=args.run_id or None,
        tags=args.tags,
    )
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
