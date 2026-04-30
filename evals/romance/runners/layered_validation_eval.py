from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.romance.beat_plan_eval import BeatPlanEvalRunner
from evals.romance.harness import RomanceEvalHarness
from evals.romance.report_paths import build_structured_run_dir, normalize_reports_root, write_text_with_aliases
from evals.romance.step_plan_evals import StepPlanEvalRunner


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_label(label: str) -> str:
    keep = [ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(label or "").strip()]
    return "".join(keep).strip("_") or datetime.now().strftime("%Y%m%d_%H%M%S")


def _summary_relpath(path: str | Path, *, root: Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve().relative_to(root.resolve()))
    except Exception:
        return str(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run layered validation: Step8 static -> beat-plan -> fast prose -> optional deep prose."
    )
    parser.add_argument("--label", default="", help="Run label used for the output directory.")
    parser.add_argument("--cases-dir", default="evals/romance/cases", help="Directory containing eval case JSON files.")
    parser.add_argument("--reports-root", default="evals/romance/reports", help="Directory where reports are written.")
    parser.add_argument("--case-ids", nargs="*", default=None, help="Optional case ids to validate.")
    parser.add_argument(
        "--fast-max-cases",
        type=int,
        default=1,
        help="Maximum number of cases to escalate to fast prose validation after upstream layers clear.",
    )
    parser.add_argument(
        "--fast-case-ids",
        nargs="*",
        default=None,
        help="Optional explicit case ids for fast prose validation. If omitted, the runner auto-selects non-blocked cases.",
    )
    parser.add_argument(
        "--deep-max-cases",
        type=int,
        default=1,
        help="Maximum number of cases to escalate to deep prose validation after upstream layers clear.",
    )
    parser.add_argument(
        "--deep-case-ids",
        nargs="*",
        default=None,
        help="Optional explicit case ids for deep prose validation. If omitted, the runner auto-selects non-blocked cases.",
    )
    parser.add_argument(
        "--skip-deep",
        action="store_true",
        help="Skip the expensive deep prose layer and stop after fast prose.",
    )
    parser.add_argument(
        "--skip-sanitize-context",
        action="store_true",
        help="Skip beat-plan context sanitization pass for a faster planner-only check.",
    )
    return parser


def _nonblocked_case_ids_from_step(summary: Any) -> set[str]:
    return {report.case_id for report in summary.case_reports if report.verdict != "blocked"}


def _nonblocked_case_ids_from_beat(summary: Any) -> set[str]:
    return {report.case_id for report in summary.case_reports if report.verdict != "blocked"}


def _pick_deep_case_ids(
    *,
    requested_case_ids: list[str],
    explicit_deep_case_ids: list[str] | None,
    allowed_case_ids: set[str],
    deep_max_cases: int,
) -> list[str]:
    if explicit_deep_case_ids:
        return [case_id for case_id in explicit_deep_case_ids if case_id in allowed_case_ids]

    selected = [case_id for case_id in requested_case_ids if case_id in allowed_case_ids]
    if deep_max_cases > 0:
        selected = selected[:deep_max_cases]
    return selected


def _pick_fast_case_ids(
    *,
    requested_case_ids: list[str],
    explicit_fast_case_ids: list[str] | None,
    step_summary: Any,
    beat_summary: Any,
    fast_max_cases: int,
) -> list[str]:
    allowed = _nonblocked_case_ids_from_step(step_summary) & _nonblocked_case_ids_from_beat(beat_summary)
    if explicit_fast_case_ids:
        return [case_id for case_id in explicit_fast_case_ids if case_id in allowed]
    selected = [case_id for case_id in requested_case_ids if case_id in allowed]
    if fast_max_cases > 0:
        selected = selected[:fast_max_cases]
    return selected


def render_layered_validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Layered Validation: {payload['label']}",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- cases: `{', '.join(payload['case_ids'])}`",
        f"- fast_case_ids: `{', '.join(payload['fast_case_ids']) if payload['fast_case_ids'] else '(none)'}`",
        f"- deep_case_ids: `{', '.join(payload['deep_case_ids']) if payload['deep_case_ids'] else '(none)'}`",
        "",
        "## Layers",
        "",
        f"1. step plan static: `{payload['layers']['step_static']['status']}` score={payload['layers']['step_static']['average_score']}",
        f"   - report: `{payload['layers']['step_static']['report_markdown']}`",
        f"2. beat plan eval: `{payload['layers']['beat_plan']['status']}` score={payload['layers']['beat_plan']['average_score']}",
        f"   - report: `{payload['layers']['beat_plan']['report_markdown']}`",
        f"3. fast prose eval: `{payload['layers']['chapter_fast']['status']}` core={payload['layers']['chapter_fast']['core_average']}",
        f"   - report: `{payload['layers']['chapter_fast']['report_markdown']}`",
        f"4. deep prose eval: `{payload['layers']['chapter_deep']['status']}` core={payload['layers']['chapter_deep']['core_average']}",
        f"   - report: `{payload['layers']['chapter_deep']['report_markdown']}`",
        "",
        "## Notes",
    ]
    lines.extend([f"- {note}" for note in payload.get("notes", [])])
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = build_parser().parse_args()
    reports_root, _ = normalize_reports_root(args.reports_root)
    case_ids = list(args.case_ids or [])
    label = _sanitize_label(args.label or f"layered_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    step_summary = StepPlanEvalRunner(reports_root=args.reports_root).run(
        cases_dir=args.cases_dir,
        label=f"{label}_step_static",
        case_ids=case_ids or None,
    )
    resolved_case_ids = case_ids or list(step_summary.case_ids)

    beat_summary = BeatPlanEvalRunner(reports_root=args.reports_root).run(
        cases_dir=args.cases_dir,
        label=f"{label}_beat_plan",
        case_ids=resolved_case_ids or None,
        sanitize_context=not args.skip_sanitize_context,
    )

    fast_case_ids = _pick_fast_case_ids(
        requested_case_ids=resolved_case_ids,
        explicit_fast_case_ids=args.fast_case_ids,
        step_summary=step_summary,
        beat_summary=beat_summary,
        fast_max_cases=max(int(args.fast_max_cases), 0),
    )
    fast_summary = None
    if fast_case_ids:
        fast_summary, _ = RomanceEvalHarness(
            mode="fast",
            case_dir=args.cases_dir,
            reports_root=args.reports_root,
        ).run(
            label=f"{label}_chapter_fast",
            case_ids=fast_case_ids,
        )

    deep_case_ids = []
    deep_summary = None
    if not args.skip_deep:
        deep_allowed = set(fast_case_ids) if fast_case_ids else (_nonblocked_case_ids_from_step(step_summary) & _nonblocked_case_ids_from_beat(beat_summary))
        deep_case_ids = _pick_deep_case_ids(
            requested_case_ids=fast_case_ids or resolved_case_ids,
            explicit_deep_case_ids=args.deep_case_ids,
            allowed_case_ids=deep_allowed,
            deep_max_cases=max(int(args.deep_max_cases), 0),
        )
        if deep_case_ids:
            deep_summary, _ = RomanceEvalHarness(
                mode="deep",
                case_dir=args.cases_dir,
                reports_root=args.reports_root,
            ).run(
                label=f"{label}_chapter_deep",
                case_ids=deep_case_ids,
            )

    run_paths = build_structured_run_dir(
        reports_root,
        task_slug="layered_validation",
        label=label,
        case_ids=resolved_case_ids,
        provider="analysis",
        model="mixed",
    )
    run_dir = run_paths.run_dir

    def _layer_entry(summary: Any | None, *, status: str) -> dict[str, Any]:
        if summary is None:
            return {
                "status": status,
                "report_json": "",
                "report_markdown": "",
                "average_score": 0.0,
                "core_average": {},
            }
        average_scores = getattr(summary, "average_scores", {}) or {}
        core_average = {
            key: average_scores.get(key)
            for key in (
                "romance_tension_score",
                "relationship_progression_score",
                "emotional_resonance_score",
                "hook_score",
                "character_attraction_score",
                "continuity_score",
                "mind_state_consistency_score",
                "redundancy_score",
            )
            if key in average_scores
        }
        return {
            "status": status,
            "report_json": _summary_relpath(getattr(summary, "report_json", ""), root=reports_root),
            "report_markdown": _summary_relpath(getattr(summary, "report_markdown", ""), root=reports_root),
            "average_score": round(float(getattr(summary, "average_score", 0.0) or 0.0), 2),
            "core_average": core_average,
        }

    payload = {
        "label": label,
        "generated_at": _utc_now().isoformat(),
        "run_dir": str(run_dir),
        "case_ids": resolved_case_ids,
        "fast_case_ids": fast_case_ids,
        "deep_case_ids": deep_case_ids,
        "layers": {
            "step_static": _layer_entry(step_summary, status="done"),
            "beat_plan": _layer_entry(beat_summary, status="done"),
            "chapter_fast": _layer_entry(fast_summary, status="done" if fast_summary is not None else "skipped"),
            "chapter_deep": _layer_entry(deep_summary, status="done" if deep_summary is not None else ("skipped" if args.skip_deep or not deep_case_ids else "not_run")),
        },
        "notes": [
            "Use this runner before any all-case deep replay. It pushes expensive deep prose validation behind cheaper upstream checks.",
            "By default only a bounded subset of non-blocked cases escalates to fast/deep prose, which prevents multi-hour all-case deep loops from becoming the first validation pass.",
            "If fast prose already regresses badly, stop there and fix the writer before paying for more deep cases.",
        ],
    }
    summary_json_path = run_dir / "layered_validation_summary.json"
    summary_md_path = run_dir / "layered_validation_report.md"
    write_text_with_aliases(
        summary_json_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        alias_names=("summary.json",),
    )
    write_text_with_aliases(
        summary_md_path,
        render_layered_validation_markdown(payload),
        alias_names=("report.md",),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
