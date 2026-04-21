from __future__ import annotations

import json

from novel_flow.models.schemas import ChapterBrief, ContentBlockPlanPayload
from novel_flow.tools._base import LLMChapterTool


class PlanContentBlocksTool(LLMChapterTool):
    name = "plan_content_blocks"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        chapter_brief = ChapterBrief.model_validate(json.loads(str(payload["chapter_brief_json"])))
        base_id = f"{chapter_brief.chapter_id}.sc_001"
        focus_characters = list(chapter_brief.character_focus or [])
        active_lines = list(chapter_brief.active_lines or [])
        active_twists = list(chapter_brief.active_twists or [])
        forbidden = list(chapter_brief.forbidden or [])
        clues = list(chapter_brief.allowed_clues or [])
        blocks = [
            {
                "block_id": f"{base_id}.b001",
                "chapter_id": chapter_brief.chapter_id,
                "block_index": 1,
                "purpose": f"用开场压力把读者带入本章，并落下开场钩子：{chapter_brief.opening_hook}",
                "characters": focus_characters,
                "active_lines": active_lines,
                "active_twists": active_twists,
                "scene_goal": chapter_brief.summary,
                "must_reveal": [chapter_brief.opening_hook],
                "must_hide": forbidden[:3],
                "emotional_tone": chapter_brief.reader_emotion,
                "end_state": "开场局面成立，人物被迫进入本章主压力。",
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": f"{base_id}.b002",
                "chapter_id": chapter_brief.chapter_id,
                "block_index": 2,
                "purpose": f"围绕章节目标物或行动抓手推进：{chapter_brief.chapter_object}",
                "characters": focus_characters,
                "active_lines": active_lines,
                "active_twists": active_twists,
                "scene_goal": chapter_brief.chapter_object,
                "must_reveal": [chapter_brief.chapter_object, chapter_brief.small_payoff],
                "must_hide": forbidden[:3],
                "emotional_tone": chapter_brief.emotional_turn,
                "end_state": "人物抓住一个具体推进抓手，局面比开场更难退回原状。",
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": f"{base_id}.b003",
                "chapter_id": chapter_brief.chapter_id,
                "block_index": 3,
                "purpose": f"完成情绪翻转和关系重估：{chapter_brief.relationship_reprice}",
                "characters": focus_characters,
                "active_lines": active_lines,
                "active_twists": active_twists,
                "scene_goal": chapter_brief.character_shift,
                "must_reveal": [chapter_brief.character_shift, chapter_brief.relationship_reprice, *clues[:2]],
                "must_hide": forbidden[:3],
                "emotional_tone": chapter_brief.emotional_turn,
                "end_state": "角色立场或关系定价发生可感知变化。",
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": f"{base_id}.b004",
                "chapter_id": chapter_brief.chapter_id,
                "block_index": 4,
                "purpose": f"以结尾拉力收束本章，抛出下一章牵引：{chapter_brief.ending_pull}",
                "characters": focus_characters,
                "active_lines": active_lines,
                "active_twists": active_twists,
                "scene_goal": chapter_brief.ending_pull,
                "must_reveal": [chapter_brief.ending_pull],
                "must_hide": forbidden[:3],
                "emotional_tone": chapter_brief.reader_emotion,
                "end_state": "章节在新的不稳定点上收束，读者被自然牵向下一章。",
                "text": "",
                "status": "draft",
                "version": 1,
            },
        ]
        return ContentBlockPlanPayload.model_validate({"blocks": blocks}).model_dump(mode="json")
