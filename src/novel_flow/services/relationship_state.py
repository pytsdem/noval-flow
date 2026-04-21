from __future__ import annotations

from novel_flow.models.schemas import ActualChapterSummary, ChapterBrief, SceneCard


class RelationshipStateBuilder:
    @classmethod
    def build(
        cls,
        *,
        completed_chapter_memory_text: str,
        chapter_brief: ChapterBrief,
        scene_card: SceneCard,
        actual_summaries: list[ActualChapterSummary] | None = None,
    ) -> str:
        del completed_chapter_memory_text
        return cls._build_lines(
            chapter_brief=chapter_brief,
            actual_summaries=actual_summaries,
            exit_target=scene_card.exit_state,
        )

    @classmethod
    def build_chapter_state(
        cls,
        *,
        chapter_brief: ChapterBrief,
        actual_summaries: list[ActualChapterSummary] | None = None,
    ) -> str:
        return cls._build_lines(
            chapter_brief=chapter_brief,
            actual_summaries=actual_summaries,
            exit_target=chapter_brief.emotional_turn,
        )

    @staticmethod
    def _build_lines(
        *,
        chapter_brief: ChapterBrief,
        actual_summaries: list[ActualChapterSummary] | None,
        exit_target: str,
    ) -> str:
        focus = [name for name in chapter_brief.character_focus if str(name).strip()]
        lines = ["[Relationship state]", ""]
        if len(focus) >= 2:
            center = focus[0]
            for other in focus[1:]:
                lines.extend(
                    [
                        f"{center} -> {other}",
                        f"- Current public relationship: {chapter_brief.relationship_reprice}",
                        f"- Emotional temperature: {chapter_brief.emotional_turn}",
                        f"- This chapter should move toward: {exit_target}",
                        "- Forbidden shortcut: do not skip misreading, cost, or unrevealed truth.",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    f"- Relationship axis: {chapter_brief.relationship_reprice}",
                    f"- Emotional temperature: {chapter_brief.emotional_turn}",
                    f"- This chapter should move toward: {exit_target}",
                    "",
                ]
            )
        if actual_summaries:
            latest = actual_summaries[-1]
            if latest.relationship_state:
                lines.append("Carry-over from previous chapter:")
                for item in latest.relationship_state[:3]:
                    lines.append(f"- {item}")
        return "\n".join(lines).strip()
