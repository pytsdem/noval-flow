from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_DB, DEFAULT_QUERY, build_master_agent, print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug MasterAgent.")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start a new novel and write the first chapter.")
    start.add_argument("--query", default=DEFAULT_QUERY, help="Research query used in the pipeline.")

    cont = subparsers.add_parser("continue", help="Continue an existing novel by writing the next chapter.")
    cont.add_argument("--book-id", help="Existing book id.")
    cont.add_argument("--title", help="Book title or partial title.")

    subparsers.add_parser("list", help="List novels currently stored in memory.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    master = build_master_agent(args.db)

    if args.command == "list":
        print_json({"books": master.list_books()})
        return

    if args.command == "start":
        result = master.start_new_novel(query=args.query)
    else:
        result = master.continue_novel(book_id=args.book_id, title=args.title)

    print_json(
        {
            "run_id": result["run_id"],
            "book_id": result["book_after_patch"].id,
            "book_title": result["book_after_patch"].title,
            "chapter_written": result["chapter_written"].model_dump(mode="json"),
            "critic_report": result["critic_report"].model_dump(mode="json"),
            "patch_instruction": result["patch_instruction"].model_dump(mode="json")
            if result["patch_instruction"]
            else None,
        }
    )


if __name__ == "__main__":
    main()
