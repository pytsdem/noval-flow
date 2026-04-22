from __future__ import annotations

from typing import Any, Sequence

from novel_flow.models.schemas import CharacterMindset


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


class CharacterMindsetFormatter:
    @staticmethod
    def format_text(character_mindsets: Sequence[CharacterMindset]) -> str:
        lines = ["[Chapter character mindsets]"]
        if not character_mindsets:
            lines.append("No chapter character mindsets generated.")
            return "\n".join(lines).strip()

        for mindset in character_mindsets:
            attitudes = dict(mindset.attitude_to_key_others or {})
            lines.extend(
                [
                    "",
                    f"{mindset.character_name} / {mindset.character_id}",
                    f"- Surface emotion: {mindset.surface_emotion}",
                    f"- Core emotion: {mindset.core_emotion}",
                    f"- Primary goal: {mindset.primary_goal}",
                    f"- Hidden need: {mindset.hidden_need}",
                    f"- Fear: {mindset.fear}",
                    f"- Self control: {mindset.self_control_level}",
                    f"- Breaking point hint: {mindset.breaking_point_hint}",
                    f"- Known but unspoken: {mindset.known_but_unspoken}",
                    f"- Misbelief: {mindset.misbelief}",
                    f"- Chapter change hint: {mindset.chapter_change_hint}",
                ]
            )
            if attitudes:
                lines.append("- Attitude to key others:")
                for other_id, attitude in attitudes.items():
                    clean_id = _normalize_text(other_id)
                    clean_attitude = _normalize_text(attitude)
                    if clean_id and clean_attitude:
                        lines.append(f"  - {clean_id}: {clean_attitude}")
        return "\n".join(lines).strip()
