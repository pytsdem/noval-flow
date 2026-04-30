from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from statistics import mean
from typing import Any

from evals.romance.history_models import (
    AggregateFindings,
    HistoricalEvalCase,
    WorkflowDiagnosticDetail,
    WorkflowDiagnosticsCaseReport,
    WorkflowDiagnosticsSummary,
)
from evals.romance.judges.rule_metrics import (
    ActionCarriedRevealRuleAnalyzer,
    AntiSlopRuleAnalyzer,
    ExplanationDensityRuleAnalyzer,
    PronounLeadRuleAnalyzer,
    RedundancyRuleAnalyzer,
    RelationshipCostRealizationRuleAnalyzer,
)
from evals.romance.loader import load_historical_cases
from evals.romance.models import RomanceCaseResult, RomanceMetricDetail, RomanceRunSummary
from evals.romance.report_paths import build_structured_run_dir, normalize_reports_root, write_text_with_aliases


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

WORKFLOW_LAYERS = [
    "input_definition_layer",
    "state_modeling_layer",
    "writing_pack_layer",
    "chapter_planning_layer",
    "draft_execution_layer",
    "revision_layer",
]

STEP_KEYS = [
    "brief_quality_score",
    "relationship_state_quality_score",
    "mind_state_quality_score",
    "writing_pack_quality_score",
    "block_plan_quality_score",
    "writer_execution_quality_score",
    "patch_effectiveness_score",
]


def _clamp(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


def _level_penalty(level: str) -> float:
    mapping = {
        "critical": 3.0,
        "high": 2.0,
        "medium": 1.0,
        "low": 0.5,
    }
    return mapping.get(str(level or "").strip().lower(), 0.0)


def _report_issues(report: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    return [item for item in list(report.get("issues") or []) if isinstance(item, dict)]


def _latest_review_reports(case: HistoricalEvalCase) -> dict[str, Any]:
    if case.intermediates.review_reports:
        latest = case.intermediates.review_reports[-1]
        if isinstance(latest, dict):
            return dict(latest.get("review_reports") or {})
    return {}


def _tool_report(case: HistoricalEvalCase, tool_name: str) -> dict[str, Any]:
    return dict(_latest_review_reports(case).get(tool_name) or {})


def _eval_result_map(eval_summary: str | Path | None) -> dict[str, RomanceCaseResult]:
    if not eval_summary:
        return {}
    path = Path(eval_summary)
    if path.is_dir():
        path = path / "summary.json"
    summary = RomanceRunSummary.model_validate_json(path.read_text(encoding="utf-8"))
    return {item.case_id: item for item in summary.case_results}


def _heuristic_detail(*, score: float, reason: str, evidence: list[str], hint: str, source: str = "hybrid") -> RomanceMetricDetail:
    return RomanceMetricDetail(
        score=_clamp(score),
        reason=reason,
        evidence_summary=" | ".join(item for item in evidence if item) or "No explicit supporting evidence captured.",
        improvement_hint=hint,
        source=source,
    )


def _review_binary_score(report: dict[str, Any], *, pass_score: float = 8.0, fail_score: float = 5.2) -> float:
    if not report:
        return 6.0
    if report.get("passed") is True and report.get("rewrite_needed") is not True:
        return pass_score
    return max(0.0, fail_score - _level_penalty(report.get("level")))


class WorkflowDiagnosticsRunner:
    def __init__(self, *, reports_root: str | Path | None = None) -> None:
        self.reports_root, self.runs_root = normalize_reports_root(reports_root)

    def run(
        self,
        *,
        case_dir: str | Path,
        label: str = "",
        case_ids: list[str] | None = None,
        eval_summary: str | Path | None = None,
    ) -> WorkflowDiagnosticsSummary:
        cases = load_historical_cases(Path(case_dir), case_ids=case_ids)
        eval_results = _eval_result_map(eval_summary)
        run_label = str(label or Path(case_dir).name or "workflow_diagnostics").strip()
        run_paths = build_structured_run_dir(
            self.reports_root,
            task_slug="workflow_diagnostics",
            label=run_label,
            case_ids=[case.case_id for case in cases],
            provider="analysis",
            model="diagnostics",
        )
        run_dir = run_paths.run_dir

        case_reports: list[WorkflowDiagnosticsCaseReport] = []
        notes: list[str] = []
        for case in cases:
            report = self._diagnose_case(case=case, eval_result=eval_results.get(case.case_id))
            report = report.model_copy(update={"source_case_json": str(Path(case_dir) / f"{case.case_id}.json")})
            case_reports.append(report)
            case_path = run_dir / f"{case.case_id}.json"
            case_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            if eval_results.get(case.case_id) is None:
                notes.append(f"{case.case_id}: final_text_scores were computed heuristically because no eval summary entry was provided.")

        summary = WorkflowDiagnosticsSummary(
            label=run_label,
            source_case_dir=str(Path(case_dir)),
            case_ids=[item.case_id for item in cases],
            case_reports=case_reports,
            aggregate_findings=self._aggregate(case_reports),
            notes=sorted(set(notes)),
        )
        json_path = run_dir / "workflow_diagnostics_summary.json"
        md_path = run_dir / "workflow_diagnostics_report.md"
        summary = summary.model_copy(update={"report_json": str(json_path), "report_markdown": str(md_path)})
        write_text_with_aliases(
            json_path,
            summary.model_dump_json(indent=2),
            alias_names=("diagnostics_summary.json",),
        )
        write_text_with_aliases(md_path, render_workflow_diagnostics_markdown(summary), alias_names=("report.md",))
        return summary

    def _diagnose_case(
        self,
        *,
        case: HistoricalEvalCase,
        eval_result: RomanceCaseResult | None,
    ) -> WorkflowDiagnosticsCaseReport:
        diagnostic_signals = self._diagnostic_signals(case)
        final_text_scores = self._final_text_scores(case=case, eval_result=eval_result)
        workflow_layer_diagnostics = self._workflow_layer_diagnostics(
            case=case,
            final_text_scores=final_text_scores,
            diagnostic_signals=diagnostic_signals,
        )
        step_diagnostics = self._step_diagnostics(case=case, workflow_layers=workflow_layer_diagnostics, final_text_scores=final_text_scores)
        root_causes, targets = self._root_causes(workflow_layer_diagnostics=workflow_layer_diagnostics, step_diagnostics=step_diagnostics)
        return WorkflowDiagnosticsCaseReport(
            case_id=case.case_id,
            title=case.metadata.chapter_title or str(case.inputs.chapter_brief.get("title") or case.case_id),
            tags=list(case.metadata.tags or []),
            final_text_scores=final_text_scores,
            diagnostic_signals=diagnostic_signals,
            workflow_layer_diagnostics=workflow_layer_diagnostics,
            step_diagnostics=step_diagnostics,
            root_cause_hypothesis=root_causes,
            optimization_targets=targets,
            cost_metrics=case.metrics,
            missing_fields=[item.field for item in case.export_notes if item.level == "warning"],
        )

    def _diagnostic_signals(self, case: HistoricalEvalCase) -> dict[str, RomanceMetricDetail]:
        return {
            "anti_slop_score": AntiSlopRuleAnalyzer().analyze(
                chapter_text=case.outputs.final_text,
                review_reports=_latest_review_reports(case),
            ),
            "pronoun_lead_score": PronounLeadRuleAnalyzer().analyze(
                chapter_text=case.outputs.final_text,
            ),
            "explanation_density_score": ExplanationDensityRuleAnalyzer().analyze(
                chapter_text=case.outputs.final_text,
            ),
            "action_carried_reveal_score": ActionCarriedRevealRuleAnalyzer().analyze(
                chapter_text=case.outputs.final_text,
            ),
            "relationship_cost_realization_score": RelationshipCostRealizationRuleAnalyzer().analyze(
                chapter_text=case.outputs.final_text,
            ),
        }

    def _final_text_scores(
        self,
        *,
        case: HistoricalEvalCase,
        eval_result: RomanceCaseResult | None,
    ) -> dict[str, RomanceMetricDetail]:
        if eval_result is not None and eval_result.metrics:
            return dict(eval_result.metrics)

        prose = _tool_report(case, "review_prose_quality")
        humanity = _tool_report(case, "review_humanity")
        continuity = _tool_report(case, "review_continuity")
        chapter_engine = _tool_report(case, "review_chapter_engine")
        plot_logic = _tool_report(case, "review_plot_logic")
        character_integrity = _tool_report(case, "review_character_integrity")
        brief = dict(case.inputs.chapter_brief or {})
        final_text = case.outputs.final_text

        redundancy = RedundancyRuleAnalyzer().analyze(
            chapter_text=final_text,
            stage_log=list(case.intermediates.stage_log or []),
            review_reports=_latest_review_reports(case),
        )
        continuity_score = _review_binary_score(continuity, pass_score=8.2, fail_score=5.4)
        continuity_score -= 0.3 if plot_logic.get("passed") is False else 0.0
        tension_score = mean(
            [
                float(prose.get("tension_score") or 6.5),
                float(prose.get("pressure_authenticity_score") or 6.4),
                7.2 if str(brief.get("romance_seed") or "").strip() else 6.0,
                7.0 if str(brief.get("reader_emotion") or "").strip() else 6.0,
            ]
        )
        relationship_penalty = 0.0
        relationship_blob = json.dumps(
            {
                "relationship_state": case.inputs.relationship_state,
                "review_chapter_engine": chapter_engine,
                "review_continuity": continuity,
            },
            ensure_ascii=False,
        ).lower()
        if any(token in relationship_blob for token in ("relationship_reprice", "relationship", "关系", "暧昧")):
            relationship_penalty -= 0.4
        relationship_score = mean(
            [
                7.2 if str(brief.get("relationship_reprice") or "").strip() else 5.8,
                7.0 if str(case.inputs.relationship_state.get("text") or "").strip() else 5.6,
                continuity_score,
            ]
        ) + relationship_penalty
        emotional_score = mean(
            [
                float(prose.get("emotion_externalization_score") or 6.0),
                float(humanity.get("human_warmth_score") or 6.0),
                7.0 if str(brief.get("human_pain_anchor") or "").strip() else 5.8,
            ]
        )
        attraction_score = mean(
            [
                float(prose.get("dialogue_subtext_score") or 6.2),
                float(prose.get("memorability_score") or 6.2),
                float(prose.get("double_duty_detail_score") or 6.2),
            ]
        )
        hook_issue_count = len(_report_issues(chapter_engine))
        hook_score = mean(
            [
                7.6 if str(brief.get("opening_hook") or "").strip() else 5.8,
                7.4 if str(brief.get("ending_pull") or "").strip() else 5.8,
                float(prose.get("memorability_score") or 6.0),
            ]
        ) - min(hook_issue_count * 0.35, 1.4)
        mind_state_score = mean(
            [
                7.2 if list(case.inputs.character_mind_states or []) else 5.4,
                _review_binary_score(character_integrity, pass_score=8.0, fail_score=5.3),
                continuity_score,
            ]
        )

        evidence_seed = [
            str(brief.get("summary") or ""),
            str(brief.get("relationship_reprice") or ""),
            str(brief.get("ending_pull") or ""),
        ]
        return {
            "romance_tension_score": _heuristic_detail(
                score=tension_score,
                reason="Heuristic score based on prose pressure, reader emotion, and romance seed coverage.",
                evidence=[str(prose.get("rewrite_guidance") or ""), *evidence_seed],
                hint="Strengthen visible cost and immediate pressure in the scene body, not only in the chapter brief.",
            ),
            "relationship_progression_score": _heuristic_detail(
                score=relationship_score,
                reason="Heuristic score based on relationship-state coverage, reprice target, and continuity behavior.",
                evidence=[str(case.inputs.relationship_state.get("text") or ""), str(brief.get("relationship_reprice") or "")],
                hint="Make the relationship repricing land in an observable move, not only in setup text.",
            ),
            "emotional_resonance_score": _heuristic_detail(
                score=emotional_score,
                reason="Heuristic score based on humanity and externalized emotion signals.",
                evidence=[str(humanity.get("rewrite_guidance") or ""), str(brief.get("human_pain_anchor") or "")],
                hint="Turn abstract emotion into bodily leakage, tradeoff, and supporting-character reaction.",
            ),
            "character_attraction_score": _heuristic_detail(
                score=attraction_score,
                reason="Heuristic score based on memorability, subtext, and detail efficiency.",
                evidence=[str(prose.get("evidence_notes") or ""), str(brief.get("romance_seed") or "")],
                hint="Sharpen chemistry through contrast, micro-reaction, and selective detail instead of repeated summary.",
            ),
            "hook_score": _heuristic_detail(
                score=hook_score,
                reason="Heuristic score based on opening_hook, ending_pull, and chapter engine issue pressure.",
                evidence=[str(brief.get("opening_hook") or ""), str(brief.get("ending_pull") or ""), str(chapter_engine.get("rewrite_guidance") or "")],
                hint="Ensure the opening hook and ending pull are each paid off in distinct visible beats.",
            ),
            "continuity_score": _heuristic_detail(
                score=continuity_score,
                reason="Derived from continuity and plot-logic review outcomes.",
                evidence=[str(continuity.get("rewrite_guidance") or ""), str(plot_logic.get("rewrite_guidance") or "")],
                hint="Protect continuity and causality before chasing higher romance intensity.",
            ),
            "redundancy_score": redundancy,
            "mind_state_consistency_score": _heuristic_detail(
                score=mind_state_score,
                reason="Heuristic score based on persisted mind states and character-integrity review signals.",
                evidence=[str(character_integrity.get("rewrite_guidance") or ""), json.dumps(case.inputs.character_mind_states[:2], ensure_ascii=False)],
                hint="Preserve viewpoint-specific desire, fear, and restraint inside the final prose behavior.",
            ),
        }

    def _workflow_layer_diagnostics(
        self,
        *,
        case: HistoricalEvalCase,
        final_text_scores: dict[str, RomanceMetricDetail],
        diagnostic_signals: dict[str, RomanceMetricDetail],
    ) -> dict[str, WorkflowDiagnosticDetail]:
        brief = dict(case.inputs.chapter_brief or {})
        writing_pack = dict(case.inputs.writing_pack or {})
        block_plan = dict(case.intermediates.block_plan or {})
        latest_review = _latest_review_reports(case)
        final_judge = dict(case.intermediates.final_judge or {})
        anti_slop_detail = diagnostic_signals.get("anti_slop_score")
        anti_slop_score = anti_slop_detail.score if anti_slop_detail is not None else 7.0
        pronoun_detail = diagnostic_signals.get("pronoun_lead_score")
        pronoun_score = pronoun_detail.score if pronoun_detail is not None else 7.0
        explanation_detail = diagnostic_signals.get("explanation_density_score")
        explanation_score = explanation_detail.score if explanation_detail is not None else 7.0
        action_reveal_detail = diagnostic_signals.get("action_carried_reveal_score")
        action_reveal_score = action_reveal_detail.score if action_reveal_detail is not None else 7.0
        relationship_cost_detail = diagnostic_signals.get("relationship_cost_realization_score")
        relationship_cost_score = relationship_cost_detail.score if relationship_cost_detail is not None else 7.0

        input_completeness = mean(
            [
                8.0 if brief else 4.5,
                7.8 if str(case.inputs.chapter_payload or "").strip() else 4.8,
                7.3 if list(case.inputs.recent_actual_summaries or []) else 5.5,
            ]
        )
        state_completeness = mean(
            [
                7.6 if str(case.inputs.relationship_state.get("text") or "").strip() else 5.0,
                7.8 if list(case.inputs.character_mind_states or []) else 5.0,
                final_text_scores["mind_state_consistency_score"].score,
            ]
        )
        writing_pack_completeness = mean(
            [
                7.6 if str(writing_pack.get("step_6_twists_text") or "").strip() else 5.5,
                7.6 if str(writing_pack.get("step_7_story_lines_text") or "").strip() else 5.5,
                7.4 if str(writing_pack.get("relevant_world_rules_text") or "").strip() else 5.2,
                7.4 if str(writing_pack.get("chapter_payload_text") or case.inputs.chapter_payload).strip() else 5.2,
            ]
        )
        planning_score = mean(
            [
                7.8 if int(block_plan.get("block_count") or 0) >= 3 else 5.0,
                7.4 if list(block_plan.get("blocks") or []) else 5.0,
                final_text_scores["hook_score"].score,
            ]
        )
        draft_score = mean(
            [
                final_text_scores["romance_tension_score"].score,
                final_text_scores["relationship_progression_score"].score,
                final_text_scores["emotional_resonance_score"].score,
                final_text_scores["character_attraction_score"].score,
                final_text_scores["continuity_score"].score,
                anti_slop_score,
                pronoun_score,
                explanation_score,
                action_reveal_score,
                relationship_cost_score,
            ]
        )
        revision_score = self._patch_effectiveness_score(case)
        if case.metrics.patch_rounds:
            revision_score = mean([revision_score, anti_slop_score])
        elif anti_slop_score < 6.0:
            revision_score -= 0.3
        if case.metrics.used_full_rewrite:
            revision_score -= 0.5
        if bool(final_judge.get("blocking_reasons")):
            revision_score -= min(len(list(final_judge.get("blocking_reasons") or [])) * 0.2, 1.0)

        return {
            "input_definition_layer": WorkflowDiagnosticDetail(
                score=_clamp(input_completeness),
                reason="Measures whether the exporter captured enough brief and carry-over context for reliable replay and diagnosis.",
                evidence=[
                    f"chapter_brief_present={bool(brief)}",
                    f"chapter_payload_present={bool(str(case.inputs.chapter_payload).strip())}",
                    f"recent_actual_summaries={len(case.inputs.recent_actual_summaries)}",
                ],
                improvement_hint="Backfill missing chapter brief, payload, and prior summary signals before optimizing downstream prompts.",
            ),
            "state_modeling_layer": WorkflowDiagnosticDetail(
                score=_clamp(state_completeness),
                reason="Measures relationship-state and mind-state fidelity between inputs and final prose behavior.",
                evidence=[
                    f"relationship_state_present={bool(str(case.inputs.relationship_state.get('text') or '').strip())}",
                    f"mind_states={len(case.inputs.character_mind_states)}",
                    f"mind_state_consistency={final_text_scores['mind_state_consistency_score'].score:.2f}",
                ],
                improvement_hint="Strengthen persisted relationship and mindset packets before touching surface prose prompts.",
            ),
            "writing_pack_layer": WorkflowDiagnosticDetail(
                score=_clamp(writing_pack_completeness),
                reason="Measures whether the writing pack preserved world rules, active twists, story lines, and chapter payload details.",
                evidence=[
                    f"world_rules_present={bool(str(writing_pack.get('relevant_world_rules_text') or '').strip())}",
                    f"twists_present={bool(str(writing_pack.get('step_6_twists_text') or '').strip())}",
                    f"story_lines_present={bool(str(writing_pack.get('step_7_story_lines_text') or '').strip())}",
                ],
                improvement_hint="Reduce information loss inside the writing pack before expanding rewrite scope.",
            ),
            "chapter_planning_layer": WorkflowDiagnosticDetail(
                score=_clamp(planning_score),
                reason="Measures whether block planning created a usable skeleton for hooks, escalation, and relationship movement.",
                evidence=[
                    f"block_count={int(block_plan.get('block_count') or 0)}",
                    f"hook_score={final_text_scores['hook_score'].score:.2f}",
                    f"planning_stage={str(block_plan.get('stage') or '')}",
                ],
                improvement_hint="Improve block responsibilities and middle escalation before changing final polish behavior.",
            ),
            "draft_execution_layer": WorkflowDiagnosticDetail(
                score=_clamp(draft_score),
                reason="Measures how well the draft converted planning and context into readable romance payoff, continuity, and pull.",
                evidence=[
                    f"romance_tension={final_text_scores['romance_tension_score'].score:.2f}",
                    f"relationship_progression={final_text_scores['relationship_progression_score'].score:.2f}",
                    f"continuity={final_text_scores['continuity_score'].score:.2f}",
                    f"anti_slop={anti_slop_score:.2f}",
                    f"pronoun_lead={pronoun_score:.2f}",
                    f"explanation_density={explanation_score:.2f}",
                    f"action_reveal={action_reveal_score:.2f}",
                    f"relationship_cost={relationship_cost_score:.2f}",
                    f"failing_tools={','.join(case.metrics.failing_tools) or 'none'}",
                ],
                improvement_hint="Prefer fixing drafting behavior and plan execution over hiding issues in judge prompts or summary-style explanation sentences.",
            ),
            "revision_layer": WorkflowDiagnosticDetail(
                score=_clamp(revision_score),
                reason="Measures whether review and rewrite rounds reduced blockers without overusing full rewrite, while also removing direct-thought and explanation slop from the final prose.",
                evidence=[
                    f"review_rounds={case.metrics.review_rounds}",
                    f"patch_rounds={case.metrics.patch_rounds}",
                    f"used_full_rewrite={str(case.metrics.used_full_rewrite).lower()}",
                    f"blocking_reasons={len(list(final_judge.get('blocking_reasons') or []))}",
                    f"anti_slop={anti_slop_score:.2f}",
                ],
                improvement_hint="Keep revision focused and patch-oriented; use final polish to delete direct-thought / explanation sentences before escalating rewrite scope.",
            ),
        }

    def _patch_effectiveness_score(self, case: HistoricalEvalCase) -> float:
        review_iterations = list(case.intermediates.review_reports or [])
        if not review_iterations:
            return 6.0 if not case.metrics.patch_rounds else 5.5
        if len(review_iterations) == 1:
            if bool(review_iterations[0].get("final_judge", {}).get("passed")):
                return 7.8
            return 5.8
        first_blockers = len(list(review_iterations[0].get("final_judge", {}).get("blocking_reasons") or []))
        last_blockers = len(list(review_iterations[-1].get("final_judge", {}).get("blocking_reasons") or []))
        delta = first_blockers - last_blockers
        base = 6.0
        if delta > 0:
            base += min(delta * 0.9, 2.4)
        elif delta < 0:
            base -= min(abs(delta) * 0.9, 2.4)
        if bool(review_iterations[-1].get("final_judge", {}).get("passed")):
            base += 1.0
        return _clamp(base)

    def _step_diagnostics(
        self,
        *,
        case: HistoricalEvalCase,
        workflow_layers: dict[str, WorkflowDiagnosticDetail],
        final_text_scores: dict[str, RomanceMetricDetail],
    ) -> dict[str, WorkflowDiagnosticDetail]:
        brief = dict(case.inputs.chapter_brief or {})
        block_plan = dict(case.intermediates.block_plan or {})
        return {
            "brief_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(workflow_layers["input_definition_layer"].score - (0.6 if not str(brief.get("opening_hook") or "").strip() else 0.0)),
                reason="Measures how actionable the chapter brief is for hook, restriction, and relationship movement.",
                evidence=[
                    f"opening_hook_present={bool(str(brief.get('opening_hook') or '').strip())}",
                    f"ending_pull_present={bool(str(brief.get('ending_pull') or '').strip())}",
                    f"relationship_reprice_present={bool(str(brief.get('relationship_reprice') or '').strip())}",
                ],
                improvement_hint="Tighten chapter briefs before blaming downstream rewrite behavior.",
            ),
            "relationship_state_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(workflow_layers["state_modeling_layer"].score),
                reason="Measures whether relationship state was explicit enough to support repricing on page.",
                evidence=[
                    f"relationship_state_text_present={bool(str(case.inputs.relationship_state.get('text') or '').strip())}",
                    f"relationship_progression={final_text_scores['relationship_progression_score'].score:.2f}",
                ],
                improvement_hint="Persist state deltas that the writer can visibly cash out inside one chapter.",
            ),
            "mind_state_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(mean([workflow_layers["state_modeling_layer"].score, final_text_scores["mind_state_consistency_score"].score])),
                reason="Measures whether character mind states stayed concrete enough to constrain prose behavior.",
                evidence=[
                    f"mind_states={len(case.inputs.character_mind_states)}",
                    f"mind_state_consistency={final_text_scores['mind_state_consistency_score'].score:.2f}",
                ],
                improvement_hint="Prefer explicit fear, hidden need, and restraint signals over generic emotional labels.",
            ),
            "writing_pack_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(workflow_layers["writing_pack_layer"].score),
                reason="Measures whether compressed writing-pack fields preserved the information the draft needed.",
                evidence=[
                    f"world_rules_present={bool(str(case.inputs.writing_pack.get('relevant_world_rules_text') or '').strip())}",
                    f"story_lines_present={bool(str(case.inputs.writing_pack.get('step_7_story_lines_text') or '').strip())}",
                ],
                improvement_hint="Focus on writing-pack preservation before adding more review passes.",
            ),
            "block_plan_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(mean([workflow_layers["chapter_planning_layer"].score, 7.2 if list(block_plan.get("blocks") or []) else 5.0])),
                reason="Measures whether content blocks created enough differentiated turns and responsibility boundaries.",
                evidence=[
                    f"block_count={int(block_plan.get('block_count') or 0)}",
                    f"planning_stage={str(block_plan.get('stage') or '')}",
                ],
                improvement_hint="Make block responsibilities sharper so middle escalation does not flatten.",
            ),
            "writer_execution_quality_score": WorkflowDiagnosticDetail(
                score=_clamp(workflow_layers["draft_execution_layer"].score),
                reason="Measures whether the drafting step delivered tension, hook, emotional resonance, and continuity together.",
                evidence=[
                    f"romance_tension={final_text_scores['romance_tension_score'].score:.2f}",
                    f"emotional_resonance={final_text_scores['emotional_resonance_score'].score:.2f}",
                    f"continuity={final_text_scores['continuity_score'].score:.2f}",
                ],
                improvement_hint="Modify real drafting behavior before considering judge-side prompt changes.",
            ),
            "patch_effectiveness_score": WorkflowDiagnosticDetail(
                score=_clamp(self._patch_effectiveness_score(case)),
                reason="Measures whether revision loops removed blockers efficiently without defaulting to full rewrite.",
                evidence=[
                    f"review_rounds={case.metrics.review_rounds}",
                    f"patch_rounds={case.metrics.patch_rounds}",
                    f"used_full_rewrite={str(case.metrics.used_full_rewrite).lower()}",
                ],
                improvement_hint="Keep revisions local and measurable; do not expand full rewrite by default.",
            ),
        }

    def _root_causes(
        self,
        *,
        workflow_layer_diagnostics: dict[str, WorkflowDiagnosticDetail],
        step_diagnostics: dict[str, WorkflowDiagnosticDetail],
    ) -> tuple[list[str], list[str]]:
        layer_order = sorted(workflow_layer_diagnostics.items(), key=lambda item: item[1].score)
        step_order = sorted(step_diagnostics.items(), key=lambda item: item[1].score)
        root_causes: list[str] = []
        targets: list[str] = []
        layer_targets = {
            "input_definition_layer": "tighten chapter brief and carry-over input definition",
            "state_modeling_layer": "improve persisted relationship and mind-state modeling",
            "writing_pack_layer": "improve writing-pack compression and signal preservation",
            "chapter_planning_layer": "improve content-block planning and middle escalation",
            "draft_execution_layer": "improve writer execution instead of judge-side scoring",
            "revision_layer": "improve patch logic and reduce default full rewrites",
        }
        step_targets = {
            "brief_quality_score": "tighten chapter brief specificity",
            "relationship_state_quality_score": "stabilize relationship-state packets",
            "mind_state_quality_score": "strengthen character mindset schema and carry-over",
            "writing_pack_quality_score": "preserve active twist and line signals in the writing pack",
            "block_plan_quality_score": "clarify block responsibilities and turn sequencing",
            "writer_execution_quality_score": "improve drafting prompts and execution logic",
            "patch_effectiveness_score": "improve patch planning before escalating rewrite scope",
        }
        for key, detail in layer_order[:2]:
            root_causes.append(f"{key}: {detail.reason}")
            targets.append(layer_targets[key])
        for key, detail in step_order[:2]:
            root_causes.append(f"{key}: {detail.reason}")
            targets.append(step_targets[key])
        return root_causes, list(dict.fromkeys(targets))

    @staticmethod
    def _aggregate(case_reports: list[WorkflowDiagnosticsCaseReport]) -> AggregateFindings:
        low_scores: Counter[str] = Counter()
        root_layers: Counter[str] = Counter()
        root_steps: Counter[str] = Counter()
        failure_tags: Counter[str] = Counter()
        full_rewrite_cases: list[str] = []
        redundancy_cases: list[str] = []
        slop_cases: list[str] = []
        for report in case_reports:
            for metric_name, detail in report.final_text_scores.items():
                if detail.score < 7.0:
                    low_scores[metric_name] += 1
            lowest_layer = min(report.workflow_layer_diagnostics.items(), key=lambda item: item[1].score)[0]
            lowest_step = min(report.step_diagnostics.items(), key=lambda item: item[1].score)[0]
            root_layers[lowest_layer] += 1
            root_steps[lowest_step] += 1
            if report.cost_metrics.used_full_rewrite:
                full_rewrite_cases.append(report.case_id)
            redundancy_detail = report.final_text_scores.get("redundancy_score")
            if redundancy_detail is not None and redundancy_detail.score < 7.0:
                redundancy_cases.append(report.case_id)
            anti_slop_detail = report.diagnostic_signals.get("anti_slop_score")
            pronoun_detail = report.diagnostic_signals.get("pronoun_lead_score")
            explanation_detail = report.diagnostic_signals.get("explanation_density_score")
            action_reveal_detail = report.diagnostic_signals.get("action_carried_reveal_score")
            relationship_cost_detail = report.diagnostic_signals.get("relationship_cost_realization_score")
            if (
                (anti_slop_detail is not None and anti_slop_detail.score < 7.0)
                or (pronoun_detail is not None and pronoun_detail.score < 7.0)
                or (explanation_detail is not None and explanation_detail.score < 7.0)
                or (action_reveal_detail is not None and action_reveal_detail.score < 7.0)
                or (relationship_cost_detail is not None and relationship_cost_detail.score < 7.0)
            ):
                slop_cases.append(report.case_id)
            if sum(1 for detail in report.final_text_scores.values() if detail.score < 7.0) >= 2:
                for tag in report.tags:
                    failure_tags[tag] += 1
        return AggregateFindings(
            most_common_low_scores=[item for item, _ in low_scores.most_common(5)],
            most_common_root_layers=[item for item, _ in root_layers.most_common(5)],
            most_common_root_steps=[item for item, _ in root_steps.most_common(5)],
            frequent_full_rewrite_cases=sorted(full_rewrite_cases),
            redundancy_hotspot_cases=sorted(redundancy_cases),
            slop_hotspot_cases=sorted(slop_cases),
            failure_prone_tags=[item for item, _ in failure_tags.most_common(5)],
        )


def render_workflow_diagnostics_markdown(summary: WorkflowDiagnosticsSummary) -> str:
    lines = [
        f"# Workflow Diagnostics Report: {summary.label}",
        "",
        f"- source_case_dir: `{summary.source_case_dir}`",
        f"- generated_at: `{summary.generated_at.isoformat()}`",
        f"- cases: `{len(summary.case_reports)}`",
        "",
        "## Aggregate Findings",
        "",
        f"- most_common_low_scores: {', '.join(summary.aggregate_findings.most_common_low_scores) or 'None'}",
        f"- most_common_root_layers: {', '.join(summary.aggregate_findings.most_common_root_layers) or 'None'}",
        f"- most_common_root_steps: {', '.join(summary.aggregate_findings.most_common_root_steps) or 'None'}",
        f"- failure_prone_tags: {', '.join(summary.aggregate_findings.failure_prone_tags) or 'None'}",
        f"- frequent_full_rewrite_cases: {', '.join(summary.aggregate_findings.frequent_full_rewrite_cases) or 'None'}",
        f"- redundancy_hotspot_cases: {', '.join(summary.aggregate_findings.redundancy_hotspot_cases) or 'None'}",
        f"- slop_hotspot_cases: {', '.join(summary.aggregate_findings.slop_hotspot_cases) or 'None'}",
    ]
    for report in summary.case_reports:
        lines.extend(
            [
                "",
                f"## {report.case_id} - {report.title}",
                "",
                "| metric | score |",
                "| --- | ---: |",
            ]
        )
        for metric in CORE_METRICS:
            detail = report.final_text_scores.get(metric)
            if detail is None:
                continue
            lines.append(f"| {metric} | {detail.score:.2f} |")
        if report.diagnostic_signals:
            lines.extend(
                [
                    "",
                    "| diagnostic signal | score |",
                    "| --- | ---: |",
                ]
            )
            for key, detail in report.diagnostic_signals.items():
                lines.append(f"| {key} | {detail.score:.2f} |")
        lines.extend(
            [
                "",
                "| workflow layer | score |",
                "| --- | ---: |",
            ]
        )
        for key in WORKFLOW_LAYERS:
            detail = report.workflow_layer_diagnostics.get(key)
            if detail is None:
                continue
            lines.append(f"| {key} | {detail.score:.2f} |")
        lines.extend(
            [
                "",
                f"- root_cause_hypothesis: {', '.join(report.root_cause_hypothesis) or 'None'}",
                f"- optimization_targets: {', '.join(report.optimization_targets) or 'None'}",
                (
                    "- cost_metrics: "
                    f"review_rounds={report.cost_metrics.review_rounds}, "
                    f"patch_rounds={report.cost_metrics.patch_rounds}, "
                    f"used_full_rewrite={str(report.cost_metrics.used_full_rewrite).lower()}, "
                    f"quality_risk={report.cost_metrics.quality_risk:.2f}"
                ),
            ]
        )
        if report.missing_fields:
            lines.append(f"- missing_fields: {', '.join(report.missing_fields)}")
    if summary.notes:
        lines.extend(["", "## Notes", ""])
        for item in summary.notes:
            lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"
