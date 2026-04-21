from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import FinalJudgeResult


class FinalJudgeTool:
    name = "final_judge"

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        review_reports = dict(payload.get("review_reports", {}) or {})
        prose = review_reports.get("review_prose_quality", {})
        instruction = review_reports.get("review_instruction_compliance", {})
        continuity = review_reports.get("review_continuity", {})
        reveal = review_reports.get("review_reveal_leak", {})
        plot = review_reports.get("review_plot_logic", {})
        clue = review_reports.get("review_clue_origin", {})

        blocking_reasons: list[str] = []
        for tool_name, report in review_reports.items():
            if str(report.get("level") or "").lower() == "critical":
                blocking_reasons.append(f"{tool_name} has critical issues.")

        if str(reveal.get("level") or "").lower() == "high":
            blocking_reasons.append("Reveal leak remains high risk.")
        if str(plot.get("level") or "").lower() == "high":
            blocking_reasons.append("Plot logic remains high risk.")
        if str(clue.get("level") or "").lower() == "high":
            blocking_reasons.append("Clue origin remains high risk.")
        if not bool(instruction.get("passed", False)):
            blocking_reasons.append("Instruction compliance did not pass.")
        if not bool(continuity.get("passed", False)):
            blocking_reasons.append("Continuity did not pass.")
        if int(prose.get("prose_score") or 0) < 7:
            blocking_reasons.append("Prose score is below 7.")
        if int(prose.get("tension_score") or 0) < 7:
            blocking_reasons.append("Tension score is below 7.")
        if int(prose.get("exposition_score") or 10) > 4:
            blocking_reasons.append("Exposition score is above 4.")

        result = FinalJudgeResult(
            passed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            metrics={
                "instruction_passed": bool(instruction.get("passed", False)),
                "continuity_passed": bool(continuity.get("passed", False)),
                "reveal_level": str(reveal.get("level") or ""),
                "plot_level": str(plot.get("level") or ""),
                "clue_level": str(clue.get("level") or ""),
                "prose_score": int(prose.get("prose_score") or 0),
                "tension_score": int(prose.get("tension_score") or 0),
                "exposition_score": int(prose.get("exposition_score") or 10),
            },
        )
        return result.model_dump(mode="json")
