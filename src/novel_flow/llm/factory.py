from __future__ import annotations

import logging

from novel_flow.config import Settings
from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMClient
from novel_flow.llm.codex_cli import CodexCLIClient
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.llm.openai import OpenAILLMClient


class FallbackLLMClient(LLMClient):
    def __init__(self, primary: LLMClient, fallback: LLMClient, *, primary_name: str, fallback_name: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, messages, temperature: float = 0.7) -> str:
        try:
            return self.primary.generate(messages=messages, temperature=temperature)
        except AgentExecutionError as exc:
            self.logger.warning(
                "Primary LLM provider '%s' failed, falling back to '%s': %s",
                self.primary_name,
                self.fallback_name,
                exc,
            )
            return self.fallback.generate(messages=messages, temperature=temperature)


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.strip().lower()
    if provider == "deepseek":
        if not settings.deepseek_api_key or not settings.deepseek_model:
            raise ValueError("Missing DEEPSEEK_API_KEY or DEEPSEEK_MODEL. Check your .env file.")
        return OpenAILLMClient(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )
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
    if provider == "codex":
        primary = CodexCLIClient(
            exe=settings.codex_exe,
            model=settings.codex_model,
        )
        if settings.doubao_api_key and settings.doubao_model:
            fallback = DoubaoLLMClient(
                api_key=settings.doubao_api_key,
                model=settings.doubao_model,
                base_url=settings.doubao_base_url,
            )
            return FallbackLLMClient(
                primary=primary,
                fallback=fallback,
                primary_name="codex",
                fallback_name="doubao",
            )
        if settings.deepseek_api_key and settings.deepseek_model:
            fallback = OpenAILLMClient(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model,
                base_url=settings.deepseek_base_url,
            )
            return FallbackLLMClient(
                primary=primary,
                fallback=fallback,
                primary_name="codex",
                fallback_name="deepseek",
            )
        if settings.openai_api_key and settings.openai_model:
            fallback = OpenAILLMClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
            )
            return FallbackLLMClient(
                primary=primary,
                fallback=fallback,
                primary_name="codex",
                fallback_name="openai",
            )
        return primary
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {settings.llm_provider}. Use 'doubao', 'deepseek', 'openai', or 'codex'."
    )
