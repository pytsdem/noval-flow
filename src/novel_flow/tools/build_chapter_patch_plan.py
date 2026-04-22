from __future__ import annotations

import json

from novel_flow.models.schemas import ChapterPatchPlanPayload, ChapterPatchTarget, ContentBlock
from novel_flow.tools._base import LLMChapterTool


class BuildChapterPatchPlanTool(LLMChapterTool):
    name = "build_chapter_patch_plan"
    DEFAULT_GLOBAL_CONSTRAINTS = [
        "不得引入新设定。",
        "不得提前揭露隐藏真相。",
        "未命中的 block 不要改动。",
        "优先修复衔接、重复和情绪落点，不要顺手扩写半章。",
    ]
    DEFAULT_LOCAL_CONTEXT = ["prev_block", "next_block", "relationship_state"]

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        planned_blocks = self._load_planned_blocks(payload.get("planned_blocks_json"))
        prompt = self.render_prompt(
            "writer/build_chapter_patch_plan.txt",
            chapter_text=payload.get("chapter_text", ""),
            planned_blocks_json=self._planned_blocks_json(planned_blocks),
            review_reports_json=self._json_text(payload.get("review_reports", {})),
            chapter_summary_context_text=payload.get("chapter_summary_context_text", ""),
            relationship_state_text=payload.get("relationship_state_text", ""),
        )
        raw = self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=ChapterPatchPlanPayload,
        )
        plan = ChapterPatchPlanPayload.model_validate(raw)
        all_block_ids = [block.block_id for block in planned_blocks]
        normalized_targets: list[ChapterPatchTarget] = []
        seen_targets: set[str] = set()
        for target in plan.patch_targets:
            target_id = str(target.target_id or "").strip()
            if not target_id or target_id not in all_block_ids or target_id in seen_targets:
                continue
            seen_targets.add(target_id)
            instructions = [str(item).strip() for item in target.instructions if str(item).strip()]
            local_context = [str(item).strip() for item in target.local_context_needed if str(item).strip()]
            normalized_targets.append(
                target.model_copy(
                    update={
                        "instructions": instructions or [f"修复 {target.problem_type}，同时保持原 block 的推进功能。"],
                        "local_context_needed": local_context or list(self.DEFAULT_LOCAL_CONTEXT),
                    }
                )
            )
        unchanged_blocks = [block_id for block_id in all_block_ids if block_id not in seen_targets]
        constraints = self._dedupe_texts(plan.global_constraints) or list(self.DEFAULT_GLOBAL_CONSTRAINTS)
        return ChapterPatchPlanPayload(
            patch_targets=normalized_targets,
            unchanged_blocks=unchanged_blocks,
            global_constraints=constraints,
        ).model_dump(mode="json")

    @staticmethod
    def _load_planned_blocks(raw_blocks: object) -> list[ContentBlock]:
        if isinstance(raw_blocks, str):
            payload = json.loads(raw_blocks)
        else:
            payload = raw_blocks or {}
        items = payload.get("blocks", payload if isinstance(payload, list) else [])
        return [ContentBlock.model_validate(item) for item in items]

    @staticmethod
    def _planned_blocks_json(blocks: list[ContentBlock]) -> str:
        return json.dumps({"blocks": [block.model_dump(mode="json") for block in blocks]}, ensure_ascii=False, indent=2)

    @staticmethod
    def _json_text(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _dedupe_texts(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result
