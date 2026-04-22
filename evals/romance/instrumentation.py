from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from novel_flow.llm.base import LLMClient, LLMMessage


@dataclass
class LLMCallRecord:
    phase: str
    temperature: float
    prompt_chars: int


class InstrumentedLLMClient(LLMClient):
    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.phase = "generation"
        self.records: list[LLMCallRecord] = []

    def set_phase(self, phase: str) -> None:
        self.phase = str(phase or "generation")

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        prompt_chars = sum(len(message.content) for message in messages)
        self.records.append(
            LLMCallRecord(
                phase=self.phase,
                temperature=float(temperature),
                prompt_chars=prompt_chars,
            )
        )
        return self.inner.generate(messages=messages, temperature=temperature)

    def count(self, prefix: str) -> int:
        return sum(1 for record in self.records if record.phase.startswith(prefix))

    def prompt_chars(self, prefix: str) -> int:
        return sum(record.prompt_chars for record in self.records if record.phase.startswith(prefix))


@dataclass
class ToolCallRecord:
    tool_name: str
    payload_keys: list[str] = field(default_factory=list)


class InstrumentedToolRegistry:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.records: list[ToolCallRecord] = []

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.records.append(
            ToolCallRecord(
                tool_name=tool_name,
                payload_keys=sorted(str(key) for key in payload.keys()),
            )
        )
        return self.inner.execute(tool_name, payload)

    def counts(self) -> dict[str, int]:
        counter = Counter(record.tool_name for record in self.records)
        return dict(sorted(counter.items()))
