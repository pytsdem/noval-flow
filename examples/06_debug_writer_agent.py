from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_DB, DEFAULT_QUERY, build_blueprint_agent, build_memory_agent, build_writer_agent, print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug chapter writing.")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_cmd = subparsers.add_parser("start", help="Create a new book shell and write the first chapter.")
    new_cmd.add_argument("--query", default=DEFAULT_QUERY, help="Research query used to build the blueprint.")

    cont_cmd = subparsers.add_parser("continue", help="Write the next chapter for an existing book.")
    cont_cmd.add_argument("--book-id", required=True, help="Book id to continue.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    memory = build_memory_agent(args.db)
    writer = build_writer_agent()
    blueprint_agent = build_blueprint_agent()

    if args.command == "start":
        blueprint = blueprint_agent.build_blueprint(research_query=args.query)
        book = writer.create_book(blueprint=blueprint, source_query=args.query)
        memory.save_book(book)
        updated_book, chapter = writer.write_next_chapter(book)
    else:
        book = memory.load_book(args.book_id)
        if book is None:
            raise ValueError(f"Book not found: {args.book_id}")
        updated_book, chapter = writer.write_next_chapter(book)

    memory.save_book(updated_book)
    print_json(
        {
            "agent": "WriterAgent",
            "mode": "write_next_chapter",
            "book_id": updated_book.id,
            "book_title": updated_book.title,
            "chapter": chapter.model_dump(mode="json"),
            "next_chapter_index": updated_book.metadata.get("next_chapter_index"),
            "completed_chapter_ids": updated_book.metadata.get("completed_chapter_ids", []),
        }
    )


if __name__ == "__main__":
    main()
