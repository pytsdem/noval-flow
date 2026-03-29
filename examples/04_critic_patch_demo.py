from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_DB, build_memory_agent, build_writer_agent, print_json
from novel_flow.models.schemas import PatchInstruction, PatchOperation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug chapter patching.")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--book-id", required=True, help="Book id to patch.")
    parser.add_argument("--block-id", required=True, help="Target block id.")
    parser.add_argument("--operation", choices=["replace", "append", "prepend"], default="replace")
    parser.add_argument("--reason", default="manual debug patch", help="Patch reason.")
    parser.add_argument("--patch-content", required=True, help="Patch content.")
    return parser


def find_block_text(book, block_id: str) -> str:
    for volume in book.volumes:
        for chapter in volume.chapters:
            for scene in chapter.scenes:
                for block in scene.blocks:
                    if block.id == block_id:
                        return block.text
    raise ValueError(f"Block not found: {block_id}")


def main() -> None:
    args = build_parser().parse_args()
    memory = build_memory_agent(args.db)
    writer = build_writer_agent()
    book = memory.load_book(args.book_id)
    if book is None:
        raise ValueError(f"Book not found: {args.book_id}")

    instruction = PatchInstruction(
        patch_id="patch_debug_manual",
        target_block_id=args.block_id,
        operation=PatchOperation(args.operation),
        reason=args.reason,
        content=args.patch_content,
    )
    patched_book, payload = writer.patch_block(book=book, instruction=instruction)
    memory.save_book(patched_book)
    print_json(
        {
            "agent": "WriterAgent",
            "mode": "patch_block",
            "book_id": args.book_id,
            "block_id": args.block_id,
            "patch_version": payload["patch_version"],
            "text": find_block_text(patched_book, args.block_id),
        }
    )


if __name__ == "__main__":
    main()
