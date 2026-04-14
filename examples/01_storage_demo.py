from __future__ import annotations

# Demo 01
# 这个文件只验证 Memory/Storage 层：
# 1. 构造一个最小 BookDocument
# 2. 存入 SQLite
# 3. 再读回，确认结构化存储可用

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novel_flow.models.schemas import BookDocument, CharacterCard, StoryPremise, Volume
from novel_flow.storage.sqlite_store import SQLiteStore


def main() -> None:
    store = SQLiteStore(ROOT / "data" / "example_storage.db")
    book = BookDocument(
        id="book_demo_storage",
        title="存储演示小说",
        premise=StoryPremise(
            title="存储演示小说",
            high_concept="验证结构化书稿落库",
            genre="都市",
            target_style="都市情感",
            emotional_hook="压抑后的反击",
            central_conflict="女主在婚礼事故后重新夺回叙事权",
        ),
        characters=[CharacterCard(name="沈知微", role="女主", goal="自救", flaw="隐忍")],
        volumes=[Volume(id="vol_001", title="第一卷", summary="演示卷", chapters=[])],
    )
    store.save_book(book)
    loaded = store.load_book(book.id)
    print({"saved_book_id": book.id, "loaded_title": loaded.title if loaded else None})


if __name__ == "__main__":
    main()
