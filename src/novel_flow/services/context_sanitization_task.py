from __future__ import annotations

import json
from dataclasses import replace

from novel_flow.models.schemas import ContextSanitizationPayload, TwistDesign, WriterContext
from novel_flow.tools._base import LLMChapterTool


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_hidden(current_chapter_id: str, twist: TwistDesign) -> bool:
    return _chapter_order(current_chapter_id) < _chapter_order(twist.reveal_at)


class ContextSanitizationTask(LLMChapterTool):
    def sanitize_writer_context(
        self,
        *,
        writer_context: WriterContext,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
    ) -> WriterContext:
        hidden_twists = [twist for twist in active_twists if _is_hidden(current_chapter_id, twist)]
        if not hidden_twists:
            return writer_context

        prompt = self.render_prompt(
            "writer/context_sanitization.txt",
            current_chapter_id=current_chapter_id,
            active_twists_json=json.dumps([item.model_dump(mode="json") for item in hidden_twists], ensure_ascii=False, indent=2),
            completed_chapter_memory_text=writer_context.completed_chapter_memory_text,
            step_1_story_foundation_text=writer_context.step_1_story_foundation_text,
            step_3_character_packets_text=writer_context.step_3_character_packets_text,
            step_5_character_milestones_text=writer_context.step_5_character_milestones_text,
            step_6_twists_text=writer_context.step_6_twists_text,
            step_7_story_lines_text=writer_context.step_7_story_lines_text,
            step_8_chapter_brief_text=writer_context.step_8_chapter_brief_text,
            scene_character_context_text=writer_context.scene_character_context_text,
            relationship_state_text=writer_context.relationship_state_text,
        )
        payload = self.generate_json(
            prompt=prompt,
            schema_name="context_sanitization",
            schema_model=ContextSanitizationPayload,
        )
        return replace(
            writer_context,
            completed_chapter_memory_text=payload["completed_chapter_memory_text"],
            step_1_story_foundation_text=payload["step_1_story_foundation_text"],
            step_3_character_packets_text=payload["step_3_character_packets_text"],
            step_5_character_milestones_text=payload["step_5_character_milestones_text"],
            step_6_twists_text=payload["step_6_twists_text"],
            step_7_story_lines_text=payload["step_7_story_lines_text"],
            step_8_chapter_brief_text=payload["step_8_chapter_brief_text"],
            scene_character_context_text=payload["scene_character_context_text"],
            relationship_state_text=payload["relationship_state_text"],
        )
