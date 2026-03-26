from __future__ import annotations

# Debug 08
# 这个文件是 CriticAgent 的单独调试入口。
# 作用：
# 1. 先生成一本书
# 2. 输出结构化 IssueCard
# 3. 可选打印 PatchInstruction，方便你检查审稿建议是否具体可执行

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, add_llm_argument, build_llm_client
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.services.patcher import PatchExecutor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug CriticAgent.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Source query used to build the draft.")
    parser.add_argument("--show-patch", action="store_true", help="Also print the patch instruction.")
    add_llm_argument(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    llm_client = build_llm_client(args.mock_llm)
    writer = WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor())
    critic = CriticAgent(llm_client=llm_client)

    blueprint = writer.build_blueprint(research_query=args.query)
    book = writer.create_book(blueprint=blueprint, source_query=args.query)
    report = critic.review_book(book=book)

    payload: dict[str, object] = {
        "agent": "CriticAgent",
        "book_id": book.id,
        "report_id": report.report_id,
        "issue_count": len(report.issues),
        "issues": [issue.model_dump(mode="json") for issue in report.issues],
    }
    if args.show_patch and report.issues:
        payload["patch_instruction"] = critic.build_patch_instruction(report.issues[0]).model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
