from __future__ import annotations

from novel_flow.tools._base import LLMChapterTool


class ReviseBlockTool(LLMChapterTool):
    name = "revise_block_if_needed"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/revise_content_block.txt",
            chapter_payload_text=payload["chapter_payload_text"],
            relevant_world_rules_text=payload["relevant_world_rules_text"],
            scene_character_context_text=payload["scene_character_context_text"],
            relationship_state_text=payload["relationship_state_text"],
            block_card_text=payload["block_card_text"],
            block_text=payload["block_text"],
            review_json=payload["review_json"],
            block_revision_plan_json=payload.get("block_revision_plan_json", "{}"),
            prior_chapter_text_tail=payload.get("prior_chapter_text_tail", ""),
            style_card_text=payload["style_card_text"],
            loaded_skill_instructions_text=payload.get("loaded_skill_instructions_text", ""),
        )
        return {"block_text": self.generate_text(prompt=prompt, temperature=0.45)}
