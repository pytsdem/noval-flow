from __future__ import annotations

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
    StoryPremise,
    StoryLine,
    ToolPlanPayload,
    TwistDesign,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.chapter_context import ChapterContextAssembler
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.json_generation import safe_json_generate
from novel_flow.services.review_aggregator import ReviewAggregator
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.services.tool_registry import ToolRegistry


class WritingChapterAgent(BaseAgent):
    REVIEW_TOOLS = [
        "review_instruction_compliance",
        "review_reveal_leak",
        "review_plot_logic",
        "review_clue_origin",
        "review_continuity",
        "review_hook_appearance",
        "review_prose_quality",
        "review_chapter_engine",
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
        self._emit_stage(
            stage="context_ready",
            action="组装正文固定信息包",
            reason="chapter_brief、twist_designs、story_lines、character_cards、worldbuilding 已整理为正文上下文。",
            chapter_id=chapter_brief.chapter_id,
            context_keys=[
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
            context_bundle={
                "completed_chapter_memory_text": context.completed_chapter_memory_text,
                "step_1_story_foundation_text": context.step_1_story_foundation_text,
                "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
                "step_3_character_packets_text": context.step_3_character_packets_text,
                "step_4_event_timeline_text": context.step_4_event_timeline_text,
                "step_5_character_milestones_text": context.step_5_character_milestones_text,
                "step_6_twists_text": context.step_6_twists_text,
                "step_7_story_lines_text": context.step_7_story_lines_text,
                "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
                "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
                "relationship_state_text": context.relationship_state_text,
                "style_card_text": context.style_card_text,
            },
        )

        active_skills = self.skill_manager.initial_skills()
        self._emit_stage(
            stage="draft_v0_start",
            action="加载初始 skills 并写正文初稿",
            reason="正文阶段进入 agent 闭环，先生成 draft_v0。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in active_skills],
        )
        chapter_text = self._draft_v0(
            chapter_brief=chapter_brief,
            context=context,
            active_skills=active_skills,
        )
        stage_log.append(
            {
                "stage": "draft_v0",
                "skill_ids": [skill.skill_id for skill in active_skills],
                "chapter_length": len(chapter_text),
                "previous_scene_tail": "",
                "current_chapter_draft_tail": self._tail_text(chapter_text),
            }
        )
        self._emit_stage(
            stage="draft_v0_done",
            action="完成正文初稿",
            reason="draft_v0 已生成，准备进入 review tool 规划。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in active_skills],
            chapter_length=len(chapter_text),
            current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
        )

        final_judge: dict[str, Any] = {}
        review_reports: dict[str, Any] = {}

        for iteration in range(1, self.max_iterations + 1):
            active_skills = (
                self.skill_manager.discover(
                    chapter_brief=chapter_brief,
                    review_reports=review_reports,
                )
                if review_reports
                else active_skills
            )
            self._emit_stage(
                stage=f"review_iteration_{iteration}_skills",
                action="确定当前轮次 skills",
                reason="根据上一轮 review 结果选择要加载的说明包。",
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
                reason="模型已根据当前 skills 和已有报告生成下一轮 review 计划。",
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
            self._emit_stage(
                stage=f"review_iteration_{iteration}_aggregate",
                action="汇总 review 结果并生成 revision_plan",
                reason="ReviewAggregator 已合并各 tool 的问题与硬约束。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                review_reports=review_reports,
                revision_plan=revision_plan.model_dump(mode="json"),
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
                    "final_judge": final_judge,
                }
            )
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
                reasons = "; ".join(str(item) for item in final_judge.get("blocking_reasons", []) or [])
                raise ValueError(f"WritingChapterAgent failed final judge after {self.max_iterations} iterations: {reasons}")

            self._emit_stage(
                stage=f"rewrite_iteration_{iteration}_start",
                action="按 revision_plan 重写正文",
                reason="本轮未过 judge，开始 rewrite_by_plan。",
                chapter_id=chapter_brief.chapter_id,
                iteration=iteration,
                revision_plan=revision_plan.model_dump(mode="json"),
            )
            rewrite_result = self.tool_registry.execute(
                "rewrite_by_plan",
                {
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
                    "current_chapter_draft_tail": self._tail_text(chapter_text),
                    "previous_scene_tail": "",
                    "revision_plan": revision_plan.model_dump(mode="json"),
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
                reason="rewrite_by_plan 已返回新草稿，准备进入下一轮 review。",
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
            reason="正文已通过 judge，开始做终稿润色。",
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
            reason="终稿润色完成，开始生成 actual_chapter_summary。",
            chapter_id=chapter_brief.chapter_id,
            skill_ids=[skill.skill_id for skill in finalize_skills],
            chapter_length=len(chapter_text),
            current_chapter_draft_tail=self._tail_text(chapter_text, max_chars=500),
        )
        self._emit_stage(
            stage="summarize_actual_chapter_start",
            action="生成 actual_chapter_summary",
            reason="整理本章真实发生、读者认知与锁住的真相。",
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
            actual_chapter_summary=actual_summary,
            stage_log=stage_log,
            review_reports=review_reports,
            final_judge=final_judge,
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

    def _draft_v0(self, *, chapter_brief: ChapterBrief, context: Any, active_skills: list[Any]) -> str:
        prompt = self._render_prompt(
            "writer/write_chapter_agent_draft_v0.txt",
            skills_text=self.skill_manager.format_for_model(active_skills),
            completed_chapter_memory_text=context.completed_chapter_memory_text,
            step_1_story_foundation_text=context.step_1_story_foundation_text,
            step_2_worldbuilding_text=context.step_2_worldbuilding_text,
            step_3_character_packets_text=context.step_3_character_packets_text,
            step_4_event_timeline_text=context.step_4_event_timeline_text,
            step_5_character_milestones_text=context.step_5_character_milestones_text,
            step_6_twists_text=context.step_6_twists_text,
            step_7_story_lines_text=context.step_7_story_lines_text,
            step_8_chapter_brief_text=context.step_8_chapter_brief_text,
            chapter_payload_text=context.chapter_payload_text,
            timeline_anchor_facts_text=context.timeline_anchor_facts_text,
            relevant_world_rules_text=context.relevant_world_rules_text,
            scene_character_context_text=context.scene_character_context_text,
            relationship_state_text=context.relationship_state_text,
            style_card_text=context.style_card_text,
        )
        return self.llm_client.generate(
            messages=self._messages(prompt),
            temperature=0.65,
        ).strip()

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
        for required in ("review_instruction_compliance", "review_continuity"):
            if required not in ordered:
                ordered.insert(0, required)
        return ordered[:8]

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
