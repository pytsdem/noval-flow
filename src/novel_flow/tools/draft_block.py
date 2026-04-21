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
            scene_character_context_text=payload["scene_character_context_text"],
            relationship_state_text=payload["relationship_state_text"],
            block_card_text=payload["block_card_text"],
            prior_block_summary_text=payload.get("prior_block_summary_text", ""),
            prior_chapter_text_tail=payload.get("prior_chapter_text_tail", ""),
            style_card_text=payload["style_card_text"],
        )
        return {"block_text": self.generate_text(prompt=prompt, temperature=0.6)}
