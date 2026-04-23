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

PAIRWISE_METRIC_WEIGHTS = {
    "romance_tension_score": 5,
    "relationship_progression_score": 4,
    "emotional_resonance_score": 3,
    "character_attraction_score": 3,
    "hook_score": 2,
    "continuity_score": 4,
    "mind_state_consistency_score": 4,
    "redundancy_score": 2,
}

PAIRWISE_DELTA_THRESHOLD = 0.2
PAIRWISE_BLOCKER_WEIGHT = 8
PAIRWISE_COST_PENALTIES = {
    "llm_calls": (3.0, 2),
    "patch_rounds": (1.0, 1),
    "duration_seconds": (20.0, 1),
}


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
    pairwise_preference = build_pairwise_preference(diff)
    decision = evaluate_romance_diff(diff, pairwise_preference=pairwise_preference)
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
        "pairwise_preference": pairwise_preference,
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


def _build_pairwise_case_preference(case_diff: Any) -> dict[str, Any]:
    candidate_wins: list[str] = []
    baseline_wins: list[str] = []
    neutral_metrics: list[str] = []
    guard_failures: list[str] = []
    cost_flags: list[str] = []
    weighted_margin = 0

    for metric, weight in PAIRWISE_METRIC_WEIGHTS.items():
        score_delta = case_diff.score_deltas.get(metric)
        if score_delta is None:
            continue
        delta = float(score_delta.delta)
        if delta >= PAIRWISE_DELTA_THRESHOLD:
            weighted_margin += weight
            candidate_wins.append(metric)
        elif delta <= -PAIRWISE_DELTA_THRESHOLD:
            weighted_margin -= weight
            baseline_wins.append(metric)
            if metric in GUARD_METRICS:
                guard_failures.append(metric)
        else:
            neutral_metrics.append(metric)

    if case_diff.new_blockers:
        weighted_margin -= PAIRWISE_BLOCKER_WEIGHT * len(case_diff.new_blockers)
        guard_failures.extend(f"new_blocker:{flag}" for flag in case_diff.new_blockers)
    if case_diff.resolved_blockers:
        weighted_margin += PAIRWISE_BLOCKER_WEIGHT * len(case_diff.resolved_blockers)

    for cost_key, (threshold, penalty) in PAIRWISE_COST_PENALTIES.items():
        delta = float(case_diff.cost_deltas.get(cost_key, 0.0))
        if delta > threshold:
            weighted_margin -= penalty
            cost_flags.append(f"{cost_key}>+{threshold:g}")

    preferred_side = "tie"
    if weighted_margin > 0:
        preferred_side = "candidate"
    elif weighted_margin < 0:
        preferred_side = "baseline"

    return {
        "case_id": case_diff.case_id,
        "title": case_diff.title,
        "preferred_side": preferred_side,
        "weighted_margin": weighted_margin,
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "neutral_metrics": neutral_metrics,
        "guard_failures": guard_failures,
        "cost_flags": cost_flags,
        "new_blockers": list(case_diff.new_blockers),
        "resolved_blockers": list(case_diff.resolved_blockers),
    }


def build_pairwise_preference(diff: RomanceRunDiff) -> dict[str, Any]:
    case_preferences = [_build_pairwise_case_preference(case_diff) for case_diff in diff.case_diffs]
    candidate_case_wins = sum(1 for item in case_preferences if item["preferred_side"] == "candidate")
    baseline_case_wins = sum(1 for item in case_preferences if item["preferred_side"] == "baseline")
    tied_case_count = sum(1 for item in case_preferences if item["preferred_side"] == "tie")
    weighted_margin = round(sum(float(item["weighted_margin"]) for item in case_preferences), 2)

    overall_preferred_side = "tie"
    if candidate_case_wins > baseline_case_wins:
        overall_preferred_side = "candidate"
    elif baseline_case_wins > candidate_case_wins:
        overall_preferred_side = "baseline"
    elif weighted_margin > 0:
        overall_preferred_side = "candidate"
    elif weighted_margin < 0:
        overall_preferred_side = "baseline"

    return {
        "overall_preferred_side": overall_preferred_side,
        "candidate_case_wins": candidate_case_wins,
        "baseline_case_wins": baseline_case_wins,
        "tied_case_count": tied_case_count,
        "weighted_margin": weighted_margin,
        "delta_threshold": PAIRWISE_DELTA_THRESHOLD,
        "metric_weights": dict(PAIRWISE_METRIC_WEIGHTS),
        "case_preferences": case_preferences,
    }


def evaluate_romance_diff(
    diff: RomanceRunDiff,
    *,
    pairwise_preference: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    if pairwise_preference and pairwise_preference.get("overall_preferred_side") == "baseline":
        accept = False
        reasons.append("Pairwise case preference favored the baseline.")
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
        "pairwise_preferred_side": (pairwise_preference or {}).get("overall_preferred_side", "tie"),
        "pairwise_weighted_margin": round(float((pairwise_preference or {}).get("weighted_margin", 0.0)), 2),
        "pairwise_candidate_case_wins": int((pairwise_preference or {}).get("candidate_case_wins", 0)),
        "pairwise_baseline_case_wins": int((pairwise_preference or {}).get("baseline_case_wins", 0)),
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
        f"- pairwise_preferred_side: `{payload.get('decision', {}).get('pairwise_preferred_side', 'tie')}`",
        f"- pairwise_weighted_margin: `{payload.get('decision', {}).get('pairwise_weighted_margin', 0.0):+.2f}`",
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
    pairwise_preference = payload.get("pairwise_preference", {})
    if pairwise_preference:
        lines.extend(
            [
                "",
                "## Pairwise Preference",
                "",
                f"- overall_preferred_side: `{pairwise_preference.get('overall_preferred_side', 'tie')}`",
                f"- candidate_case_wins: `{int(pairwise_preference.get('candidate_case_wins', 0))}`",
                f"- baseline_case_wins: `{int(pairwise_preference.get('baseline_case_wins', 0))}`",
                f"- tied_case_count: `{int(pairwise_preference.get('tied_case_count', 0))}`",
                f"- weighted_margin: `{float(pairwise_preference.get('weighted_margin', 0.0)):+.2f}`",
                f"- delta_threshold: `{float(pairwise_preference.get('delta_threshold', 0.0)):.2f}`",
                "",
                "| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |",
                "| --- | --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for item in pairwise_preference.get("case_preferences", []):
            lines.append(
                "| {case_id} | {preferred} | {margin:+.2f} | {candidate_wins} | {baseline_wins} | {guard_failures} | {cost_flags} |".format(
                    case_id=item.get("case_id", ""),
                    preferred=item.get("preferred_side", "tie"),
                    margin=float(item.get("weighted_margin", 0.0)),
                    candidate_wins=", ".join(item.get("candidate_wins", [])) or "None",
                    baseline_wins=", ".join(item.get("baseline_wins", [])) or "None",
                    guard_failures=", ".join(item.get("guard_failures", [])) or "None",
                    cost_flags=", ".join(item.get("cost_flags", [])) or "None",
                )
            )
    return "\n".join(lines).strip() + "\n"
