from __future__ import annotations

from pathlib import Path

from evals.romance.models import RomanceRunDiff, RomanceRunSummary


CORE_METRICS = [
    "romance_tension_score",
    "relationship_progression_score",
    "emotional_resonance_score",
    "character_attraction_score",
    "hook_score",
    "continuity_score",
    "redundancy_score",
    "mind_state_consistency_score",
]


def _render_mapping(mapping: dict[str, int]) -> str:
    if not mapping:
        return "None"
    return "；".join(f"{key}={value}" for key, value in mapping.items())


def _render_target_stub(result: RomanceRunSummary | None, limit: int = 5) -> str:
    if result is None:
        return "None"
    items = list(result.optimization_target_counts.items())[:limit]
    if not items:
        return "None"
    return "；".join(f"{module}({count})" for module, count in items)


def render_run_markdown(summary: RomanceRunSummary) -> str:
    lines = [
        f"# Romance Eval Report: {summary.label}",
        "",
        f"- mode: `{summary.mode}`",
        f"- provider: `{summary.provider}`",
        f"- model: `{summary.model}`",
        f"- generated_at: `{summary.generated_at.isoformat()}`",
        f"- cases: `{len(summary.case_results)}`",
        f"- verdict_counts: {_render_mapping(summary.verdict_counts)}",
        f"- blocked_case_ids: {', '.join(summary.blocked_case_ids) or 'None'}",
        f"- top_optimization_targets: {_render_target_stub(summary)}",
        "",
        "## Average Scores",
        "",
        "| metric | score |",
        "| --- | ---: |",
    ]
    for metric in CORE_METRICS:
        lines.append(f"| {metric} | {summary.average_scores.get(metric, 0.0):.2f} |")

    for result in summary.case_results:
        lines.extend(
            [
                "",
                f"## {result.case_id} - {result.title}",
                "",
                f"- verdict: `{result.verdict}`",
                "| metric | score | note |",
                "| --- | ---: | --- |",
            ]
        )
        for metric in CORE_METRICS:
            detail = result.metrics.get(metric)
            note = detail.reason if detail is not None else ""
            lines.append(f"| {metric} | {result.scores.get(metric, 0.0):.2f} | {note} |")
        judge_redundancy = result.breakdowns.get("judge_redundancy_score")
        rule_redundancy = result.breakdowns.get("rule_redundancy_score")
        rule_anti_slop = result.breakdowns.get("rule_anti_slop_score")
        if judge_redundancy is not None or rule_redundancy is not None or rule_anti_slop is not None:
            lines.extend(
                [
                    "",
                    "| redundancy view | score |",
                    "| --- | ---: |",
                ]
            )
            if judge_redundancy is not None:
                lines.append(f"| judge_redundancy_score | {judge_redundancy.score:.2f} |")
            if rule_redundancy is not None:
                lines.append(f"| rule_redundancy_score | {rule_redundancy.score:.2f} |")
            if rule_anti_slop is not None:
                lines.append(f"| rule_anti_slop_score | {rule_anti_slop.score:.2f} |")
            lines.append(f"| hybrid_redundancy_score | {result.scores.get('redundancy_score', 0.0):.2f} |")
        if result.hard_fail_flags:
            lines.extend(
                [
                    "",
                    "| hard fail flag | severity | related_metrics |",
                    "| --- | --- | --- |",
                ]
            )
            for flag in result.hard_fail_flags:
                related_metrics = ", ".join(flag.related_metrics) or "None"
                lines.append(f"| {flag.flag_type} | {flag.severity} | {related_metrics} |")
        if result.optimization_targets:
            lines.extend(
                [
                    "",
                    "| target_module | issue_type | severity | confidence |",
                    "| --- | --- | --- | ---: |",
                ]
            )
            for target in result.optimization_targets[:5]:
                lines.append(
                    f"| {target.target_module} | {target.issue_type} | {target.severity} | {target.confidence:.2f} |"
                )
        lines.extend(
            [
                "",
                f"- strengths: {'；'.join(result.diagnosis.strengths) or 'None'}",
                f"- weaknesses: {'；'.join(result.diagnosis.weaknesses) or 'None'}",
                f"- improvement_hints: {'；'.join(result.diagnosis.improvement_hints) or 'None'}",
                (
                    "- cost: "
                    f"llm_calls={result.cost_metrics.llm_calls}, "
                    f"judge_llm_calls={result.cost_metrics.judge_llm_calls}, "
                    f"review_calls={result.cost_metrics.review_calls}, "
                    f"patch_rounds={result.cost_metrics.patch_rounds}, "
                    f"used_full_rewrite={str(result.cost_metrics.used_full_rewrite).lower()}, "
                    f"duration_seconds={result.cost_metrics.duration_seconds:.2f}"
                ),
            ]
        )
        if result.errors:
            lines.append(f"- errors: {'；'.join(result.errors)}")
    if summary.errors:
        lines.extend(["", "## Run Errors", ""])
        for item in summary.errors:
            lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def render_diff_markdown(diff: RomanceRunDiff) -> str:
    lines = [
        f"# Romance Eval Diff: {diff.candidate_label} vs {diff.baseline_label}",
        "",
        f"- compared_at: `{diff.compared_at.isoformat()}`",
        "",
        "## Average Delta",
        "",
        "| metric | baseline | candidate | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric in CORE_METRICS:
        item = diff.average_score_deltas.get(metric)
        if item is None:
            continue
        lines.append(
            f"| {metric} | {item.baseline:.2f} | {item.candidate:.2f} | {item.delta:+.2f} |"
        )
    lines.extend(
        [
            "",
            f"- improved_metrics: {'；'.join(diff.improved_metrics) or 'None'}",
            f"- declined_metrics: {'；'.join(diff.declined_metrics) or 'None'}",
            f"- blocked_case_delta: {diff.blocked_case_delta:+d}",
            f"- new_blocker_case_ids: {', '.join(diff.new_blocker_case_ids) or 'None'}",
            f"- resolved_blocker_case_ids: {', '.join(diff.resolved_blocker_case_ids) or 'None'}",
        ]
    )
    for case_diff in diff.case_diffs:
        lines.extend(
            [
                "",
                f"## {case_diff.case_id} - {case_diff.title}",
                "",
                f"- verdict: `{case_diff.baseline_verdict}` -> `{case_diff.candidate_verdict}`",
                "| metric | delta |",
                "| --- | ---: |",
            ]
        )
        for metric in CORE_METRICS:
            item = case_diff.score_deltas.get(metric)
            if item is None:
                continue
            lines.append(f"| {metric} | {item.delta:+.2f} |")
        if case_diff.cost_deltas:
            cost_parts = [f"{key}={value:+.2f}" for key, value in case_diff.cost_deltas.items()]
            lines.append("")
            lines.append(f"- cost_deltas: {'；'.join(cost_parts)}")
        if case_diff.new_blockers:
            lines.append(f"- new_blockers: {'；'.join(case_diff.new_blockers)}")
        if case_diff.resolved_blockers:
            lines.append(f"- resolved_blockers: {'；'.join(case_diff.resolved_blockers)}")
        lines.append(f"- improved_metrics: {'；'.join(case_diff.improved_metrics) or 'None'}")
        lines.append(f"- declined_metrics: {'；'.join(case_diff.declined_metrics) or 'None'}")
    return "\n".join(lines).strip() + "\n"


def write_summary_files(summary: RomanceRunSummary, run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "summary.json"
    md_path = run_dir / "report.md"
    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_run_markdown(summary), encoding="utf-8")
    return json_path, md_path


def write_diff_files(diff: RomanceRunDiff, run_dir: Path, *, baseline_label: str) -> tuple[Path, Path]:
    safe_label = baseline_label.replace(" ", "_")
    json_path = run_dir / f"diff_vs_{safe_label}.json"
    md_path = run_dir / f"diff_vs_{safe_label}.md"
    json_path.write_text(diff.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_diff_markdown(diff), encoding="utf-8")
    return json_path, md_path
