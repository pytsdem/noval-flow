from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_flow.models.schemas import ChapterBrief
from novel_flow.services.skill_registry import SkillDefinition, SkillRegistry


@dataclass
class SkillManager:
    registry: SkillRegistry

    DEFAULT_SKILLS = ("base_style", "chapter_quality_guard")
    FINAL_SKILLS = ("chapter_finalize",)

    def initial_skills(self) -> list[SkillDefinition]:
        return self._definitions(self.DEFAULT_SKILLS)

    def finalize_skills(self) -> list[SkillDefinition]:
        return self._definitions([*self.DEFAULT_SKILLS, *self.FINAL_SKILLS])

    def discover(self, *, chapter_brief: ChapterBrief, review_reports: dict[str, dict[str, Any]]) -> list[SkillDefinition]:
        skill_ids = list(self.DEFAULT_SKILLS)

        prose = review_reports.get("review_prose_quality", {})
        if (
            int(prose.get("prose_score") or 0) < 7
            or int(prose.get("tension_score") or 0) < 7
            or int(prose.get("exposition_score") or 10) > 4
            or bool(prose.get("rewrite_needed"))
        ):
            skill_ids.append("prose_improvement")

        reveal = review_reports.get("review_reveal_leak", {})
        if not bool(reveal.get("passed", True)) or str(reveal.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("reveal_guard")

        plot = review_reports.get("review_plot_logic", {})
        if not bool(plot.get("passed", True)) or str(plot.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("plot_guard")

        clue = review_reports.get("review_clue_origin", {})
        if not bool(clue.get("passed", True)) or str(clue.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("clue_consistency")

        engine = review_reports.get("review_chapter_engine", {})
        engine_issue_text = " ".join(str(item) for item in engine.get("issues", []) or []).lower()
        if chapter_brief.chapter_type == "opening" and (
            "opening" in engine_issue_text or int(prose.get("tension_score") or 0) < 7
        ):
            skill_ids.append("opening_boost")
        if "flashback" in engine_issue_text or "backstory" in engine_issue_text:
            skill_ids.append("flashback_guard")

        return self._definitions(skill_ids)

    @staticmethod
    def format_for_model(skills: list[SkillDefinition]) -> str:
        blocks: list[str] = []
        for skill in skills:
            blocks.extend(
                [
                    f"[Skill] {skill.skill_id}",
                    f"Tools: {', '.join(skill.tools) or 'None'}",
                    f"Triggers: {', '.join(skill.triggers) or 'Always on'}",
                    f"Success condition: {skill.success_condition}",
                    f"Max iterations: {skill.max_iterations}",
                    skill.instruction_text,
                    "",
                ]
            )
        return "\n".join(blocks).strip()

    @staticmethod
    def recommended_tools(skills: list[SkillDefinition]) -> list[str]:
        ordered: list[str] = []
        for skill in skills:
            for tool_name in skill.tools:
                if tool_name not in ordered:
                    ordered.append(tool_name)
        return ordered

    def _definitions(self, skill_ids: list[str] | tuple[str, ...]) -> list[SkillDefinition]:
        seen: set[str] = set()
        results: list[SkillDefinition] = []
        for skill_id in skill_ids:
            if skill_id in seen:
                continue
            try:
                skill = self.registry.get(skill_id)
            except KeyError:
                continue
            seen.add(skill_id)
            results.append(skill)
        return results
