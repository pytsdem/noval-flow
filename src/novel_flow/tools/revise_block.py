from __future__ import annotations

from novel_flow.tools._base import LLMChapterTool


class ReviseBlockTool(LLMChapterTool):
    name = "revise_block_if_needed"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/revise_content_block.txt",
            chapter_goal=payload.get("chapter_goal", ""),
            hard_facts=payload.get("hard_facts", ""),
            character_state=payload.get("character_state", ""),
            beat=payload.get("beat", "{}"),
            previous_text_tail=payload.get("previous_text_tail", ""),
            chapter_so_far=payload.get("chapter_so_far", ""),
            style_rules=payload.get("style_rules", ""),
            target_length=payload.get("target_length", ""),
            block_text=payload["block_text"],
            review_json=payload["review_json"],
            block_revision_plan_json=payload.get("block_revision_plan_json", "{}"),
        )
        return {"block_text": self.generate_text(prompt=prompt, temperature=0.45)}
