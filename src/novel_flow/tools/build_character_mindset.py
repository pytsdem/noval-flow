from __future__ import annotations

from novel_flow.models.schemas import CharacterMindset
from novel_flow.tools._base import LLMChapterTool


class BuildCharacterMindsetTool(LLMChapterTool):
    name = "build_character_mindset"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/build_character_mindset.txt",
            current_character_mindset_json=payload.get("current_character_mindset_json", "{}"),
            character_card_json=payload.get("character_card_json", "{}"),
            step_1_story_foundation_text=payload.get("step_1_story_foundation_text", ""),
            step_2_worldbuilding_text=payload.get("step_2_worldbuilding_text", ""),
            step_3_character_packets_text=payload.get("step_3_character_packets_text", ""),
            step_4_event_timeline_text=payload.get("step_4_event_timeline_text", ""),
            step_5_scoped_text=payload.get("step_5_scoped_text", ""),
            step_6_scoped_text=payload.get("step_6_scoped_text", ""),
            step_7_story_lines_text=payload.get("step_7_story_lines_text", ""),
            step_8_chapter_brief_text=payload.get("step_8_chapter_brief_text", ""),
        )
        raw = self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=CharacterMindset,
        )
        mindset = CharacterMindset.model_validate(raw)
        character_name = str(payload.get("character_name") or mindset.character_name or "").strip()
        character_id = str(payload.get("character_id") or mindset.character_id or character_name).strip()
        return mindset.model_copy(
            update={
                "character_name": character_name or mindset.character_name,
                "character_id": character_id or mindset.character_id,
            }
        ).model_dump(mode="json")
