from __future__ import annotations

from novel_flow.models.schemas import ChapterBrief, CharacterCard, SceneCard, TwistDesign


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_hidden_twist(current_chapter_id: str, twist: TwistDesign) -> bool:
    return _chapter_order(current_chapter_id) < _chapter_order(twist.reveal_at)


class CharacterContextBuilder:
    @classmethod
    def build(
        cls,
        *,
        character_cards: list[CharacterCard],
        chapter_brief: ChapterBrief,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
        forbidden: list[str] | None,
        scene_card: SceneCard,
        completed_chapter_memory_text: str,
    ) -> str:
        del completed_chapter_memory_text
        return cls._build_lines(
            character_cards=character_cards,
            chapter_brief=chapter_brief,
            current_chapter_id=current_chapter_id,
            active_twists=active_twists,
            forbidden=forbidden,
            visible_goal=scene_card.visible_goal,
        )

    @classmethod
    def build_chapter_context(
        cls,
        *,
        character_cards: list[CharacterCard],
        chapter_brief: ChapterBrief,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
    ) -> str:
        return cls._build_lines(
            character_cards=character_cards,
            chapter_brief=chapter_brief,
            current_chapter_id=current_chapter_id,
            active_twists=active_twists,
            forbidden=chapter_brief.forbidden,
            visible_goal=chapter_brief.chapter_object,
        )

    @staticmethod
    def _build_lines(
        *,
        character_cards: list[CharacterCard],
        chapter_brief: ChapterBrief,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
        forbidden: list[str] | None,
        visible_goal: str,
    ) -> str:
        focus_names = list(dict.fromkeys(name for name in chapter_brief.character_focus if str(name).strip()))
        hidden_character_names = {
            name
            for twist in active_twists
            if _is_hidden_twist(current_chapter_id, twist)
            for name in twist.related_characters
        }
        lines = ["[Scene character context]", ""]
        for name in focus_names:
            card = next((item for item in character_cards if item.name == name), None)
            if card is None:
                continue
            identity = " / ".join(
                part for part in [card.role, card.occupation, card.social_background] if str(part).strip()
            ) or "Identity should be shown naturally in-scene."
            personality = " / ".join(
                part for part in [card.personality, card.behavior_pattern] if str(part).strip()
            ) or "Restrained under pressure."
            surface_goal = card.initial_state or card.motivation or visible_goal
            visible_goal = card.initial_state or visible_goal
            internal_goal = card.motivation or card.arc or surface_goal
            is_hidden = card.name in hidden_character_names
            behavior_rules = [
                rule
                for rule in [card.behavior_pattern, f"Stay inside chapter limit: {chapter_brief.world_limit}"]
                if str(rule).strip()
            ]
            lines.extend(
                [
                    f"{card.name}",
                    f"- Public identity: {identity}",
                    f"- Current goal (internal use): {'Hidden motive exists; keep it abstract for prose layer.' if is_hidden else internal_goal}",
                    f"- Output visible goal: {visible_goal}",
                    f"- Action lane: move around '{visible_goal}' without breaking '{chapter_brief.world_limit}'.",
                    f"- Personality execution: {personality}",
                    f"- Behavioral rules: {'; '.join(behavior_rules)}",
                ]
            )
            if is_hidden:
                lines.append("- Hidden truth lock: do not state unrevealed motive, sacrifice, or final arc destination.")
                lines.append("- Allowed outer signs: pause, deflection, restraint, changed address, avoidance, incomplete answer.")
            else:
                emotional_base = card.initial_state or card.personality or "Emotion should surface through action and address."
                lines.append(f"- Emotional base tone: {emotional_base}")
            lines.append("")

        if forbidden:
            lines.append("Global chapter bans:")
            for item in forbidden:
                lines.append(f"- {item}")
        return "\n".join(lines).strip()
