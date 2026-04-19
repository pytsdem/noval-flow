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
        focus = [name for name in chapter_brief.character_focus if str(name).strip()]
        lines = ["【本场关系状态】", ""]
        if len(focus) >= 2:
            center = focus[0]
            for other in focus[1:]:
                lines.extend(
                    [
                        f"{center} ↔ {other}：",
                        f"- 当前公开关系：围绕“{chapter_brief.relationship_reprice}”重新定价。",
                        f"- 当前关系温度：{chapter_brief.emotional_turn}",
                        f"- 本场变化目标：{scene_card.exit_state}",
                        f"- 禁止变化：不得跳过误会，不得直接说破未揭露真相。",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    f"- 关系主轴：{chapter_brief.relationship_reprice}",
                    f"- 情绪温度：{chapter_brief.emotional_turn}",
                    f"- 本场变化目标：{scene_card.exit_state}",
                    "",
                ]
            )
        if actual_summaries:
            latest = actual_summaries[-1]
            if latest.relationship_state:
                lines.append("上一章关系余波：")
                for item in latest.relationship_state[:3]:
                    lines.append(f"- {item}")
        return "\n".join(lines).strip()
