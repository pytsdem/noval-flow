from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from novel_flow.models.schemas import AgentResult


class BaseAgent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = logging.getLogger(name)

    @abstractmethod
    def run(self, **kwargs: Any) -> AgentResult:
        raise NotImplementedError
