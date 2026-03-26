from __future__ import annotations

import logging

import httpx

from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMClient, LLMMessage


class DoubaoLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.base_url}/chat/completions"
        try:
            response = httpx.post(endpoint, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            self.logger.exception("Doubao request failed")
            raise AgentExecutionError(f"Doubao generation failed: {exc}") from exc
