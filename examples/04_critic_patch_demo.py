from __future__ import annotations

# Demo 04
# 这个文件验证 CriticAgent + WriterAgent.patch_block：
# 1. 先生成一本书
# 2. 让 CriticAgent 输出 IssueCard
# 3. 根据 IssueCard 生成 PatchInstruction
# 4. 对目标 block 做精准修改并打印 patch 结果

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, add_llm_argument, build_llm_client
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.services.patcher import PatchExecutor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo 04: validate CriticAgent + patch flow.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Research query used to build the blueprint.")
    add_llm_argument(parser)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    llm_client = build_llm_client(args.mock_llm)
    writer = WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor())
    critic = CriticAgent(llm_client=llm_client)

    blueprint = writer.build_blueprint(research_query=args.query)
    book = writer.create_book(blueprint=blueprint, source_query=args.query)
    report = critic.review_book(book)

    if not report.issues:
        print({"issues": 0})
        return

    instruction = critic.build_patch_instruction(report.issues[0])
    patched_book, payload = writer.patch_block(book=book, instruction=instruction)
    patched_block = patched_book.volumes[0].chapters[0].scenes[0].blocks[0]
    print(
        {
            "issue_id": report.issues[0].issue_id,
            "target_block_id": instruction.target_block_id,
            "patch_version_id": payload["patch_version"]["version_id"],
            "patched_preview": patched_block.text[:80],
        }
    )


if __name__ == "__main__":
    main()
