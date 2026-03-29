from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.master import MasterAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.config import Settings
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.services.crawler import MockTrendCrawler
from novel_flow.services.patcher import PatchExecutor
from novel_flow.storage.sqlite_store import SQLiteStore


DEFAULT_DB = "data/example_master.db"
DEFAULT_QUERY = "research-debug-query"


def build_llm_client() -> DoubaoLLMClient:
    settings = Settings.from_env()
    if not settings.doubao_api_key or not settings.doubao_model:
        raise ValueError("Missing DOUBAO_API_KEY or DOUBAO_MODEL.")
    return DoubaoLLMClient(
        api_key=settings.doubao_api_key,
        model=settings.doubao_model,
        base_url=settings.doubao_base_url,
    )


def build_store(db_path: str) -> SQLiteStore:
    return SQLiteStore(ROOT / db_path)


def build_memory_agent(db_path: str) -> MemoryAgent:
    return MemoryAgent(store=build_store(db_path))


def build_writer_agent() -> WriterAgent:
    return WriterAgent(llm_client=build_llm_client(), patch_executor=PatchExecutor())


def build_blueprint_agent() -> BlueprintAgent:
    return BlueprintAgent(llm_client=build_llm_client())


def build_critic_agent() -> CriticAgent:
    return CriticAgent(llm_client=build_llm_client())


def build_master_agent(db_path: str) -> MasterAgent:
    store = build_store(db_path)
    return MasterAgent(
        memory_agent=MemoryAgent(store=store),
        research_agent=ResearchAgent(crawler=MockTrendCrawler()),
        blueprint_agent=BlueprintAgent(llm_client=build_llm_client()),
        writer_agent=WriterAgent(llm_client=build_llm_client(), patch_executor=PatchExecutor()),
        critic_agent=CriticAgent(llm_client=build_llm_client()),
    )


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
