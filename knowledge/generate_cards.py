from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novel_flow.config import Settings
from novel_flow.services.knowledge_card_generator import KnowledgeCardGenerator


# IDE 里直接点运行时，默认使用下面这组配置。
SOURCE_NAME = "new_note"
MAX_CARDS = 4
INPUT_FILE = ROOT / "knowledge" / "_inbox.txt"
OUTPUT_DIR = ROOT / "knowledge" / "cards"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate knowledge cards from raw notes with Doubao.")
    parser.add_argument("--input-file", help="Path to a text or markdown file.")
    parser.add_argument("--stdin", action="store_true", help="Read raw text from stdin instead of knowledge/_inbox.txt.")
    parser.add_argument("--source-name", help="Logical source name written into generated cards.")
    parser.add_argument("--output-dir", help="Directory to write generated cards.")
    parser.add_argument("--max-cards", type=int, help="Upper bound for generated cards.")
    parser.add_argument("--dry-run", action="store_true", help="Print generated cards instead of writing files.")
    return parser


def main() -> None:
    print(f"[knowledge] Python: {sys.executable}", file=sys.stderr, flush=True)
    args = build_parser().parse_args()
    source_name = args.source_name or SOURCE_NAME
    max_cards = args.max_cards or MAX_CARDS
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    input_desc = "stdin" if args.stdin else str(Path(args.input_file) if args.input_file else INPUT_FILE)
    print(f"[knowledge] Loading input from: {input_desc}", file=sys.stderr, flush=True)
    raw_text = read_input(args.input_file, from_stdin=args.stdin)
    print(f"[knowledge] Loaded {len(raw_text)} chars", file=sys.stderr, flush=True)

    print("[knowledge] Initializing generator...", file=sys.stderr, flush=True)
    generator = KnowledgeCardGenerator.from_settings(Settings.from_env())
    print(f"[knowledge] Requesting cards from model, source={source_name}, max_cards={max_cards}", file=sys.stderr, flush=True)
    cards = generator.generate_cards(raw_text=raw_text, source_name=source_name, max_cards=max_cards)
    print(f"[knowledge] Model returned {len(cards)} card(s)", file=sys.stderr, flush=True)

    if args.dry_run:
        print("[knowledge] Dry run mode, printing cards only", file=sys.stderr, flush=True)
        print(json.dumps({"cards": [card.model_dump(mode="json") for card in cards]}, ensure_ascii=False, indent=2))
        return

    print(f"[knowledge] Writing cards to: {output_dir}", file=sys.stderr, flush=True)
    written_files = generator.write_cards(cards=cards, output_dir=output_dir)
    print(f"[knowledge] Wrote {len(written_files)} file(s)", file=sys.stderr, flush=True)
    print(
        json.dumps(
            {
                "source_name": source_name,
                "card_count": len(cards),
                "files": [str(path) for path in written_files],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def read_input(input_file: str | None, *, from_stdin: bool) -> str:
    if input_file:
        return Path(input_file).read_text(encoding="utf-8")
    if from_stdin:
        return sys.stdin.read()
    return INPUT_FILE.read_text(encoding="utf-8")


if __name__ == "__main__":
    main()
