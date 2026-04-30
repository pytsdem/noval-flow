from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _iter_entries(index_path: Path) -> list[tuple[str, Path]]:
    index = _read_json(index_path)
    base_dir = index_path.parent
    entries: list[tuple[str, Path]] = []
    for collection in list(index.get("collections") or []):
        for rel in list(collection.get("entries") or []):
            entry_dir = base_dir / str(rel)
            if entry_dir.is_dir():
                entries.append((collection.get("id") or "unknown_collection", entry_dir))
    return entries


def export_corpus(*, index_path: Path, output_path: Path) -> int:
    rows: list[dict[str, Any]] = []
    for collection_id, entry_dir in _iter_entries(index_path):
        entry_json = entry_dir / "entry.json"
        if not entry_json.exists():
            continue
        entry = _read_json(entry_json)
        notes_path = entry_dir / "notes.md"
        notes = _read_text(notes_path) if notes_path.exists() else ""
        for chapter_index in (1, 2, 3):
            chapter_path = entry_dir / f"chapter{chapter_index}.txt"
            if not chapter_path.exists():
                continue
            rows.append(
                {
                    "sample_id": entry.get("id") or entry_dir.name,
                    "collection_id": collection_id,
                    "title": entry.get("title") or entry_dir.name,
                    "author": entry.get("author") or "",
                    "tags": list(entry.get("tags") or []),
                    "opening_pattern": entry.get("opening_pattern") or "",
                    "voice_signature": entry.get("voice_signature") or "",
                    "chapter_index": chapter_index,
                    "chapter_title": (entry.get("chapter_titles") or ["", "", ""])[chapter_index - 1],
                    "text": _read_text(chapter_path),
                    "chapter_summary": (entry.get("chapter_summaries") or {}).get(f"chapter{chapter_index}", ""),
                    "story_opening_flow": list(entry.get("story_opening_flow") or []),
                    "narrative_rhythm": list(entry.get("narrative_rhythm") or []),
                    "retention_mechanics": list(entry.get("retention_mechanics") or []),
                    "strong_points": list(entry.get("strong_points") or []),
                    "what_to_learn": list(entry.get("what_to_learn") or []),
                    "analysis_basis": entry.get("analysis_basis") or "",
                    "notes_markdown": notes,
                }
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export local positive examples into a JSONL corpus for later SFT/distillation work.")
    parser.add_argument(
        "--index",
        default="evals/romance/positive_examples/index.json",
        help="Positive example index.json path.",
    )
    parser.add_argument(
        "--output",
        default="evals/romance/positive_examples/corpus/positive_examples_v1.jsonl",
        help="Output JSONL path.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    count = export_corpus(
        index_path=Path(args.index),
        output_path=Path(args.output),
    )
    print(
        json.dumps(
            {
                "rows": count,
                "output": str(Path(args.output)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
