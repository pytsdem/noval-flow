from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from novel_flow.models.schemas import ChapterBrief
from novel_flow.services.skill_registry import SkillDefinition, SkillRegistry


StageName = Literal["block", "chapter", "finalize"]


@dataclass
class SkillManager:
    registry: SkillRegistry

    BLOCK_SKILLS = ("base_style", "reveal_guard", "character_integrity", "time_consistency_guard")
    CHAPTER_DEFAULT_SKILLS = ("base_style", "chapter_quality_guard")
    FINAL_SKILLS = ("chapter_finalize",)
    CHAPTER_OPTIONAL_SKILLS = (
        "prose_improvement",
        "humanity_boost",
        "opening_boost",
        "reveal_guard",
        "plot_guard",
        "clue_consistency",
        "flashback_guard",
    )

    def initial_skills(self, *, stage: StageName = "chapter") -> list[SkillDefinition]:
        if stage == "block":
            return self._definitions(self.BLOCK_SKILLS)
        if stage == "finalize":
            return self._definitions([*self.CHAPTER_DEFAULT_SKILLS, *self.FINAL_SKILLS])
        return self._definitions(self.CHAPTER_DEFAULT_SKILLS)

    def finalize_skills(self) -> list[SkillDefinition]:
        return self.initial_skills(stage="finalize")

    def discover(
        self,
        *,
        chapter_brief: ChapterBrief,
        review_reports: dict[str, dict[str, Any]],
        stage: StageName = "chapter",
    ) -> list[SkillDefinition]:
        if stage == "block":
            return self.initial_skills(stage="block")

        skill_ids = list(self.CHAPTER_DEFAULT_SKILLS)

        prose = review_reports.get("review_prose_quality", {})
        if (
            int(prose.get("prose_score") or 0) < 7
            or int(prose.get("tension_score") or 0) < 7
            or int(prose.get("memorability_score") or 0) < 7
            or int(prose.get("pressure_authenticity_score") or 0) < 7
            or int(prose.get("exposition_score") or 10) > 4
            or bool(prose.get("rewrite_needed"))
        ):
            skill_ids.append("prose_improvement")

        humanity = review_reports.get("review_humanity", {})
        if not bool(humanity.get("passed", True)) or int(humanity.get("human_warmth_score") or 0) < 7:
            skill_ids.append("humanity_boost")

        engine = review_reports.get("review_chapter_engine", {})
        engine_issue_text = " ".join(
            str(item.get("category") or item.get("evidence") or item.get("reason") or item)
            if isinstance(item, dict)
            else str(item)
            for item in engine.get("issues", []) or []
        ).lower()
        if chapter_brief.chapter_type == "opening" and (
            "opening" in engine_issue_text
            or "ending" in engine_issue_text
            or "pull" in engine_issue_text
            or not bool(engine.get("passed", True))
        ):
            skill_ids.append("opening_boost")

        reveal = review_reports.get("review_reveal_leak", {})
        if not bool(reveal.get("passed", True)) or str(reveal.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("reveal_guard")

        plot = review_reports.get("review_plot_logic", {})
        if not bool(plot.get("passed", True)) or str(plot.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("plot_guard")

        clue = review_reports.get("review_clue_origin", {})
        if not bool(clue.get("passed", True)) or str(clue.get("level") or "").lower() in {"high", "critical"}:
            skill_ids.append("clue_consistency")

        if "flashback" in engine_issue_text or "backstory" in engine_issue_text:
            skill_ids.append("flashback_guard")

        ordered_ids = [skill_id for skill_id in skill_ids if skill_id in {*self.CHAPTER_DEFAULT_SKILLS, *self.CHAPTER_OPTIONAL_SKILLS}]
        return self._definitions(ordered_ids)

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
