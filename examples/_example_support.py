from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novel_flow.config import Settings
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.llm.mock import MockLLMClient


DEFAULT_QUERY = "知乎体高热度都市情感反转"


def add_llm_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mock-llm", action="store_true", help="Use mock LLM instead of Doubao.")


def build_llm_client(use_mock_llm: bool) -> MockLLMClient | DoubaoLLMClient:
    settings = Settings.from_env()
    if use_mock_llm:
        return MockLLMClient()
    if not settings.doubao_api_key or not settings.doubao_model:
        raise ValueError("Missing DOUBAO_API_KEY or DOUBAO_MODEL. Set env vars or use --mock-llm.")
    return DoubaoLLMClient(
        api_key=settings.doubao_api_key,
        model=settings.doubao_model,
        base_url=settings.doubao_base_url,
    )
