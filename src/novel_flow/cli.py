from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.master import MasterAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.config import Settings
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.llm.mock import MockLLMClient
from novel_flow.logger import configure_logging
from novel_flow.services.crawler import MockTrendCrawler
from novel_flow.services.patcher import PatchExecutor
from novel_flow.storage.sqlite_store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Novel Flow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_mock = subparsers.add_parser("run-mock", help="Run the mock multi-agent pipeline.")
    run_mock.add_argument("--db", default="data/novel_flow.db", help="SQLite database path.")
    run_mock.add_argument("--query", default="知乎体高热度都市情感反转", help="Research query.")
    run_mock.add_argument("--mock-llm", action="store_true", help="Use mock LLM instead of Doubao.")
    return parser


def build_master(settings: Settings, use_mock_llm: bool) -> MasterAgent:
    store = SQLiteStore(db_path=settings.database_path)
    memory_agent = MemoryAgent(store=store)
    research_agent = ResearchAgent(crawler=MockTrendCrawler())
    llm_client = _build_llm(settings=settings, use_mock_llm=use_mock_llm)
    writer_agent = WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor())
    critic_agent = CriticAgent(llm_client=llm_client)
    return MasterAgent(memory_agent=memory_agent, research_agent=research_agent, writer_agent=writer_agent, critic_agent=critic_agent)


def _build_llm(settings: Settings, use_mock_llm: bool) -> MockLLMClient | DoubaoLLMClient:
    if use_mock_llm:
        return MockLLMClient()
    if not settings.doubao_api_key or not settings.doubao_model:
        raise ValueError("Doubao configuration missing. Set DOUBAO_API_KEY and DOUBAO_MODEL, or use --mock-llm.")
    return DoubaoLLMClient(
        api_key=settings.doubao_api_key,
        model=settings.doubao_model,
        base_url=settings.doubao_base_url,
    )


def run_mock_command(db_path: str, query: str, use_mock_llm: bool) -> int:
    settings = Settings.from_env(database_path=db_path)
    configure_logging(settings.log_level)
    logger = logging.getLogger("novel_flow.cli")

    master = build_master(settings=settings, use_mock_llm=use_mock_llm)
    result = master.run_mock_pipeline(query=query)
    output = {
        "run_id": result["run_id"],
        "book_id": result["book_after_patch"].id,
        "book_title": result["book_after_patch"].title,
        "chapter_count": sum(len(volume.chapters) for volume in result["book_after_patch"].volumes),
        "issue_count": len(result["critic_report"].issues),
        "patched_block_id": result["patch_instruction"].target_block_id if result["patch_instruction"] else None,
        "database": str(Path(db_path).resolve()),
    }
    logger.info("Mock pipeline completed for book %s", output["book_title"])
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run-mock":
        return run_mock_command(db_path=args.db, query=args.query, use_mock_llm=args.mock_llm)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
