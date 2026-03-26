from __future__ import annotations

# Demo 05
# 这个文件验证 MasterAgent 的全流程编排：
# 1. 调 ResearchAgent 生成调研报告
# 2. 调 WriterAgent 创建书稿
# 3. 调 CriticAgent 审稿
# 4. 如有问题则执行精准 patch
# 5. 由 MemoryAgent 持久化全流程结果

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, add_llm_argument, build_llm_client
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.master import MasterAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.services.crawler import MockTrendCrawler
from novel_flow.services.patcher import PatchExecutor
from novel_flow.storage.sqlite_store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo 05: validate MasterAgent pipeline.")
    parser.add_argument("--db", default="data/example_master.db", help="SQLite database path.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query used in the pipeline.")
    add_llm_argument(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = SQLiteStore(ROOT / args.db)
    llm_client = build_llm_client(args.mock_llm)
    master = MasterAgent(
        memory_agent=MemoryAgent(store=store),
        research_agent=ResearchAgent(crawler=MockTrendCrawler()),
        writer_agent=WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor()),
        critic_agent=CriticAgent(llm_client=llm_client),
    )
    result = master.run_mock_pipeline(query=args.query)
    print(
        {
            "run_id": result["run_id"],
            "book_id": result["book_after_patch"].id,
            "issue_count": len(result["critic_report"].issues),
            "patched_block_id": result["patch_instruction"].target_block_id if result["patch_instruction"] else None,
        }
    )


if __name__ == "__main__":
    main()
