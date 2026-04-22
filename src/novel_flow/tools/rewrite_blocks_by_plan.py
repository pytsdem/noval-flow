from __future__ import annotations

import json
from typing import Any

from novel_flow.models.schemas import (
    ChapterPatchPlanPayload,
    ContentBlock,
    PatchReportItem,
    PatchedBlock,
    RewriteBlocksByPlanPayload,
)
from novel_flow.tools._base import LLMChapterTool


class RewriteBlocksByPlanTool(LLMChapterTool):
    name = "rewrite_blocks_by_plan"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        original_blocks = self._load_blocks(payload.get("original_blocks_json"))
        patch_plan = self._load_patch_plan(payload.get("patch_plan"))
        block_order = [block.block_id for block in original_blocks]
        block_map = {block.block_id: block for block in original_blocks}
        patched_blocks: list[PatchedBlock] = []
        patch_report: list[PatchReportItem] = []
        rewritten_ids: set[str] = set()

        for target in patch_plan.patch_targets:
            if target.target_id in rewritten_ids:
                continue
            current_block = block_map.get(target.target_id)
            if current_block is None:
                patch_report.append(
                    PatchReportItem(
                        block_id=target.target_id,
                        applied=False,
                        notes="未找到目标 block，已跳过。",
                    )
                )
                continue
            rewritten_ids.add(target.target_id)
            previous_block = self._adjacent_block(block_order, block_map, target.target_id, offset=-1)
            next_block = self._adjacent_block(block_order, block_map, target.target_id, offset=1)
            prompt = self.render_prompt(
                "writer/rewrite_blocks_by_plan.txt",
                chapter_payload_text=payload.get("chapter_payload_text", ""),
                scene_character_context_text=payload.get("scene_character_context_text", ""),
                relationship_state_text=payload.get("relationship_state_text", ""),
                style_card_text=payload.get("style_card_text", ""),
                patch_target_json=self._json_text(target.model_dump(mode="json")),
                global_constraints_json=self._json_text(patch_plan.global_constraints),
                current_block_card_text=self._block_card_text(current_block),
                current_block_text=current_block.text,
                previous_block_text=previous_block.text if previous_block is not None else "",
                next_block_text=next_block.text if next_block is not None else "",
            )
            candidate_text = self.generate_text(prompt=prompt, temperature=0.45).strip()
            applied = bool(candidate_text)
            final_text = candidate_text if applied else str(current_block.text or "").strip()
            updated_block = current_block.model_copy(
                update={
                    "text": final_text,
                    "status": "committed",
                    "version": max(int(current_block.version), 1) + (1 if applied else 0),
                }
            )
            block_map[target.target_id] = updated_block
            patched_blocks.append(
                PatchedBlock(
                    block_id=target.target_id,
                    old_summary=self._old_summary(current_block),
                    new_text=final_text,
                )
            )
            patch_report.append(
                PatchReportItem(
                    block_id=target.target_id,
                    applied=applied,
                    notes="已按 patch plan 重写目标 block。" if applied else "模型未返回新文本，保留原文。",
                )
            )

        merged_chapter_text = self._merge_chapter([block_map[block_id] for block_id in block_order if block_id in block_map])
        return RewriteBlocksByPlanPayload(
            patched_blocks=patched_blocks,
            merged_chapter_text=merged_chapter_text,
            patch_report=patch_report,
        ).model_dump(mode="json")

    @staticmethod
    def _load_blocks(raw_blocks: object) -> list[ContentBlock]:
        if isinstance(raw_blocks, str):
            payload = json.loads(raw_blocks)
        else:
            payload = raw_blocks or []
        items = payload.get("blocks", payload if isinstance(payload, list) else [])
        return [ContentBlock.model_validate(item) for item in items]

    @staticmethod
    def _load_patch_plan(raw_plan: object) -> ChapterPatchPlanPayload:
        if isinstance(raw_plan, str):
            payload = json.loads(raw_plan)
        else:
            payload = raw_plan or {}
        return ChapterPatchPlanPayload.model_validate(payload)

    @staticmethod
    def _merge_chapter(blocks: list[ContentBlock]) -> str:
        return "\n\n".join(str(block.text or "").strip() for block in blocks if str(block.text or "").strip()).strip()

    @staticmethod
    def _adjacent_block(
        block_order: list[str],
        block_map: dict[str, ContentBlock],
        block_id: str,
        *,
        offset: int,
    ) -> ContentBlock | None:
        if block_id not in block_order:
            return None
        index = block_order.index(block_id) + offset
        if index < 0 or index >= len(block_order):
            return None
        return block_map.get(block_order[index])

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _old_summary(block: ContentBlock) -> str:
        if str(block.purpose or "").strip():
            return str(block.purpose).strip()
        text = str(block.text or "").strip()
        return text[:80] if text else "原 block 文本"

    @staticmethod
    def _block_card_text(block: ContentBlock) -> str:
        lines = [
            f"block_id: {block.block_id}",
            f"purpose: {block.purpose}",
            f"scene_goal: {block.scene_goal}",
            f"end_state: {block.end_state}",
            f"cost_shift: {block.cost_shift}",
            f"reader_feeling_target: {block.reader_feeling_target}",
            f"turn_type: {block.turn_type}",
            "must_reveal:",
        ]
        for item in block.must_reveal or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_hide:")
        for item in block.must_hide or ["None."]:
            lines.append(f"- {item}")
        lines.append("style_risk_guard:")
        for item in block.style_risk_guard or ["None."]:
            lines.append(f"- {item}")
        return "\n".join(lines).strip()
