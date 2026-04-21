from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import DynamicInstructionPayload, RevisionPlan


class DynamicInstructionBuilder:
    @classmethod
    def build(
        cls,
        *,
        review_reports: dict[str, dict[str, Any]],
        revision_plan: RevisionPlan,
        active_skill_ids: list[str] | None = None,
    ) -> DynamicInstructionPayload:
        focus: list[str] = []
        must_fix = list(revision_plan.must_fix[:6])
        skills = list(active_skill_ids or revision_plan.triggered_skills)
        tone_adjustment = (
            "Keep the prose in natural Simplified Chinese, reduce explanation-first writing, "
            "and push pressure onto concrete reaction, cost, and relationship friction."
        )
        scene_strategy_parts: list[str] = []

        engine = review_reports.get("review_chapter_engine", {})
        if cls._has_issues(engine):
            focus.append("Make the opening hook, chapter object, relationship reprice, and ending pull land on the page instead of in summary.")
            scene_strategy_parts.append("Let the chapter object do double duty: move plot while changing relationship pressure or clue value.")
            scene_strategy_parts.append("If an important character re-enters, use recognition signals and the character's current concern instead of re-introducing identity.")

        humanity = review_reports.get("review_humanity", {})
        if cls._has_issues(humanity):
            focus.append("Translate abstract feeling into concrete cost, bodily leakage, private self-judgment, or a supporting character's reaction.")
            scene_strategy_parts.append("Every major emotional beat should cost someone something visible in status, body, money, choice, or family.")

        prose = review_reports.get("review_prose_quality", {})
        if int(prose.get("scene_texture_score") or 0) < 7:
            focus.append("Add selective scene texture through labor, etiquette, objects, weather, money, and bodily strain.")
        if int(prose.get("dialogue_subtext_score") or 0) < 7:
            focus.append("Let dialogue carry concealment, testing, status, and the part that cannot be said directly.")
        if int(prose.get("memorability_score") or 0) < 7:
            focus.append("Sharpen one or two details or reaction beats so the chapter leaves a residue in memory.")
        if int(prose.get("pressure_authenticity_score") or 0) < 7:
            focus.append("Make pressure feel real by tying it to institutional rules, livelihood, body state, or social consequence.")

        plot = review_reports.get("review_plot_logic", {})
        if cls._has_issues(plot):
            focus.append("Repair the causal chain so turns come from visible triggers, compromises, or costs rather than author convenience.")
            scene_strategy_parts.append("When a risky move happens, show the trigger and the price before the result lands.")

        clue = review_reports.get("review_clue_origin", {})
        if cls._has_issues(clue):
            focus.append("Reveal important clues through pressure, avoidance, and visible slips instead of author-arranged information drops.")
            scene_strategy_parts.append("Let clue exposure pass through relationship pressure, evasion, bodily leakage, or object mishandling before anyone tries to explain it.")

        if not focus:
            focus.append("Keep the current direction, but preserve the chapter's strongest pressure, human texture, and forward pull.")

        return DynamicInstructionPayload(
            focus=cls._dedupe(focus),
            skills_to_emphasize=cls._dedupe(skills),
            must_fix=cls._dedupe(must_fix),
            tone_adjustment=tone_adjustment,
            scene_strategy=" ".join(scene_strategy_parts).strip() or "Revise only where the chapter revision plan points; do not expand hidden truth or extra exposition.",
        )

    @staticmethod
    def _has_issues(report: dict[str, Any]) -> bool:
        if not report:
            return False
        if not bool(report.get("passed", True)):
            return True
        return bool(report.get("issues"))

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result
