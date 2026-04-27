from __future__ import annotations

from novel_flow.tools._base import LLMChapterTool


class DraftBlockTool(LLMChapterTool):
    name = "draft_block"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/draft_content_block.txt",
            completed_chapter_memory_text=payload["completed_chapter_memory_text"],
            chapter_payload_text=payload["chapter_payload_text"],
            relevant_world_rules_text=payload["relevant_world_rules_text"],
            assistant_persona_prompt=payload.get("assistant_persona_prompt", ""),
            writing_requirements_json=payload.get("writing_requirements_json", "{}"),
            scene_character_context_text=payload["scene_character_context_text"],
            relationship_state_text=payload["relationship_state_text"],
            chapter_character_mindsets_text=payload.get("chapter_character_mindsets_text", ""),
            current_chapter_written_blocks_json=payload.get("current_chapter_written_blocks_json", "[]"),
            current_chapter_draft_tail=payload.get("current_chapter_draft_tail", ""),
            block_card_text=payload["block_card_text"],
            prior_block_summary_text=payload.get("prior_block_summary_text", ""),
            delivered_beat_summary_text=payload.get("delivered_beat_summary_text", ""),
            prior_chapter_text_tail=payload.get("prior_chapter_text_tail", ""),
            human_reaction_target=payload.get("human_reaction_target", "[]"),
            cost_shift=payload.get("cost_shift", ""),
            reader_feeling_target=payload.get("reader_feeling_target", ""),
            paragraph_budget=payload.get("paragraph_budget", ""),
            micro_hook=payload.get("micro_hook", ""),
            turn_type=payload.get("turn_type", ""),
            paragraph_shape=payload.get("paragraph_shape", "[]"),
            character_anchor_line=payload.get("character_anchor_line", ""),
            style_risk_guard=payload.get("style_risk_guard", "[]"),
            clue_reveal_mechanism=payload.get("clue_reveal_mechanism", ""),
            character_reentry_mode=payload.get("character_reentry_mode", ""),
            style_card_text=payload["style_card_text"],
            loaded_skill_instructions_text=payload.get("loaded_skill_instructions_text", ""),
        )
        return {"block_text": self.generate_text(prompt=prompt, temperature=0.6)}
