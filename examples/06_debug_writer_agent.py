from __future__ import annotations

# Debug 06
# 这个文件是 WriterAgent 的单独调试入口。
# 可调模式：
# - create：创建初始书稿
# - rewrite_unit：重写某个 block
# - patch_block：手工对某个 block 做精准替换
# - expand：对某个 block 扩写

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from _example_support import DEFAULT_QUERY, add_llm_argument, build_llm_client
from novel_flow.agents.writer import WriterAgent
from novel_flow.models.schemas import PatchInstruction, PatchOperation
from novel_flow.services.patcher import PatchExecutor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug WriterAgent with Doubao or mock LLM.")
    parser.add_argument("--mode", choices=["create", "rewrite_unit", "patch_block", "expand"], default="create")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Source query used to build the blueprint.")
    parser.add_argument("--block-id", default="ch_001.sc_001.b001", help="Target block id.")
    parser.add_argument(
        "--guidance",
        default="加强婚礼现场的压迫感，并让女主的反击动机更明确。",
        help="Guidance for rewrite_unit mode.",
    )
    parser.add_argument(
        "--expansion-goal",
        default="增加婚礼现场细节和宾客反应，强化公开羞辱感。",
        help="Goal for expand mode.",
    )
    parser.add_argument(
        "--patch-content",
        default=(
            "我听见那句“替身”时，手里的捧花几乎被我掐断。"
            "休息室外铺着长长的香槟色地毯，门缝里漏出来的笑声像耳光一样，"
            "提醒我这场婚礼从来不是童话，而是一场精心布置的公开羞辱。"
        ),
        help="Replacement content for patch_block mode.",
    )
    add_llm_argument(parser)
    return parser


def build_writer(use_mock_llm: bool) -> WriterAgent:
    return WriterAgent(llm_client=build_llm_client(use_mock_llm), patch_executor=PatchExecutor())


def main() -> None:
    args = build_parser().parse_args()
    writer = build_writer(use_mock_llm=args.mock_llm)
    blueprint = writer.build_blueprint(research_query=args.query)
    book = writer.create_book(blueprint=blueprint, source_query=args.query)

    if args.mode == "create":
        first_block = book.volumes[0].chapters[0].scenes[0].blocks[0]
        print_json(
            {
                "agent": "WriterAgent",
                "mode": "create",
                "book_id": book.id,
                "book_title": book.title,
                "first_block_id": first_block.id,
                "first_block_text": first_block.text,
            }
        )
        return

    if args.mode == "rewrite_unit":
        patched_book = writer.rewrite_unit(book=book, block_id=args.block_id, guidance=args.guidance)
        print_json(
            {
                "agent": "WriterAgent",
                "mode": "rewrite_unit",
                "block_id": args.block_id,
                "guidance": args.guidance,
                "text": find_block_text(patched_book, args.block_id),
            }
        )
        return

    if args.mode == "expand":
        expanded_book = writer.expand(book=book, block_id=args.block_id, expansion_goal=args.expansion_goal)
        print_json(
            {
                "agent": "WriterAgent",
                "mode": "expand",
                "block_id": args.block_id,
                "expansion_goal": args.expansion_goal,
                "text": find_block_text(expanded_book, args.block_id),
            }
        )
        return

    instruction = PatchInstruction(
        patch_id="patch_debug_manual",
        target_block_id=args.block_id,
        operation=PatchOperation.REPLACE,
        reason="manual debug patch",
        content=args.patch_content,
    )
    patched_book, payload = writer.patch_block(book=book, instruction=instruction)
    print_json(
        {
            "agent": "WriterAgent",
            "mode": "patch_block",
            "block_id": args.block_id,
            "patch_version": payload["patch_version"],
            "text": find_block_text(patched_book, args.block_id),
        }
    )


def find_block_text(book, block_id: str) -> str:
    for volume in book.volumes:
        for chapter in volume.chapters:
            for scene in chapter.scenes:
                for block in scene.blocks:
                    if block.id == block_id:
                        return block.text
    raise ValueError(f"Block not found: {block_id}")


def print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
