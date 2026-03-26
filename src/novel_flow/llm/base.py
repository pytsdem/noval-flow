from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMClient(ABC):
    @abstractmethod
    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        raise NotImplementedError
