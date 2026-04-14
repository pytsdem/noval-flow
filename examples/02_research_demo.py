from __future__ import annotations

# Demo 02
# 这个文件只验证 ResearchAgent：
# 1. 使用 mock crawler 抓热点素材
# 2. 生成结构化 ResearchReport
# 3. 输出调研结果摘要

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novel_flow.agents.research import ResearchAgent
from novel_flow.services.crawler import MockTrendCrawler


def main() -> None:
    agent = ResearchAgent(crawler=MockTrendCrawler())
    report = agent.collect_report(query="都市情感反转")
    print(
        {
            "report_id": report.report_id,
            "sources": report.sources,
            "trend_count": len(report.trend_items),
            "genre_candidates": report.genre_candidates,
        }
    )


if __name__ == "__main__":
    main()
