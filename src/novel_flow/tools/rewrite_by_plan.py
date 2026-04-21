from __future__ import annotations

import json

from novel_flow.tools._base import LLMChapterTool


class RewriteByPlanTool(LLMChapterTool):
    name = "rewrite_by_plan"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/rewrite_by_plan.txt",
            completed_chapter_memory_text=payload["completed_chapter_memory_text"],
            step_1_story_foundation_text=payload["step_1_story_foundation_text"],
            step_2_worldbuilding_text=payload["step_2_worldbuilding_text"],
            step_3_character_packets_text=payload["step_3_character_packets_text"],
            step_4_event_timeline_text=payload["step_4_event_timeline_text"],
            step_5_character_milestones_text=payload["step_5_character_milestones_text"],
            step_6_twists_text=payload["step_6_twists_text"],
            step_7_story_lines_text=payload["step_7_story_lines_text"],
            step_8_chapter_brief_text=payload["step_8_chapter_brief_text"],
            chapter_payload_text=payload["chapter_payload_text"],
            timeline_anchor_facts_text=payload["timeline_anchor_facts_text"],
            relevant_world_rules_text=payload["relevant_world_rules_text"],
            scene_character_context_text=payload["scene_character_context_text"],
            relationship_state_text=payload["relationship_state_text"],
            style_card_text=payload["style_card_text"],
            chapter_text=payload["chapter_text"],
            current_chapter_draft_tail=payload.get("current_chapter_draft_tail", ""),
            previous_scene_tail=payload.get("previous_scene_tail", ""),
            revision_plan_json=json.dumps(payload["revision_plan"], ensure_ascii=False, indent=2),
        )
        return {"chapter_text": self.generate_text(prompt=prompt, temperature=0.55)}
