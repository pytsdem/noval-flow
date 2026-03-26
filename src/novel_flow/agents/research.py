from __future__ import annotations

from typing import Any
from uuid import uuid4

from novel_flow.agents.base import BaseAgent
from novel_flow.models.schemas import AgentResult, ResearchReport
from novel_flow.services.crawler import TrendCrawler


class ResearchAgent(BaseAgent):
    def __init__(self, crawler: TrendCrawler) -> None:
        super().__init__(name="ResearchAgent")
        self.crawler = crawler

    def collect_report(self, query: str) -> ResearchReport:
        trend_items = self.crawler.collect(query)
        emotional_patterns = sorted({tag for item in trend_items for tag in item.emotional_tags})
        conflict_patterns = sorted({tag for item in trend_items for tag in item.conflict_tags})
        comment_preferences = sorted({tag for item in trend_items for tag in item.audience_preferences})
        return ResearchReport(
            report_id=f"research_{uuid4().hex[:10]}",
            query=query,
            sources=sorted({item.source for item in trend_items}),
            trend_items=trend_items,
            genre_candidates=["都市言情", "豪门博弈", "情感反转"],
            emotional_patterns=emotional_patterns,
            conflict_patterns=conflict_patterns,
            comment_preferences=comment_preferences,
            writing_recommendations=[
                "第一章必须在 800 字内抛出核心冲突。",
                "每章保留 1 个评论区讨论点，例如身份误认或价值反击。",
                "女主成长线需要和情感线并行推进，避免只靠恋爱驱动。",
            ],
        )

    def run(self, **kwargs: Any) -> AgentResult:
        query = str(kwargs["query"])
        report = self.collect_report(query=query)
        return AgentResult(
            agent_name=self.name,
            success=True,
            message=f"Collected {len(report.trend_items)} trend items.",
            payload={"research_report": report.model_dump(mode="json")},
        )
