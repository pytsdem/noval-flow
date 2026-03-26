from __future__ import annotations

# Debug 07
# 这个文件是 ResearchAgent 的单独调试入口。
# 作用：
# 1. 调整 query
# 2. 查看热点素材和标签提取结果
# 3. 检查结构化 ResearchReport 是否满足预期

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY
from novel_flow.agents.research import ResearchAgent
from novel_flow.services.crawler import MockTrendCrawler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug ResearchAgent.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query.")
    parser.add_argument("--show-items", action="store_true", help="Print full trend items.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    agent = ResearchAgent(crawler=MockTrendCrawler())
    report = agent.collect_report(query=args.query)
    payload: dict[str, object] = {
        "agent": "ResearchAgent",
        "query": args.query,
        "report_id": report.report_id,
        "sources": report.sources,
        "trend_count": len(report.trend_items),
        "genre_candidates": report.genre_candidates,
        "emotional_patterns": report.emotional_patterns,
        "conflict_patterns": report.conflict_patterns,
        "comment_preferences": report.comment_preferences,
    }
    if args.show_items:
        payload["trend_items"] = [item.model_dump(mode="json") for item in report.trend_items]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
