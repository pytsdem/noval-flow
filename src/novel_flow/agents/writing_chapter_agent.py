from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from typing import Any

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.llm.executor import build_messages
from novel_flow.models.schemas import (
    ActualChapterSummary,
    AgentResult,
    ChapterContract,
    ChapterExecutionResult,
    ChapterBeat,
    CharacterCard,
    CharacterMindset,
    StoryPremise,
    StoryLine,
    TwistDesign,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.chapter_tool_payloads import ChapterToolPayloadBuilder
from novel_flow.services.character_mindset_formatter import CharacterMindsetFormatter
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.novel_context import (
    NovelContextFormatter,
    NovelContextSelectorService,
    NovelContextSnapshot,
)
from novel_flow.services.prose_lint import (
    ProseSurfaceSignals,
    analyze_prose_surface,
    build_revision_brief,
)
from novel_flow.services.review_aggregator import ReviewAggregator
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.services.selectors import get_character_card_by_name
from novel_flow.services.tool_registry import ToolRegistry


class WritingChapterAgent(BaseAgent):
    INCREMENTAL_BLOCK_DRAFTING_ENABLED = False
    SEQUENTIAL_BEAT_DRAFTING_ENABLED = True
    FAST_CHAPTER_REVIEW_TOOLS = [
        "review_structure_and_continuity",
        "review_prose_and_humanity",
    ]
    DEEP_CHAPTER_REVIEW_TOOLS = [
        "review_structure_and_continuity",
        "review_prose_and_humanity",
    ]
    BLOCK_REVIEW_TOOLS = [
        "review_reveal_leak",
        "review_character_integrity",
        "review_time_consistency",
        "review_block_quality",
    ]
    DEEP_BLOCK_REVIEW_TOOLS = [
        "review_block_quality",
    ]
    CHAPTER_REVIEW_TOOLS = list(FAST_CHAPTER_REVIEW_TOOLS)
    OPTIONAL_CHAPTER_REVIEW_TOOLS: list[str] = []
    OUTPUT_FORMAT_RULES = [
        "Prefer Chinese full-width punctuation.",
        "Keep dialogue on its own paragraph when possible.",
        "Keep one blank line between paragraphs.",
        "Avoid page-sized paragraphs in front-end reading.",
        "Do not flatten deliberate short lines or pauses.",
        "Let one paragraph usually carry one main action, one main reaction, or one main observation.",
        "Do not pack action, another person's reaction, and author explanation into one paragraph.",
        "Important supporting-character reactions should usually stand alone as their own paragraph.",
        "Usually keep each paragraph around 30-120 Chinese characters.",
        "Treat paragraphs longer than 180 Chinese characters as a formatting risk.",
    ]

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_library: PromptLibrary | None = None,
        skill_manager: SkillManager | None = None,
        tool_registry: ToolRegistry | None = None,
        max_iterations: int | None = None,
        mode: str = "fast",
    ) -> None:
        super().__init__(name="WritingChapterAgent")
        self.llm_client = llm_client
        self.prompt_library = prompt_library or PromptLibrary()
        self.skill_manager = skill_manager or SkillManager(registry=SkillRegistry())
        self.tool_registry = tool_registry or ToolRegistry.build_default(
            llm_client=llm_client,
            prompt_library=self.prompt_library,
        )
        self.context_sanitizer = ContextSanitizationTask(
            llm_client=llm_client,
            prompt_library=self.prompt_library,
        )
        normalized_mode = str(mode or "fast").strip().lower()
        if normalized_mode not in {"fast", "deep"}:
            raise ValueError(f"Unsupported WritingChapterAgent mode: {mode}")
        self.mode = normalized_mode
        self.max_iterations = max_iterations if max_iterations is not None else (1 if self.mode == "fast" else 3)
        self.max_patch_rounds = 2 if self.mode == "fast" else max(int(self.max_iterations), 2)

    def write_chapter(
        self,
        *,
        chapter_brief: ChapterContract,
        twist_designs: list[TwistDesign],
        story_lines: list[StoryLine],
        character_cards: list[CharacterCard],
        worldbuilding: dict[str, Any] | None,
        actual_chapter_summaries: list[ActualChapterSummary],
        premise: StoryPremise | None = None,
        character_milestones: list[dict[str, Any]] | None = None,
        prior_character_mindsets: list[CharacterMindset] | None = None,
        prebuilt_context: Any | None = None,
        on_block_committed: Callable[[ChapterBeat], None] | None = None,
        on_chapter_preview_updated: Callable[[dict[str, Any]], None] | None = None,
    ) -> ChapterExecutionResult:
        snapshot = NovelContextSelectorService.create_snapshot(
            chapter_brief=chapter_brief,
            premise=premise,
            twist_designs=twist_designs,
            story_lines=story_lines,
            worldbuilding=worldbuilding or {},
            character_cards=character_cards,
            character_milestones=character_milestones or [],
            actual_summaries=actual_chapter_summaries,
            current_chapter_id=chapter_brief.chapter_id,
        )
        context = prebuilt_context
        if context is None:
            selection = NovelContextSelectorService.select(
                snapshot=snapshot,
                strategy="writer_context",
            )
            context = NovelContextFormatter.format_writer_context(
                selection,
                context_sanitizer=self.context_sanitizer,
            )
        stage_log: list[dict[str, Any]] = []
        review_reports: dict[str, Any] = {}
        final_judge: dict[str, Any] = {}
        requires_human_review = False

        self._emit_stage(
            stage="context_ready",
            action="Context ready",
            reason="The chapter context package is ready for block planning and drafting.",
            chapter_id=chapter_brief.chapter_id,
            context_bundle=self._context_bundle(context),
        )
        character_mindsets = self._build_character_mindsets(
            snapshot=snapshot,
            context=context,
            character_cards=character_cards,
            prior_character_mindsets=prior_character_mindsets or [],
        )
        character_mindsets_text = CharacterMindsetFormatter.format_text(character_mindsets)
        setattr(context, "chapter_character_mindsets", character_mindsets)
        setattr(context, "chapter_character_mindsets_text", character_mindsets_text)
        stage_log.append(
            {
                "stage": "build_character_mindsets",
                "character_mindsets": [item.model_dump(mode="json") for item in character_mindsets],
            }
        )
        self._emit_stage(
            stage="character_mindsets_ready",
            action="Character mindsets ready",
            reason="Chapter-bound character mindsets are generated before planning the writing package.",
            chapter_id=chapter_brief.chapter_id,
            character_mindsets=[item.model_dump(mode="json") for item in character_mindsets],
        )

        block_skills = self.skill_manager.initial_skills(stage="block")
        block_skill_text = self.skill_manager.format_for_model(block_skills)
        self._emit_stage(
            stage="plan_content_blocks_start",
            action="Plan chapter beats",
            reason="Plan the chapter contract as a beat sequence before drafting.",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in block_skills],
        )
        planned_blocks = self._plan_content_blocks(
            chapter_brief=chapter_brief,
            context=context,
        )
        stage_log.append(
            {
                "stage": "plan_content_blocks",
                "skill_ids": [skill.skill_id for skill in block_skills],
                "block_count": len(planned_blocks),
                "blocks": [block.model_dump(mode="json") for block in planned_blocks],
            }
        )
        self._emit_stage(
            stage="plan_content_blocks_done",
            action="Planned chapter beats",
            reason="The chapter contract is now unpacked into beat-level execution units.",
            chapter_id=chapter_brief.chapter_id,
            planned_blocks=[block.model_dump(mode="json") for block in planned_blocks],
        )

        committed_blocks = [block.model_copy(deep=True) for block in planned_blocks]
        chapter_text = ""
        if self.INCREMENTAL_BLOCK_DRAFTING_ENABLED:
            committed_blocks = []
            for block in planned_blocks:
                block_context = self._fetch_block_context(
                    context=context,
                    block=block,
                    committed_blocks=committed_blocks,
                )
                block_card_text = ChapterToolPayloadBuilder.block_card_text(block)
                self._emit_stage(
                    stage=f"block_{block.block_index}_draft_start",
                    action="Draft block",
                    reason="Write the current chapter beat before any chapter-level rewrite.",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=block.block_id,
                    block_index=block.block_index,
                )
                draft_result = self.tool_registry.execute(
                    "draft_block",
                    ChapterToolPayloadBuilder.build_draft_block_payload(
                        block=block,
                        block_context=block_context,
                        loaded_skill_instructions_text=block_skill_text,
                    ),
                )
                block_text = str(draft_result.get("block_text") or "").strip()
                block_review_reports = self._run_block_review_tools(
                    context=context,
                    block=block,
                    block_text=block_text,
                    block_context=block_context,
                )
                block_revision_plan = ReviewAggregator.aggregate_block(
                    review_reports=block_review_reports,
                    triggered_skills=[skill.skill_id for skill in block_skills],
                    block_id=block.block_id,
                )
                revised = False
                if self._needs_block_revision(block_review_reports):
                    self._emit_stage(
                        stage=f"block_{block.block_index}_revise_start",
                        action="Revise block",
                        reason="The beat-level light review found issues that should be fixed before commit.",
                        chapter_id=chapter_brief.chapter_id,
                        block_id=block.block_id,
                        block_index=block.block_index,
                        block_revision_plan=block_revision_plan.model_dump(mode="json"),
                    )
                    revise_result = self.tool_registry.execute(
                        "revise_block_if_needed",
                        ChapterToolPayloadBuilder.build_revise_block_payload(
                            block=block,
                            block_context=block_context,
                            block_text=block_text,
                            review_reports=block_review_reports,
                            block_revision_plan=block_revision_plan.model_dump(mode="json"),
                            loaded_skill_instructions_text=block_skill_text,
                        ),
                    )
                    block_text = str(revise_result.get("block_text") or block_text).strip()
                    revised = True
                committed_block = block.model_copy(
                    update={
                        "text": block_text,
                        "status": "committed",
                        "version": max(int(block.version), 1) + (1 if revised else 0),
                    }
                )
                committed_blocks.append(committed_block)
                chapter_text = self._merge_blocks_to_chapter(committed_blocks)
                stage_log.append(
                    {
                        "stage": f"commit_block_{block.block_index}",
                        "block_id": committed_block.block_id,
                        "block_index": committed_block.block_index,
                        "status": committed_block.status,
                        "version": committed_block.version,
                        "block_review_reports": block_review_reports,
                        "block_revision_plan": block_revision_plan.model_dump(mode="json"),
                        "chapter_length": len(chapter_text),
                    }
                )
                if on_block_committed is not None:
                    on_block_committed(committed_block)
                self._emit_chapter_preview(
                    chapter_brief=chapter_brief,
                    content_blocks=committed_blocks,
                    character_mindsets=character_mindsets,
                    final_text="",
                    final_version=0,
                    is_finalized=False,
                    preview_mode="content_blocks",
                    callback=on_chapter_preview_updated,
                )
                self._emit_stage(
                    stage=f"block_{block.block_index}_committed",
                    action="Committed block",
                    reason="The current chapter beat is committed and can be shown incrementally.",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=committed_block.block_id,
                    block_index=committed_block.block_index,
                    committed_block=committed_block.model_dump(mode="json"),
                    current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
                )

            self._emit_stage(
                stage="merge_blocks_to_chapter_done",
                action="Merged chapter beats",
                reason="All chapter beats are committed and ready for chapter-level review.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
                chapter_length=len(chapter_text),
            )
            stage_log.append(
                {
                    "stage": "merge_blocks_to_chapter",
                    "block_count": len(committed_blocks),
                    "chapter_length": len(chapter_text),
                }
            )
        elif self.SEQUENTIAL_BEAT_DRAFTING_ENABLED:
            self._emit_stage(
                stage="write_chapter_full_start",
                action="Write chapter beat by beat",
                reason="Draft the chapter one beat at a time so each planned block adds new value without resetting the scene.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
            )
            committed_blocks, chapter_text, beat_stage_log = self._draft_chapter_beat_by_beat(
                chapter_brief=chapter_brief,
                context=context,
                planned_blocks=committed_blocks,
                loaded_skill_instructions_text=block_skill_text,
                character_mindsets=character_mindsets,
                on_block_committed=on_block_committed,
                on_chapter_preview_updated=on_chapter_preview_updated,
            )
            stage_log.extend(beat_stage_log)
            stage_log.append(
                {
                    "stage": "write_chapter_full",
                    "mode": "sequential_beat_drafting",
                    "block_count": len(committed_blocks),
                    "chapter_length": len(chapter_text),
                }
            )
            self._emit_chapter_preview(
                chapter_brief=chapter_brief,
                content_blocks=committed_blocks,
                character_mindsets=character_mindsets,
                final_text=chapter_text,
                final_version=1,
                is_finalized=False,
                preview_mode="chapter_draft",
                callback=on_chapter_preview_updated,
            )
            self._emit_stage(
                stage="write_chapter_full_done",
                action="Finished sequential beat draft",
                reason="The chapter prose now follows the planned chapter beats one beat at a time and is ready for chapter-level review.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
                chapter_length=len(chapter_text),
            )
        else:
            self._emit_stage(
                stage="write_chapter_full_start",
                action="Write full chapter from plan",
                reason="Use the planned chapter beats as the chapter skeleton and draft the full prose in one pass.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
            )
            chapter_text = self._draft_chapter_from_plan(
                chapter_brief=chapter_brief,
                context=context,
                planned_blocks=committed_blocks,
            )
            stage_log.append(
                {
                    "stage": "write_chapter_full",
                    "block_count": len(committed_blocks),
                    "chapter_length": len(chapter_text),
                }
            )
            self._emit_chapter_preview(
                chapter_brief=chapter_brief,
                content_blocks=committed_blocks,
                character_mindsets=character_mindsets,
                final_text=chapter_text,
                final_version=1,
                is_finalized=False,
                preview_mode="chapter_draft",
                callback=on_chapter_preview_updated,
            )
            self._emit_stage(
                stage="write_chapter_full_done",
                action="Finished chapter draft from plan",
                reason="The chapter prose now follows the planned beat list and is ready for chapter-level review.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
                chapter_length=len(chapter_text),
            )

        active_skills = self.skill_manager.initial_skills(stage="chapter")
        review_reports = {}
        self._emit_stage(
            stage="review_iteration_1_skills",
            action="Select chapter skills",
            reason="Use the lighter chapter-level skill set for the current mode.",
            chapter_id=chapter_brief.chapter_id,
            iteration=1,
            mode=self.mode,
            skill_ids=[skill.skill_id for skill in active_skills],
        )
        planned_tools = self._plan_review_tools(
            chapter_brief=chapter_brief,
            review_reports=review_reports,
            active_skills=active_skills,
            content_blocks=committed_blocks,
        )
        self._emit_stage(
            stage="review_iteration_1_plan",
            action="Plan chapter reviews",
            reason="Keep the chapter-level review set light and deterministic.",
            chapter_id=chapter_brief.chapter_id,
            iteration=1,
            mode=self.mode,
            tool_calls=planned_tools,
        )
        review_reports = self._run_review_tools(
            tool_names=planned_tools,
            chapter_brief=chapter_brief,
            context=context,
            chapter_text=chapter_text,
            chapter_id=chapter_brief.chapter_id,
            iteration=1,
            planned_blocks=committed_blocks,
        )
        final_judge = self._build_review_gate_result(review_reports)
        self._emit_stage(
            stage="review_iteration_1_judge",
            action="Run light review gate",
            reason="Decide whether the chapter can finalize directly or needs a focused block patch.",
            chapter_id=chapter_brief.chapter_id,
            iteration=1,
            mode=self.mode,
            final_judge=final_judge,
        )
        stage_log.append(
            {
                "stage": "review_iteration_1",
                "mode": self.mode,
                "skill_ids": [skill.skill_id for skill in active_skills],
                "tool_calls": planned_tools,
                "review_reports": review_reports,
                "final_judge": final_judge,
            }
        )
        if bool(final_judge.get("passed")):
            self._emit_stage(
                stage="review_iteration_1_passed",
                action="Chapter review passed",
                reason="The fast review gate passed; proceed to final polish.",
                chapter_id=chapter_brief.chapter_id,
                iteration=1,
                mode=self.mode,
                final_judge=final_judge,
            )
        else:
            if not self._blocks_have_text(committed_blocks):
                committed_blocks = self._materialize_full_draft_blocks(
                    planned_blocks=committed_blocks,
                    chapter_text=chapter_text,
                )
                self._emit_stage(
                    stage="materialize_full_draft_blocks_done",
                    action="Materialize block texts",
                    reason="Map the full-chapter draft back onto planned blocks so only targeted blocks can be patched.",
                    chapter_id=chapter_brief.chapter_id,
                    block_count=len(committed_blocks),
                )
            review_source: dict[str, Any] = dict(review_reports)
            patch_round = 0
            while patch_round < self.max_patch_rounds:
                patch_round += 1
                self._emit_stage(
                    stage=f"patch_round_{patch_round}_plan_start",
                    action="Build chapter patch plan",
                    reason="Convert review findings into the smallest possible block-level patch plan.",
                    chapter_id=chapter_brief.chapter_id,
                    patch_round=patch_round,
                    mode=self.mode,
                )
                patch_plan = self.tool_registry.execute(
                    "build_chapter_patch_plan",
                    ChapterToolPayloadBuilder.build_chapter_patch_plan_payload(
                        chapter_text=chapter_text,
                        chapter_brief=chapter_brief,
                        context=context,
                        review_reports=review_source,
                        planned_blocks=committed_blocks,
                    ),
                )
                self._emit_stage(
                    stage=f"patch_round_{patch_round}_plan_done",
                    action="Chapter patch plan ready",
                    reason="The patch planner has selected the exact blocks that should change.",
                    chapter_id=chapter_brief.chapter_id,
                    patch_round=patch_round,
                    mode=self.mode,
                    patch_plan=patch_plan,
                )
                if not list(patch_plan.get("patch_targets") or []):
                    requires_human_review = True
                    final_judge = self._build_patch_loop_failure_result(
                        judge_result={},
                        patch_round=patch_round,
                        reason="Patch planner could not find safe local targets. 建议切到 deep 模式继续修。",
                    )
                    stage_log.append(
                        {
                            "stage": f"patch_round_{patch_round}_no_targets",
                            "patch_round": patch_round,
                            "patch_plan": patch_plan,
                            "final_judge": final_judge,
                        }
                    )
                    self._emit_stage(
                        stage=f"patch_round_{patch_round}_no_targets",
                        action="Patch plan stopped",
                        reason="No safe block-level patch target was found, so the loop stops and suggests deep mode.",
                        chapter_id=chapter_brief.chapter_id,
                        patch_round=patch_round,
                        final_judge=final_judge,
                    )
                    break
                if self._patch_plan_requires_structural_rebuild(patch_plan):
                    requires_human_review = True
                    final_judge = self._build_patch_loop_failure_result(
                        judge_result={},
                        patch_round=patch_round,
                        reason="Patch plan requires deleting or reordering beats. Fast local patch cannot safely do that; keep the current draft and suggest deep structural rewrite.",
                    )
                    stage_log.append(
                        {
                            "stage": f"patch_round_{patch_round}_structural_stop",
                            "patch_round": patch_round,
                            "patch_plan": patch_plan,
                            "final_judge": final_judge,
                        }
                    )
                    self._emit_stage(
                        stage=f"patch_round_{patch_round}_structural_stop",
                        action="Structural patch requested",
                        reason="The patch plan needs beat deletion or reordering, which the fast local patch path cannot apply safely.",
                        chapter_id=chapter_brief.chapter_id,
                        patch_round=patch_round,
                        final_judge=final_judge,
                    )
                    break

                self._emit_stage(
                    stage=f"patch_round_{patch_round}_rewrite_start",
                    action="Rewrite targeted blocks",
                    reason="Rewrite only the blocks selected by the patch planner.",
                    chapter_id=chapter_brief.chapter_id,
                    patch_round=patch_round,
                    mode=self.mode,
                    patch_targets=list(patch_plan.get("patch_targets") or []),
                )
                rewrite_result = self.tool_registry.execute(
                    "rewrite_blocks_by_plan",
                    ChapterToolPayloadBuilder.build_rewrite_blocks_by_plan_payload(
                        context=context,
                        planned_blocks=committed_blocks,
                        patch_plan=patch_plan,
                    ),
                )
                committed_blocks = self._apply_patch_result_to_blocks(
                    original_blocks=committed_blocks,
                    rewrite_result=rewrite_result,
                )
                chapter_text = str(rewrite_result.get("merged_chapter_text") or chapter_text).strip()
                self._emit_chapter_preview(
                    chapter_brief=chapter_brief,
                    content_blocks=committed_blocks,
                    character_mindsets=character_mindsets,
                    final_text=chapter_text,
                    final_version=patch_round,
                    is_finalized=False,
                    preview_mode="chapter_rewrite",
                    callback=on_chapter_preview_updated,
                )
                self._emit_stage(
                    stage=f"patch_round_{patch_round}_rewrite_done",
                    action="Targeted block rewrite complete",
                    reason="Only the selected blocks were rewritten and merged back into the chapter.",
                    chapter_id=chapter_brief.chapter_id,
                    patch_round=patch_round,
                    mode=self.mode,
                    rewrite_result=rewrite_result,
                )
                judge_result = self.tool_registry.execute(
                    "judge_patched_chapter",
                    ChapterToolPayloadBuilder.build_judge_patched_chapter_payload(
                        chapter_text=chapter_text,
                        chapter_brief=chapter_brief,
                        context=context,
                        content_blocks=committed_blocks,
                        patch_plan=patch_plan,
                    ),
                )
                final_judge = self._normalize_patch_judge_result(
                    judge_result=judge_result,
                    patch_round=patch_round,
                )
                review_reports["judge_patched_chapter"] = judge_result
                stage_log.append(
                    {
                        "stage": f"patch_round_{patch_round}",
                        "patch_round": patch_round,
                        "patch_plan": patch_plan,
                        "rewrite_result": rewrite_result,
                        "judge_result": judge_result,
                        "final_judge": final_judge,
                    }
                )
                self._emit_stage(
                    stage=f"patch_round_{patch_round}_judge",
                    action="Judge patched chapter",
                    reason="Check whether the targeted patch resolved the issues without causing fresh obvious damage.",
                    chapter_id=chapter_brief.chapter_id,
                    patch_round=patch_round,
                    mode=self.mode,
                    judge_result=judge_result,
                    final_judge=final_judge,
                )
                if bool(final_judge.get("passed")):
                    self._emit_stage(
                        stage=f"patch_round_{patch_round}_passed",
                        action="Patch loop passed",
                        reason="The patch judge passed and the chapter can proceed to final polish.",
                        chapter_id=chapter_brief.chapter_id,
                        patch_round=patch_round,
                        mode=self.mode,
                        final_judge=final_judge,
                    )
                    break
                if patch_round >= self.max_patch_rounds:
                    requires_human_review = True
                    final_judge = self._build_patch_loop_failure_result(
                        judge_result=judge_result,
                        patch_round=patch_round,
                        reason="Patch judge still failed after the fast patch limit. 建议切到 deep 模式继续修。",
                    )
                    self._emit_stage(
                        stage="max_patch_rounds_reached",
                        action="Reached patch limit",
                        reason="Stop the fast patch loop and keep the best patched version while suggesting deep mode.",
                        chapter_id=chapter_brief.chapter_id,
                        patch_round=patch_round,
                        mode=self.mode,
                        final_judge=final_judge,
                    )
                    stage_log.append(
                        {
                            "stage": "max_patch_rounds_reached",
                            "patch_round": patch_round,
                            "requires_human_review": True,
                            "final_judge": final_judge,
                        }
                    )
                    break
                review_source = self._review_source_from_patch_judge(judge_result)

        finalize_skills = self.skill_manager.finalize_skills()
        self._emit_stage(
            stage="final_polish_start",
            action="Final polish",
            reason="The best chapter draft is ready for final polish.",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in finalize_skills],
        )
        polished = self.tool_registry.execute(
            "final_polish",
            ChapterToolPayloadBuilder.build_final_polish_payload(
                context=context,
                chapter_text=chapter_text,
                loaded_skill_instructions_text=self.skill_manager.format_for_model(finalize_skills),
                chapter_brief=chapter_brief,
            ),
        )
        chapter_text = str(polished.get("chapter_text") or "").strip()
        self._emit_chapter_preview(
            chapter_brief=chapter_brief,
            content_blocks=committed_blocks,
            character_mindsets=character_mindsets,
            final_text=chapter_text,
            final_version=max(int(final_judge.get("metrics", {}).get("prose_score") or 0), 1),
            is_finalized=False,
            preview_mode="final_polish",
            callback=on_chapter_preview_updated,
        )
        stage_log.append(
            {
                "stage": "final_polish",
                "skill_ids": [skill.skill_id for skill in finalize_skills],
                "chapter_length": len(chapter_text),
            }
        )
        self._emit_stage(
            stage="final_polish_done",
            action="Final polish complete",
            reason="Do a format-only cleanup before the actual chapter summary.",
            chapter_id=chapter_brief.chapter_id,
            chapter_length=len(chapter_text),
        )
        formatted = self.tool_registry.execute(
            "format_adjustment_suggestion",
            ChapterToolPayloadBuilder.build_format_adjustment_payload(
                context=context,
                chapter_text=chapter_text,
                output_format_rules=self.OUTPUT_FORMAT_RULES,
            ),
        )
        chapter_text = str(formatted.get("text") or chapter_text).strip()
        self._emit_chapter_preview(
            chapter_brief=chapter_brief,
            content_blocks=committed_blocks,
            character_mindsets=character_mindsets,
            final_text=chapter_text,
            final_version=max(int(final_judge.get("metrics", {}).get("prose_score") or 0), 1),
            is_finalized=True,
            preview_mode="final_text",
            callback=on_chapter_preview_updated,
        )
        stage_log.append(
            {
                "stage": "format_adjustment",
                "chapter_length": len(chapter_text),
                "format_issues": list(formatted.get("format_issues") or []),
            }
        )
        self._emit_stage(
            stage="format_adjustment_done",
            action="Format adjustment complete",
            reason="Formatting is cleaned without changing facts or emotional logic.",
            chapter_id=chapter_brief.chapter_id,
            chapter_length=len(chapter_text),
            format_issues=list(formatted.get("format_issues") or []),
        )
        summary_payload = self.tool_registry.execute(
            "summarize_actual_chapter",
            ChapterToolPayloadBuilder.build_summarize_actual_chapter_payload(
                chapter_text=chapter_text,
                chapter_brief=chapter_brief,
                context=context,
            ),
        )
        actual_summary = ActualChapterSummary.model_validate(summary_payload)
        stage_log.append(
            {
                "stage": "summarize_actual_chapter",
                "chapter_id": actual_summary.chapter_id,
            }
        )
        self._emit_stage(
            stage="summarize_actual_chapter_done",
            action="Actual chapter summary complete",
            reason="The chapter writing loop is complete.",
            chapter_id=actual_summary.chapter_id,
            summary=actual_summary.model_dump(mode="json"),
        )
        return ChapterExecutionResult(
            chapter_text=chapter_text,
            content_blocks=committed_blocks,
            character_mindsets=character_mindsets,
            actual_chapter_summary=actual_summary,
            stage_log=stage_log,
            review_reports=review_reports,
            final_judge=final_judge,
            requires_human_review=requires_human_review,
        )

    def run(self, **kwargs: Any) -> AgentResult:
        result = self.write_chapter(
            chapter_brief=kwargs["chapter_brief"],
            premise=kwargs.get("premise"),
            twist_designs=kwargs["twist_designs"],
            story_lines=kwargs["story_lines"],
            character_cards=kwargs["character_cards"],
            character_milestones=kwargs.get("character_milestones"),
            prior_character_mindsets=kwargs.get("prior_character_mindsets"),
            worldbuilding=kwargs.get("worldbuilding"),
            actual_chapter_summaries=kwargs.get("actual_chapter_summaries", []),
            prebuilt_context=kwargs.get("prebuilt_context"),
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            message=f"Wrote chapter {kwargs['chapter_brief'].chapter_id}.",
            payload=result.model_dump(mode="json"),
        )

    def _draft_chapter_from_plan(
        self,
        *,
        chapter_brief: ChapterContract,
        context: Any,
        planned_blocks: list[ChapterBeat],
    ) -> str:
        payload = self.tool_registry.execute(
            "write_chapter_full",
            ChapterToolPayloadBuilder.build_write_chapter_full_payload(
                chapter_brief=chapter_brief,
                context=context,
                planned_blocks=planned_blocks,
            ),
        )
        return str(payload.get("chapter_text") or "").strip()

    def _draft_chapter_beat_by_beat(
        self,
        *,
        chapter_brief: ChapterContract,
        context: Any,
        planned_blocks: list[ChapterBeat],
        loaded_skill_instructions_text: str,
        character_mindsets: list[CharacterMindset],
        on_block_committed: Callable[[ChapterBeat], None] | None = None,
        on_chapter_preview_updated: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[list[ChapterBeat], str, list[dict[str, Any]]]:
        committed_blocks: list[ChapterBeat] = []
        stage_log: list[dict[str, Any]] = []
        chapter_text = ""
        for index, block in enumerate(planned_blocks):
            remaining_blocks = planned_blocks[index + 1 :]
            block_context = self._fetch_block_context(
                context=context,
                block=block,
                committed_blocks=committed_blocks,
                remaining_blocks=remaining_blocks,
            )
            self._emit_stage(
                stage=f"beat_{block.block_index}_draft_start",
                action="Draft beat",
                reason="Write the next beat using the already committed beats as carry-over memory instead of restarting the chapter.",
                chapter_id=chapter_brief.chapter_id,
                block_id=block.block_id,
                block_index=block.block_index,
                delivered_beat_summary_text=block_context.get("delivered_beat_summary_text", ""),
            )
            if self.mode == "deep":
                candidates = self._draft_block_candidates(
                    block=block,
                    block_context=block_context,
                    loaded_skill_instructions_text=loaded_skill_instructions_text,
                )
                chosen = self._choose_best_block_candidate(block=block, candidates=candidates)
                block_text = str(chosen["text"] or "").strip()
            else:
                draft_result = self.tool_registry.execute(
                    "draft_block",
                    ChapterToolPayloadBuilder.build_draft_block_payload(
                        block=block,
                        block_context=block_context,
                        loaded_skill_instructions_text=loaded_skill_instructions_text,
                        candidate_strategy="balanced_scene",
                    ),
                )
                block_text = str(draft_result.get("block_text") or "").strip()
                chosen = {
                    "strategy": "balanced_scene",
                    "surface": analyze_prose_surface(block_text, block=block),
                }
                candidates = [chosen]
            if not block_text:
                raise ValueError(f"draft_block returned empty text for {block.block_id}")
            forced_boundary_revision = self._force_beat_boundary_revision(
                context=context,
                block=block,
                block_context=block_context,
                block_text=block_text,
                candidate_strategy=str(chosen["strategy"] or "").strip(),
            )
            if forced_boundary_revision is not None:
                block_text = forced_boundary_revision
                chosen["surface"] = analyze_prose_surface(block_text, block=block)
                self._emit_stage(
                    stage=f"beat_{block.block_index}_boundary_trim_done",
                    action="Trim beat back to boundary",
                    reason="The beat draft overran its local budget or stole future scene work, so a local revision pulled it back before commit.",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=block.block_id,
                    block_index=block.block_index,
                    target_chars=block.target_chars,
                    trimmed_length=len(block_text),
                )
            chosen_surface = chosen["surface"]
            block_review_reports: dict[str, Any] = {}
            revision_brief_text = ""
            revised = False
            if self.mode == "deep":
                should_run_block_review = self._should_run_block_review(chosen_surface)
                if should_run_block_review:
                    block_review_reports = self._run_block_review_tools(
                        context=context,
                        block=block,
                        block_text=block_text,
                        block_context=block_context,
                    )
                revision_brief_text = build_revision_brief(
                    block=block,
                    review_reports=block_review_reports,
                    surface=chosen_surface,
                )
                if self._needs_block_revision(block_review_reports) or self._needs_surface_revision(chosen_surface):
                    revise_result = self.tool_registry.execute(
                        "revise_block_if_needed",
                        ChapterToolPayloadBuilder.build_revise_block_payload(
                            block=block,
                            block_context=block_context,
                            block_text=block_text,
                            review_reports=block_review_reports,
                            block_revision_plan={
                                "scope": "block",
                                "target_id": block.block_id,
                                "summary": "Tighten prose surface and cash relationship cost without changing chapter structure.",
                            },
                            loaded_skill_instructions_text=loaded_skill_instructions_text,
                            candidate_strategy=str(chosen["strategy"] or "").strip(),
                            revision_brief_text=revision_brief_text,
                        ),
                    )
                    revised_text = str(revise_result.get("block_text") or "").strip()
                    if revised_text:
                        revised_surface = analyze_prose_surface(revised_text, block=block)
                        if self._should_keep_revised_block(
                            original_text=block_text,
                            revised_text=revised_text,
                            original_surface=chosen_surface,
                            revised_surface=revised_surface,
                        ):
                            block_text = revised_text
                            chosen_surface = revised_surface
                            revised = True
            committed_block = block.model_copy(
                update={
                    "text": block_text,
                    "status": "committed",
                    "version": max(int(block.version), 1) + (1 if revised else 0),
                }
            )
            committed_blocks.append(committed_block)
            chapter_text = self._merge_blocks_to_chapter(committed_blocks)
            stage_log.append(
                {
                    "stage": f"draft_beat_{block.block_index}",
                    "block_id": committed_block.block_id,
                    "block_index": committed_block.block_index,
                    "candidate_count": len(candidates),
                    "selected_strategy": chosen["strategy"],
                    "surface_score": chosen_surface.overall_score,
                    "action_carried_reveal_score": chosen_surface.action_carried_reveal_score,
                    "relationship_cost_realization_score": chosen_surface.relationship_cost_realization_score,
                    "pronoun_lead_ratio": chosen_surface.pronoun_lead_ratio,
                    "explanation_ratio": chosen_surface.explanation_ratio,
                    "revised": revised,
                    "chapter_length": len(chapter_text),
                    "delivered_beat_summary_text": block_context.get("delivered_beat_summary_text", ""),
                }
            )
            if on_block_committed is not None:
                on_block_committed(committed_block)
            self._emit_chapter_preview(
                chapter_brief=chapter_brief,
                content_blocks=committed_blocks,
                character_mindsets=character_mindsets,
                final_text=chapter_text,
                final_version=0,
                is_finalized=False,
                preview_mode="chapter_draft",
                callback=on_chapter_preview_updated,
            )
            self._emit_stage(
                stage=f"beat_{block.block_index}_draft_done",
                action="Committed beat draft",
                reason="The beat is drafted and now becomes carry-over context for the next beat.",
                chapter_id=chapter_brief.chapter_id,
                block_id=committed_block.block_id,
                block_index=committed_block.block_index,
                committed_block=committed_block.model_dump(mode="json"),
                selected_strategy=chosen["strategy"],
                prose_surface={
                    "overall_score": chosen_surface.overall_score,
                    "action_carried_reveal_score": chosen_surface.action_carried_reveal_score,
                    "relationship_cost_realization_score": chosen_surface.relationship_cost_realization_score,
                    "pronoun_lead_ratio": chosen_surface.pronoun_lead_ratio,
                    "explanation_ratio": chosen_surface.explanation_ratio,
                    "procedure_pressure": chosen_surface.procedure_pressure,
                    "evidence": chosen_surface.evidence,
                },
                revision_brief=revision_brief_text if revised else "",
                current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
            )
        return committed_blocks, chapter_text, stage_log

    def _plan_content_blocks(self, *, chapter_brief: ChapterContract, context: Any) -> list[ChapterBeat]:
        payload = self.tool_registry.execute(
            "plan_content_blocks",
            ChapterToolPayloadBuilder.build_plan_content_blocks_payload(
                chapter_brief=chapter_brief,
                context=context,
            ),
        )
        blocks = [ChapterBeat.model_validate(item) for item in payload.get("blocks", [])]
        if not blocks:
            raise ValueError("plan_content_blocks returned no beats")
        return blocks

    def _build_character_mindsets(
        self,
        *,
        snapshot: NovelContextSnapshot,
        context: Any,
        character_cards: list[CharacterCard],
        prior_character_mindsets: list[CharacterMindset],
    ) -> list[CharacterMindset]:
        target_cards = self._select_character_mindset_cards(
            chapter_brief=snapshot.chapter_brief,
            character_cards=character_cards,
        )
        if not target_cards:
            return []

        prior_map: dict[str, CharacterMindset] = {}
        for item in prior_character_mindsets:
            try:
                mindset = CharacterMindset.model_validate(item)
            except Exception:
                continue
            key = str(mindset.character_name or "").strip()
            if key and key not in prior_map:
                prior_map[key] = mindset

        results: list[CharacterMindset] = []
        for card in target_cards:
            scoped_selection = NovelContextSelectorService.select(
                snapshot=snapshot,
                strategy="character_mindset_scoped_steps",
                character_name=card.name,
            )
            scoped_steps = NovelContextFormatter.format_character_mindset_scoped_steps(
                scoped_selection
            )
            previous = prior_map.get(card.name)
            payload = self.tool_registry.execute(
                "build_character_mindset",
                ChapterToolPayloadBuilder.build_character_mindset_payload(
                    context=context,
                    character_card=card,
                    previous_mindset=previous,
                    scoped_steps=scoped_steps,
                    character_id=self._character_id_from_name(card.name),
                ),
            )
            results.append(CharacterMindset.model_validate(payload))
        return results

    @staticmethod
    def _select_character_mindset_cards(
        *,
        chapter_brief: ChapterContract,
        character_cards: list[CharacterCard],
    ) -> list[CharacterCard]:
        focus_names = list(dict.fromkeys(str(name or "").strip() for name in chapter_brief.character_focus if str(name or "").strip()))
        selected: list[CharacterCard] = []
        for name in focus_names:
            card = get_character_card_by_name(character_cards, name)
            if card is None:
                continue
            selected.append(card)
            if len(selected) >= 2:
                break
        return selected

    @staticmethod
    def _character_id_from_name(name: str) -> str:
        return str(name or "").strip()

    @staticmethod
    def _candidate_strategies_for_block(block: ChapterBeat) -> list[str]:
        strategies = ["voice_and_body_first"]
        if str(block.relationship_delta or "").strip() or str(block.cost_shift or "").strip():
            strategies.append("relationship_cost_first")
        strategies.append("balanced_scene")
        deduped: list[str] = []
        for item in strategies:
            if item not in deduped:
                deduped.append(item)
        return deduped[:2]

    def _draft_block_candidates(
        self,
        *,
        block: ChapterBeat,
        block_context: dict[str, Any],
        loaded_skill_instructions_text: str,
    ) -> list[dict[str, Any]]:
        strategies = self._candidate_strategies_for_block(block)
        if len(strategies) <= 1:
            single = self._draft_single_block_candidate(
                block=block,
                block_context=block_context,
                loaded_skill_instructions_text=loaded_skill_instructions_text,
                strategy=strategies[0] if strategies else "balanced_scene",
            )
            return [single] if single is not None else []

        candidates: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(2, len(strategies))) as executor:
            futures = {
                executor.submit(
                    self._draft_single_block_candidate,
                    block=block,
                    block_context=block_context,
                    loaded_skill_instructions_text=loaded_skill_instructions_text,
                    strategy=strategy,
                ): strategy
                for strategy in strategies
            }
            for future in as_completed(futures):
                candidate = future.result()
                if candidate is not None:
                    candidates.append(candidate)
        return candidates

    def _draft_single_block_candidate(
        self,
        *,
        block: ChapterBeat,
        block_context: dict[str, Any],
        loaded_skill_instructions_text: str,
        strategy: str,
    ) -> dict[str, Any] | None:
        draft_result = self.tool_registry.execute(
            "draft_block",
            ChapterToolPayloadBuilder.build_draft_block_payload(
                block=block,
                block_context=block_context,
                loaded_skill_instructions_text=loaded_skill_instructions_text,
                candidate_strategy=strategy,
            ),
        )
        block_text = str(draft_result.get("block_text") or "").strip()
        if not block_text:
            return None
        surface = analyze_prose_surface(block_text, block=block)
        return {
            "strategy": strategy,
            "text": block_text,
            "surface": surface,
            "selection_score": self._surface_selection_score(surface),
        }

    @classmethod
    def _choose_best_block_candidate(
        cls,
        *,
        block: ChapterBeat,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not candidates:
            raise ValueError(f"No usable draft_block candidate for {block.block_id}")
        ranked = sorted(
            candidates,
            key=lambda item: (
                float(item.get("selection_score") or 0.0),
                float(getattr(item.get("surface"), "overall_score", 0.0)),
                float(getattr(item.get("surface"), "relationship_cost_realization_score", 0.0)),
                float(getattr(item.get("surface"), "action_carried_reveal_score", 0.0)),
            ),
            reverse=True,
        )
        return ranked[0]

    @staticmethod
    def _surface_selection_score(surface: ProseSurfaceSignals) -> float:
        return (
            float(surface.overall_score)
            + float(surface.action_carried_reveal_score) * 0.45
            + float(surface.relationship_cost_realization_score) * 0.55
            - float(surface.procedure_pressure) * 0.40
            - float(surface.pronoun_lead_ratio) * 10.0
            - float(surface.explanation_ratio) * 12.0
        )

    def _fetch_block_context(
        self,
        *,
        context: Any,
        block: ChapterBeat,
        committed_blocks: list[ChapterBeat],
        remaining_blocks: list[ChapterBeat] | None = None,
    ) -> dict[str, Any]:
        return ChapterToolPayloadBuilder.build_block_runtime_context(
            context=context,
            block=block,
            committed_blocks=committed_blocks,
            remaining_blocks=remaining_blocks,
        )

    def _force_beat_boundary_revision(
        self,
        *,
        context: Any,
        block: ChapterBeat,
        block_context: dict[str, Any],
        block_text: str,
        candidate_strategy: str = "",
    ) -> str | None:
        if not self._needs_beat_boundary_revision(block=block, block_text=block_text):
            return None
        review_json = {
            "beat_boundary_guard": {
                "passed": False,
                "issues": [
                    {
                        "category": "beat_boundary_overrun",
                        "severity": "high",
                        "reason": "This beat is too long for its target or is likely cashing later-beat work early.",
                        "evidence": f"target_chars={block.target_chars}, drafted_chars={len(block_text)}",
                        "fix": "Shorten to the current beat only; stop before later clues, later confrontation, or later hook work.",
                    }
                ],
            }
        }
        revision_plan = {
            "scope": "block",
            "target_id": block.block_id,
            "summary": "Trim the beat back to its own scene boundary.",
            "must_fix": [
                "Keep only the current beat's scene turn and end state.",
                "Delete later-scene material, second action cycles, and after-turn explanation.",
            ],
            "keep": [
                str(block.scene_goal or "").strip(),
                str(block.end_state or "").strip(),
            ],
            "hard_constraints": [
                ChapterToolPayloadBuilder.target_length_guard(block.target_chars),
                "Do not steal the next beat's clue, confrontation, or hook.",
            ],
        }
        revise_result = self.tool_registry.execute(
            "revise_block_if_needed",
            ChapterToolPayloadBuilder.build_revise_block_payload(
                block=block,
                block_context=block_context,
                block_text=block_text,
                review_reports=review_json,
                block_revision_plan=revision_plan,
                loaded_skill_instructions_text="",
                candidate_strategy=candidate_strategy,
                revision_brief_text="Cut everything beyond this beat's own turn and visible end state.",
            ),
        )
        revised_text = str(revise_result.get("block_text") or "").strip()
        return revised_text or block_text

    @classmethod
    def _needs_beat_boundary_revision(cls, *, block: ChapterBeat, block_text: str) -> bool:
        clean = str(block_text or "").strip()
        if not clean:
            return False
        hard_ceiling = cls._beat_hard_ceiling(block.target_chars)
        if len(clean) > hard_ceiling:
            return True
        paragraph_count = len(cls._split_paragraphs(clean))
        return bool(block.target_chars and block.target_chars <= 1100 and paragraph_count > 6)

    @staticmethod
    def _beat_hard_ceiling(target_chars: int | str | None) -> int:
        try:
            target = int(target_chars or 0)
        except (TypeError, ValueError):
            target = 0
        if target <= 0:
            return 1200
        return max(320, int(round(target * 1.35)))

    @staticmethod
    def _needs_surface_revision(surface: ProseSurfaceSignals) -> bool:
        return (
            surface.pronoun_lead_ratio > 0.26
            or surface.explanation_ratio > 0.22
            or surface.action_carried_reveal_score < 6.2
            or surface.relationship_cost_realization_score < 6.2
            or surface.procedure_pressure > 5.6
        )

    @staticmethod
    def _should_run_block_review(surface: ProseSurfaceSignals) -> bool:
        return (
            surface.overall_score < 8.1
            or surface.procedure_pressure > 3.6
            or surface.pronoun_lead_ratio > 0.18
            or surface.explanation_ratio > 0.16
            or surface.action_carried_reveal_score < 7.6
            or surface.relationship_cost_realization_score < 7.6
        )

    @classmethod
    def _should_keep_revised_block(
        cls,
        *,
        original_text: str,
        revised_text: str,
        original_surface: ProseSurfaceSignals,
        revised_surface: ProseSurfaceSignals,
    ) -> bool:
        if not str(revised_text or "").strip():
            return False
        if str(revised_text).strip() == str(original_text).strip():
            return False
        original_score = cls._surface_selection_score(original_surface)
        revised_score = cls._surface_selection_score(revised_surface)
        if revised_score >= original_score - 0.15:
            return True
        if (
            revised_surface.explanation_ratio < original_surface.explanation_ratio
            and revised_surface.pronoun_lead_ratio <= original_surface.pronoun_lead_ratio
            and revised_surface.relationship_cost_realization_score >= original_surface.relationship_cost_realization_score
        ):
            return True
        return False

    def _run_block_review_tools(
        self,
        *,
        context: Any,
        block: ChapterBeat,
        block_text: str,
        block_context: dict[str, Any],
    ) -> dict[str, Any]:
        reports: dict[str, Any] = {}
        tool_names = self.DEEP_BLOCK_REVIEW_TOOLS if self.mode == "deep" else self.BLOCK_REVIEW_TOOLS
        for tool_name in tool_names:
            reports[tool_name] = self.tool_registry.execute(
                tool_name,
                ChapterToolPayloadBuilder.build_block_review_payload(
                    tool_name=tool_name,
                    context=context,
                    block=block,
                    block_text=block_text,
                    block_context=block_context,
                ),
            )
        return reports

    @staticmethod
    def _needs_block_revision(review_reports: dict[str, Any]) -> bool:
        for report in review_reports.values():
            if not isinstance(report, dict):
                continue
            if not bool(report.get("passed", True)):
                return True
            if report.get("issues"):
                return True
        return False

    @staticmethod
    def _merge_blocks_to_chapter(blocks: list[ChapterBeat]) -> str:
        return "\n\n".join(str(block.text or "").strip() for block in blocks if str(block.text or "").strip()).strip()

    @staticmethod
    def _blocks_have_text(blocks: list[ChapterBeat]) -> bool:
        return all(str(block.text or "").strip() for block in blocks)

    @staticmethod
    def _report_passed(report: dict[str, Any]) -> bool:
        return bool(report.get("passed", report.get("pass", False)))

    @classmethod
    def _all_reviews_passed(cls, review_reports: dict[str, Any]) -> bool:
        if not review_reports:
            return False
        for report in review_reports.values():
            if not isinstance(report, dict):
                return False
            if not cls._report_passed(report):
                return False
            if list(report.get("issues") or []):
                return False
        return True

    @classmethod
    def _build_review_gate_result(cls, review_reports: dict[str, Any]) -> dict[str, Any]:
        blocking_reasons: list[str] = []
        for tool_name, report in review_reports.items():
            if not isinstance(report, dict):
                blocking_reasons.append(f"{tool_name} returned an invalid report.")
                continue
            issues = list(report.get("issues") or [])
            if not cls._report_passed(report):
                summary = str(report.get("summary") or "").strip()
                blocking_reasons.append(summary or f"{tool_name} did not pass.")
                continue
            if issues:
                blocking_reasons.append(f"{tool_name} still reported {len(issues)} issue(s).")
        return {
            "passed": not blocking_reasons,
            "blocking_reasons": blocking_reasons,
            "metrics": {
                "review_tools": len(review_reports),
                "issue_count": sum(len(list(report.get("issues") or [])) for report in review_reports.values() if isinstance(report, dict)),
            },
        }

    @classmethod
    def _materialize_full_draft_blocks(
        cls,
        *,
        planned_blocks: list[ChapterBeat],
        chapter_text: str,
    ) -> list[ChapterBeat]:
        block_texts = cls._split_text_into_block_texts(chapter_text=chapter_text, block_count=len(planned_blocks))
        materialized: list[ChapterBeat] = []
        for index, block in enumerate(planned_blocks):
            text = block_texts[index] if index < len(block_texts) else ""
            materialized.append(
                block.model_copy(
                    update={
                        "text": text,
                        "status": "committed" if text else block.status,
                    }
                )
            )
        return materialized

    @classmethod
    def _split_text_into_block_texts(cls, *, chapter_text: str, block_count: int) -> list[str]:
        clean = str(chapter_text or "").strip()
        if block_count <= 0:
            return []
        if not clean:
            return [""] * block_count
        paragraphs = cls._split_paragraphs(clean)
        if len(paragraphs) >= block_count:
            return cls._pack_units_to_block_count(paragraphs, block_count=block_count, separator="\n\n")
        sentences = cls._split_sentences(clean)
        if len(sentences) >= block_count:
            return cls._pack_units_to_block_count(sentences, block_count=block_count, separator="")
        return cls._chunk_text_evenly(clean, block_count=block_count)

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        return [item.strip() for item in re.split(r"\n\s*\n+", str(text or "").strip()) if item.strip()]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        pieces = re.findall(r"[^。！？!?；;]+[。！？!?；;]?|\S", str(text or "").strip())
        return [item.strip() for item in pieces if item and item.strip()]

    @staticmethod
    def _pack_units_to_block_count(units: list[str], *, block_count: int, separator: str) -> list[str]:
        base_size, extra = divmod(len(units), block_count)
        result: list[str] = []
        cursor = 0
        for index in range(block_count):
            take = base_size + (1 if index < extra else 0)
            take = max(take, 1)
            chunk = units[cursor : cursor + take]
            if not chunk:
                result.append("")
                continue
            cursor += take
            result.append(separator.join(chunk).strip())
        if cursor < len(units) and result:
            remainder = separator.join(units[cursor:]).strip()
            if result[-1] and remainder:
                result[-1] = f"{result[-1]}{separator}{remainder}".strip()
            elif remainder:
                result[-1] = remainder
        return result

    @staticmethod
    def _chunk_text_evenly(text: str, *, block_count: int) -> list[str]:
        clean = str(text or "").strip()
        if not clean:
            return [""] * block_count
        total = len(clean)
        average = max(total // block_count, 1)
        result: list[str] = []
        start = 0
        punctuation = "。！？!?；;，,"
        for index in range(block_count):
            if index == block_count - 1:
                result.append(clean[start:].strip())
                break
            tentative_end = min(start + average, total - (block_count - index - 1))
            end = tentative_end
            while end < total and clean[end] not in punctuation and end - tentative_end < 30:
                end += 1
            if end < total:
                end += 1
            chunk = clean[start:end].strip()
            if not chunk:
                chunk = clean[start:tentative_end].strip()
                end = tentative_end
            result.append(chunk)
            start = end
        while len(result) < block_count:
            result.append("")
        return result[:block_count]

    @classmethod
    def _apply_patch_result_to_blocks(
        cls,
        *,
        original_blocks: list[ChapterBeat],
        rewrite_result: dict[str, Any],
    ) -> list[ChapterBeat]:
        patched_map = {
            str(item.get("block_id") or "").strip(): str(item.get("new_text") or "").strip()
            for item in list(rewrite_result.get("patched_blocks") or [])
            if str(item.get("block_id") or "").strip()
        }
        updated_blocks: list[ChapterBeat] = []
        for block in original_blocks:
            if block.block_id not in patched_map:
                updated_blocks.append(block)
                continue
            new_text = patched_map[block.block_id]
            changed = new_text != str(block.text or "").strip()
            updated_blocks.append(
                block.model_copy(
                    update={
                        "text": new_text,
                        "status": "committed",
                        "version": max(int(block.version), 1) + (1 if changed else 0),
                    }
                )
            )
        return updated_blocks

    @staticmethod
    def _patch_plan_requires_structural_rebuild(patch_plan: dict[str, Any]) -> bool:
        structural_markers = (
            "移至",
            "移到",
            "之后",
            "之前",
            "顺序",
            "重排",
            "删除",
            "移除",
            "并入",
            "挪到",
            "reorder",
            "move after",
            "move before",
            "delete",
            "remove",
        )
        for target in list(patch_plan.get("patch_targets") or []):
            parts = [
                str(target.get("problem_type") or ""),
                str(target.get("goal") or ""),
                *[str(item or "") for item in list(target.get("instructions") or [])],
            ]
            combined = "\n".join(parts).lower()
            if any(marker in combined for marker in structural_markers):
                return True
        return False

    @staticmethod
    def _normalize_patch_judge_result(*, judge_result: dict[str, Any], patch_round: int) -> dict[str, Any]:
        remaining = list(judge_result.get("remaining_issues") or [])
        introduced = list(judge_result.get("newly_introduced_issues") or [])
        reasons = [str(item.get("reason") or "").strip() for item in [*remaining, *introduced] if str(item.get("reason") or "").strip()]
        if "llm_pass" in judge_result:
            llm_pass = bool(judge_result.get("llm_pass"))
        else:
            llm_pass = bool(judge_result.get("pass") or judge_result.get("passed"))
        recommendation = str(judge_result.get("recommendation") or "").strip()
        passed = (
            llm_pass
            and not remaining
            and not introduced
            and not WritingChapterAgent._recommendation_requires_followup(recommendation)
        )
        if llm_pass and not passed and recommendation:
            reasons.append(f"Patch judge requested follow-up: {recommendation}")
        return {
            "passed": passed,
            "blocking_reasons": reasons,
            "metrics": {
                "patch_round": patch_round,
                "llm_pass_flag": llm_pass,
                "remaining_issue_count": len(remaining),
                "introduced_issue_count": len(introduced),
            },
            "recommendation": recommendation,
        }

    @staticmethod
    def _recommendation_requires_followup(recommendation: str) -> bool:
        normalized = str(recommendation or "").strip().lower()
        if not normalized:
            return False
        satisfied_markers = (
            "无需再补",
            "无需补",
            "无需额外补打补丁",
            "无需额外补丁",
            "可保留当前版本",
            "无需再补补丁",
            "无需补补丁",
            "无需补丁",
            "可以结束",
            "可推进",
        )
        if any(marker in normalized for marker in satisfied_markers):
            return False
        followup_markers = (
            "建议补",
            "继续补",
            "再补",
            "补一次",
            "继续 patch",
            "another patch",
            "retry patch",
            "patch again",
            "suggest deep",
            "切到 deep",
            "建议切到 deep",
            "need another patch",
        )
        return any(marker in normalized for marker in followup_markers)

    @classmethod
    def _build_patch_loop_failure_result(
        cls,
        *,
        judge_result: dict[str, Any],
        patch_round: int,
        reason: str,
    ) -> dict[str, Any]:
        result = cls._normalize_patch_judge_result(judge_result=judge_result, patch_round=patch_round)
        blocking = list(result.get("blocking_reasons") or [])
        if reason:
            blocking.append(reason)
        result["passed"] = False
        result["blocking_reasons"] = blocking
        result["recommendation"] = reason
        return result

    @staticmethod
    def _review_source_from_patch_judge(judge_result: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for prefix, items in (
            ("remaining", list(judge_result.get("remaining_issues") or [])),
            ("introduced", list(judge_result.get("newly_introduced_issues") or [])),
        ):
            for index, item in enumerate(items, start=1):
                issues.append(
                    {
                        "issue_id": f"{prefix}_{index}",
                        "severity": "medium",
                        "problem_type": str(item.get("problem_type") or prefix).strip() or prefix,
                        "reason": str(item.get("reason") or "").strip(),
                        "target_blocks": list(item.get("target_blocks") or []),
                        "patch_hint": str(item.get("reason") or "").strip(),
                    }
                )
        return {
            "judge_patched_chapter": {
                "pass": bool(judge_result.get("pass") or judge_result.get("passed")),
                "issues": issues,
                "summary": str(judge_result.get("recommendation") or "").strip(),
            }
        }

    def _plan_review_tools(
        self,
        *,
        chapter_brief: ChapterContract,
        review_reports: dict[str, Any],
        active_skills: list[Any],
        content_blocks: list[ChapterBeat],
    ) -> list[str]:
        del chapter_brief, review_reports, active_skills, content_blocks
        base_tools = self.FAST_CHAPTER_REVIEW_TOOLS if self.mode == "fast" else self.DEEP_CHAPTER_REVIEW_TOOLS
        return list(base_tools)

    @staticmethod
    def _chapter_needs_clue_review(
        *,
        chapter_brief: ChapterContract,
        review_reports: dict[str, Any],
        content_blocks: list[ChapterBeat],
    ) -> bool:
        if chapter_brief.allowed_clues:
            return True
        if review_reports.get("review_clue_origin"):
            return True
        return any(block.clue_reveal_mechanism is not None for block in content_blocks)

    def _run_review_tools(
        self,
        *,
        tool_names: list[str],
        chapter_brief: ChapterContract,
        context: Any,
        chapter_text: str,
        chapter_id: str,
        iteration: int,
        planned_blocks: list[ChapterBeat],
    ) -> dict[str, Any]:
        payload = ChapterToolPayloadBuilder.build_chapter_review_payload(
            chapter_brief=chapter_brief,
            context=context,
            chapter_text=chapter_text,
            planned_blocks=planned_blocks,
        )
        reports: dict[str, Any] = {}
        for tool_name in tool_names:
            self._emit_stage(
                stage=f"review_iteration_{iteration}_tool_start",
                action="Run review tool",
                reason=f"Start {tool_name}.",
                chapter_id=chapter_id,
                iteration=iteration,
                tool_name=tool_name,
            )
            reports[tool_name] = self.tool_registry.execute(tool_name, payload)
            self._emit_stage(
                stage=f"review_iteration_{iteration}_tool_done",
                action="Review tool finished",
                reason=f"{tool_name} returned its report.",
                chapter_id=chapter_id,
                iteration=iteration,
                tool_name=tool_name,
                tool_result=reports[tool_name],
            )
        return reports

    @staticmethod
    def _tail_text(text: str, *, max_chars: int = 1200) -> str:
        clean = str(text or "").strip()
        return clean[-max_chars:] if clean else ""

    @staticmethod
    def _context_bundle(context: Any) -> dict[str, Any]:
        return {
            "selection_summary_text": context.selection_summary_text,
            "time_anchor_text": context.time_anchor_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "step_1_story_foundation_text": context.step_1_story_foundation_text,
            "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
            "step_3_character_packets_text": context.step_3_character_packets_text,
            "step_4_event_timeline_text": context.step_4_event_timeline_text,
            "step_5_character_milestones_text": context.step_5_character_milestones_text,
            "step_6_twists_text": context.step_6_twists_text,
            "step_7_story_lines_text": context.step_7_story_lines_text,
            "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
            "chapter_payload_text": context.chapter_payload_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
            "style_card_text": context.style_card_text,
            "assistant_persona_prompt": getattr(context, "assistant_persona_prompt", ""),
            "writing_requirements_json": getattr(context, "writing_requirements_json", "{}"),
            "previous_chapter_full_text": getattr(context, "previous_chapter_full_text", ""),
        }

    @staticmethod
    def _judge_score(result: dict[str, Any]) -> int:
        if not result:
            return -1000
        score = 0
        if bool(result.get("passed", result.get("pass", False))):
            score += 1000
        score -= len(result.get("blocking_reasons", []) or []) * 20
        metrics = dict(result.get("metrics", {}) or {})
        score += int(metrics.get("prose_score") or 0)
        score += int(metrics.get("tension_score") or 0)
        score += int(metrics.get("human_warmth_score") or 0)
        score += int(metrics.get("memorability_score") or 0)
        score += int(metrics.get("pressure_authenticity_score") or 0)
        score -= int(metrics.get("exposition_score") or 0)
        return score

    def _emit_stage(
        self,
        *,
        stage: str,
        action: str,
        reason: str,
        **payload: Any,
    ) -> None:
        ev.emit(
            "stage",
            agent=self.name,
            title=action,
            stage=stage,
            action=action,
            reason=reason,
            **payload,
        )

    @staticmethod
    def _emit_chapter_preview(
        *,
        chapter_brief: ChapterContract,
        content_blocks: list[ChapterBeat],
        character_mindsets: list[CharacterMindset],
        final_text: str,
        final_version: int,
        is_finalized: bool,
        preview_mode: str,
        callback: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if callback is None:
            return
        callback(
            {
                "chapter_id": chapter_brief.chapter_id,
                "chapter_title": chapter_brief.title,
                "content_blocks": [item.model_dump(mode="json") for item in content_blocks],
                "character_mindsets": [item.model_dump(mode="json") for item in character_mindsets],
                "final_text": str(final_text or "").strip(),
                "final_version": max(int(final_version), 0),
                "is_finalized": bool(is_finalized),
                "preview_mode": preview_mode,
            }
        )

    def _render_prompt(self, relative_path: str, **kwargs: Any) -> str:
        return self.prompt_library.render(relative_path, **kwargs)

    def _messages(self, prompt: str) -> list[LLMMessage]:
        return build_messages(
            system_prompt=(
                "You are a chapter-writing agent. "
                "All user-facing content must be in Simplified Chinese unless the prompt explicitly requires another language. "
                "If asked for prose, return prose only. "
                "If asked for JSON, return valid JSON only. "
                "For JSON, keep ids and schema-required enums unchanged, but write natural-language string content in Simplified Chinese."
            ),
            prompt=prompt,
        )
