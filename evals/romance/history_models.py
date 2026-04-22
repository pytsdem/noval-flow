from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.romance.models import RomanceEvalCase, RomanceMetricDetail


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseExportNote(BaseModel):
    level: Literal["info", "warning"] = "info"
    field: str = ""
    message: str


class HistoricalCaseMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    book_id: str = ""
    chapter_id: str = ""
    run_id: str = ""
    timestamp: str = ""
    pipeline_version: str = ""
    mode: str = "other"
    source: str = "db"
    tags: list[str] = Field(default_factory=list)
    chapter_title: str = ""
    sample_mode: str = ""
    source_label: str = ""


class HistoricalCaseInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    chapter_brief: dict[str, Any] = Field(default_factory=dict)
    chapter_payload: str = ""
    relationship_state: dict[str, Any] = Field(default_factory=dict)
    character_mind_states: list[dict[str, Any]] = Field(default_factory=list)
    scene_character_context: dict[str, Any] = Field(default_factory=dict)
    recent_actual_summaries: list[dict[str, Any]] = Field(default_factory=list)
    writing_pack: dict[str, Any] = Field(default_factory=dict)
    sanitized_writer_context: dict[str, Any] = Field(default_factory=dict)
    premise: dict[str, Any] = Field(default_factory=dict)
    twist_designs: list[dict[str, Any]] = Field(default_factory=list)
    story_lines: list[dict[str, Any]] = Field(default_factory=list)
    character_cards: list[dict[str, Any]] = Field(default_factory=list)
    worldbuilding: dict[str, Any] = Field(default_factory=dict)
    character_milestones: list[dict[str, Any]] = Field(default_factory=list)
    goals: dict[str, Any] = Field(default_factory=dict)
    context_overrides: dict[str, Any] = Field(default_factory=dict)


class HistoricalCaseIntermediates(BaseModel):
    model_config = ConfigDict(extra="allow")

    block_plan: dict[str, Any] = Field(default_factory=dict)
    review_reports: list[dict[str, Any]] = Field(default_factory=list)
    patch_plan: dict[str, Any] = Field(default_factory=dict)
    patch_reports: list[dict[str, Any]] = Field(default_factory=list)
    actual_summary: dict[str, Any] = Field(default_factory=dict)
    chapter_summary: dict[str, Any] = Field(default_factory=dict)
    stage_log: list[dict[str, Any]] = Field(default_factory=list)
    content_blocks: list[dict[str, Any]] = Field(default_factory=list)
    final_judge: dict[str, Any] = Field(default_factory=dict)


class HistoricalCaseOutputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    final_text: str = ""
    final_summary: str = ""
    final_status: Literal["success", "patched", "failed_partial", "unknown"] = "unknown"
    final_version: int = 0


class HistoricalCaseMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm_calls: int | None = None
    review_rounds: int = 0
    patch_rounds: int = 0
    used_full_rewrite: bool = False
    latency_ms: int | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    tool_calls_by_name: dict[str, int] = Field(default_factory=dict)
    failing_tools: list[str] = Field(default_factory=list)
    quality_risk: float = 0.0


class HistoricalEvalCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    metadata: HistoricalCaseMetadata = Field(default_factory=HistoricalCaseMetadata)
    inputs: HistoricalCaseInputs = Field(default_factory=HistoricalCaseInputs)
    intermediates: HistoricalCaseIntermediates = Field(default_factory=HistoricalCaseIntermediates)
    outputs: HistoricalCaseOutputs = Field(default_factory=HistoricalCaseOutputs)
    metrics: HistoricalCaseMetrics = Field(default_factory=HistoricalCaseMetrics)
    export_notes: list[CaseExportNote] = Field(default_factory=list)
    replay_case: dict[str, Any] = Field(default_factory=dict)

    def to_romance_eval_case(self) -> RomanceEvalCase:
        if self.replay_case:
            return RomanceEvalCase.model_validate(self.replay_case)

        brief = self.inputs.chapter_brief
        goals = dict(self.inputs.goals or {})
        if not goals:
            goals = {
                "chapter_goal": str(brief.get("summary") or self.outputs.final_summary or self.case_id),
                "emotional_goal": str(brief.get("reader_emotion") or ""),
                "relationship_goal": str(brief.get("relationship_reprice") or ""),
                "hook_goal": str(brief.get("opening_hook") or brief.get("ending_pull") or ""),
                "continuation_drive": str(brief.get("ending_pull") or ""),
            }

        payload = {
            "case_id": self.case_id,
            "title": self.metadata.chapter_title or str(brief.get("title") or self.case_id),
            "description": self.outputs.final_summary or str(brief.get("summary") or ""),
            "tags": list(self.metadata.tags or []),
            "premise": dict(self.inputs.premise or {}),
            "chapter_brief": dict(brief or {}),
            "twist_designs": list(self.inputs.twist_designs or []),
            "story_lines": list(self.inputs.story_lines or []),
            "character_cards": list(self.inputs.character_cards or []),
            "worldbuilding": dict(self.inputs.worldbuilding or {}),
            "character_milestones": list(self.inputs.character_milestones or []),
            "actual_chapter_summaries": list(self.inputs.recent_actual_summaries or []),
            "prior_character_mindsets": list(self.inputs.character_mind_states or []),
            "goals": goals,
            "context_overrides": dict(self.inputs.context_overrides or {}),
        }
        return RomanceEvalCase.model_validate(payload)


class CaseExportSummary(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    output_dir: str = ""
    source_db: str = ""
    sample_mode: str = "latest"
    limit: int = 0
    exported_case_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkflowDiagnosticDetail(BaseModel):
    score: float = Field(ge=0.0, le=10.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    improvement_hint: str = ""
    source: Literal["heuristic", "eval", "hybrid"] = "heuristic"


class WorkflowDiagnosticsCaseReport(BaseModel):
    case_id: str
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    final_text_scores: dict[str, RomanceMetricDetail] = Field(default_factory=dict)
    workflow_layer_diagnostics: dict[str, WorkflowDiagnosticDetail] = Field(default_factory=dict)
    step_diagnostics: dict[str, WorkflowDiagnosticDetail] = Field(default_factory=dict)
    root_cause_hypothesis: list[str] = Field(default_factory=list)
    optimization_targets: list[str] = Field(default_factory=list)
    cost_metrics: HistoricalCaseMetrics = Field(default_factory=HistoricalCaseMetrics)
    source_case_json: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AggregateFindings(BaseModel):
    most_common_low_scores: list[str] = Field(default_factory=list)
    most_common_root_layers: list[str] = Field(default_factory=list)
    most_common_root_steps: list[str] = Field(default_factory=list)
    frequent_full_rewrite_cases: list[str] = Field(default_factory=list)
    redundancy_hotspot_cases: list[str] = Field(default_factory=list)
    failure_prone_tags: list[str] = Field(default_factory=list)


class WorkflowDiagnosticsSummary(BaseModel):
    label: str
    generated_at: datetime = Field(default_factory=utc_now)
    source_case_dir: str = ""
    case_ids: list[str] = Field(default_factory=list)
    case_reports: list[WorkflowDiagnosticsCaseReport] = Field(default_factory=list)
    aggregate_findings: AggregateFindings = Field(default_factory=AggregateFindings)
    report_json: str = ""
    report_markdown: str = ""
    notes: list[str] = Field(default_factory=list)


class StepGateDecision(BaseModel):
    verdict: Literal["pass", "warn", "blocked"] = "warn"
    accept_for_chapter_generation: bool = False
    gating_step_keys: list[str] = Field(default_factory=list)
    blocking_steps: list[str] = Field(default_factory=list)
    warning_steps: list[str] = Field(default_factory=list)
    average_step_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class StepEvalCaseReport(BaseModel):
    case_id: str
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    workflow_layer_diagnostics: dict[str, WorkflowDiagnosticDetail] = Field(default_factory=dict)
    step_diagnostics: dict[str, WorkflowDiagnosticDetail] = Field(default_factory=dict)
    gate_decision: StepGateDecision = Field(default_factory=StepGateDecision)
    cost_metrics: HistoricalCaseMetrics = Field(default_factory=HistoricalCaseMetrics)
    source_case_json: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StepEvalAggregateFindings(BaseModel):
    most_common_blocking_steps: list[str] = Field(default_factory=list)
    most_common_warning_steps: list[str] = Field(default_factory=list)
    blocked_case_ids: list[str] = Field(default_factory=list)
    accepted_case_ids: list[str] = Field(default_factory=list)
    failure_prone_tags: list[str] = Field(default_factory=list)


class StepEvalSummary(BaseModel):
    label: str
    generated_at: datetime = Field(default_factory=utc_now)
    source_case_dir: str = ""
    case_ids: list[str] = Field(default_factory=list)
    case_reports: list[StepEvalCaseReport] = Field(default_factory=list)
    aggregate_findings: StepEvalAggregateFindings = Field(default_factory=StepEvalAggregateFindings)
    gate_counts: dict[str, int] = Field(default_factory=dict)
    report_json: str = ""
    report_markdown: str = ""
    notes: list[str] = Field(default_factory=list)
