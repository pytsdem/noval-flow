from __future__ import annotations

from novel_flow.tools._base import LLMChapterTool


class WriteChapterFullTool(LLMChapterTool):
    name = "write_chapter_full"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/write_chapter_full.txt",
            assistant_persona_prompt=payload.get("assistant_persona_prompt", ""),
            chapter_id=payload.get("chapter_id", ""),
            chapter_title=payload.get("chapter_title", ""),
            chapter_summary=payload.get("chapter_summary", ""),
            chapter_plan_json=payload.get("chapter_plan_json", "{}"),
            step_1_to_7_outputs_json=payload.get("step_1_to_7_outputs_json", "{}"),
            chapter_payload_text=payload.get("chapter_payload_text", ""),
            timeline_anchor_facts_text=payload.get("timeline_anchor_facts_text", ""),
            scene_character_context_text=payload.get("scene_character_context_text", ""),
            relationship_state_text=payload.get("relationship_state_text", ""),
            chapter_character_mindsets_text=payload.get("chapter_character_mindsets_text", ""),
            style_card_text=payload.get("style_card_text", ""),
            previous_chapter_full_text=payload.get("previous_chapter_full_text", ""),
            completed_chapter_summary_bundle=payload.get("completed_chapter_summary_bundle", ""),
            writing_requirements_json=payload.get("writing_requirements_json", "{}"),
            reference_pack=payload.get("reference_pack", ""),
        )
        return {"chapter_text": self.generate_text(prompt=prompt, temperature=0.65)}
