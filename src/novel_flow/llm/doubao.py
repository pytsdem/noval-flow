from __future__ import annotations

import json
import logging
import sys
import time
from uuid import uuid4

import httpx

from novel_flow import events as ev
from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMClient, LLMMessage


class DoubaoLLMClient(LLMClient):
    _STREAM_EMIT_MIN_CHARS = 120
    _STREAM_EMIT_MAX_WAIT_SECONDS = 0.4
    _REQUEST_TIMEOUT = httpx.Timeout(timeout=30.0, read=900.0)
    _MAX_READ_TIMEOUT_RETRIES = 1

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        ev.check_cancelled()
        call_id = f"llm_{uuid4().hex[:10]}"
        prompt_preview = messages[-1].content[:600] if messages else ""
        ev.emit(
            "llm_prompt",
            agent="DoubaoLLM",
            title="?? Prompt",
            call_id=call_id,
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
        attempts = self._MAX_READ_TIMEOUT_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                chunks: list[str] = []
                chunk_index = 0
                stream_buffer = ""
                last_emit_ts = time.monotonic()

                def flush_stream_buffer() -> None:
                    nonlocal stream_buffer, chunk_index, last_emit_ts
                    if not stream_buffer:
                        return
                    chunk_index += 1
                    ev.emit(
                        "llm_stream",
                        agent="DoubaoLLM",
                        title="????",
                        call_id=call_id,
                        preview=stream_buffer,
                        chunk_index=chunk_index,
                    )
                    stream_buffer = ""
                    last_emit_ts = time.monotonic()

                with httpx.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self._REQUEST_TIMEOUT,
                ) as response:
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
                                stream_buffer += delta
                                now_ts = time.monotonic()
                                if (
                                    len(stream_buffer) >= self._STREAM_EMIT_MIN_CHARS
                                    or (now_ts - last_emit_ts) >= self._STREAM_EMIT_MAX_WAIT_SECONDS
                                ):
                                    flush_stream_buffer()
                                sys.stderr.write(delta)
                                sys.stderr.flush()
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                    flush_stream_buffer()

                sys.stderr.write("\n")
                sys.stderr.flush()
                result = "".join(chunks)
                ev.check_cancelled()
                ev.emit(
                    "llm_reply",
                    agent="DoubaoLLM",
                    title="????",
                    call_id=call_id,
                    preview=result[:600],
                    length=len(result),
                )
                return result
            except httpx.ReadTimeout as exc:
                is_last_attempt = attempt >= attempts
                self.logger.warning(
                    "Doubao request timed out on attempt %s/%s for model '%s'",
                    attempt,
                    attempts,
                    self.model,
                )
                if is_last_attempt:
                    self.logger.exception("Doubao request failed")
                    raise AgentExecutionError(f"Doubao generation failed: {exc}") from exc
                time.sleep(min(2.0 * attempt, 5.0))
            except (httpx.HTTPError, TypeError) as exc:
                self.logger.exception("Doubao request failed")
                raise AgentExecutionError(f"Doubao generation failed: {exc}") from exc

        raise AgentExecutionError("Doubao generation failed: exhausted retry budget without a result")
