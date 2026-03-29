from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_DB, build_critic_agent, build_memory_agent, print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug chapter critique.")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--book-id", required=True, help="Book id to critique.")
    parser.add_argument("--show-patch", action="store_true", help="Also print the first patch instruction.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    memory = build_memory_agent(args.db)
    critic = build_critic_agent()
    book = memory.load_book(args.book_id)
    if book is None:
        raise ValueError(f"Book not found: {args.book_id}")

    report = critic.review_book(book=book)
    memory.save_critic_report(report)

    payload: dict[str, object] = {
        "agent": "CriticAgent",
        "book_id": book.id,
        "report_id": report.report_id,
        "issue_count": len(report.issues),
        "issues": [issue.model_dump(mode="json") for issue in report.issues],
    }
    if args.show_patch and report.issues:
        payload["patch_instruction"] = critic.build_patch_instruction(report.issues[0]).model_dump(mode="json")
    print_json(payload)


if __name__ == "__main__":
    main()
