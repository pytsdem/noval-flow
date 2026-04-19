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
        focus_names = list(dict.fromkeys(chapter_brief.character_focus))
        hidden_character_names = {
            name
            for twist in active_twists
            if _is_hidden_twist(current_chapter_id, twist)
            for name in twist.related_characters
        }
        lines = ["【本场登场角色卡】", ""]
        for name in focus_names:
            card = next((item for item in character_cards if item.name == name), None)
            if card is None:
                continue
            lines.append(f"{card.name}：")
            identity = "，".join(
                part for part in [card.role, card.occupation, card.social_background] if str(part).strip()
            ) or "身份待在当前场景中自然显露。"
            surface_goal = card.initial_state or card.motivation or scene_card.visible_goal
            personality = "；".join(
                part for part in [card.personality, card.behavior_pattern] if str(part).strip()
            ) or "克制，不轻易明说。"
            lines.append(f"- 当前公开身份：{identity}")
            lines.append(f"- 当前表面目标：{surface_goal}")
            lines.append(f"- 当前行动方向：围绕“{scene_card.visible_goal}”行动，并受“{chapter_brief.world_limit}”限制。")
            lines.append(f"- 当前不能做：{chapter_brief.world_limit}")
            lines.append(f"- 性格执行：{personality}")
            if card.name in hidden_character_names:
                lines.append("- 当前禁止写：不能写未揭露的真实动机、真实苦衷、后期成长终点或反转真相。")
                lines.append("- 允许外显：停顿、垂眼、指尖收紧、回避旧词、答非所问。")
            else:
                emotion = card.initial_state or card.personality or "情绪通过动作和称谓外显。"
                lines.append(f"- 情绪底色：{emotion}")
            lines.append("")
        if forbidden:
            lines.append("全场统一禁写：")
            for item in forbidden:
                lines.append(f"- {item}")
        return "\n".join(lines).strip()
