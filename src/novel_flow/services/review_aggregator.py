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

    @classmethod
    def aggregate(
        cls,
        *,
        review_reports: dict[str, dict[str, Any]],
        triggered_skills: list[str],
    ) -> RevisionPlan:
        must_fix: list[str] = []
        should_fix: list[str] = []
        keep: list[str] = []
        evidence_focus: list[str] = []

        for tool_name, report in review_reports.items():
            if tool_name == "review_prose_quality":
                prose_score = int(report.get("prose_score") or 0)
                tension_score = int(report.get("tension_score") or 0)
                exposition_score = int(report.get("exposition_score") or 10)
                evidence_focus.extend(str(item).strip() for item in report.get("evidence_notes", []) or [] if str(item).strip())
                if prose_score >= 7 and tension_score >= 7 and exposition_score <= 4:
                    keep.append("Preserve the stronger prose rhythm and chapter pressure already achieved.")
                if prose_score < 7:
                    must_fix.append(f"Raise prose quality to at least 7/10. Guidance: {report.get('rewrite_guidance') or 'Tighten prose.'}")
                if tension_score < 7:
                    must_fix.append(f"Raise tension to at least 7/10. Guidance: {report.get('rewrite_guidance') or 'Increase pressure and consequences.'}")
                if exposition_score > 4:
                    must_fix.append(f"Reduce exposition to 4/10 or below. Guidance: {report.get('rewrite_guidance') or 'Cut explanation.'}")
                if int(report.get("human_warmth_score") or 0) < 7:
                    must_fix.append("Increase human warmth with concrete life cost, bodily leakage, and specific self-judgment.")
                continue

            if tool_name == "review_humanity":
                if int(report.get("human_warmth_score") or 0) < 7:
                    must_fix.append("Raise humanity so emotion lands on concrete cost, bodily response, and recognizably human thought.")
                for issue in report.get("issues", []) or []:
                    cls._append_issue(issue, must_fix, should_fix, evidence_focus)
                guidance = str(report.get("rewrite_guidance") or "").strip()
                if guidance:
                    should_fix.append(guidance)
                continue

            raw_issues = report.get("issues", []) or []
            level = str(report.get("level") or "medium").lower()
            passed = bool(report.get("passed", False))
            guidance = str(report.get("rewrite_guidance") or "").strip()
            if passed and not raw_issues:
                keep.append(f"{tool_name} passed; preserve the compliant parts.")
                continue
            if raw_issues:
                for issue in raw_issues:
                    cls._append_issue(issue, must_fix, should_fix, evidence_focus, fallback_level=level, fallback_tool_name=tool_name)
            elif guidance:
                (must_fix if level in {"critical", "high"} or not passed else should_fix).append(guidance)
            elif not passed:
                (must_fix if level in {"critical", "high"} or not passed else should_fix).append(f"{tool_name} still fails and needs revision.")

        summary_parts = [
            f"must_fix={len(must_fix)}",
            f"should_fix={len(should_fix)}",
            f"keep={len(keep)}",
            f"skills={', '.join(triggered_skills) or 'base_style, chapter_quality_guard'}",
        ]
        return RevisionPlan(
            summary=" | ".join(summary_parts),
            must_fix=cls._dedupe(must_fix),
            should_fix=cls._dedupe(should_fix),
            keep=cls._dedupe(keep),
            hard_constraints=list(cls.DEFAULT_HARD_CONSTRAINTS),
            triggered_skills=cls._dedupe(triggered_skills),
            evidence_focus=cls._dedupe(evidence_focus),
        )

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

    @classmethod
    def _append_issue(
        cls,
        issue: Any,
        must_fix: list[str],
        should_fix: list[str],
        evidence_focus: list[str],
        *,
        fallback_level: str = "medium",
        fallback_tool_name: str = "",
    ) -> None:
        if isinstance(issue, dict):
            severity = str(issue.get("severity") or fallback_level or "medium").lower()
            evidence = str(issue.get("evidence") or "").strip()
            reason = str(issue.get("reason") or "").strip()
            fix = str(issue.get("fix") or "").strip()
            category = str(issue.get("category") or fallback_tool_name or "issue").strip()
            target = must_fix if severity in {"critical", "high"} else should_fix
            text = f"[{category}] {fix}" if fix else f"[{category}] Fix the evidenced issue."
            if evidence or reason:
                detail = " | ".join(part for part in [evidence, reason] if part)
                text = f"{text} Evidence: {detail}"
                evidence_focus.append(detail)
            target.append(text)
            return

        text = str(issue).strip()
        if not text:
            return
        (must_fix if fallback_level in {"critical", "high"} else should_fix).append(text)
