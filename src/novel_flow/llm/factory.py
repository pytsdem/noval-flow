from __future__ import annotations

from novel_flow.config import Settings
from novel_flow.llm.base import LLMClient
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.llm.openai import OpenAILLMClient


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.strip().lower()
    if provider == "openai":
        if not settings.openai_api_key or not settings.openai_model:
            raise ValueError("Missing OPENAI_API_KEY or OPENAI_MODEL. Check your .env file.")
        return OpenAILLMClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
    if provider == "doubao":
        if not settings.doubao_api_key or not settings.doubao_model:
            raise ValueError("Missing DOUBAO_API_KEY or DOUBAO_MODEL. Check your .env file.")
        return DoubaoLLMClient(
            api_key=settings.doubao_api_key,
            model=settings.doubao_model,
            base_url=settings.doubao_base_url,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}. Use 'doubao' or 'openai'.")
