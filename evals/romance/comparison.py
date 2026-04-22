from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from evals.romance.harness import compare_run_summaries
from evals.romance.history_models import StepEvalSummary, WorkflowDiagnosticsSummary
from evals.romance.models import RomanceRunDiff, RomanceRunSummary
from evals.romance.step_evals import STEP_GATE_KEYS
from evals.romance.workflow_diagnostics import CORE_METRICS


CORE_OBJECTIVES = [
    "romance_tension_score",
    "relationship_progression_score",
    "emotional_resonance_score",
    "character_attraction_score",
    "hook_score",
]

GUARD_METRICS = [
    "continuity_score",
    "mind_state_consistency_score",
    "redundancy_score",
]


def _load_json(path_or_dir: str | Path) -> tuple[dict[str, Any], Path]:
    path = Path(path_or_dir)
    if path.is_dir():
        for candidate in ("summary.json", "diagnostics_summary.json", "step_eval_summary.json"):
            candidate_path = path / candidate
            if candidate_path.exists():
                path = candidate_path
                break
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, path


def compare_paths(baseline: str | Path, candidate: str | Path) -> dict[str, Any]:
    baseline_payload, baseline_path = _load_json(baseline)
    candidate_payload, candidate_path = _load_json(candidate)
    if "case_results" in baseline_payload and "case_results" in candidate_payload:
        summary = compare_romance_eval_paths(baseline_path, candidate_path)
        summary["baseline_path"] = str(baseline_path)
        summary["candidate_path"] = str(candidate_path)
        return summary
    if "gate_counts" in baseline_payload and "gate_counts" in candidate_payload:
        summary = compare_step_eval_paths(baseline_path, candidate_path)
        summary["baseline_path"] = str(baseline_path)
        summary["candidate_path"] = str(candidate_path)
        return summary
    if "case_reports" in baseline_payload and "case_reports" in candidate_payload:
        summary = compare_workflow_diagnostics_paths(baseline_path, candidate_path)
        summary["baseline_path"] = str(baseline_path)
        summary["candidate_path"] = str(candidate_path)
        return summary
    raise ValueError("Unsupported comparison payloads. Expected romance summary.json, diagnostics_summary.json, or step_eval_summary.json.")


def compare_romance_eval_paths(baseline: str | Path, candidate: str | Path) -> dict[str, Any]:
    diff = compare_run_summaries(baseline, candidate)
    decision = evaluate_romance_diff(diff)
    return {
        "comparison_type": "romance_eval",
        "baseline_label": diff.baseline_label,
        "candidate_label": diff.candidate_label,
        "average_score_deltas": {
            key: value.model_dump(mode="json")
            for key, value in diff.average_score_deltas.items()
        },
        "case_diffs": [item.model_dump(mode="json") for item in diff.case_diffs],
        "improved_metrics": list(diff.improved_metrics),
        "declined_metrics": list(diff.declined_metrics),
        "blocked_case_delta": diff.blocked_case_delta,
        "new_blocker_case_ids": list(diff.new_blocker_case_ids),
        "resolved_blocker_case_ids": list(diff.resolved_blocker_case_ids),
        "decision": decision,
    }


def compare_workflow_diagnostics_paths(baseline: str | Path, candidate: str | Path) -> dict[str, Any]:
    baseline_summary = WorkflowDiagnosticsSummary.model_validate_json(Path(baseline).read_text(encoding="utf-8"))
    candidate_summary = WorkflowDiagnosticsSummary.model_validate_json(Path(candidate).read_text(encoding="utf-8"))
    baseline_cases = {item.case_id: item for item in baseline_summary.case_reports}
    candidate_cases = {item.case_id: item for item in candidate_summary.case_reports}
    average_score_deltas: dict[str, float] = {}
    average_layer_deltas: dict[str, float] = {}
    for metric in CORE_METRICS:
        baseline_values = [item.final_text_scores[metric].score for item in baseline_summary.case_reports if metric in item.final_text_scores]
        candidate_values = [item.final_text_scores[metric].score for item in candidate_summary.case_reports if metric in item.final_text_scores]
        average_score_deltas[metric] = round((mean(candidate_values) if candidate_values else 0.0) - (mean(baseline_values) if baseline_values else 0.0), 2)
    for layer in [
        "input_definition_layer",
        "state_modeling_layer",
        "writing_pack_layer",
        "chapter_planning_layer",
        "draft_execution_layer",
        "revision_layer",
    ]:
        baseline_values = [item.workflow_layer_diagnostics[layer].score for item in baseline_summary.case_reports if layer in item.workflow_layer_diagnostics]
        candidate_values = [item.workflow_layer_diagnostics[layer].score for item in candidate_summary.case_reports if layer in item.workflow_layer_diagnostics]
        average_layer_deltas[layer] = round((mean(candidate_values) if candidate_values else 0.0) - (mean(baseline_values) if baseline_values else 0.0), 2)
    case_diffs = []
    for case_id in sorted(set(baseline_cases) & set(candidate_cases)):
        base_case = baseline_cases[case_id]
        cand_case = candidate_cases[case_id]
        metric_deltas = {
            metric: round(cand_case.final_text_scores[metric].score - base_case.final_text_scores[metric].score, 2)
            for metric in CORE_METRICS
            if metric in base_case.final_text_scores and metric in cand_case.final_text_scores
        }
        layer_deltas = {
            layer: round(cand_case.workflow_layer_diagnostics[layer].score - base_case.workflow_layer_diagnostics[layer].score, 2)
            for layer in base_case.workflow_layer_diagnostics
            if layer in cand_case.workflow_layer_diagnostics
        }
        case_diffs.append(
            {
                "case_id": case_id,
                "title": cand_case.title,
                "metric_deltas": metric_deltas,
                "layer_deltas": layer_deltas,
                "used_full_rewrite_delta": int(cand_case.cost_metrics.used_full_rewrite) - int(base_case.cost_metrics.used_full_rewrite),
            }
        )
    decision = evaluate_workflow_diagnostics_delta(
        average_score_deltas=average_score_deltas,
        average_layer_deltas=average_layer_deltas,
    )
    return {
        "comparison_type": "workflow_diagnostics",
        "baseline_label": baseline_summary.label,
        "candidate_label": candidate_summary.label,
        "average_score_deltas": average_score_deltas,
        "average_layer_deltas": average_layer_deltas,
        "case_diffs": case_diffs,
        "decision": decision,
    }


def compare_step_eval_paths(baseline: str | Path, candidate: str | Path) -> dict[str, Any]:
    baseline_summary = StepEvalSummary.model_validate_json(Path(baseline).read_text(encoding="utf-8"))
    candidate_summary = StepEvalSummary.model_validate_json(Path(candidate).read_text(encoding="utf-8"))
    baseline_cases = {item.case_id: item for item in baseline_summary.case_reports}
    candidate_cases = {item.case_id: item for item in candidate_summary.case_reports}

    average_step_deltas: dict[str, float] = {}
    for key in STEP_GATE_KEYS:
        baseline_values = [item.step_diagnostics[key].score for item in baseline_summary.case_reports if key in item.step_diagnostics]
        candidate_values = [item.step_diagnostics[key].score for item in candidate_summary.case_reports if key in item.step_diagnostics]
        average_step_deltas[key] = round((mean(candidate_values) if candidate_values else 0.0) - (mean(baseline_values) if baseline_values else 0.0), 2)

    gate_count_deltas = {
        verdict: int(candidate_summary.gate_counts.get(verdict, 0)) - int(baseline_summary.gate_counts.get(verdict, 0))
        for verdict in ("pass", "warn", "blocked")
    }

    case_diffs = []
    for case_id in sorted(set(baseline_cases) & set(candidate_cases)):
        base_case = baseline_cases[case_id]
        cand_case = candidate_cases[case_id]
        case_diffs.append(
            {
                "case_id": case_id,
                "title": cand_case.title,
                "step_deltas": {
                    key: round(cand_case.step_diagnostics[key].score - base_case.step_diagnostics[key].score, 2)
                    for key in STEP_GATE_KEYS
                    if key in base_case.step_diagnostics and key in cand_case.step_diagnostics
                },
                "baseline_verdict": base_case.gate_decision.verdict,
                "candidate_verdict": cand_case.gate_decision.verdict,
                "accept_delta": int(cand_case.gate_decision.accept_for_chapter_generation) - int(base_case.gate_decision.accept_for_chapter_generation),
            }
        )

    decision = evaluate_step_eval_delta(
        average_step_deltas=average_step_deltas,
        gate_count_deltas=gate_count_deltas,
    )
    return {
        "comparison_type": "step_eval",
        "baseline_label": baseline_summary.label,
        "candidate_label": candidate_summary.label,
        "average_step_deltas": average_step_deltas,
        "gate_count_deltas": gate_count_deltas,
        "case_diffs": case_diffs,
        "decision": decision,
    }


def evaluate_romance_diff(diff: RomanceRunDiff) -> dict[str, Any]:
    core_delta = round(mean(diff.average_score_deltas[item].delta for item in CORE_OBJECTIVES), 2)
    guard_delta = round(mean(diff.average_score_deltas[item].delta for item in GUARD_METRICS), 2)
    llm_delta = round(
        mean(item.cost_deltas.get("llm_calls", 0.0) for item in diff.case_diffs) if diff.case_diffs else 0.0,
        2,
    )
    duration_delta = round(
        mean(item.cost_deltas.get("duration_seconds", 0.0) for item in diff.case_diffs) if diff.case_diffs else 0.0,
        2,
    )
    reasons: list[str] = []
    accept = True
    if core_delta <= 0:
        accept = False
        reasons.append("Core romance objectives did not improve on average.")
    if diff.new_blocker_case_ids:
        accept = False
        reasons.append("Candidate introduced new blocker cases.")
    if diff.blocked_case_delta > 0:
        accept = False
        reasons.append("Blocked case count increased.")
    if diff.average_score_deltas["continuity_score"].delta < -0.2:
        accept = False
        reasons.append("Continuity regressed beyond the safety threshold.")
    if diff.average_score_deltas["mind_state_consistency_score"].delta < -0.2:
        accept = False
        reasons.append("Mind-state consistency regressed beyond the safety threshold.")
    if diff.average_score_deltas["redundancy_score"].delta < -0.2:
        accept = False
        reasons.append("Redundancy regressed beyond the safety threshold.")
    if llm_delta > 3.0:
        accept = False
        reasons.append("Average llm_calls cost increased too much.")
    if duration_delta > 20.0:
        accept = False
        reasons.append("Average duration increased too much.")
    if accept:
        reasons.append("Candidate improved core romance objectives without violating continuity, mind-state, or cost guards.")
        if diff.resolved_blocker_case_ids:
            reasons.append("Candidate also resolved previously blocked cases.")
    return {
        "accept_change": accept,
        "core_metric_delta": core_delta,
        "guard_metric_delta": guard_delta,
        "average_llm_calls_delta": llm_delta,
        "average_duration_seconds_delta": duration_delta,
        "blocked_case_delta": diff.blocked_case_delta,
        "new_blocker_case_ids": list(diff.new_blocker_case_ids),
        "resolved_blocker_case_ids": list(diff.resolved_blocker_case_ids),
        "reasons": reasons,
    }


def evaluate_workflow_diagnostics_delta(
    *,
    average_score_deltas: dict[str, float],
    average_layer_deltas: dict[str, float],
) -> dict[str, Any]:
    core_delta = round(mean(average_score_deltas[item] for item in CORE_OBJECTIVES), 2)
    guard_delta = round(mean(average_score_deltas[item] for item in GUARD_METRICS), 2)
    revision_delta = round(average_layer_deltas.get("revision_layer", 0.0), 2)
    accept = core_delta > 0 and average_score_deltas.get("continuity_score", 0.0) >= -0.2 and average_score_deltas.get("mind_state_consistency_score", 0.0) >= -0.2
    reasons = []
    if accept:
        reasons.append("Workflow diagnostics improved on core objectives without triggering continuity or mind-state regressions.")
    else:
        reasons.append("Workflow diagnostics did not clear the non-regression gate.")
    if revision_delta < 0:
        reasons.append("Revision layer quality worsened, so patch behavior should be re-checked.")
    return {
        "accept_change": accept,
        "core_metric_delta": core_delta,
        "guard_metric_delta": guard_delta,
        "revision_layer_delta": revision_delta,
        "reasons": reasons,
    }


def evaluate_step_eval_delta(
    *,
    average_step_deltas: dict[str, float],
    gate_count_deltas: dict[str, int],
) -> dict[str, Any]:
    core_delta = round(mean(average_step_deltas.values()), 2) if average_step_deltas else 0.0
    blocked_case_delta = int(gate_count_deltas.get("blocked", 0))
    accepted_case_delta = int(gate_count_deltas.get("pass", 0)) + max(int(gate_count_deltas.get("warn", 0)), 0)
    accept = True
    reasons: list[str] = []
    if core_delta <= 0:
        accept = False
        reasons.append("Upstream step quality did not improve on average.")
    if blocked_case_delta > 0:
        accept = False
        reasons.append("More cases are blocked at the step gate than baseline.")
    for critical_key in ("writing_pack_quality_score", "block_plan_quality_score", "relationship_state_quality_score"):
        if average_step_deltas.get(critical_key, 0.0) < -0.2:
            accept = False
            reasons.append(f"{critical_key} regressed beyond the step-gate safety threshold.")
    if accept:
        reasons.append("Step gate quality improved without creating more blocked chapter-ready cases.")
    return {
        "accept_change": accept,
        "core_metric_delta": core_delta,
        "blocked_case_delta": blocked_case_delta,
        "accepted_case_delta": accepted_case_delta,
        "reasons": reasons,
    }


def render_comparison_markdown(payload: dict[str, Any]) -> str:
    average_table = payload.get("average_score_deltas", {})
    average_label = "metric"
    if payload.get("comparison_type") == "step_eval":
        average_table = payload.get("average_step_deltas", {})
        average_label = "upstream step"
    lines = [
        f"# Comparison Report: {payload.get('candidate_label', '')} vs {payload.get('baseline_label', '')}",
        "",
        f"- comparison_type: `{payload.get('comparison_type', '')}`",
        "",
        "## Decision",
        "",
        f"- accept_change: `{str(payload.get('decision', {}).get('accept_change', False)).lower()}`",
        f"- core_metric_delta: `{payload.get('decision', {}).get('core_metric_delta', 0.0):.2f}`",
        f"- guard_metric_delta: `{payload.get('decision', {}).get('guard_metric_delta', 0.0):.2f}`",
        f"- blocked_case_delta: `{payload.get('decision', {}).get('blocked_case_delta', 0):+d}`",
        f"- new_blocker_case_ids: {', '.join(payload.get('decision', {}).get('new_blocker_case_ids', [])) or 'None'}",
        f"- resolved_blocker_case_ids: {', '.join(payload.get('decision', {}).get('resolved_blocker_case_ids', [])) or 'None'}",
        f"- reasons: {', '.join(payload.get('decision', {}).get('reasons', [])) or 'None'}",
        "",
        "## Average Deltas",
        "",
        f"| {average_label} | delta |",
        "| --- | ---: |",
    ]
    for key, value in average_table.items():
        delta = value.get("delta") if isinstance(value, dict) else value
        lines.append(f"| {key} | {float(delta):+.2f} |")
    layer_deltas = payload.get("average_layer_deltas", {})
    if layer_deltas:
        lines.extend(["", "| workflow layer | delta |", "| --- | ---: |"])
        for key, value in layer_deltas.items():
            lines.append(f"| {key} | {float(value):+.2f} |")
    gate_deltas = payload.get("gate_count_deltas", {})
    if gate_deltas:
        lines.extend(["", "| gate verdict | delta |", "| --- | ---: |"])
        for key, value in gate_deltas.items():
            lines.append(f"| {key} | {int(value):+d} |")
    return "\n".join(lines).strip() + "\n"
