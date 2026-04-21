from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    ActualChapterSummary,
    AgentResult,
    ChapterBrief,
    ChapterExecutionResult,
    CharacterCard,
    ContentBlock,
    StoryPremise,
    StoryLine,
    TwistDesign,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.chapter_context import ChapterContextAssembler, build_current_chapter_context
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.dynamic_instruction_builder import DynamicInstructionBuilder
from novel_flow.services.review_aggregator import ReviewAggregator
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.services.tool_registry import ToolRegistry


class WritingChapterAgent(BaseAgent):
    INCREMENTAL_BLOCK_DRAFTING_ENABLED = False
    BLOCK_REVIEW_TOOLS = [
        "review_reveal_leak",
        "review_character_integrity",
        "review_time_consistency",
        "review_block_quality",
    ]
    CHAPTER_REVIEW_TOOLS = [
        "review_instruction_compliance",
        "review_prose_quality",
        "review_plot_logic",
        "review_continuity",
        "review_humanity",
        "review_chapter_engine",
    ]
    OPTIONAL_CHAPTER_REVIEW_TOOLS = [
        "review_clue_origin",
    ]
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
        max_iterations: int = 3,
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
        self.max_iterations = max_iterations

    def write_chapter(
        self,
        *,
        chapter_brief: ChapterBrief,
        twist_designs: list[TwistDesign],
        story_lines: list[StoryLine],
        character_cards: list[CharacterCard],
        worldbuilding: dict[str, Any] | None,
        actual_chapter_summaries: list[ActualChapterSummary],
        premise: StoryPremise | None = None,
        character_milestones: list[dict[str, Any]] | None = None,
        prebuilt_context: Any | None = None,
        on_block_committed: Callable[[ContentBlock], None] | None = None,
        on_chapter_preview_updated: Callable[[dict[str, Any]], None] | None = None,
    ) -> ChapterExecutionResult:
        context = prebuilt_context or ChapterContextAssembler.build(
            chapter_brief=chapter_brief,
            premise=premise,
            twist_designs=twist_designs,
            story_lines=story_lines,
            worldbuilding=worldbuilding or {},
            character_cards=character_cards,
            character_milestones=character_milestones or [],
            actual_summaries=actual_chapter_summaries,
            current_chapter_id=chapter_brief.chapter_id,
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

        block_skills = self.skill_manager.initial_skills(stage="block")
        block_skill_text = self.skill_manager.format_for_model(block_skills)
        self._emit_stage(
            stage="plan_content_blocks_start",
            action="Plan content blocks",
            reason="Plan the chapter as content blocks before drafting.",
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
            action="Planned content blocks",
            reason="The chapter now has a block-level writing design.",
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
                block_card_text = self._block_card_text(block)
                self._emit_stage(
                    stage=f"block_{block.block_index}_draft_start",
                    action="Draft block",
                    reason="Write the current content block before any chapter-level rewrite.",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=block.block_id,
                    block_index=block.block_index,
                )
                draft_result = self.tool_registry.execute(
                    "draft_block",
                    {
                        **block_context,
                        **self._block_prompt_fields(block),
                        "block_card_text": block_card_text,
                        "loaded_skill_instructions_text": block_skill_text,
                    },
                )
                block_text = str(draft_result.get("block_text") or "").strip()
                block_review_reports = self._run_block_review_tools(
                    context=context,
                    block=block,
                    block_text=block_text,
                    block_context=block_context,
                    block_card_text=block_card_text,
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
                        reason="The block-level light review found issues that should be fixed before commit.",
                        chapter_id=chapter_brief.chapter_id,
                        block_id=block.block_id,
                        block_index=block.block_index,
                        block_revision_plan=block_revision_plan.model_dump(mode="json"),
                    )
                    revise_result = self.tool_registry.execute(
                        "revise_block_if_needed",
                        {
                            **block_context,
                            **self._block_prompt_fields(block),
                            "block_card_text": block_card_text,
                            "block_text": block_text,
                            "review_json": json.dumps(block_review_reports, ensure_ascii=False, indent=2),
                            "block_revision_plan_json": json.dumps(block_revision_plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                            "loaded_skill_instructions_text": block_skill_text,
                        },
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
                    final_text="",
                    final_version=0,
                    is_finalized=False,
                    preview_mode="content_blocks",
                    callback=on_chapter_preview_updated,
                )
                self._emit_stage(
                    stage=f"block_{block.block_index}_committed",
                    action="Committed block",
                    reason="The current content block is committed and can be shown incrementally.",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=committed_block.block_id,
                    block_index=committed_block.block_index,
                    committed_block=committed_block.model_dump(mode="json"),
                    current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
                )

            self._emit_stage(
                stage="merge_blocks_to_chapter_done",
                action="Merged content blocks",
                reason="All content blocks are committed and ready for chapter-level review.",
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
        else:
            self._emit_stage(
                stage="write_chapter_full_start",
                action="Write full chapter from plan",
                reason="Use the planned content blocks as the chapter skeleton and draft the full prose in one pass.",
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
                final_text=chapter_text,
                final_version=1,
                is_finalized=False,
                preview_mode="chapter_draft",
                callback=on_chapter_preview_updated,
            )
            self._emit_stage(
                stage="write_chapter_full_done",
                action="Finished chapter draft from plan",
                reason="The chapter prose now follows the planned content block list and is ready for chapter-level review.",
                chapter_id=chapter_brief.chapter_id,
                block_count=len(committed_blocks),
                chapter_length=len(chapter_text),
            )

        active_skills = self.skill_manager.initial_skills(stage="chapter")
        best_snapshot = {
            "chapter_text": chapter_text,
            "review_reports": review_reports,
            "final_judge": final_judge,
            "stage_log": list(stage_log),
        }

        for iteration in range(1, self.max_iterations + 1):
            if review_reports:
                active_skills = self.skill_manager.discover(
                    chapter_brief=chapter_brief,
                    review_reports=review_reports,
                    stage="chapter",
                )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_skills",
                action="Select chapter skills",
                reason="Use focused chapter-level skills for the current review cycle.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                skill_ids=[skill.skill_id for skill in active_skills],
            )
            planned_tools = self._plan_review_tools(
                chapter_brief=chapter_brief,
                review_reports=review_reports,
                active_skills=active_skills,
                content_blocks=committed_blocks,
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_plan",
                action="Plan chapter reviews",
                reason="Keep the chapter-level heavy review set focused and deterministic.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                tool_calls=planned_tools,
            )
            review_reports = self._run_review_tools(
                tool_names=planned_tools,
                chapter_brief=chapter_brief,
                context=context,
                chapter_text=chapter_text,
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
            )
            chapter_revision_plan = ReviewAggregator.aggregate_chapter(
                review_reports=review_reports,
                triggered_skills=[skill.skill_id for skill in active_skills],
                chapter_id=chapter_brief.chapter_id,
            )
            dynamic_instruction = DynamicInstructionBuilder.build(
                review_reports=review_reports,
                revision_plan=chapter_revision_plan,
                active_skill_ids=[skill.skill_id for skill in active_skills],
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_aggregate",
                action="Aggregate chapter reviews",
                reason="Build a chapter-only revision plan from chapter-level review evidence.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                review_reports=review_reports,
                chapter_revision_plan=chapter_revision_plan.model_dump(mode="json"),
                dynamic_instruction=dynamic_instruction.model_dump(mode="json"),
            )
            final_judge = self.tool_registry.execute(
                "final_judge",
                {"review_reports": review_reports},
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_judge",
                action="Run final judge",
                reason="Decide whether the chapter can pass or needs a focused rewrite.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                final_judge=final_judge,
            )
            stage_log.append(
                {
                    "stage": f"review_iteration_{iteration}",
                    "skill_ids": [skill.skill_id for skill in active_skills],
                    "tool_calls": planned_tools,
                    "review_reports": review_reports,
                    "chapter_revision_plan": chapter_revision_plan.model_dump(mode="json"),
                    "dynamic_instruction": dynamic_instruction.model_dump(mode="json"),
                    "final_judge": final_judge,
                }
            )
            if self._judge_score(final_judge) >= self._judge_score(best_snapshot["final_judge"]):
                best_snapshot = {
                    "chapter_text": chapter_text,
                    "review_reports": review_reports,
                    "final_judge": final_judge,
                    "stage_log": list(stage_log),
                }
            if bool(final_judge.get("passed")):
                self._emit_stage(
                    stage=f"review_iteration_{iteration}_passed",
                    action="Chapter review passed",
                    reason="Proceed to final polish and format cleanup.",
                    chapter_id=chapter_brief.chapter_id,
                    iteration=iteration,
                    final_judge=final_judge,
                )
                break
            if iteration >= self.max_iterations:
                requires_human_review = True
                chapter_text = str(best_snapshot["chapter_text"] or chapter_text)
                review_reports = dict(best_snapshot["review_reports"] or review_reports)
                final_judge = dict(best_snapshot["final_judge"] or final_judge)
                stage_log = list(best_snapshot["stage_log"] or stage_log)
                stage_log.append(
                    {
                        "stage": "max_iterations_reached",
                        "requires_human_review": True,
                        "blocking_reasons": final_judge.get("blocking_reasons", []),
                    }
                )
                self._emit_stage(
                    stage="max_iterations_reached",
                    action="Reached max iterations",
                    reason="Keep the best available chapter version and mark it for human review.",
                    chapter_id=chapter_brief.chapter_id,
                    final_judge=final_judge,
                )
                break

            self._emit_stage(
                stage=f"rewrite_iteration_{iteration}_start",
                action="Rewrite chapter by plan",
                reason="Use the chapter-only revision plan to improve prose, humanity, and chapter engine.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                chapter_revision_plan=chapter_revision_plan.model_dump(mode="json"),
            )
            rewrite_result = self.tool_registry.execute(
                "rewrite_by_plan",
                {
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
                    "style_card_text": context.style_card_text,
                    "original_text": chapter_text,
                    "chapter_text": chapter_text,
                    "current_chapter_draft_tail": self._tail_text(chapter_text),
                    "previous_scene_tail": "",
                    "revision_plan": chapter_revision_plan.model_dump(mode="json"),
                    "dynamic_instruction_text": json.dumps(dynamic_instruction.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    "loaded_skill_instructions_text": self.skill_manager.format_for_model(active_skills),
                },
            )
            chapter_text = str(rewrite_result.get("chapter_text") or "").strip()
            self._emit_chapter_preview(
                chapter_brief=chapter_brief,
                content_blocks=committed_blocks,
                final_text=chapter_text,
                final_version=iteration,
                is_finalized=False,
                preview_mode="chapter_rewrite",
                callback=on_chapter_preview_updated,
            )
            stage_log.append(
                {
                    "stage": f"rewrite_iteration_{iteration}",
                    "skill_ids": [skill.skill_id for skill in active_skills],
                    "chapter_length": len(chapter_text),
                }
            )
            self._emit_stage(
                stage=f"rewrite_iteration_{iteration}_done",
                action="Finished chapter rewrite",
                reason="The chapter rewrite is ready for another focused heavy review pass.",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                chapter_length=len(chapter_text),
            )

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
            {
                "chapter_payload_text": context.chapter_payload_text,
                "style_card_text": context.style_card_text,
                "chapter_text": chapter_text,
                "loaded_skill_instructions_text": self.skill_manager.format_for_model(finalize_skills),
            },
        )
        chapter_text = str(polished.get("chapter_text") or "").strip()
        self._emit_chapter_preview(
            chapter_brief=chapter_brief,
            content_blocks=committed_blocks,
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
            {
                "final_polished_text": chapter_text,
                "output_format_rules": self.OUTPUT_FORMAT_RULES,
                "loaded_tool_context": context.chapter_payload_text,
            },
        )
        chapter_text = str(formatted.get("text") or chapter_text).strip()
        self._emit_chapter_preview(
            chapter_brief=chapter_brief,
            content_blocks=committed_blocks,
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
            {
                "chapter_text": chapter_text,
                "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
                "step_1_story_foundation_text": context.step_1_story_foundation_text,
                "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
                "step_3_character_packets_text": context.step_3_character_packets_text,
                "step_4_event_timeline_text": context.step_4_event_timeline_text,
                "step_5_character_milestones_text": context.step_5_character_milestones_text,
                "step_6_twists_text": context.step_6_twists_text,
                "step_7_story_lines_text": context.step_7_story_lines_text,
                "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
                "chapter_payload_text": context.chapter_payload_text,
                "time_anchor_text": context.time_anchor_text,
                "active_twists": [item.model_dump(mode="json") for item in context.active_twists],
                "active_story_lines": [item.model_dump(mode="json") for item in context.active_story_lines],
            },
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
        chapter_brief: ChapterBrief,
        context: Any,
        planned_blocks: list[ContentBlock],
    ) -> str:
        payload = self.tool_registry.execute(
            "write_chapter_full",
            {
                "assistant_persona_prompt": getattr(context, "assistant_persona_prompt", ""),
                "chapter_id": chapter_brief.chapter_id,
                "chapter_title": chapter_brief.title,
                "chapter_summary": chapter_brief.summary,
                "chapter_plan_json": self._chapter_plan_json(planned_blocks),
                "step_1_to_7_outputs_json": self._step_1_to_7_outputs_json(context),
                "chapter_payload_text": context.chapter_payload_text,
                "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
                "scene_character_context_text": context.scene_character_context_text,
                "relationship_state_text": context.relationship_state_text,
                "style_card_text": context.style_card_text,
                "previous_chapter_full_text": getattr(context, "previous_chapter_full_text", ""),
                "completed_chapter_summary_bundle": getattr(context, "completed_chapter_summary_bundle", context.completed_chapter_memory_text),
                "writing_requirements_json": getattr(context, "writing_requirements_json", "{}"),
                "reference_pack": getattr(context, "reference_pack", ""),
            },
        )
        return str(payload.get("chapter_text") or "").strip()

    def _plan_content_blocks(self, *, chapter_brief: ChapterBrief, context: Any) -> list[ContentBlock]:
        payload = self.tool_registry.execute(
            "plan_content_blocks",
            {
                "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
                "completed_chapter_memory_text": context.completed_chapter_memory_text,
                "chapter_payload_text": context.chapter_payload_text,
                "relevant_world_rules_text": context.relevant_world_rules_text,
                "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
                "scene_character_context_text": context.scene_character_context_text,
                "relationship_state_text": context.relationship_state_text,
                "style_card_text": context.style_card_text,
                "target_word_count_text": chapter_brief.info_budget,
            },
        )
        blocks = [ContentBlock.model_validate(item) for item in payload.get("blocks", [])]
        if not blocks:
            raise ValueError("plan_content_blocks returned no blocks")
        return blocks

    @classmethod
    def _chapter_plan_json(cls, planned_blocks: list[ContentBlock]) -> str:
        return cls._json_text({"blocks": [block.model_dump(mode="json") for block in planned_blocks]})

    @classmethod
    def _step_1_to_7_outputs_json(cls, context: Any) -> str:
        return cls._json_text(
            {
                "step_1_story_foundation_text": context.step_1_story_foundation_text,
                "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
                "step_3_character_packets_text": context.step_3_character_packets_text,
                "step_4_event_timeline_text": context.step_4_event_timeline_text,
                "step_5_character_milestones_text": context.step_5_character_milestones_text,
                "step_6_twists_text": context.step_6_twists_text,
                "step_7_story_lines_text": context.step_7_story_lines_text,
            }
        )

    def _fetch_block_context(
        self,
        *,
        context: Any,
        block: ContentBlock,
        committed_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        current_chapter_context = build_current_chapter_context(
            block.chapter_id,
            committed_blocks,
            max_blocks=4,
            tail_chars=1000,
        )
        prior_summary_lines = ["[Earlier committed blocks]"]
        current_written_blocks = list(current_chapter_context["current_chapter_written_blocks_json"])
        if current_written_blocks:
            for item in current_written_blocks:
                prior_summary_lines.extend(
                    [
                        "",
                        f"{item['block_id']} / {item['purpose']}",
                        f"- End state: {item['end_state']}",
                        f"- Text tail: {self._tail_text(str(item['text']), max_chars=220)}",
                    ]
                )
        else:
            prior_summary_lines.append("No committed blocks yet.")
        return {
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "chapter_payload_text": context.chapter_payload_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "current_chapter_written_blocks_json": self._json_text(current_written_blocks),
            "current_chapter_draft_tail": str(current_chapter_context["current_chapter_draft_tail"] or ""),
            "prior_block_summary_text": "\n".join(prior_summary_lines).strip(),
            "prior_chapter_text_tail": str(current_chapter_context["current_chapter_draft_tail"] or ""),
            "style_card_text": context.style_card_text,
        }

    def _run_block_review_tools(
        self,
        *,
        context: Any,
        block: ContentBlock,
        block_text: str,
        block_context: dict[str, Any],
        block_card_text: str,
    ) -> dict[str, Any]:
        reports: dict[str, Any] = {}
        review_scope_text = (
            "Review only the current content block. "
            "Keep the review light and local: catch reveal leakage, character-forced behavior, "
            "time carry-over conflicts, and whether the block actually feels like a live fiction beat."
        )
        common = {
            "chapter_payload_text": context.chapter_payload_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "time_anchor_text": context.time_anchor_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_text": block_text,
            "block_card_text": block_card_text,
            "active_twists_json": json.dumps([item.model_dump(mode="json") for item in context.active_twists], ensure_ascii=False, indent=2),
            "review_scope_text": review_scope_text,
        }
        for tool_name in self.BLOCK_REVIEW_TOOLS:
            if tool_name == "review_block_quality":
                reports[tool_name] = self.tool_registry.execute(
                    tool_name,
                    {
                        "chapter_payload_text": context.chapter_payload_text,
                        "relevant_world_rules_text": context.relevant_world_rules_text,
                        "scene_character_context_text": context.scene_character_context_text,
                        "relationship_state_text": context.relationship_state_text,
                        "current_chapter_written_blocks_json": block_context["current_chapter_written_blocks_json"],
                        "current_chapter_draft_tail": block_context["current_chapter_draft_tail"],
                        "block_card_text": block_card_text,
                        "prior_block_summary_text": block_context["prior_block_summary_text"],
                        "prior_chapter_text_tail": block_context["prior_chapter_text_tail"],
                        "block_text": block_text,
                        **self._block_prompt_fields(block),
                    },
                )
                continue
            reports[tool_name] = self.tool_registry.execute(tool_name, common)
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
    def _block_card_text(block: ContentBlock) -> str:
        lines = [
            "[Content block card]",
            "",
            f"block_id: {block.block_id}",
            f"chapter_id: {block.chapter_id}",
            f"block_index: {block.block_index}",
            f"purpose: {block.purpose}",
            f"scene_goal: {block.scene_goal}",
            f"emotional_tone: {block.emotional_tone}",
            f"end_state: {block.end_state}",
            f"cost_shift: {block.cost_shift}",
            f"reader_feeling_target: {block.reader_feeling_target}",
            f"paragraph_budget: {block.paragraph_budget}",
            f"micro_hook: {block.micro_hook}",
            f"turn_type: {block.turn_type}",
            "paragraph_shape:",
        ]
        for item in block.paragraph_shape or ["None."]:
            lines.append(f"- {item}")
        lines.append("character_anchor_line:")
        if block.character_anchor_line is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- owner: {block.character_anchor_line.owner or 'None.'}",
                    f"- form: {block.character_anchor_line.form or 'None.'}",
                    f"- surface_function: {block.character_anchor_line.surface_function or 'None.'}",
                    f"- hidden_function: {block.character_anchor_line.hidden_function or 'None.'}",
                    f"- must_reveal_about_character: {block.character_anchor_line.must_reveal_about_character or 'None.'}",
                    f"- preferred_shape: {block.character_anchor_line.preferred_shape or 'None.'}",
                    "- must_not_do:",
                ]
            )
            for item in block.character_anchor_line.must_not_do or ["None."]:
                lines.append(f"  - {item}")
        lines.extend(
            [
            "characters:",
            ]
        )
        for item in block.characters or ["None."]:
            lines.append(f"- {item}")
        lines.append("active_lines:")
        for item in block.active_lines or ["None."]:
            lines.append(f"- {item}")
        lines.append("active_twists:")
        for item in block.active_twists or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_reveal:")
        for item in block.must_reveal or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_hide:")
        for item in block.must_hide or ["None."]:
            lines.append(f"- {item}")
        lines.append("human_reaction_target:")
        for item in block.human_reaction_target or ["None."]:
            lines.append(f"- {item}")
        lines.append("style_risk_guard:")
        for item in block.style_risk_guard or ["None."]:
            lines.append(f"- {item}")
        lines.append("character_reentry_mode:")
        if block.character_reentry_mode is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- target_character: {block.character_reentry_mode.target_character or 'None.'}",
                    f"- identity_already_known: {block.character_reentry_mode.identity_already_known}",
                    f"- reentry_strategy: {block.character_reentry_mode.reentry_strategy or 'None.'}",
                    f"- first_signal: {block.character_reentry_mode.first_signal or 'None.'}",
                    f"- first_emotional_focus: {block.character_reentry_mode.first_emotional_focus or 'None.'}",
                    "- must_avoid:",
                ]
            )
            for item in block.character_reentry_mode.must_avoid or ["None."]:
                lines.append(f"  - {item}")
        lines.append("clue_reveal_mechanism:")
        if block.clue_reveal_mechanism is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- clue: {block.clue_reveal_mechanism.clue or 'None.'}",
                    f"- style: {block.clue_reveal_mechanism.style or 'None.'}",
                    f"- pressure_source: {block.clue_reveal_mechanism.pressure_source or 'None.'}",
                    f"- surface_trigger: {block.clue_reveal_mechanism.surface_trigger or 'None.'}",
                    f"- first_noticer: {block.clue_reveal_mechanism.first_noticer or 'None.'}",
                    f"- owner_reaction: {block.clue_reveal_mechanism.owner_reaction or 'None.'}",
                ]
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    @classmethod
    def _block_prompt_fields(cls, block: ContentBlock) -> dict[str, str]:
        return {
            "human_reaction_target": cls._json_text(list(block.human_reaction_target or [])),
            "cost_shift": str(block.cost_shift or "").strip(),
            "reader_feeling_target": str(block.reader_feeling_target or "").strip(),
            "paragraph_budget": str(block.paragraph_budget or "").strip(),
            "micro_hook": str(block.micro_hook or "").strip(),
            "turn_type": str(block.turn_type or "").strip(),
            "paragraph_shape": cls._json_text(list(block.paragraph_shape or [])),
            "character_anchor_line": (
                cls._json_text(block.character_anchor_line.model_dump(mode="json"))
                if block.character_anchor_line is not None
                else ""
            ),
            "style_risk_guard": cls._json_text(list(block.style_risk_guard or [])),
            "clue_reveal_mechanism": (
                cls._json_text(block.clue_reveal_mechanism.model_dump(mode="json"))
                if block.clue_reveal_mechanism is not None
                else ""
            ),
            "character_reentry_mode": (
                cls._json_text(block.character_reentry_mode.model_dump(mode="json"))
                if block.character_reentry_mode is not None
                else ""
            ),
        }

    @staticmethod
    def _merge_blocks_to_chapter(blocks: list[ContentBlock]) -> str:
        return "\n\n".join(str(block.text or "").strip() for block in blocks if str(block.text or "").strip()).strip()

    def _plan_review_tools(
        self,
        *,
        chapter_brief: ChapterBrief,
        review_reports: dict[str, Any],
        active_skills: list[Any],
        content_blocks: list[ContentBlock],
    ) -> list[str]:
        ordered: list[str] = []

        for tool_name in self.CHAPTER_REVIEW_TOOLS:
            if tool_name not in ordered:
                ordered.append(tool_name)

        if self._chapter_needs_clue_review(
            chapter_brief=chapter_brief,
            review_reports=review_reports,
            content_blocks=content_blocks,
        ):
            ordered.append("review_clue_origin")

        deduped: list[str] = []
        allowed = {*(self.CHAPTER_REVIEW_TOOLS), *(self.OPTIONAL_CHAPTER_REVIEW_TOOLS)}
        for tool_name in ordered:
            if tool_name in allowed and tool_name not in deduped:
                deduped.append(tool_name)
        return deduped

    @staticmethod
    def _chapter_needs_clue_review(
        *,
        chapter_brief: ChapterBrief,
        review_reports: dict[str, Any],
        content_blocks: list[ContentBlock],
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
        chapter_brief: ChapterBrief,
        context: Any,
        chapter_text: str,
        chapter_id: str,
        iteration: int,
    ) -> dict[str, Any]:
        payload = {
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
            "style_card_text": context.style_card_text,
            "chapter_text": chapter_text,
            "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
            "active_twists": [item.model_dump(mode="json") for item in context.active_twists],
            "active_twists_json": json.dumps([item.model_dump(mode="json") for item in context.active_twists], ensure_ascii=False, indent=2),
        }
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
        if bool(result.get("passed")):
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
        chapter_brief: ChapterBrief,
        content_blocks: list[ContentBlock],
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
                "final_text": str(final_text or "").strip(),
                "final_version": max(int(final_version), 0),
                "is_finalized": bool(is_finalized),
                "preview_mode": preview_mode,
            }
        )

    def _render_prompt(self, relative_path: str, **kwargs: Any) -> str:
        return self.prompt_library.render(relative_path, **kwargs)

    def _messages(self, prompt: str) -> list[LLMMessage]:
        return [
            LLMMessage(
                role="system",
                content=(
                    "You are a chapter-writing agent. "
                    "All user-facing content must be in Simplified Chinese unless the prompt explicitly requires another language. "
                    "If asked for prose, return prose only. "
                    "If asked for JSON, return valid JSON only. "
                    "For JSON, keep ids and schema-required enums unchanged, but write natural-language string content in Simplified Chinese."
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]
