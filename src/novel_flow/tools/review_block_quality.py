from __future__ import annotations

from novel_flow.models.schemas import BlockQualityReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewBlockQualityTool(LLMChapterTool):
    name = "review_block_quality"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/review_block_quality.txt",
            chapter_payload_text=payload.get("chapter_payload_text", ""),
            relevant_world_rules_text=payload.get("relevant_world_rules_text", ""),
            scene_character_context_text=payload.get("scene_character_context_text", ""),
            relationship_state_text=payload.get("relationship_state_text", ""),
            current_chapter_written_blocks_json=payload.get("current_chapter_written_blocks_json", "[]"),
            current_chapter_draft_tail=payload.get("current_chapter_draft_tail", ""),
            block_card_text=payload.get("block_card_text", ""),
            prior_block_summary_text=payload.get("prior_block_summary_text", ""),
            prior_chapter_text_tail=payload.get("prior_chapter_text_tail", ""),
            block_text=payload.get("block_text", ""),
            human_reaction_target=payload.get("human_reaction_target", "[]"),
            cost_shift=payload.get("cost_shift", ""),
            reader_feeling_target=payload.get("reader_feeling_target", ""),
            paragraph_budget=payload.get("paragraph_budget", ""),
            paragraph_shape=payload.get("paragraph_shape", "[]"),
            character_anchor_line=payload.get("character_anchor_line", ""),
            style_risk_guard=payload.get("style_risk_guard", "[]"),
            clue_reveal_mechanism=payload.get("clue_reveal_mechanism", ""),
            character_reentry_mode=payload.get("character_reentry_mode", ""),
        )
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=BlockQualityReviewPayload,
        )
