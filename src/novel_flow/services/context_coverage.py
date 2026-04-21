from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import ChapterBrief, CharacterCard, StoryPremise


class WriterContextCoverageValidator:
    @classmethod
    def validate(
        cls,
        *,
        chapter_brief: ChapterBrief,
        premise: StoryPremise | None,
        story_blueprint: dict[str, Any] | None,
        character_cards: list[CharacterCard],
        character_milestones: list[dict[str, Any]],
    ) -> list[str]:
        issues: list[str] = []
        if premise is None:
            issues.append("缺少 step1 premise。")
        story_blueprint = story_blueprint or {}
        if not isinstance(story_blueprint.get("story_engine"), dict) or not story_blueprint.get("story_engine"):
            issues.append("缺少 step2 story_engine。")
        event_timeline = story_blueprint.get("event_timeline", [])
        if not isinstance(event_timeline, list) or not event_timeline:
            issues.append("缺少 step4 event_timeline。")

        focus_names = [str(name or "").strip() for name in chapter_brief.character_focus if str(name or "").strip()]
        card_names = {card.name for card in character_cards if str(card.name or "").strip()}
        milestone_names = {
            str(item.get("character_name") or "").strip()
            for item in character_milestones
            if isinstance(item, dict) and str(item.get("character_name") or "").strip()
        }
        missing_cards = [name for name in focus_names if name not in card_names]
        missing_milestones = [name for name in focus_names if name not in milestone_names]
        if missing_cards:
            issues.append(f"step3 缺少当前章节角色卡：{', '.join(missing_cards)}")
        if missing_milestones:
            issues.append(f"step5 缺少当前章节角色发展线：{', '.join(missing_milestones)}")

        if chapter_brief.active_twists:
            twists = story_blueprint.get("twist_designs", [])
            twist_ids = {
                str(item.get("twist_id") or "").strip()
                for item in twists
                if isinstance(item, dict) and str(item.get("twist_id") or "").strip()
            }
            missing = [twist_id for twist_id in chapter_brief.active_twists if twist_id not in twist_ids]
            if missing:
                issues.append(f"step6 缺少当前章节激活反转：{', '.join(missing)}")

        if chapter_brief.active_lines:
            lines = story_blueprint.get("story_lines", [])
            line_ids = {
                str(item.get("line_id") or "").strip()
                for item in lines
                if isinstance(item, dict) and str(item.get("line_id") or "").strip()
            }
            missing = [line_id for line_id in chapter_brief.active_lines if line_id not in line_ids]
            if missing:
                issues.append(f"step7 缺少当前章节激活故事线：{', '.join(missing)}")
        return issues
