from __future__ import annotations

import json
import logging
import sys

import httpx

from novel_flow import events as ev
from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMClient, LLMMessage


class DoubaoLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        ev.check_cancelled()
        prompt_preview = messages[-1].content[:600] if messages else ""
        ev.emit(
            "llm_prompt",
            agent="DoubaoLLM",
            title="发送 Prompt",
            preview=prompt_preview,
            total_chars=sum(len(m.content) for m in messages),
        )

        payload = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.base_url}/chat/completions"
        try:
            chunks: list[str] = []
            chunk_index = 0
            with httpx.stream("POST", endpoint, headers=headers, json=payload, timeout=180.0) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    ev.check_cancelled()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            chunks.append(delta)
                            chunk_index += 1
                            ev.emit(
                                "llm_stream",
                                agent="DoubaoLLM",
                                title="流式输出",
                                preview=delta,
                                chunk_index=chunk_index,
                            )
                            sys.stderr.write(delta)
                            sys.stderr.flush()
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
            sys.stderr.write("\n")
            sys.stderr.flush()
            result = "".join(chunks)
            ev.check_cancelled()
            ev.emit(
                "llm_reply",
                agent="DoubaoLLM",
                title="收到回复",
                preview=result[:600],
                length=len(result),
            )
            return result
        except (httpx.HTTPError, TypeError) as exc:
            self.logger.exception("Doubao request failed")
            raise AgentExecutionError(f"Doubao generation failed: {exc}") from exc
