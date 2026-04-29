from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean

from evals.romance.history_models import (
    StepEvalAggregateFindings,
    StepEvalCaseReport,
    StepEvalSummary,
    StepGateDecision,
)
from evals.romance.loader import load_historical_cases
from evals.romance.models import RomanceCaseResult, RomanceRunSummary
from evals.romance.report_paths import build_structured_run_dir, write_text_with_aliases
from evals.romance.workflow_diagnostics import WorkflowDiagnosticsRunner


STEP_GATE_KEYS = [
    "brief_quality_score",
    "relationship_state_quality_score",
    "mind_state_quality_score",
    "writing_pack_quality_score",
    "block_plan_quality_score",
]

STEP_ACCEPT_THRESHOLDS = {
    "brief_quality_score": 6.6,
    "relationship_state_quality_score": 6.3,
    "mind_state_quality_score": 6.3,
    "writing_pack_quality_score": 6.8,
    "block_plan_quality_score": 6.8,
}

STEP_PASS_THRESHOLDS = {
    "brief_quality_score": 7.1,
    "relationship_state_quality_score": 6.8,
    "mind_state_quality_score": 6.8,
    "writing_pack_quality_score": 7.2,
    "block_plan_quality_score": 7.2,
}

STEP_ACCEPT_AVERAGE = 6.6
STEP_PASS_AVERAGE = 7.0


def _eval_result_map(eval_summary: str | Path | None) -> dict[str, RomanceCaseResult]:
    if not eval_summary:
        return {}
    path = Path(eval_summary)
    if path.is_dir():
        path = path / "summary.json"
    summary = RomanceRunSummary.model_validate_json(path.read_text(encoding="utf-8"))
    return {item.case_id: item for item in summary.case_results}


class StepEvalRunner:
    def __init__(self, *, reports_root: str | Path | None = None) -> None:
        self.diagnostics_runner = WorkflowDiagnosticsRunner(reports_root=reports_root)
        self.reports_root = self.diagnostics_runner.reports_root

    def run(
        self,
        *,
        case_dir: str | Path,
        label: str = "",
        case_ids: list[str] | None = None,
        eval_summary: str | Path | None = None,
    ) -> StepEvalSummary:
        cases = load_historical_cases(Path(case_dir), case_ids=case_ids)
        eval_results = _eval_result_map(eval_summary)
        run_label = str(label or f"{Path(case_dir).name}_step_eval").strip()
        run_paths = build_structured_run_dir(
            self.reports_root,
            task_slug="historical_step_gate_eval",
            label=run_label,
            case_ids=[case.case_id for case in cases],
            provider="analysis",
            model="gate",
        )
        run_dir = run_paths.run_dir

        case_reports: list[StepEvalCaseReport] = []
        notes: list[str] = []
        for case in cases:
            diagnostics = self.diagnostics_runner._diagnose_case(case=case, eval_result=eval_results.get(case.case_id))
            report = self._build_case_report(diagnostics=diagnostics)
            report = report.model_copy(update={"source_case_json": str(Path(case_dir) / f"{case.case_id}.json")})
            case_reports.append(report)
            (run_dir / f"{case.case_id}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
            if eval_results.get(case.case_id) is None:
                notes.append(f"{case.case_id}: step gate used diagnostics-only evidence because no eval summary entry was provided.")

        verdict_counter = Counter(report.gate_decision.verdict for report in case_reports)
        summary = StepEvalSummary(
            label=run_label,
            source_case_dir=str(Path(case_dir)),
            case_ids=[item.case_id for item in cases],
            case_reports=case_reports,
            aggregate_findings=self._aggregate(case_reports),
            gate_counts={key: verdict_counter.get(key, 0) for key in ("pass", "warn", "blocked")},
            notes=sorted(set(notes)),
        )
        json_path = run_dir / "historical_step_gate_eval_summary.json"
        md_path = run_dir / "historical_step_gate_eval_report.md"
        summary = summary.model_copy(update={"report_json": str(json_path), "report_markdown": str(md_path)})
        write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("step_eval_summary.json",))
        write_text_with_aliases(md_path, render_step_eval_markdown(summary), alias_names=("report.md",))
        return summary

    @staticmethod
    def _build_case_report(*, diagnostics) -> StepEvalCaseReport:
        gate_decision = StepEvalRunner._gate_decision(diagnostics.step_diagnostics)
        notes: list[str] = []
        if diagnostics.workflow_layer_diagnostics.get("writing_pack_layer") and diagnostics.workflow_layer_diagnostics["writing_pack_layer"].score < 6.8:
            notes.append("writing_pack_layer is below the chapter-ready threshold.")
        if diagnostics.workflow_layer_diagnostics.get("chapter_planning_layer") and diagnostics.workflow_layer_diagnostics["chapter_planning_layer"].score < 6.8:
            notes.append("chapter_planning_layer is below the chapter-ready threshold.")
        return StepEvalCaseReport(
            case_id=diagnostics.case_id,
            title=diagnostics.title,
            tags=list(diagnostics.tags or []),
            workflow_layer_diagnostics=dict(diagnostics.workflow_layer_diagnostics),
            step_diagnostics={key: diagnostics.step_diagnostics[key] for key in STEP_GATE_KEYS if key in diagnostics.step_diagnostics},
            gate_decision=gate_decision,
            cost_metrics=diagnostics.cost_metrics,
            missing_fields=list(diagnostics.missing_fields or []),
            notes=notes,
        )

    @staticmethod
    def _gate_decision(step_diagnostics) -> StepGateDecision:
        available_scores = {
            key: step_diagnostics[key].score
            for key in STEP_GATE_KEYS
            if key in step_diagnostics
        }
        average_step_score = round(mean(available_scores.values()), 2) if available_scores else 0.0
        blocking_steps = [
            key
            for key, score in available_scores.items()
            if score < STEP_ACCEPT_THRESHOLDS[key]
        ]
        warning_steps = [
            key
            for key, score in available_scores.items()
            if key not in blocking_steps and score < STEP_PASS_THRESHOLDS[key]
        ]
        accept_for_chapter_generation = not blocking_steps and average_step_score >= STEP_ACCEPT_AVERAGE
        verdict = "blocked"
        if accept_for_chapter_generation:
            verdict = "pass" if not warning_steps and average_step_score >= STEP_PASS_AVERAGE else "warn"

        reasons: list[str] = []
        if blocking_steps:
            reasons.append(
                "Step gate blocked chapter generation because these upstream artifacts are below minimum quality: "
                + ", ".join(blocking_steps)
            )
        elif warning_steps:
            reasons.append(
                "Step gate allows chapter generation, but these upstream artifacts should be improved first: "
                + ", ".join(warning_steps)
            )
        if available_scores and average_step_score < STEP_ACCEPT_AVERAGE:
            reasons.append(f"Average upstream step score is only {average_step_score:.2f}, below the chapter-ready threshold.")
        if accept_for_chapter_generation and not reasons:
            reasons.append("Upstream step artifacts are stable enough to reuse for chapter generation.")

        return StepGateDecision(
            verdict=verdict,
            accept_for_chapter_generation=accept_for_chapter_generation,
            gating_step_keys=list(STEP_GATE_KEYS),
            blocking_steps=blocking_steps,
            warning_steps=warning_steps,
            average_step_score=average_step_score,
            reasons=reasons,
        )

    @staticmethod
    def _aggregate(case_reports: list[StepEvalCaseReport]) -> StepEvalAggregateFindings:
        blocking_steps: Counter[str] = Counter()
        warning_steps: Counter[str] = Counter()
        failure_tags: Counter[str] = Counter()
        blocked_case_ids: list[str] = []
        accepted_case_ids: list[str] = []

        for report in case_reports:
            if report.gate_decision.accept_for_chapter_generation:
                accepted_case_ids.append(report.case_id)
            if report.gate_decision.verdict == "blocked":
                blocked_case_ids.append(report.case_id)
            for key in report.gate_decision.blocking_steps:
                blocking_steps[key] += 1
            for key in report.gate_decision.warning_steps:
                warning_steps[key] += 1
            if report.gate_decision.verdict != "pass":
                for tag in report.tags:
                    failure_tags[tag] += 1

        return StepEvalAggregateFindings(
            most_common_blocking_steps=[item for item, _ in blocking_steps.most_common(5)],
            most_common_warning_steps=[item for item, _ in warning_steps.most_common(5)],
            blocked_case_ids=sorted(blocked_case_ids),
            accepted_case_ids=sorted(accepted_case_ids),
            failure_prone_tags=[item for item, _ in failure_tags.most_common(5)],
        )


def render_step_eval_markdown(summary: StepEvalSummary) -> str:
    lines = [
        f"# Step Eval Report: {summary.label}",
        "",
        f"- source_case_dir: `{summary.source_case_dir}`",
        f"- generated_at: `{summary.generated_at.isoformat()}`",
        f"- cases: `{len(summary.case_reports)}`",
        f"- gate_counts: pass={summary.gate_counts.get('pass', 0)}, warn={summary.gate_counts.get('warn', 0)}, blocked={summary.gate_counts.get('blocked', 0)}",
        "",
        "## Aggregate Findings",
        "",
        f"- most_common_blocking_steps: {', '.join(summary.aggregate_findings.most_common_blocking_steps) or 'None'}",
        f"- most_common_warning_steps: {', '.join(summary.aggregate_findings.most_common_warning_steps) or 'None'}",
        f"- blocked_case_ids: {', '.join(summary.aggregate_findings.blocked_case_ids) or 'None'}",
        f"- accepted_case_ids: {', '.join(summary.aggregate_findings.accepted_case_ids) or 'None'}",
        f"- failure_prone_tags: {', '.join(summary.aggregate_findings.failure_prone_tags) or 'None'}",
    ]
    for report in summary.case_reports:
        lines.extend(
            [
                "",
                f"## {report.case_id} - {report.title}",
                "",
                f"- verdict: `{report.gate_decision.verdict}`",
                f"- accept_for_chapter_generation: `{str(report.gate_decision.accept_for_chapter_generation).lower()}`",
                f"- average_step_score: `{report.gate_decision.average_step_score:.2f}`",
                f"- blocking_steps: {', '.join(report.gate_decision.blocking_steps) or 'None'}",
                f"- warning_steps: {', '.join(report.gate_decision.warning_steps) or 'None'}",
                f"- reasons: {', '.join(report.gate_decision.reasons) or 'None'}",
                "",
                "| upstream step | score |",
                "| --- | ---: |",
            ]
        )
        for key in STEP_GATE_KEYS:
            detail = report.step_diagnostics.get(key)
            if detail is None:
                continue
            lines.append(f"| {key} | {detail.score:.2f} |")
        if report.notes:
            lines.append("")
            lines.append(f"- notes: {', '.join(report.notes)}")
        if report.missing_fields:
            lines.append(f"- missing_fields: {', '.join(report.missing_fields)}")
    if summary.notes:
        lines.extend(["", "## Notes", ""])
        for item in summary.notes:
            lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"
