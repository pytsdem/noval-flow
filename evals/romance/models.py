from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from novel_flow.models.schemas import (
    ActualChapterSummary,
    ChapterBrief,
    CharacterCard,
    CharacterMindset,
    StoryLine,
    StoryPremise,
    TwistDesign,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RomanceCaseGoals(BaseModel):
    chapter_goal: str
    emotional_goal: str
    relationship_goal: str
    hook_goal: str = ""
    continuation_drive: str = ""


class RomanceCaseContextOverrides(BaseModel):
    assistant_persona_prompt: str = ""
    writing_requirements: dict[str, Any] = Field(default_factory=dict)
    reference_pack: str = ""
    previous_chapter_full_text: str = ""
    completed_chapter_summary_bundle: str = ""
    chapter_payload_text: str = ""
    timeline_anchor_facts_text: str = ""
    relevant_world_rules_text: str = ""
    scene_character_context_text: str = ""
    relationship_state_text: str = ""


class RomanceEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    premise: StoryPremise
    chapter_brief: ChapterBrief
    twist_designs: list[TwistDesign] = Field(default_factory=list)
    story_lines: list[StoryLine] = Field(default_factory=list)
    character_cards: list[CharacterCard] = Field(default_factory=list)
    worldbuilding: dict[str, Any] = Field(default_factory=dict)
    character_milestones: list[dict[str, Any]] = Field(default_factory=list)
    actual_chapter_summaries: list[ActualChapterSummary] = Field(default_factory=list)
    prior_character_mindsets: list[CharacterMindset] = Field(default_factory=list)
    goals: RomanceCaseGoals
    context_overrides: RomanceCaseContextOverrides = Field(default_factory=RomanceCaseContextOverrides)


class RomanceMetricDetail(BaseModel):
    score: float = Field(ge=0.0, le=10.0)
    reason: str
    evidence_summary: str
    improvement_hint: str
    source: Literal["llm", "rule", "hybrid", "fallback"] = "llm"


class RomanceJudgeDiagnosis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_hints: list[str] = Field(default_factory=list)


class RomanceJudgePayload(BaseModel):
    romance_tension: RomanceMetricDetail
    relationship_progression: RomanceMetricDetail
    emotional_resonance: RomanceMetricDetail
    male_lead_attraction: RomanceMetricDetail
    female_lead_attraction: RomanceMetricDetail
    lead_pair_chemistry: RomanceMetricDetail
    opening_hook: RomanceMetricDetail
    ending_hook: RomanceMetricDetail
    continuity: RomanceMetricDetail
    redundancy: RomanceMetricDetail
    mind_state_consistency: RomanceMetricDetail
    diagnosis: RomanceJudgeDiagnosis = Field(default_factory=RomanceJudgeDiagnosis)


class RomanceHardFailFlag(BaseModel):
    flag_type: str
    severity: Literal["blocker", "high"]
    reason: str
    evidence_summary: str
    related_metrics: list[str] = Field(default_factory=list)
    suggested_modules: list[str] = Field(default_factory=list)
    source: Literal["heuristic", "judge", "rule", "fallback"] = "heuristic"


class RomanceOptimizationTarget(BaseModel):
    target_module: str
    issue_type: str
    severity: Literal["blocker", "high", "medium"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    evidence_summary: str
    patch_hint: str
    related_metrics: list[str] = Field(default_factory=list)
    expected_metric_gains: list[str] = Field(default_factory=list)


class RomanceCostMetrics(BaseModel):
    llm_calls: int = 0
    judge_llm_calls: int = 0
    review_calls: int = 0
    patch_rounds: int = 0
    used_full_rewrite: bool = False
    duration_seconds: float = 0.0
    block_count: int = 0
    patched_block_count: int = 0
    patched_block_ratio: float = 0.0
    generation_prompt_chars: int = 0
    judge_prompt_chars: int = 0
    tool_calls_by_name: dict[str, int] = Field(default_factory=dict)


class RomanceCaseArtifacts(BaseModel):
    case_dir: str = ""
    case_input_json: str = ""
    writer_context_json: str = ""
    chapter_execution_json: str = ""
    stage_log_json: str = ""
    final_text_txt: str = ""
    judge_json: str = ""
    result_json: str = ""


class RomanceCaseResult(BaseModel):
    case_id: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "needs_work", "blocked"] = "needs_work"
    scores: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, RomanceMetricDetail] = Field(default_factory=dict)
    breakdowns: dict[str, RomanceMetricDetail] = Field(default_factory=dict)
    diagnosis: RomanceJudgeDiagnosis = Field(default_factory=RomanceJudgeDiagnosis)
    hard_fail_flags: list[RomanceHardFailFlag] = Field(default_factory=list)
    optimization_targets: list[RomanceOptimizationTarget] = Field(default_factory=list)
    cost_metrics: RomanceCostMetrics = Field(default_factory=RomanceCostMetrics)
    artifacts: RomanceCaseArtifacts = Field(default_factory=RomanceCaseArtifacts)
    errors: list[str] = Field(default_factory=list)


class RomanceRunSummary(BaseModel):
    label: str
    mode: str
    generated_at: datetime = Field(default_factory=utc_now)
    provider: str = ""
    model: str = ""
    run_dir: str = ""
    case_ids: list[str] = Field(default_factory=list)
    average_scores: dict[str, float] = Field(default_factory=dict)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    blocked_case_ids: list[str] = Field(default_factory=list)
    optimization_target_counts: dict[str, int] = Field(default_factory=dict)
    case_results: list[RomanceCaseResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    compared_to: str = ""
    report_markdown: str = ""
    report_json: str = ""


class ScoreDelta(BaseModel):
    baseline: float
    candidate: float
    delta: float


class RomanceCaseDiff(BaseModel):
    case_id: str
    title: str
    baseline_verdict: str = ""
    candidate_verdict: str = ""
    score_deltas: dict[str, ScoreDelta] = Field(default_factory=dict)
    improved_metrics: list[str] = Field(default_factory=list)
    declined_metrics: list[str] = Field(default_factory=list)
    new_blockers: list[str] = Field(default_factory=list)
    resolved_blockers: list[str] = Field(default_factory=list)
    cost_deltas: dict[str, float] = Field(default_factory=dict)


class RomanceRunDiff(BaseModel):
    baseline_label: str
    candidate_label: str
    compared_at: datetime = Field(default_factory=utc_now)
    average_score_deltas: dict[str, ScoreDelta] = Field(default_factory=dict)
    case_diffs: list[RomanceCaseDiff] = Field(default_factory=list)
    improved_metrics: list[str] = Field(default_factory=list)
    declined_metrics: list[str] = Field(default_factory=list)
    blocked_case_delta: int = 0
    new_blocker_case_ids: list[str] = Field(default_factory=list)
    resolved_blocker_case_ids: list[str] = Field(default_factory=list)
    baseline_path: str = ""
    candidate_path: str = ""
