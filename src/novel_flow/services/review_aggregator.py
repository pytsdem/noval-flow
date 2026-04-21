from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import RevisionPlan


class ReviewAggregator:
    DEFAULT_HARD_CONSTRAINTS = [
        "Do not add new truths, characters, clues, or setting rules.",
        "Do not break chapter brief hard constraints or current reader belief.",
        "Do not explain allowed clues beyond what the brief permits.",
        "Do not reveal hidden twist truth before reveal_at.",
        "Keep continuity with completed chapter memory.",
    ]
    BLOCK_HARD_CONSTRAINTS = [
        "Fix only the current block.",
        "Do not add new facts, clues, reveals, or chapter-level turns.",
        "Keep the block aligned with scene_goal, must_reveal, must_hide, end_state, cost_shift, and reader_feeling_target.",
        "Keep paragraph rhythm readable for front-end display.",
        "Obey paragraph_budget and style_risk_guard while revising.",
    ]

    @classmethod
    def aggregate_block(
        cls,
        *,
        review_reports: dict[str, dict[str, Any]],
        triggered_skills: list[str],
        block_id: str,
    ) -> RevisionPlan:
        p0: list[str] = []
        p1: list[str] = []
        p2: list[str] = []
        keep: list[str] = []
        evidence_focus: list[str] = []

        for tool_name, report in review_reports.items():
            if cls._report_passes_cleanly(report):
                keep.append(f"{tool_name} passed for {block_id}; preserve the current block direction.")
                continue
            raw_issues = report.get("issues", []) or []
            for note in report.get("evidence_focus", []) or []:
                text = str(note).strip()
                if text:
                    evidence_focus.append(text)
            for issue in raw_issues:
                priority = cls._block_priority(tool_name=tool_name, issue=issue, report=report)
                cls._append_issue(issue, priority_target=cls._priority_bucket(priority, p0, p1, p2), evidence_focus=evidence_focus, fallback_tool_name=tool_name)
            guidance = str(report.get("rewrite_guidance") or "").strip()
            if guidance:
                cls._priority_bucket("p1" if tool_name == "review_block_quality" else "p0", p0, p1, p2).append(guidance)
            elif not raw_issues and not bool(report.get("passed", True)):
                cls._priority_bucket("p1" if tool_name == "review_block_quality" else "p0", p0, p1, p2).append(
                    f"{tool_name} still needs a local fix for {block_id}."
                )

        return cls._build_plan(
            scope="block",
            target_id=block_id,
            p0=p0,
            p1=p1,
            p2=p2,
            keep=keep,
            hard_constraints=cls.BLOCK_HARD_CONSTRAINTS,
            triggered_skills=triggered_skills,
            evidence_focus=evidence_focus,
        )

    @classmethod
    def aggregate_chapter(
        cls,
        *,
        review_reports: dict[str, dict[str, Any]],
        triggered_skills: list[str],
        chapter_id: str,
    ) -> RevisionPlan:
        p0: list[str] = []
        p1: list[str] = []
        p2: list[str] = []
        keep: list[str] = []
        evidence_focus: list[str] = []

        prose = review_reports.get("review_prose_quality", {})
        if prose:
            if int(prose.get("prose_score") or 0) >= 7 and int(prose.get("human_warmth_score") or 0) >= 7:
                keep.append("Preserve the stronger prose rhythm, scene texture, and human warmth already on the page.")
            for issue in prose.get("issues", []) or []:
                cls._append_issue(issue, priority_target=p2, evidence_focus=evidence_focus, fallback_tool_name="review_prose_quality")
            cls._score_to_priority(
                target=p2,
                condition=int(prose.get("prose_score") or 0) < 7,
                text=f"Raise prose control above 7/10. {str(prose.get('rewrite_guidance') or '').strip()}".strip(),
            )
            cls._score_to_priority(
                target=p2,
                condition=int(prose.get("human_warmth_score") or 0) < 7,
                text="Increase human warmth through concrete cost, bodily leakage, and self-judgment.",
            )
            cls._score_to_priority(
                target=p2,
                condition=int(prose.get("dialogue_subtext_score") or 0) < 7,
                text="Strengthen dialogue subtext so power, concealment, and misread are carried inside the spoken lines.",
            )
            cls._score_to_priority(
                target=p2,
                condition=int(prose.get("memorability_score") or 0) < 7,
                text="Make at least one beat or image linger in reader memory instead of passing as functional exposition.",
            )
            cls._score_to_priority(
                target=p2,
                condition=int(prose.get("pressure_authenticity_score") or 0) < 7,
                text="Make pressure feel earned through status, money, body, family, etiquette, or consequence.",
            )
            for note in prose.get("evidence_notes", []) or []:
                text = str(note).strip()
                if text:
                    evidence_focus.append(text)

        humanity = review_reports.get("review_humanity", {})
        if humanity:
            for issue in humanity.get("issues", []) or []:
                cls._append_issue(issue, priority_target=p2, evidence_focus=evidence_focus, fallback_tool_name="review_humanity")
            if int(humanity.get("human_warmth_score") or 0) < 7:
                p2.append("Bind major feeling to concrete cost, body reaction, daily-life loss, or self-judgment.")
            guidance = str(humanity.get("rewrite_guidance") or "").strip()
            if guidance:
                p2.append(guidance)

        for tool_name, report in review_reports.items():
            if tool_name in {"review_prose_quality", "review_humanity"}:
                continue
            if cls._report_passes_cleanly(report):
                keep.append(f"{tool_name} passed; preserve the compliant parts of the chapter.")
                continue
            raw_issues = report.get("issues", []) or []
            for note in report.get("evidence_focus", []) or []:
                text = str(note).strip()
                if text:
                    evidence_focus.append(text)
            for issue in raw_issues:
                priority = cls._chapter_priority(tool_name=tool_name, issue=issue, report=report)
                cls._append_issue(issue, priority_target=cls._priority_bucket(priority, p0, p1, p2), evidence_focus=evidence_focus, fallback_tool_name=tool_name)
            guidance = str(report.get("rewrite_guidance") or "").strip()
            if guidance:
                bucket = cls._priority_bucket("p0" if tool_name in {"review_reveal_leak", "review_plot_logic", "review_time_consistency", "review_character_integrity"} else "p1", p0, p1, p2)
                bucket.append(guidance)
            elif not raw_issues and not bool(report.get("passed", True)):
                cls._priority_bucket("p0" if tool_name in {"review_reveal_leak", "review_plot_logic", "review_time_consistency", "review_character_integrity"} else "p1", p0, p1, p2).append(
                    f"{tool_name} still needs a chapter-level fix."
                )

        return cls._build_plan(
            scope="chapter",
            target_id=chapter_id,
            p0=p0,
            p1=p1,
            p2=p2,
            keep=keep,
            hard_constraints=cls.DEFAULT_HARD_CONSTRAINTS,
            triggered_skills=triggered_skills,
            evidence_focus=evidence_focus,
        )

    @classmethod
    def _build_plan(
        cls,
        *,
        scope: str,
        target_id: str,
        p0: list[str],
        p1: list[str],
        p2: list[str],
        keep: list[str],
        hard_constraints: list[str],
        triggered_skills: list[str],
        evidence_focus: list[str],
    ) -> RevisionPlan:
        clean_p0 = cls._dedupe(p0)
        clean_p1 = cls._dedupe(p1)
        clean_p2 = cls._dedupe(p2)
        return RevisionPlan(
            scope=scope,
            target_id=target_id,
            summary=" | ".join(
                [
                    f"scope={scope}",
                    f"target={target_id or 'chapter'}",
                    f"p0={len(clean_p0)}",
                    f"p1={len(clean_p1)}",
                    f"p2={len(clean_p2)}",
                ]
            ),
            p0=clean_p0,
            p1=clean_p1,
            p2=clean_p2,
            must_fix=cls._dedupe([*clean_p0, *clean_p1]),
            should_fix=clean_p2,
            keep=cls._dedupe(keep),
            hard_constraints=list(hard_constraints),
            triggered_skills=cls._dedupe(triggered_skills),
            evidence_focus=cls._dedupe(evidence_focus),
        )

    @staticmethod
    def _report_passes_cleanly(report: dict[str, Any]) -> bool:
        if not report:
            return False
        issues = report.get("issues", []) or []
        return bool(report.get("passed", False)) and not issues

    @staticmethod
    def _priority_bucket(priority: str, p0: list[str], p1: list[str], p2: list[str]) -> list[str]:
        if priority == "p0":
            return p0
        if priority == "p1":
            return p1
        return p2

    @classmethod
    def _block_priority(cls, *, tool_name: str, issue: Any, report: dict[str, Any]) -> str:
        category = cls._issue_category(issue, tool_name)
        severity = cls._issue_severity(issue, report)
        if tool_name in {"review_reveal_leak", "review_time_consistency", "review_character_integrity"}:
            return "p0" if severity in {"critical", "high"} else "p1"
        if category in {
            "block_goal",
            "scene_goal",
            "end_state",
            "block_flat",
            "outline_prose",
            "summary_prose",
            "human_reaction_missing",
            "cost_shift_missing",
            "reader_feeling_missing",
            "clue_reveal_forced",
            "character_reentry_forced",
        }:
            return "p1"
        return "p2"

    @classmethod
    def _chapter_priority(cls, *, tool_name: str, issue: Any, report: dict[str, Any]) -> str:
        category = cls._issue_category(issue, tool_name)
        severity = cls._issue_severity(issue, report)
        if tool_name in {"review_reveal_leak", "review_plot_logic", "review_time_consistency", "review_character_integrity"}:
            return "p0" if severity in {"critical", "high"} else "p1"
        if category in {
            "instruction_violation",
            "opening_hook",
            "ending_pull",
            "chapter_object",
            "relationship_reprice",
            "emotional_turn",
            "chapter_engine",
            "character_reentry",
        }:
            return "p1"
        return "p2"

    @staticmethod
    def _issue_category(issue: Any, fallback_tool_name: str) -> str:
        if isinstance(issue, dict):
            return str(issue.get("category") or fallback_tool_name or "issue").strip()
        return fallback_tool_name or "issue"

    @staticmethod
    def _issue_severity(issue: Any, report: dict[str, Any]) -> str:
        if isinstance(issue, dict):
            return str(issue.get("severity") or report.get("level") or "medium").lower()
        return str(report.get("level") or "medium").lower()

    @classmethod
    def _append_issue(
        cls,
        issue: Any,
        *,
        priority_target: list[str],
        evidence_focus: list[str],
        fallback_tool_name: str,
    ) -> None:
        if isinstance(issue, dict):
            evidence = str(issue.get("evidence") or "").strip()
            reason = str(issue.get("reason") or "").strip()
            fix = str(issue.get("fix") or "").strip()
            category = str(issue.get("category") or fallback_tool_name or "issue").strip()
            detail = " | ".join(part for part in [evidence, reason] if part)
            if detail:
                evidence_focus.append(detail)
            text = f"[{category}] {fix or 'Fix the evidenced issue.'}"
            if detail:
                text = f"{text} Evidence: {detail}"
            priority_target.append(text)
            return

        text = str(issue).strip()
        if text:
            priority_target.append(text)

    @staticmethod
    def _score_to_priority(*, target: list[str], condition: bool, text: str) -> None:
        if condition and text.strip():
            target.append(text.strip())

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
