from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class ChapterPlan(BaseModel):
    chapter_id: str
    title: str
    objective: str
    tension: str
    cliffhanger: str
    phase: str = ""
    story_function: str = ""
    key_turn: str = ""
    payoff: str = ""
    next_route_hint: str = ""
    target_words: str = ""
    scene_density: str = ""
    scene_beats: list[dict[str, str]] = Field(default_factory=list)
    planned_scene_count: int = Field(ge=1, default=2)


class BookBlueprint(BaseModel):
    blueprint_id: str
    premise: StoryPremise
    characters: list[CharacterCard]
    volume_titles: list[str]
    chapter_plans: list[ChapterPlan]
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
