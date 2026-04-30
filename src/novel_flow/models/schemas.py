from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WriterMode(str, Enum):
    CREATE = "create"
    WRITE_NEXT_CHAPTER = "write_next_chapter"
    REWRITE_UNIT = "rewrite_unit"
    PATCH_BLOCK = "patch_block"
    EXPAND = "expand"


class WorkflowStage(str, Enum):
    RESEARCH = "research"
    PLANNING = "planning"
    WRITING = "writing"
    CRITIQUE = "critique"
    PATCHING = "patching"
    COMPLETE = "complete"


class DirectorAction(str, Enum):
    RUN_RESEARCH = "run_research"
    RETRIEVE_REFERENCES = "retrieve_references"
    BUILD_BLUEPRINT = "build_blueprint"
    CREATE_BOOK = "create_book"
    WRITE_CHAPTER = "write_chapter"
    CRITIQUE = "critique"
    PATCH = "patch"
    FINISH = "finish"


class TrendItem(BaseModel):
    source: str
    title: str
    summary: str
    url: str
    heat_score: int = Field(ge=0, le=100)
    topic_tags: list[str] = Field(default_factory=list)
    emotional_tags: list[str] = Field(default_factory=list)
    conflict_tags: list[str] = Field(default_factory=list)
    audience_preferences: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=utc_now)


class ResearchReport(BaseModel):
    report_id: str
    query: str
    sources: list[str]
    trend_items: list[TrendItem]
    genre_candidates: list[str]
    emotional_patterns: list[str]
    conflict_patterns: list[str]
    comment_preferences: list[str]
    writing_recommendations: list[str]
    created_at: datetime = Field(default_factory=utc_now)


class KnowledgeCard(BaseModel):
    card_id: str
    kind: str
    title: str = ""
    summary: str
    domain: str = ""
    layer: str = ""
    polarity: str = ""
    cluster_id: str = ""
    tags: list[str] = Field(default_factory=list)
    applicable_stages: list[str] = Field(default_factory=list)
    scene_types: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    techniques: list[str] = Field(default_factory=list)
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    source: str = ""


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CharacterCard(BaseModel):
    name: str
    role: str
    social_background: str = ""
    education_background: str = ""
    occupation: str = ""
    appearance: str = ""
    personality: str = ""
    career: str = ""
    initial_state: str = ""
    motivation: str = ""
    behavior_pattern: str = ""
    arc: str = ""
    relationships: str = ""
    development_axes: list[str] = Field(default_factory=list)


class CharacterCandidateLink(BaseModel):
    target: str
    relation: str = ""


class NewCharacterCandidate(BaseModel):
    candidate_id: str
    name: str
    first_appearance_chapter: str = ""
    role_in_scene: str = ""
    why_needed: str = ""
    provisional_traits: list[str] = Field(default_factory=list)
    links_to_existing_characters: list[CharacterCandidateLink] = Field(default_factory=list)
    expected_recurrence: str = "unknown"
    suggested_action: str = "add"


class StoryPremise(BaseModel):
    title: str
    high_concept: str
    theme_statement: str = ""
    story_summary: str = ""
    genre: str
    target_style: str
    emotional_hook: str
    central_conflict: str
    core_hook: str = ""
    escalation_path: list[str] = Field(default_factory=list)
    twist_blueprint: list[str] = Field(default_factory=list)
    ending_payoff: str = ""
    selling_points: list[str] = Field(default_factory=list)


class TwistDesign(StrictBaseModel):
    twist_id: str
    title: str
    false_belief: str
    truth: str
    reader_alignment: str
    seed_from: str
    reveal_at: str
    allowed_clues: list[str] = Field(default_factory=list, max_length=3)
    forbidden_reveals: list[str] = Field(default_factory=list, max_length=5)
    pov_lock: str
    related_characters: list[str] = Field(default_factory=list)
    payoff_effect: str


class StoryLine(StrictBaseModel):
    line_id: str
    name: str
    line_type: str
    visibility: Literal["visible", "hidden", "misdirection", "mixed"]
    core_question: str
    reader_hook_mode: str
    start_state: str
    midpoint_shift: str
    end_state: str
    carried_twists: list[str] = Field(default_factory=list)
    line_rules: list[str] = Field(default_factory=list, max_length=4)


class ChapterClueRevealMechanism(StrictBaseModel):
    style: Literal[
        "",
        "direct_pressure",
        "natural_exposure",
        "object_accident",
        "overheard",
        "ritual_trigger",
        "subordinate_report",
        "withheld_reveal",
    ] = ""
    pressure_source: str = ""
    surface_trigger: str = ""
    first_noticer: str = ""
    owner_reaction: str = ""


class ChapterBrief(StrictBaseModel):
    chapter_id: str
    title: str
    chapter_type: str
    active_lines: list[str] = Field(default_factory=list, max_length=3)
    active_twists: list[str] = Field(default_factory=list, max_length=3)
    summary: str
    incoming_hook: str
    opening_hook: str
    core_scene: str = ""
    chapter_object: str
    reader_emotion: str
    reader_belief: str
    allowed_info: list[str] = Field(default_factory=list, max_length=4)
    allowed_clues: list[str] = Field(default_factory=list, max_length=3)
    forbidden: list[str] = Field(default_factory=list, max_length=5)
    world_limit: str
    character_focus: list[str] = Field(default_factory=list, max_length=5)
    character_shift: str
    relationship_reprice: str
    emotional_turn: str
    backstory_trigger: str
    cost_of_progress: str = ""
    relationship_cost: str = ""
    must_hurt_now: str = ""
    hook_kind: Literal[
        "question",
        "cost",
        "deadline",
        "reveal",
        "danger",
        "aftermath",
        "withheld_answer",
    ] = "question"
    pace_curve: Literal[
        "front_loaded",
        "steady_climb",
        "mid_pivot",
        "late_snap",
        "aftershock",
    ] = "steady_climb"
    must_not_repeat: list[str] = Field(default_factory=list, max_length=6)
    scene_engine: Literal[
        "opening_pressure",
        "disruptor_arrival",
        "drunken_truth",
        "private_to_public_interruption",
        "earned_flashback",
        "investigation_pressure",
        "court_pressure",
        "relationship_collision",
        "clue_reversal",
        "aftermath_choice",
    ]
    clue_reveal_mechanism: ChapterClueRevealMechanism = Field(default_factory=ChapterClueRevealMechanism)
    character_reentry_focus: dict[str, str] = Field(default_factory=dict)
    human_pain_anchor: str = ""
    romance_seed: str = ""
    small_payoff: str
    ending_pull: str
    info_budget: str

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_clue_reveal_style(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        mechanism = payload.get("clue_reveal_mechanism")
        if not isinstance(mechanism, dict):
            mechanism = {}
        else:
            mechanism = dict(mechanism)
        legacy_style = str(payload.pop("clue_reveal_style", "") or "").strip()
        if legacy_style and not str(mechanism.get("style", "") or "").strip():
            mechanism["style"] = legacy_style
        payload["clue_reveal_mechanism"] = mechanism
        return payload

    @model_validator(mode="after")
    def backfill_contract_defaults(self) -> "ChapterBrief":
        if not str(self.cost_of_progress or "").strip():
            self.cost_of_progress = (
                str(self.human_pain_anchor or "").strip()
                or str(self.world_limit or "").strip()
                or str(self.emotional_turn or "").strip()
            )
        if not str(self.relationship_cost or "").strip():
            self.relationship_cost = (
                str(self.relationship_reprice or "").strip()
                or str(self.cost_of_progress or "").strip()
                or str(self.human_pain_anchor or "").strip()
            )
        if not str(self.must_hurt_now or "").strip():
            self.must_hurt_now = (
                str(self.human_pain_anchor or "").strip()
                or str(self.relationship_cost or "").strip()
                or str(self.cost_of_progress or "").strip()
            )
        if not list(self.must_not_repeat or []):
            guards = [str(item or "").strip() for item in self.forbidden[:3] if str(item or "").strip()]
            guards.extend(
                [
                    "Do not restate the same relationship judgment in multiple beats.",
                    "Do not replay finished pressure with explanation instead of consequence.",
                ]
            )
            deduped: list[str] = []
            for item in guards:
                if item and item not in deduped:
                    deduped.append(item)
            self.must_not_repeat = deduped[:6]
        return self

    @property
    def chapter_mission(self) -> str:
        return str(self.summary or "").strip()

    @property
    def plot_carrier(self) -> str:
        return str(self.chapter_object or "").strip()

    @property
    def character_delta(self) -> str:
        return str(self.character_shift or "").strip()

    @property
    def relationship_delta(self) -> str:
        return str(self.relationship_reprice or "").strip()

    @property
    def must_payoff(self) -> str:
        return str(self.small_payoff or "").strip()

    @property
    def final_hook(self) -> str:
        return str(self.ending_pull or "").strip()

    @property
    def pace_contract(self) -> str:
        return str(self.info_budget or "").strip()

    def contract_view(self) -> dict[str, Any]:
        return {
            "chapter_mission": self.chapter_mission,
            "plot_carrier": self.plot_carrier,
            "character_delta": self.character_delta,
            "relationship_delta": self.relationship_delta,
            "cost_of_progress": str(self.cost_of_progress or "").strip(),
            "relationship_cost": str(self.relationship_cost or "").strip(),
            "must_hurt_now": str(self.must_hurt_now or "").strip(),
            "must_payoff": self.must_payoff,
            "final_hook": self.final_hook,
            "hook_kind": self.hook_kind,
            "pace_curve": self.pace_curve,
            "pace_contract": self.pace_contract,
            "must_not_repeat": list(self.must_not_repeat or []),
        }


class SceneCard(StrictBaseModel):
    scene_id: str
    purpose: str
    pov: str
    location: str
    visible_goal: str
    obstacle: str
    must_show: list[str] = Field(default_factory=list, max_length=4)
    must_not_show: list[str] = Field(default_factory=list, max_length=4)
    reader_proxy: str
    proxy_function: str
    exit_state: str


class ScenePlan(StrictBaseModel):
    scenes: list[SceneCard] = Field(default_factory=list, min_length=1, max_length=5)


class ActualChapterSummary(StrictBaseModel):
    chapter_id: str
    actual_events: list[str] = Field(default_factory=list, max_length=8)
    reader_now_knows: list[str] = Field(default_factory=list, max_length=8)
    reader_now_believes: list[str] = Field(default_factory=list, max_length=6)
    open_questions: list[str] = Field(default_factory=list, max_length=8)
    character_states: list[str] = Field(default_factory=list)
    relationship_state: list[str] = Field(default_factory=list)
    seeded_clues: list[str] = Field(default_factory=list, max_length=8)
    locked_truths: list[str] = Field(default_factory=list, max_length=8)
    time_state: dict[str, str] = Field(default_factory=dict)


class CharacterMindset(StrictBaseModel):
    character_id: str
    character_name: str
    surface_emotion: str
    core_emotion: str
    primary_goal: str
    hidden_need: str
    fear: str
    attitude_to_key_others: dict[str, str] = Field(default_factory=dict)
    self_control_level: Literal["low", "medium", "high", "medium_low", "medium_high"]
    breaking_point_hint: str
    known_but_unspoken: str
    misbelief: str
    chapter_change_hint: str


class CharacterReentryMode(StrictBaseModel):
    target_character: str = ""
    identity_already_known: bool = True
    reentry_strategy: str = ""
    first_signal: str = ""
    first_emotional_focus: str = ""
    must_avoid: list[str] = Field(default_factory=list)


class ClueRevealMechanism(StrictBaseModel):
    clue: str = ""
    style: Literal[
        "",
        "natural_exposure",
        "object_accident",
        "ritual_trigger",
        "subordinate_report",
        "withheld_reveal",
    ] = ""
    pressure_source: str = ""
    surface_trigger: str = ""
    first_noticer: str = ""
    owner_reaction: str = ""

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        relationship_pressure = str(payload.pop("relationship_pressure", "") or "").strip()
        body_or_object_failure = str(payload.pop("body_or_object_failure", "") or "").strip()
        who_notices = str(payload.pop("who_notices", "") or "").strip()
        who_avoids_explaining = str(payload.pop("who_avoids_explaining", "") or "").strip()
        after_effect = str(payload.pop("after_effect", "") or "").strip()
        if not str(payload.get("pressure_source") or "").strip():
            payload["pressure_source"] = relationship_pressure
        if not str(payload.get("surface_trigger") or "").strip():
            payload["surface_trigger"] = body_or_object_failure
        if not str(payload.get("first_noticer") or "").strip():
            payload["first_noticer"] = who_notices
        if not str(payload.get("owner_reaction") or "").strip():
            payload["owner_reaction"] = who_avoids_explaining or after_effect
        return payload


class CharacterAnchorLine(StrictBaseModel):
    owner: str = ""
    form: Literal["dialogue", "inner_thought", "narrative_judgment", "reaction_line"] = "dialogue"
    surface_function: str = ""
    hidden_function: str = ""
    must_reveal_about_character: str = ""
    must_not_do: list[str] = Field(default_factory=list)
    preferred_shape: str = "短、准、能留余味"


class ContentBlock(StrictBaseModel):
    block_id: str
    chapter_id: str
    block_index: int = Field(ge=1)
    purpose: str
    characters: list[str] = Field(default_factory=list)
    active_lines: list[str] = Field(default_factory=list)
    active_twists: list[str] = Field(default_factory=list)
    scene_goal: str = ""
    must_reveal: list[str] = Field(default_factory=list)
    must_hide: list[str] = Field(default_factory=list)
    new_value: str = ""
    must_not_repeat: list[str] = Field(default_factory=list)
    relationship_delta: str = ""
    clue_delta: str = ""
    must_land_in_action: list[str] = Field(default_factory=list)
    emotional_tone: str = ""
    end_state: str
    human_reaction_target: list[str] = Field(default_factory=list)
    cost_shift: str = ""
    reader_feeling_target: str = ""
    paragraph_budget: str = ""
    target_chars: int = Field(default=0, ge=0)
    paragraph_shape: list[str] = Field(default_factory=list)
    micro_hook: str = ""
    turn_type: Literal[
        "pressure_rise",
        "clue_shift",
        "emotional_slip",
        "relationship_cut",
        "ritual_embarrassment",
        "witness_reaction",
        "false_relief",
        "withheld_answer",
    ] = "pressure_rise"
    character_anchor_line: CharacterAnchorLine | None = None
    style_risk_guard: list[str] = Field(default_factory=list)
    character_reentry_mode: CharacterReentryMode | None = None
    clue_reveal_mechanism: ClueRevealMechanism | None = None
    text: str = ""
    status: Literal["draft", "committed", "replaced"] = "draft"
    version: int = Field(default=1, ge=1)

    @field_validator("block_id")
    @classmethod
    def validate_block_id(cls, value: str) -> str:
        if ".b" not in value or ".sc_" not in value or not value.startswith("ch_"):
            raise ValueError("Block id must look like ch_001.sc_001.b001")
        return value


class ContentBlockPlanPayload(StrictBaseModel):
    blocks: list[ContentBlock] = Field(default_factory=list, min_length=3, max_length=10)


ChapterContract = ChapterBrief
ChapterBeat = ContentBlock
ChapterBeatPlanPayload = ContentBlockPlanPayload


class BlockQualityReviewPayload(StrictBaseModel):
    tool_id: Literal["review_block_quality"] = "review_block_quality"
    passed: bool = False
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    scene_goal_completed: bool = False
    human_reaction_target_hit: bool = False
    cost_shift_landed: bool = False
    reader_feeling_landed: bool = False
    paragraphs_readable: bool = True
    issues: list["EvidenceIssue"] = Field(default_factory=list)
    rewrite_guidance: str = ""


class FormatAdjustmentPayload(StrictBaseModel):
    text: str
    format_issues: list[str] = Field(default_factory=list)


class BinaryReviewPayload(StrictBaseModel):
    passed: bool = False
    level: Literal["low", "medium", "high", "critical"] = "medium"
    issues: list[str] = Field(default_factory=list)
    rewrite_guidance: str = ""


class EvidenceIssue(StrictBaseModel):
    category: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    evidence: str
    reason: str
    fix: str


class EvidenceReviewPayload(StrictBaseModel):
    passed: bool = False
    level: Literal["low", "medium", "high", "critical"] = "medium"
    issues: list[EvidenceIssue] = Field(default_factory=list)
    rewrite_guidance: str = ""
    evidence_focus: list[str] = Field(default_factory=list)


class ProseQualityPayload(StrictBaseModel):
    prose_score: int = Field(default=0, ge=0, le=10)
    tension_score: int = Field(default=0, ge=0, le=10)
    subtext_score: int = Field(default=0, ge=0, le=10)
    exposition_score: int = Field(default=10, ge=0, le=10)
    cliche_score: int = Field(default=10, ge=0, le=10)
    double_duty_detail_score: int = Field(default=0, ge=0, le=10)
    scene_texture_score: int = Field(default=0, ge=0, le=10)
    emotion_externalization_score: int = Field(default=0, ge=0, le=10)
    dialogue_subtext_score: int = Field(default=0, ge=0, le=10)
    human_warmth_score: int = Field(default=0, ge=0, le=10)
    memorability_score: int = Field(default=0, ge=0, le=10)
    pressure_authenticity_score: int = Field(default=0, ge=0, le=10)
    rewrite_needed: bool = False
    rewrite_guidance: str = ""
    issues: list[EvidenceIssue] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)


class HumanityReviewPayload(StrictBaseModel):
    passed: bool = False
    level: Literal["low", "medium", "high", "critical"] = "medium"
    human_warmth_score: int = Field(default=0, ge=0, le=10)
    character_has_real_world_tradeoff: bool = False
    emotion_is_grounded_in_specific_loss: bool = False
    supporting_character_reacts_humanly: bool = False
    self_talk_feels_specific: bool = False
    pain_is_not_generic: bool = False
    issues: list[EvidenceIssue] = Field(default_factory=list)
    rewrite_guidance: str = ""


class ChapterTargetedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    issue_id: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    problem_type: str
    reason: str
    target_blocks: list[str] = Field(default_factory=list, min_length=1, max_length=4)
    patch_hint: str = ""


class ChapterTargetedReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pass_: bool = Field(default=False, alias="pass")
    issues: list[ChapterTargetedIssue] = Field(default_factory=list)
    summary: str = ""


class ChapterPatchTarget(StrictBaseModel):
    target_type: Literal["block"] = "block"
    target_id: str
    problem_type: str
    goal: str
    instructions: list[str] = Field(default_factory=list, max_length=6)
    local_context_needed: list[str] = Field(default_factory=list, max_length=6)
    source_issue_ids: list[str] = Field(default_factory=list, max_length=6)


class ChapterPatchPlanPayload(StrictBaseModel):
    patch_targets: list[ChapterPatchTarget] = Field(default_factory=list, max_length=6)
    unchanged_blocks: list[str] = Field(default_factory=list)
    global_constraints: list[str] = Field(default_factory=list, max_length=8)


class PatchedBlock(StrictBaseModel):
    block_id: str
    old_summary: str = ""
    new_text: str


class PatchReportItem(StrictBaseModel):
    block_id: str
    applied: bool = False
    notes: str = ""


class RewriteBlocksByPlanPayload(StrictBaseModel):
    patched_blocks: list[PatchedBlock] = Field(default_factory=list)
    merged_chapter_text: str = ""
    patch_report: list[PatchReportItem] = Field(default_factory=list)


class PatchJudgeIssue(StrictBaseModel):
    problem_type: str
    target_blocks: list[str] = Field(default_factory=list, min_length=1, max_length=4)
    reason: str


class PatchJudgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pass_: bool = Field(default=False, alias="pass")
    remaining_issues: list[PatchJudgeIssue] = Field(default_factory=list)
    newly_introduced_issues: list[PatchJudgeIssue] = Field(default_factory=list)
    recommendation: str = ""


class ToolCallSpec(StrictBaseModel):
    tool_name: str
    reason: str = ""


class ToolPlanPayload(StrictBaseModel):
    tool_calls: list[ToolCallSpec] = Field(default_factory=list, max_length=10)


class ContextSanitizationPayload(StrictBaseModel):
    chapter_id: str
    selection_summary_text: str
    time_anchor_text: str
    chapter_visible_context_text: str
    completed_chapter_memory_text: str
    step_1_story_foundation_text: str
    step_3_character_packets_text: str
    step_5_character_milestones_text: str
    step_6_twists_text: str
    step_7_story_lines_text: str
    step_8_chapter_brief_text: str
    scene_character_context_text: str
    relationship_state_text: str


class RevisionPlan(StrictBaseModel):
    scope: Literal["block", "chapter"] = "chapter"
    target_id: str = ""
    summary: str
    p0: list[str] = Field(default_factory=list)
    p1: list[str] = Field(default_factory=list)
    p2: list[str] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    should_fix: list[str] = Field(default_factory=list)
    keep: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    triggered_skills: list[str] = Field(default_factory=list)
    evidence_focus: list[str] = Field(default_factory=list)


class DynamicInstructionPayload(StrictBaseModel):
    focus: list[str] = Field(default_factory=list)
    skills_to_emphasize: list[str] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    tone_adjustment: str = ""
    scene_strategy: str = ""


class FinalJudgeResult(StrictBaseModel):
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ChapterExecutionResult(StrictBaseModel):
    chapter_text: str
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    character_mindsets: list[CharacterMindset] = Field(default_factory=list)
    actual_chapter_summary: ActualChapterSummary
    stage_log: list[dict[str, Any]] = Field(default_factory=list)
    review_reports: dict[str, Any] = Field(default_factory=dict)
    final_judge: dict[str, Any] = Field(default_factory=dict)
    requires_human_review: bool = False

    @property
    def chapter_beats(self) -> list[ContentBlock]:
        return self.content_blocks


class TwistDesignsPayload(StrictBaseModel):
    twist_designs: list[TwistDesign] = Field(default_factory=list)


class StoryLinesPayload(StrictBaseModel):
    story_lines: list[StoryLine] = Field(default_factory=list)


class ChapterBatchWindow(StrictBaseModel):
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    total_chapters: int = Field(ge=1)
    chapter_ids: list[str] = Field(default_factory=list)


class ChapterBriefGenerationInput(StrictBaseModel):
    batch: ChapterBatchWindow
    research_query: str
    volume_titles_json: list[str] = Field(default_factory=list)
    story_spine_json: dict[str, Any] = Field(default_factory=dict)
    worldbuilding_json: dict[str, Any] = Field(default_factory=dict)
    character_bible_json: dict[str, Any] = Field(default_factory=dict)
    event_timeline_json: list[dict[str, Any]] = Field(default_factory=list)
    character_milestones_json: list[dict[str, Any]] = Field(default_factory=list)
    twist_designs_json: list[dict[str, Any]] = Field(default_factory=list)
    story_lines_json: list[dict[str, Any]] = Field(default_factory=list)
    previous_chapter_briefs_json: list[ChapterBrief] = Field(default_factory=list)
    target_chapter_count: int = Field(default=1, ge=1)
    reference_pack: str = ""


class ChapterBriefsPayload(StrictBaseModel):
    batch: ChapterBatchWindow | None = None
    chapter_briefs: list[ChapterBrief] = Field(default_factory=list)
    merged_chapter_brief_count: int | None = None


class ScenePlanPayload(StrictBaseModel):
    scenes: list[SceneCard] = Field(default_factory=list, min_length=1, max_length=5)


@dataclass
class WriterContext:
    chapter_id: str
    selection_summary_text: str
    time_anchor_text: str
    chapter_visible_context_text: str
    completed_chapter_memory_text: str
    step_1_story_foundation_text: str
    step_2_worldbuilding_text: str
    step_3_character_packets_text: str
    step_4_event_timeline_text: str
    step_5_character_milestones_text: str
    step_6_twists_text: str
    step_7_story_lines_text: str
    step_8_chapter_brief_text: str
    chapter_payload_text: str
    timeline_anchor_facts_text: str
    relevant_world_rules_text: str
    style_card_text: str
    active_twists: list[TwistDesign]
    active_story_lines: list[StoryLine]
    scene_character_context_text: str = ""
    relationship_state_text: str = ""
    assistant_persona_prompt: str = ""
    writing_requirements_json: str = "{}"
    completed_chapter_summary_bundle: str = ""
    previous_chapter_full_text: str = ""
    reference_pack: str = ""
    chapter_character_mindsets: list[CharacterMindset] = field(default_factory=list)
    chapter_character_mindsets_text: str = ""


class BookBlueprint(BaseModel):
    blueprint_id: str
    premise: StoryPremise
    characters: list[CharacterCard]
    volume_titles: list[str]
    chapter_briefs: list[ChapterBrief] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class TextBlock(BaseModel):
    id: str
    text: str
    purpose: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_block_id(cls, value: str) -> str:
        if ".b" not in value or ".sc_" not in value or not value.startswith("ch_"):
            raise ValueError("Block id must look like ch_001.sc_002.b003")
        return value


class Scene(BaseModel):
    id: str
    title: str
    summary: str
    blocks: list[TextBlock] = Field(default_factory=list)


class Chapter(BaseModel):
    id: str
    title: str
    summary: str
    scenes: list[Scene] = Field(default_factory=list)
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    character_mindsets: list[CharacterMindset] = Field(default_factory=list, max_length=2)
    final_text: str = ""
    final_version: int = Field(default=0, ge=0)
    is_finalized: bool = False

    @property
    def chapter_beats(self) -> list[ContentBlock]:
        return self.content_blocks


class Volume(BaseModel):
    id: str
    title: str
    summary: str
    chapters: list[Chapter] = Field(default_factory=list)


class BookDocument(BaseModel):
    id: str
    title: str
    premise: StoryPremise
    characters: list[CharacterCard]
    volumes: list[Volume] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueLocation(BaseModel):
    book_id: str
    volume_id: str
    chapter_id: str
    scene_id: str
    block_id: str


class IssueCard(BaseModel):
    issue_id: str
    severity: IssueSeverity
    title: str
    problem_type: str
    location: IssueLocation
    evidence: str
    impact: str
    recommendation: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class CriticReport(BaseModel):
    report_id: str
    summary: str
    issues: list[IssueCard]
    created_at: datetime = Field(default_factory=utc_now)


class PatchOperation(str, Enum):
    REPLACE = "replace"
    APPEND = "append"
    PREPEND = "prepend"


class PatchInstruction(BaseModel):
    patch_id: str
    issue_id: str | None = None
    target_block_id: str
    operation: PatchOperation
    reason: str
    content: str


class BlockPatchVersion(BaseModel):
    version_id: str
    book_id: str
    block_id: str
    patch_id: str
    before_block: TextBlock
    after_block: TextBlock
    instruction: PatchInstruction
    created_at: datetime = Field(default_factory=utc_now)


class WorkflowState(BaseModel):
    run_id: str
    stage: WorkflowStage
    current_book_id: str | None = None
    latest_research_report_id: str | None = None
    latest_critic_report_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class DirectorDecision(BaseModel):
    action: DirectorAction
    reasoning: str
    info_gaps: list[str] = Field(default_factory=list)
    tool_input: dict[str, Any] = Field(default_factory=dict)


class ToolObservation(BaseModel):
    tool_name: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AgentResult(BaseModel):
    agent_name: str
    success: bool
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
