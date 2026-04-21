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

        for tool_name, report in review_reports.items():
            if tool_name == "review_prose_quality":
                prose_score = int(report.get("prose_score") or 0)
                tension_score = int(report.get("tension_score") or 0)
                exposition_score = int(report.get("exposition_score") or 10)
                if prose_score >= 7 and tension_score >= 7 and exposition_score <= 4:
                    keep.append("Preserve the stronger prose rhythm and chapter pressure already achieved.")
                if prose_score < 7:
                    must_fix.append(f"Raise prose quality to at least 7/10. Guidance: {report.get('rewrite_guidance') or 'Tighten prose.'}")
                if tension_score < 7:
                    must_fix.append(f"Raise tension to at least 7/10. Guidance: {report.get('rewrite_guidance') or 'Increase pressure and consequences.'}")
                if exposition_score > 4:
                    must_fix.append(f"Reduce exposition to 4/10 or below. Guidance: {report.get('rewrite_guidance') or 'Cut explanation.'}")
                continue

            issues = [str(item).strip() for item in report.get("issues", []) or [] if str(item).strip()]
            level = str(report.get("level") or "medium").lower()
            passed = bool(report.get("passed", False))
            guidance = str(report.get("rewrite_guidance") or "").strip()
            if passed and not issues:
                keep.append(f"{tool_name} passed; preserve the compliant parts.")
                continue
            target_list = must_fix if level in {"critical", "high"} or not passed else should_fix
            if issues:
                target_list.extend(issues)
            elif guidance:
                target_list.append(guidance)
            elif not passed:
                target_list.append(f"{tool_name} still fails and needs revision.")

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
