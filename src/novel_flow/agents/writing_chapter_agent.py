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
    ToolPlanPayload,
    TwistDesign,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.chapter_context import ChapterContextAssembler
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.dynamic_instruction_builder import DynamicInstructionBuilder
from novel_flow.services.json_generation import safe_json_generate
from novel_flow.services.review_aggregator import ReviewAggregator
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.services.tool_registry import ToolRegistry


class WritingChapterAgent(BaseAgent):
    REVIEW_TOOLS = [
        "review_instruction_compliance",
        "review_time_consistency",
        "review_reveal_leak",
        "review_plot_logic",
        "review_clue_origin",
        "review_continuity",
        "review_character_integrity",
        "review_humanity",
        "review_hook_appearance",
        "review_prose_quality",
        "review_chapter_engine",
    ]
    OUTPUT_FORMAT_RULES = [
        "使用中文全角标点为主",
        "对话单独成段",
        "情绪外化句、短促动作句可单独成段",
        "避免一整页超长大段",
        "不要把原本故意保留的停顿句强行合并",
        "段落间只保留一个空行",
        "清理尾随空格和重复空白",
        "保持中文网文阅读节奏，不要格式化成论文",
        "单个自然段尽量控制在 30 ~ 120 中文字之间",
        "若超过 180 中文字，应尝试拆分",
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
            action="组装正文固定信息包",
            reason="正文写作所需的 selection、sanitization、time anchor 和章节上下文已经准备完成。",
            chapter_id=chapter_brief.chapter_id,
            context_keys=[
                "selection_summary_text",
                "time_anchor_text",
                "chapter_visible_context_text",
                "completed_chapter_memory_text",
                "step_1_story_foundation_text",
                "step_2_worldbuilding_text",
                "step_3_character_packets_text",
                "step_4_event_timeline_text",
                "step_5_character_milestones_text",
                "step_6_twists_text",
                "step_7_story_lines_text",
                "step_8_chapter_brief_text",
                "chapter_payload_text",
                "timeline_anchor_facts_text",
                "relevant_world_rules_text",
                "scene_character_context_text",
                "relationship_state_text",
                "style_card_text",
            ],
            context_bundle=self._context_bundle(context),
        )

        active_skills = self.skill_manager.initial_skills()
        self._emit_stage(
            stage="plan_content_blocks_start",
            action="规划 content blocks",
            reason="正文先拆成内容块，再逐块写作、逐块提交。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in active_skills],
        )
        planned_blocks = self._plan_content_blocks(
            chapter_brief=chapter_brief,
            context=context,
        )
        stage_log.append(
            {
                "stage": "plan_content_blocks",
                "skill_ids": [skill.skill_id for skill in active_skills],
                "block_count": len(planned_blocks),
                "blocks": [block.model_dump(mode="json") for block in planned_blocks],
            }
        )
        self._emit_stage(
            stage="plan_content_blocks_done",
            action="完成 content block 规划",
            reason="接下来按 block 顺序逐块写、逐块轻审校、逐块落库。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in active_skills],
            block_count=len(planned_blocks),
            planned_blocks=[block.model_dump(mode="json") for block in planned_blocks],
        )

        committed_blocks: list[ContentBlock] = []
        chapter_text = ""
        for block in planned_blocks:
            block_context = self._fetch_block_context(
                context=context,
                block=block,
                committed_blocks=committed_blocks,
            )
            self._emit_stage(
                stage=f"block_{block.block_index}_draft_start",
                action="生成内容块草稿",
                reason="当前 block 只处理一个明确写作目的，写完后立即进入轻审校。",
                chapter_id=chapter_brief.chapter_id,
                block_id=block.block_id,
                block_index=block.block_index,
                block_purpose=block.purpose,
            )
            draft_result = self.tool_registry.execute(
                "draft_block",
                {
                    **block_context,
                    "block_card_text": self._block_card_text(block),
                },
            )
            block_text = str(draft_result.get("block_text") or "").strip()
            quick_review = self.tool_registry.execute(
                "review_block_quick",
                {
                    "chapter_payload_text": context.chapter_payload_text,
                    "relevant_world_rules_text": context.relevant_world_rules_text,
                    "block_card_text": self._block_card_text(block),
                    "prior_chapter_text_tail": block_context["prior_chapter_text_tail"],
                    "block_text": block_text,
                },
            )
            if bool(quick_review.get("rewrite_needed")):
                self._emit_stage(
                    stage=f"block_{block.block_index}_revise_start",
                    action="修正文内容块",
                    reason="block quick review 标记需要修订，先局部修，再提交。",
                    chapter_id=chapter_brief.chapter_id,
                    block_id=block.block_id,
                    block_index=block.block_index,
                    tool_result=quick_review,
                )
                revise_result = self.tool_registry.execute(
                    "revise_block_if_needed",
                    {
                        **block_context,
                        "block_card_text": self._block_card_text(block),
                        "block_text": block_text,
                        "review_json": json.dumps(quick_review, ensure_ascii=False, indent=2),
                    },
                )
                block_text = str(revise_result.get("block_text") or block_text).strip()
            committed_block = block.model_copy(
                update={
                    "text": block_text,
                    "status": "committed",
                    "version": max(int(block.version), 1),
                }
            )
            committed_blocks.append(committed_block)
            chapter_text = self._merge_blocks_to_chapter(committed_blocks)
            stage_log.append(
                {
                    "stage": f"commit_block_{block.block_index}",
                    "block_id": committed_block.block_id,
                    "block_index": committed_block.block_index,
                    "purpose": committed_block.purpose,
                    "status": committed_block.status,
                    "version": committed_block.version,
                    "chapter_length": len(chapter_text),
                    "quick_review": quick_review,
                }
            )
            if on_block_committed is not None:
                on_block_committed(committed_block)
            self._emit_stage(
                stage=f"block_{block.block_index}_committed",
                action="内容块已提交",
                reason="该 block 已落库，可供前端实时追加展示。",
                chapter_id=chapter_brief.chapter_id,
                block_id=committed_block.block_id,
                block_index=committed_block.block_index,
                block_purpose=committed_block.purpose,
                chapter_length=len(chapter_text),
                committed_block=committed_block.model_dump(mode="json"),
                current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
            )

        self._emit_stage(
            stage="merge_blocks_to_chapter_done",
            action="合并已提交 content blocks",
            reason="所有 block 已完成，进入整章级 review / rewrite / polish。",
            chapter_id=chapter_brief.chapter_id,
            block_count=len(committed_blocks),
            chapter_length=len(chapter_text),
            current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
        )
        stage_log.append(
            {
                "stage": "merge_blocks_to_chapter",
                "block_count": len(committed_blocks),
                "chapter_length": len(chapter_text),
            }
        )

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
                )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_skills",
                action="确定当前轮次 skills",
                reason="根据上一轮 review 结果选择要加载的 skill 说明包。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                skill_ids=[skill.skill_id for skill in active_skills],
            )
            planned_tools = self._plan_review_tools(
                chapter_brief=chapter_brief,
                context=context,
                chapter_text=chapter_text,
                review_reports=review_reports,
                active_skills=active_skills,
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_plan",
                action="规划 review tool 调用顺序",
                reason="模型已根据当前 skills 和已有报告生成本轮 review 计划。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                skill_ids=[skill.skill_id for skill in active_skills],
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
            revision_plan = ReviewAggregator.aggregate(
                review_reports=review_reports,
                triggered_skills=[skill.skill_id for skill in active_skills],
            )
            dynamic_instruction = DynamicInstructionBuilder.build(
                review_reports=review_reports,
                revision_plan=revision_plan,
                active_skill_ids=[skill.skill_id for skill in active_skills],
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_aggregate",
                action="汇总 review 结果并生成 revision_plan",
                reason="ReviewAggregator 已合并各 tool 的问题、证据和硬约束。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                review_reports=review_reports,
                revision_plan=revision_plan.model_dump(mode="json"),
                dynamic_instruction=dynamic_instruction.model_dump(mode="json"),
            )
            final_judge = self.tool_registry.execute(
                "final_judge",
                {"review_reports": review_reports},
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_judge",
                action="执行 Final Judge",
                reason="检查是否达到放行门槛，或继续 rewrite 闭环。",
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
                    "revision_plan": revision_plan.model_dump(mode="json"),
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
                    action="本轮通过",
                    reason="Final Judge 已放行，进入 final polish。",
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
                    action="达到最大重写轮次",
                    reason="保留当前最佳版本，并标记 requires_human_review=true。",
                    chapter_id=chapter_brief.chapter_id,
                    final_judge=final_judge,
                )
                break

            self._emit_stage(
                stage=f"rewrite_iteration_{iteration}_start",
                action="按 revision_plan 重写正文",
                reason="本轮未过 judge，开始 rewrite_by_plan。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                revision_plan=revision_plan.model_dump(mode="json"),
                dynamic_instruction=dynamic_instruction.model_dump(mode="json"),
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
                    "revision_plan": revision_plan.model_dump(mode="json"),
                    "dynamic_instruction_text": json.dumps(dynamic_instruction.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    "loaded_skill_instructions_text": self.skill_manager.format_for_model(active_skills),
                },
            )
            chapter_text = str(rewrite_result.get("chapter_text") or "").strip()
            stage_log.append(
                {
                    "stage": f"rewrite_iteration_{iteration}",
                    "skill_ids": [skill.skill_id for skill in active_skills],
                    "chapter_length": len(chapter_text),
                    "previous_scene_tail": "",
                    "current_chapter_draft_tail": self._tail_text(chapter_text),
                }
            )
            self._emit_stage(
                stage=f"rewrite_iteration_{iteration}_done",
                action="完成正文重写",
                reason="rewrite_by_plan 已返回新稿，准备进入下一轮 review。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                skill_ids=[skill.skill_id for skill in active_skills],
                chapter_length=len(chapter_text),
                current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
            )

        finalize_skills = self.skill_manager.finalize_skills()
        self._emit_stage(
            stage="final_polish_start",
            action="执行 final polish",
            reason="正文已通过 judge 或保留最佳版本，开始做终稿润色。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in finalize_skills],
        )
        polished = self.tool_registry.execute(
            "final_polish",
            {
                "chapter_payload_text": context.chapter_payload_text,
                "style_card_text": context.style_card_text,
                "chapter_text": chapter_text,
            },
        )
        chapter_text = str(polished.get("chapter_text") or "").strip()
        stage_log.append(
            {
                "stage": "final_polish",
                "skill_ids": [skill.skill_id for skill in finalize_skills],
                "chapter_length": len(chapter_text),
            }
        )
        self._emit_stage(
            stage="final_polish_done",
            action="完成 final polish",
            reason="终稿润色完成，接着做只改格式不改事实的最终整理。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in finalize_skills],
            chapter_length=len(chapter_text),
            current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
        )
        self._emit_stage(
            stage="format_adjustment_start",
            action="执行 format adjustment",
            reason="统一段落、对话换行和空白，保持前端阅读舒适度。",
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
        stage_log.append(
            {
                "stage": "format_adjustment",
                "chapter_length": len(chapter_text),
                "format_issues": list(formatted.get("format_issues") or []),
            }
        )
        self._emit_stage(
            stage="format_adjustment_done",
            action="完成 format adjustment",
            reason="最终正文格式已整理完成，接下来生成 actual_chapter_summary。",
            chapter_id=chapter_brief.chapter_id,
            chapter_length=len(chapter_text),
            format_issues=list(formatted.get("format_issues") or []),
            current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
        )
        self._emit_stage(
            stage="summarize_actual_chapter_start",
            action="生成 actual_chapter_summary",
            reason="基于格式整理后的最终文本，整理本章真实发生、读者认知与锁住的真相。",
            chapter_id=chapter_brief.chapter_id,
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
            action="actual_chapter_summary 已生成",
            reason="正文 agent 闭环完成。",
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

    def _fetch_block_context(
        self,
        *,
        context: Any,
        block: ContentBlock,
        committed_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        prior_summary_lines = ["[Earlier committed blocks]"]
        if committed_blocks:
            for item in committed_blocks[-3:]:
                prior_summary_lines.extend(
                    [
                        "",
                        f"{item.block_id} / {item.purpose}",
                        f"- End state: {item.end_state}",
                        f"- Text tail: {self._tail_text(item.text, max_chars=220)}",
                    ]
                )
        else:
            prior_summary_lines.append("No committed blocks yet.")
        return {
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "chapter_payload_text": context.chapter_payload_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "prior_block_summary_text": "\n".join(prior_summary_lines).strip(),
            "prior_chapter_text_tail": self._tail_text(self._merge_blocks_to_chapter(committed_blocks), max_chars=900),
            "style_card_text": context.style_card_text,
        }

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
            "characters:",
        ]
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
        return "\n".join(lines).strip()

    @staticmethod
    def _merge_blocks_to_chapter(blocks: list[ContentBlock]) -> str:
        return "\n\n".join(str(block.text or "").strip() for block in blocks if str(block.text or "").strip()).strip()

    def _plan_review_tools(
        self,
        *,
        chapter_brief: ChapterBrief,
        context: Any,
        chapter_text: str,
        review_reports: dict[str, Any],
        active_skills: list[Any],
    ) -> list[str]:
        fallback = self.skill_manager.recommended_tools(active_skills)
        fallback = [tool for tool in fallback if tool in self.REVIEW_TOOLS]
        if not fallback:
            fallback = list(self.REVIEW_TOOLS)

        review_summary = json.dumps(review_reports, ensure_ascii=False, indent=2) if review_reports else "No previous review reports yet."
        prompt = self._render_prompt(
            "writer/plan_review_tools.txt",
            skills_text=self.skill_manager.format_for_model(active_skills),
            allowed_tools=", ".join(self.REVIEW_TOOLS),
            recommended_tools=", ".join(fallback),
            chapter_brief_json=chapter_brief.model_dump_json(indent=2),
            chapter_payload_text=context.chapter_payload_text,
            chapter_visible_context_text=context.chapter_visible_context_text,
            time_anchor_text=context.time_anchor_text,
            review_summary=review_summary,
            chapter_excerpt=self._tail_text(chapter_text, max_chars=1800),
        )
        try:
            payload = safe_json_generate(
                self.llm_client,
                self._messages(prompt),
                schema_name="tool_plan",
                schema_model=ToolPlanPayload,
            )
            planned = [
                str(item.get("tool_name") or "").strip()
                for item in payload.get("tool_calls", [])
                if str(item.get("tool_name") or "").strip() in self.REVIEW_TOOLS
            ]
        except Exception:
            planned = []

        ordered: list[str] = []
        for tool_name in [*planned, *fallback, *self.REVIEW_TOOLS]:
            if tool_name not in self.REVIEW_TOOLS or tool_name in ordered:
                continue
            ordered.append(tool_name)
        for required in reversed(
            (
                "review_instruction_compliance",
                "review_continuity",
                "review_time_consistency",
                "review_character_integrity",
                "review_humanity",
            )
        ):
            if required in ordered:
                ordered.remove(required)
            ordered.insert(0, required)
        return ordered[:10]

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
                action="调用 review tool",
                reason=f"开始执行 {tool_name}。",
                chapter_id=chapter_id,
                iteration=iteration,
                tool_name=tool_name,
            )
            reports[tool_name] = self.tool_registry.execute(tool_name, payload)
            self._emit_stage(
                stage=f"review_iteration_{iteration}_tool_done",
                action="review tool 返回结果",
                reason=f"{tool_name} 已完成。",
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
        }

    @staticmethod
    def _judge_score(result: dict[str, Any]) -> int:
        if not result:
            return -1000
        score = 0
        if bool(result.get("passed")):
            score += 1000
        score -= len(result.get("blocking_reasons", []) or []) * 10
        metrics = dict(result.get("metrics", {}) or {})
        score += int(metrics.get("prose_score") or 0)
        score += int(metrics.get("tension_score") or 0)
        score += int(metrics.get("human_warmth_score") or 0)
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
