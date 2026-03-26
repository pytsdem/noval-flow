from __future__ import annotations

# Demo 03
# 这个文件只验证 WriterAgent 的 create 能力：
# 1. 构建 blueprint
# 2. 生成结构化书稿
# 3. 打印第一个 block，确认内容和 block id 正常

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, add_llm_argument, build_llm_client
from novel_flow.agents.writer import WriterAgent
from novel_flow.services.patcher import PatchExecutor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo 03: validate WriterAgent.create.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query used to build the blueprint.")
    add_llm_argument(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    writer = WriterAgent(llm_client=build_llm_client(args.mock_llm), patch_executor=PatchExecutor())
    blueprint = writer.build_blueprint(research_query=args.query)
    book = writer.create_book(blueprint=blueprint, source_query=args.query)
    first_block = book.volumes[0].chapters[0].scenes[0].blocks[0]
    print(
        {
            "book_id": book.id,
            "title": book.title,
            "first_block_id": first_block.id,
            "first_block_preview": first_block.text[:80],
        }
    )


if __name__ == "__main__":
    main()
