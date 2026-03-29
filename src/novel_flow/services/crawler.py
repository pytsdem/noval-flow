from __future__ import annotations

from abc import ABC, abstractmethod

from novel_flow.models.schemas import TrendItem


class TrendCrawler(ABC):
    @abstractmethod
    def collect(self, query: str) -> list[TrendItem]:
        raise NotImplementedError


class MockTrendCrawler(TrendCrawler):
    def collect(self, query: str) -> list[TrendItem]:
        return []
