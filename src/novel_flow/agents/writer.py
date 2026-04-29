from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.agents.writing_chapter_agent import WritingChapterAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.llm.executor import PromptLLMExecutor
from novel_flow.models.schemas import (
    ActualChapterSummary,
    AgentResult,
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterContract,
    ChapterBeat,
    CharacterMindset,
    CriticReport,
    IssueCard,
    IssueLocation,
    IssueSeverity,
    PatchInstruction,
    PatchOperation,
    Scene,
    SceneCard,
    ScenePlan,
    ScenePlanPayload,
    StoryLine,
    TextBlock,
    TwistDesign,
    Volume,
    WriterContext,
    WriterMode,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.context_coverage import WriterContextCoverageValidator
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.novel_context import NovelContextFormatter, NovelContextSelectorService
from novel_flow.services.patcher import PatchExecutor
from novel_flow.utils.json_generation import safe_json_generate


UPGRADE_ERROR = "当前项目数据结构已升级，请重新运行 step6、step7、step8 后再生成正文。"


class WriterAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClient,
        patch_executor: PatchExecutor,
        prompt_library: PromptLibrary | None = None,
    ) -> None:
        super().__init__(name="WriterAgent")
        self.llm_client = llm_client
        self.patch_executor = patch_executor
        self.prompt_library = prompt_library or PromptLibrary()
        self.llm_executor = PromptLLMExecutor(llm_client=self.llm_client, prompt_library=self.prompt_library)
        self.context_sanitizer = ContextSanitizationTask(
            llm_client=self.llm_client,
            prompt_library=self.prompt_library,
        )

    def create_book(self, blueprint: BookBlueprint, source_query: str, style_request: str = "") -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Initialize book shell: {blueprint.premise.title}")
        now = datetime.now(timezone.utc)
        volume_title = blueprint.volume_titles[0] if blueprint.volume_titles else "Volume 1"
        effective_style = style_request or blueprint.premise.target_style
        return BookDocument(
            id=f"book_{uuid4().hex[:10]}",
            title=blueprint.premise.title,
            premise=blueprint.premise,
            characters=blueprint.characters,
            volumes=[Volume(id="vol_001", title=volume_title, summary=blueprint.premise.central_conflict, chapters=[])],
            metadata={
                "target_words": self._target_words_for_style(effective_style),
                "style_request": style_request,
                "query": source_query,
                "user_topic": "",
                "assistant_persona_prompt": "",
                "total_word_target": "",
                "chapter_count_target": "",
                "chapter_word_target": "",
                "pace_notes": "",
                "blueprint_id": blueprint.blueprint_id,
                "next_chapter_index": 0,
                "completed_chapter_ids": [],
                "actual_chapter_summaries": [],
                "latest_critic_report": None,
                "critic_reports": {},
                "writer_context_debug": {},
                "story_blueprint": {},
            },
            created_at=now,
            updated_at=now,
        )

    def write_next_chapter(
        self,
        book: BookDocument,
        reference_pack: str = "No extra reference material.",
        *,
        runtime_store: Any | None = None,
        run_id: str | None = None,
    ) -> tuple[BookDocument, Chapter]:
        chapter_briefs = self._chapter_briefs_from_book(book)
        next_index = int(book.metadata.get("next_chapter_index", 0))
        if next_index >= len(chapter_briefs):
            raise ValueError("没有可继续生成的章节。")
        chapter_brief = chapter_briefs[next_index]
        writer_context = self._writer_context_for_chapter(
            book,
            chapter_brief.chapter_id,
            strict_for_chapter_loop=True,
            reference_pack=reference_pack,
        )
        actual_summaries = self._actual_summaries_from_book(book)
        def _persist_committed_block(block: ChapterBeat) -> None:
            if runtime_store is None or not run_id:
                return
            now_text = datetime.now(timezone.utc).isoformat()
            runtime_store.save_chapter_block(
                run_id=run_id,
                book_id=book.id,
                chapter_title=chapter_brief.title,
                block=block,
                created_at=now_text,
                updated_at=now_text,
            )

        def _persist_chapter_preview(preview_payload: dict[str, Any]) -> None:
            if runtime_store is None or not run_id:
                return
            runtime_store.save_run_output(
                run_id=run_id,
                agent="WritingChapterAgent",
                output_type="chapter_live_preview",
                title="Chapter live preview",
                payload=preview_payload,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        chapter_agent = WritingChapterAgent(
            llm_client=self.llm_client,
            prompt_library=self.prompt_library,
        )
        execution = chapter_agent.write_chapter(
            chapter_brief=chapter_brief,
            premise=book.premise,
            twist_designs=self._twists_from_book(book),
            story_lines=self._story_lines_from_book(book),
            character_cards=book.characters,
            character_milestones=self._character_milestones_from_book(book),
            prior_character_mindsets=self._latest_character_mindsets_for_chapter(
                book=book,
                focus_names=list(chapter_brief.character_focus or []),
            ),
            worldbuilding=dict(book.metadata.get("story_blueprint", {}) or {}),
            actual_chapter_summaries=actual_summaries,
            prebuilt_context=writer_context,
            on_block_committed=_persist_committed_block,
            on_chapter_preview_updated=_persist_chapter_preview,
        )
        scene = (
            self._chapter_scene_from_chapter_beats(chapter_id=chapter_brief.chapter_id, beats=execution.content_blocks)
            if any(str(item.text or "").strip() for item in execution.content_blocks)
            else self._chapter_scene_from_text(chapter_id=chapter_brief.chapter_id, text=execution.chapter_text)
        )
        chapter = Chapter(
            id=chapter_brief.chapter_id,
            title=chapter_brief.title,
            summary=chapter_brief.summary,
            scenes=[scene],
            content_blocks=execution.content_blocks,
            character_mindsets=execution.character_mindsets,
            final_text=execution.chapter_text,
            final_version=1,
            is_finalized=True,
        )

        updated_book = deepcopy(book)
        updated_book.volumes[0].chapters.append(chapter)
        completed_ids = list(updated_book.metadata.get("completed_chapter_ids", []))
        completed_ids.append(chapter_brief.chapter_id)
        updated_book.metadata["completed_chapter_ids"] = completed_ids
        updated_book.metadata["next_chapter_index"] = next_index + 1
        updated_book.metadata["last_written_chapter_id"] = chapter_brief.chapter_id
        summary_items = [item.model_dump(mode="json") for item in actual_summaries]
        summary_items.append(execution.actual_chapter_summary.model_dump(mode="json"))
        updated_book.metadata["actual_chapter_summaries"] = summary_items
        updated_book.metadata.setdefault("writer_context_debug", {})[chapter_brief.chapter_id] = {
            "completed_chapter_memory_text": writer_context.completed_chapter_memory_text,
            "step_1_story_foundation_text": writer_context.step_1_story_foundation_text,
            "step_2_worldbuilding_text": writer_context.step_2_worldbuilding_text,
            "step_3_character_packets_text": writer_context.step_3_character_packets_text,
            "step_4_event_timeline_text": writer_context.step_4_event_timeline_text,
            "step_5_character_milestones_text": writer_context.step_5_character_milestones_text,
            "step_6_twists_text": writer_context.step_6_twists_text,
            "step_7_story_lines_text": writer_context.step_7_story_lines_text,
            "step_8_chapter_brief_text": writer_context.step_8_chapter_brief_text,
            "chapter_payload_text": writer_context.chapter_payload_text,
            "timeline_anchor_facts_text": writer_context.timeline_anchor_facts_text,
            "relevant_world_rules_text": writer_context.relevant_world_rules_text,
            "scene_character_context_text": writer_context.scene_character_context_text,
            "relationship_state_text": writer_context.relationship_state_text,
            "style_card_text": writer_context.style_card_text,
            "chapter_character_mindsets_text": getattr(writer_context, "chapter_character_mindsets_text", ""),
            "assistant_persona_prompt": getattr(writer_context, "assistant_persona_prompt", ""),
            "writing_requirements_json": getattr(writer_context, "writing_requirements_json", "{}"),
            "previous_chapter_full_text": getattr(writer_context, "previous_chapter_full_text", ""),
            "reference_pack": getattr(writer_context, "reference_pack", ""),
        }
        critic_report = self._aggregate_loop_critic_report(
            book_id=book.id,
            chapter_id=chapter_brief.chapter_id,
            review_reports=execution.review_reports,
        )
        updated_book.metadata["latest_critic_report"] = critic_report.model_dump(mode="json")
        updated_book.metadata.setdefault("critic_reports", {})[chapter_brief.chapter_id] = {
            "chapter_loop": execution.review_reports,
            "final_judge": execution.final_judge,
            "aggregate": critic_report.model_dump(mode="json"),
        }
        updated_book.metadata.setdefault("writing_chapter_runs", {})[chapter_brief.chapter_id] = {
            "content_blocks": [item.model_dump(mode="json") for item in execution.content_blocks],
            "character_mindsets": [item.model_dump(mode="json") for item in execution.character_mindsets],
            "final_text": execution.chapter_text,
            "final_version": chapter.final_version,
            "is_finalized": chapter.is_finalized,
            "actual_chapter_summary": execution.actual_chapter_summary.model_dump(mode="json"),
            "stage_log": execution.stage_log,
            "review_reports": execution.review_reports,
            "final_judge": execution.final_judge,
        }
        updated_book.updated_at = datetime.now(timezone.utc)
        return updated_book, chapter

    def rewrite_unit(
        self,
        book: BookDocument,
        block_id: str,
        guidance: str,
        reference_pack: str = "No extra reference material.",
    ) -> BookDocument:
        del reference_pack
        block, chapter, _ = self._locate_block(book, block_id)
        writer_context = self._writer_context_for_chapter(book, chapter.id, sanitize_for_prose=False)
        replacement = self._rewrite_scene(
            original_text=block.text,
            rewrite_guidance=guidance,
            writer_context=writer_context,
            scene_card=self._fallback_scene_card(block_id),
        )
        patched_book, _ = self.patch_executor.apply(
            book,
            PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation.REPLACE,
                reason=guidance,
                content=replacement,
            ),
        )
        return patched_book

    def rewrite_chapter(
        self,
        book: BookDocument,
        chapter_id: str,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        del reference_pack
        volume_index, chapter_index, chapter = self._locate_chapter(book, chapter_id)
        writer_context = self._writer_context_for_chapter(book, chapter_id, sanitize_for_prose=False)
        chapter_text = self._chapter_full_text(chapter)
        rewritten = self._generate_text(
            self._render_prompt(
                "writer/chapter_final_polish.txt",
                chapter_payload_text=writer_context.chapter_payload_text + f"\n\n补充重写指令：{guidance}",
                style_card_text=writer_context.style_card_text,
                chapter_text=chapter_text,
            ),
            system_path="writer/system.txt",
            temperature=0.75,
        )
        updated_book = deepcopy(book)
        updated_book.volumes[volume_index].chapters[chapter_index] = Chapter(
            id=chapter.id,
            title=chapter.title,
            summary=chapter.summary,
            scenes=chapter.scenes,
            content_blocks=chapter.content_blocks,
            character_mindsets=chapter.character_mindsets,
            final_text=rewritten,
            final_version=max(int(chapter.final_version), 0) + 1,
            is_finalized=True,
        )
        updated_book.updated_at = datetime.now(timezone.utc)
        return updated_book

    def patch_block(self, book: BookDocument, instruction: PatchInstruction) -> tuple[BookDocument, dict[str, Any]]:
        patched_book, version = self.patch_executor.apply(book, instruction)
        return patched_book, {"patch_version": version.model_dump(mode="json")}

    def expand(
        self,
        book: BookDocument,
        block_id: str,
        expansion_goal: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        del reference_pack
        block, chapter, _ = self._locate_block(book, block_id)
        writer_context = self._writer_context_for_chapter(book, chapter.id, sanitize_for_prose=False)
        replacement = self._generate_text(
            self._render_prompt(
                "writer/expand.txt",
                text=block.text,
                expansion_goal=expansion_goal,
                chapter_payload_text=writer_context.chapter_payload_text,
            ),
            system_path="writer/system.txt",
            temperature=0.72,
        )
        patched_book, _ = self.patch_executor.apply(
            book,
            PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation.REPLACE,
                reason=expansion_goal,
                content=replacement,
            ),
        )
        return patched_book

    def run(self, **kwargs: Any) -> AgentResult:
        mode = WriterMode(kwargs["mode"])
        if mode == WriterMode.CREATE:
            book = self.create_book(
                blueprint=kwargs["blueprint"],
                source_query=kwargs.get("source_query", ""),
                style_request=str(kwargs.get("style_request", "")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Initialized book shell.", payload={"book": book.model_dump(mode="json")})
        if mode == WriterMode.WRITE_NEXT_CHAPTER:
            updated_book, chapter = self.write_next_chapter(book=kwargs["book"], reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")))
            return AgentResult(agent_name=self.name, success=True, message=f"Wrote chapter {chapter.id}.", payload={"book": updated_book.model_dump(mode="json"), "chapter": chapter.model_dump(mode="json")})
        if mode == WriterMode.REWRITE_UNIT:
            rewritten_book = self.rewrite_unit(book=kwargs["book"], block_id=kwargs["block_id"], guidance=kwargs["guidance"], reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")))
            return AgentResult(agent_name=self.name, success=True, message="Rewrote target block.", payload={"book": rewritten_book.model_dump(mode="json")})
        if mode == WriterMode.PATCH_BLOCK:
            patched_book, extra = self.patch_block(book=kwargs["book"], instruction=kwargs["instruction"])
            return AgentResult(agent_name=self.name, success=True, message="Patched target block.", payload={"book": patched_book.model_dump(mode="json"), **extra})
        if mode == WriterMode.EXPAND:
            expanded_book = self.expand(book=kwargs["book"], block_id=kwargs["block_id"], expansion_goal=kwargs["expansion_goal"], reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")))
            return AgentResult(agent_name=self.name, success=True, message="Expanded target block.", payload={"book": expanded_book.model_dump(mode="json")})
        raise ValueError(f"Unsupported writer mode: {mode}")

    def _writer_context_for_chapter(
        self,
        book: BookDocument,
        chapter_id: str,
        *,
        strict_for_chapter_loop: bool = False,
        sanitize_for_prose: bool = True,
        reference_pack: str = "暂无额外参考资料。",
    ) -> WriterContext:
        chapter_brief = next((item for item in self._chapter_briefs_from_book(book) if item.chapter_id == chapter_id), None)
        if chapter_brief is None:
            raise ValueError(UPGRADE_ERROR)
        if strict_for_chapter_loop:
            coverage_issues = WriterContextCoverageValidator.validate(
                chapter_brief=chapter_brief,
                premise=book.premise,
                story_blueprint=dict(book.metadata.get("story_blueprint", {}) or {}),
                character_cards=book.characters,
                character_milestones=self._character_milestones_from_book(book),
            )
            if coverage_issues:
                detail = "；".join(coverage_issues)
                raise ValueError(f"{UPGRADE_ERROR} 缺失信息：{detail}")
        snapshot = NovelContextSelectorService.create_snapshot(
            chapter_brief=chapter_brief,
            premise=book.premise,
            twist_designs=self._twists_from_book(book),
            story_lines=self._story_lines_from_book(book),
            worldbuilding=dict(book.metadata.get("story_blueprint", {}) or {}),
            character_cards=book.characters,
            character_milestones=self._character_milestones_from_book(book),
            actual_summaries=self._actual_summaries_from_book(book),
            current_chapter_id=chapter_id,
        )
        selection = NovelContextSelectorService.select(
            snapshot=snapshot,
            strategy="writer_context",
        )
        context = NovelContextFormatter.format_writer_context(
            selection,
            context_sanitizer=self.context_sanitizer if sanitize_for_prose else None,
        )
        return replace(
            context,
            assistant_persona_prompt=str(book.metadata.get("assistant_persona_prompt") or "").strip(),
            writing_requirements_json=json.dumps(self._writing_requirements_payload(book), ensure_ascii=False, indent=2),
            completed_chapter_summary_bundle=context.completed_chapter_memory_text,
            previous_chapter_full_text=self._previous_chapter_full_text(book=book, chapter_id=chapter_id),
            reference_pack=str(reference_pack or "No extra reference material."),
        )

    @staticmethod
    def _writing_requirements_payload(book: BookDocument) -> dict[str, Any]:
        metadata = dict(book.metadata or {})
        return {
            "query": str(metadata.get("query") or "").strip(),
            "user_topic": str(metadata.get("user_topic") or "").strip(),
            "style_request": str(metadata.get("style_request") or "").strip(),
            "assistant_persona_prompt": str(metadata.get("assistant_persona_prompt") or "").strip(),
            "total_word_target": str(metadata.get("total_word_target") or "").strip(),
            "chapter_count_target": str(metadata.get("chapter_count_target") or "").strip(),
            "chapter_word_target": str(metadata.get("chapter_word_target") or "").strip(),
            "pace_notes": str(metadata.get("pace_notes") or "").strip(),
            "target_words": metadata.get("target_words"),
        }

    def _previous_chapter_full_text(self, *, book: BookDocument, chapter_id: str) -> str:
        chapter_briefs = self._chapter_briefs_from_book(book)
        target_index = next((index for index, item in enumerate(chapter_briefs) if item.chapter_id == chapter_id), -1)
        if target_index <= 0:
            return ""
        previous_chapter_id = chapter_briefs[target_index - 1].chapter_id
        for volume in book.volumes:
            for chapter in volume.chapters:
                if chapter.id == previous_chapter_id:
                    return self._chapter_full_text(chapter)
        return ""

    def _make_scene_plan(self, *, writer_context: WriterContext, chapter_brief: ChapterContract) -> ScenePlan:
        payload = safe_json_generate(
            self.llm_client,
            self._messages(
                "writer/system.txt",
                self._render_prompt(
                    "writer/make_scene_plan.txt",
                    completed_chapter_memory_text=writer_context.completed_chapter_memory_text,
                    chapter_payload_text=writer_context.chapter_payload_text,
                    relevant_world_rules_text=writer_context.relevant_world_rules_text,
                    style_card_text=writer_context.style_card_text,
                    chapter_brief_json=chapter_brief.model_dump_json(indent=2),
                ),
            ),
            schema_name="scene_plan",
            schema_model=ScenePlanPayload,
        )
        return ScenePlan.model_validate(payload)

    def _write_scene_draft(
        self,
        *,
        writer_context: WriterContext,
        scene_card: SceneCard,
        scene_character_context_text: str,
        relationship_state_text: str,
        previous_scene_tail: str,
        current_chapter_draft_tail: str,
    ) -> str:
        return self._generate_text(
            self._render_prompt(
                "writer/write_scene_draft.txt",
                completed_chapter_memory_text=writer_context.completed_chapter_memory_text,
                chapter_payload_text=writer_context.chapter_payload_text,
                relevant_world_rules_text=writer_context.relevant_world_rules_text,
                scene_character_context_text=scene_character_context_text,
                relationship_state_text=relationship_state_text,
                scene_card_text=self._scene_card_text(scene_card),
                previous_scene_tail=previous_scene_tail or "无",
                current_chapter_draft_tail=current_chapter_draft_tail or "无",
                style_card_text=writer_context.style_card_text,
            ),
            system_path="writer/system.txt",
            temperature=0.72,
        )

    def _polish_scene(self, *, draft_text: str, writer_context: WriterContext, scene_card: SceneCard) -> str:
        return self._generate_text(
            self._render_prompt(
                "writer/polish_scene.txt",
                chapter_payload_text=writer_context.chapter_payload_text,
                scene_card_text=self._scene_card_text(scene_card),
                style_card_text=writer_context.style_card_text,
                draft_text=draft_text,
            ),
            system_path="writer/system.txt",
            temperature=0.82,
        )

    def _chapter_final_polish(self, *, chapter_text: str, writer_context: WriterContext) -> str:
        return self._generate_text(
            self._render_prompt(
                "writer/chapter_final_polish.txt",
                chapter_payload_text=writer_context.chapter_payload_text,
                style_card_text=writer_context.style_card_text,
                chapter_text=chapter_text,
                target_length="No numeric chapter target. Final polish should not expand the chapter.",
                loaded_skill_instructions_text="",
            ),
            system_path="writer/system.txt",
            temperature=0.8,
        )

    def _rewrite_scene(self, *, original_text: str, rewrite_guidance: str, writer_context: WriterContext, scene_card: SceneCard) -> str:
        return self._generate_text(
            self._render_prompt(
                "writer/rewrite_scene.txt",
                original_text=original_text,
                rewrite_guidance=rewrite_guidance,
                chapter_payload_text=writer_context.chapter_payload_text,
                scene_card_text=self._scene_card_text(scene_card),
                style_card_text=writer_context.style_card_text,
            ),
            system_path="writer/system.txt",
            temperature=0.74,
        )

    def _summarize_actual_chapter(self, *, chapter_text: str, chapter_brief: ChapterContract, writer_context: WriterContext) -> ActualChapterSummary:
        payload = safe_json_generate(
            self.llm_client,
            self._messages(
                "writer/system.txt",
                self._render_prompt(
                    "writer/summarize_actual_chapter.txt",
                    chapter_text=chapter_text,
                    chapter_brief_json=chapter_brief.model_dump_json(indent=2),
                    chapter_payload_text=writer_context.chapter_payload_text,
                    active_twists_json=json.dumps([item.model_dump(mode="json") for item in writer_context.active_twists], ensure_ascii=False, indent=2),
                    story_lines_json=json.dumps([item.model_dump(mode="json") for item in writer_context.active_story_lines], ensure_ascii=False, indent=2),
                ),
            ),
            schema_name="actual_chapter_summary",
            schema_model=ActualChapterSummary,
        )
        return ActualChapterSummary.model_validate(payload)

    def _run_scene_critics(self, *, text: str, writer_context: WriterContext, chapter_brief: ChapterContract, scene_card: SceneCard) -> list[dict[str, Any]]:
        common = {
            "chapter_payload_text": writer_context.chapter_payload_text,
            "scene_or_chapter_text": text,
            "scene_card_text": self._scene_card_text(scene_card),
        }
        return [
            self._run_critic_prompt(
                "critic/check_reveal_leak.txt",
                active_twists_json=json.dumps([item.model_dump(mode="json") for item in writer_context.active_twists], ensure_ascii=False, indent=2),
                **common,
            ),
            self._run_critic_prompt(
                "critic/check_plot_logic.txt",
                chapter_payload_text=writer_context.chapter_payload_text,
                relevant_world_rules_text=writer_context.relevant_world_rules_text,
                scene_or_chapter_text=text,
            ),
            self._run_critic_prompt("critic/check_clue_origin.txt", **common),
            self._run_critic_prompt("critic/check_prose_quality.txt", **common),
        ]

    def _check_chapter_engine(self, *, chapter_text: str, writer_context: WriterContext, chapter_brief: ChapterContract) -> dict[str, Any]:
        return self._run_critic_prompt(
            "critic/check_chapter_engine.txt",
            chapter_payload_text=writer_context.chapter_payload_text,
            chapter_brief_json=chapter_brief.model_dump_json(indent=2),
            scene_or_chapter_text=chapter_text,
        )

    def _run_critic_prompt(self, relative_path: str, **kwargs: Any) -> dict[str, Any]:
        return safe_json_generate(
            self.llm_client,
            self._messages("critic/system.txt", self._render_prompt(relative_path, **kwargs)),
            schema_name=relative_path,
        )

    def _aggregate_critic_report(
        self,
        *,
        book_id: str,
        chapter_id: str,
        scene_reports: list[dict[str, Any]],
        engine_report: dict[str, Any],
    ) -> CriticReport:
        issues: list[IssueCard] = []
        for scene_report in scene_reports:
            scene_id = str(scene_report.get("scene_id") or "")
            for report in scene_report.get("reports", []):
                level = str(report.get("level") or "medium").lower()
                if level not in {"critical", "high", "medium", "low"}:
                    level = "medium"
                for issue in report.get("issues", []) or []:
                    issues.append(
                        IssueCard(
                            issue_id=f"issue_{uuid4().hex[:10]}",
                            severity=IssueSeverity(level),
                            title=f"Scene critic: {scene_id or 'scene'}",
                            problem_type="scene_critic",
                            location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id=scene_id, block_id=""),
                            evidence=str(issue),
                            impact=str(issue),
                            recommendation=str(report.get("rewrite_guidance") or "需要按 critic 意见重写。"),
                            acceptance_criteria=[],
                        )
                    )
        engine_level = str(engine_report.get("level") or "medium").lower()
        if engine_level in {"critical", "high", "medium", "low"}:
            for issue in engine_report.get("issues", []) or []:
                issues.append(
                    IssueCard(
                        issue_id=f"issue_{uuid4().hex[:10]}",
                        severity=IssueSeverity(engine_level),
                        title="Chapter engine",
                        problem_type="chapter_engine",
                        location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id="", block_id=""),
                        evidence=str(issue),
                        impact=str(issue),
                        recommendation=str(engine_report.get("rewrite_guidance") or "需要强化章节发动机。"),
                        acceptance_criteria=[],
                    )
                )
        summary = f"共记录 {len(issues)} 条章节 critic 问题。" if issues else "本章 critic 未发现显著问题。"
        return CriticReport(report_id=f"critic_{uuid4().hex[:10]}", summary=summary, issues=issues)

    def _aggregate_loop_critic_report(
        self,
        *,
        book_id: str,
        chapter_id: str,
        review_reports: dict[str, Any],
    ) -> CriticReport:
        issues: list[IssueCard] = []
        for tool_name, report in review_reports.items():
            if tool_name == "review_prose_quality":
                prose_score = int(report.get("prose_score") or 0)
                tension_score = int(report.get("tension_score") or 0)
                exposition_score = int(report.get("exposition_score") or 10)
                if prose_score >= 7 and tension_score >= 7 and exposition_score <= 4:
                    continue
                evidence = (
                    f"prose={prose_score}, tension={tension_score}, exposition={exposition_score}, "
                    f"rewrite_needed={bool(report.get('rewrite_needed'))}"
                )
                issues.append(
                    IssueCard(
                        issue_id=f"issue_{uuid4().hex[:10]}",
                        severity=IssueSeverity.HIGH if prose_score < 7 or tension_score < 7 or exposition_score > 4 else IssueSeverity.MEDIUM,
                        title="Chapter prose quality",
                        problem_type="prose_quality",
                        location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id="", block_id=""),
                        evidence=evidence,
                        impact=evidence,
                        recommendation=str(report.get("rewrite_guidance") or "Raise prose and tension while reducing exposition."),
                        acceptance_criteria=[],
                    )
                )
                continue
            if tool_name in {"review_structure_and_continuity", "review_prose_and_humanity"}:
                for issue in report.get("issues", []) or []:
                    severity = str(issue.get("severity") or "medium").lower()
                    if severity not in {"low", "medium", "high", "critical"}:
                        severity = "medium"
                    issues.append(
                        IssueCard(
                            issue_id=f"issue_{uuid4().hex[:10]}",
                            severity=IssueSeverity(severity),
                            title=tool_name,
                            problem_type=str(issue.get("problem_type") or tool_name),
                            location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id="", block_id=""),
                            evidence=str(issue.get("reason") or ""),
                            impact=str(issue.get("reason") or ""),
                            recommendation=str(issue.get("patch_hint") or report.get("summary") or "按 patch review 结果修复目标 block。"),
                            acceptance_criteria=[],
                        )
                    )
                continue
            if tool_name == "judge_patched_chapter":
                for issue in [*(report.get("remaining_issues", []) or []), *(report.get("newly_introduced_issues", []) or [])]:
                    issues.append(
                        IssueCard(
                            issue_id=f"issue_{uuid4().hex[:10]}",
                            severity=IssueSeverity.MEDIUM,
                            title="judge_patched_chapter",
                            problem_type=str(issue.get("problem_type") or "patch_issue"),
                            location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id="", block_id=""),
                            evidence=str(issue.get("reason") or ""),
                            impact=str(issue.get("reason") or ""),
                            recommendation=str(report.get("recommendation") or "继续补丁或切到 deep 模式。"),
                            acceptance_criteria=[],
                        )
                    )
                continue

            level = str(report.get("level") or "medium").lower()
            if level not in {"low", "medium", "high", "critical"}:
                level = "medium"
            for issue in report.get("issues", []) or []:
                issues.append(
                    IssueCard(
                        issue_id=f"issue_{uuid4().hex[:10]}",
                        severity=IssueSeverity(level),
                        title=tool_name,
                        problem_type=tool_name,
                        location=IssueLocation(book_id=book_id, volume_id="vol_001", chapter_id=chapter_id, scene_id="", block_id=""),
                        evidence=str(issue),
                        impact=str(issue),
                        recommendation=str(report.get("rewrite_guidance") or "Revise according to review tool feedback."),
                        acceptance_criteria=[],
                    )
                )
        summary = f"共记录 {len(issues)} 条正文闭环问题。" if issues else "正文闭环审稿通过。"
        return CriticReport(report_id=f"critic_{uuid4().hex[:10]}", summary=summary, issues=issues)

    @staticmethod
    def _has_critical_issue(reports: list[dict[str, Any]]) -> bool:
        for report in reports:
            if str(report.get("level") or "").lower() in {"critical", "high"}:
                return True
            if report.get("rewrite_needed") and int(report.get("prose_score") or 0) < 8:
                return True
        return False

    @staticmethod
    def _engine_requires_rewrite(report: dict[str, Any]) -> bool:
        return str(report.get("level") or "").lower() in {"critical", "high"}

    @staticmethod
    def _merge_rewrite_guidance(reports: list[dict[str, Any]]) -> str:
        guidance = [str(report.get("rewrite_guidance") or "").strip() for report in reports if str(report.get("rewrite_guidance") or "").strip()]
        return "\n".join(guidance) if guidance else "删去泄密和越权，补足合法来源与关系张力。"

    @staticmethod
    def _join_issues(report: dict[str, Any]) -> str:
        return "\n".join(str(item).strip() for item in report.get("issues", []) or [] if str(item).strip())

    def _chapter_briefs_from_book(self, book: BookDocument) -> list[ChapterContract]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if "chapter_briefs" not in story_blueprint:
            raise ValueError(UPGRADE_ERROR)
        try:
            return [ChapterContract.model_validate(item) for item in story_blueprint.get("chapter_briefs", [])]
        except Exception as exc:
            raise ValueError(UPGRADE_ERROR) from exc

    def _twists_from_book(self, book: BookDocument) -> list[TwistDesign]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if "twist_designs" not in story_blueprint:
            raise ValueError(UPGRADE_ERROR)
        try:
            return [TwistDesign.model_validate(item) for item in story_blueprint.get("twist_designs", [])]
        except Exception as exc:
            raise ValueError(UPGRADE_ERROR) from exc

    def _story_lines_from_book(self, book: BookDocument) -> list[StoryLine]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if "story_lines" not in story_blueprint:
            raise ValueError(UPGRADE_ERROR)
        try:
            return [StoryLine.model_validate(item) for item in story_blueprint.get("story_lines", [])]
        except Exception as exc:
            raise ValueError(UPGRADE_ERROR) from exc

    @staticmethod
    def _character_milestones_from_book(book: BookDocument) -> list[dict[str, Any]]:
        items = book.metadata.get("character_milestones", []) or []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _latest_character_mindsets_for_chapter(
        *,
        book: BookDocument,
        focus_names: list[str],
    ) -> list[CharacterMindset]:
        target_names = list(dict.fromkeys(str(name or "").strip() for name in focus_names if str(name or "").strip()))[:2]
        if not target_names:
            return []

        found: dict[str, CharacterMindset] = {}
        for volume in reversed(book.volumes):
            for chapter in reversed(volume.chapters):
                for item in reversed(list(getattr(chapter, "character_mindsets", []) or [])):
                    try:
                        mindset = CharacterMindset.model_validate(item)
                    except Exception:
                        continue
                    name = str(mindset.character_name or "").strip()
                    if name in target_names and name not in found:
                        found[name] = mindset
                if len(found) >= len(target_names):
                    return [found[name] for name in target_names if name in found]
        return [found[name] for name in target_names if name in found]

    @staticmethod
    def _actual_summaries_from_book(book: BookDocument) -> list[ActualChapterSummary]:
        items = book.metadata.get("actual_chapter_summaries", []) or []
        results: list[ActualChapterSummary] = []
        for item in items:
            try:
                results.append(ActualChapterSummary.model_validate(item))
            except Exception:
                continue
        return results

    def _render_prompt(self, relative_path: str, **kwargs: Any) -> str:
        return self.prompt_library.render(relative_path, **kwargs)

    def _messages(self, system_path: str, prompt: str) -> list[LLMMessage]:
        return self.llm_executor.build_prompt_messages(system_path=system_path, prompt=prompt)

    def _generate_text(self, prompt: str, *, system_path: str, temperature: float) -> str:
        return self.llm_executor.generate_prompt_text(
            system_path=system_path,
            prompt=prompt,
            temperature=temperature,
        )

    @staticmethod
    def _scene_card_text(scene_card: SceneCard) -> str:
        lines = [
            "【本场场景卡】",
            "",
            f"scene_id：{scene_card.scene_id}",
            f"purpose：{scene_card.purpose}",
            f"pov：{scene_card.pov}",
            f"location：{scene_card.location}",
            f"visible_goal：{scene_card.visible_goal}",
            f"obstacle：{scene_card.obstacle}",
            "must_show：",
        ]
        for item in scene_card.must_show:
            lines.append(f"- {item}")
        lines.append("must_not_show：")
        for item in scene_card.must_not_show:
            lines.append(f"- {item}")
        lines.extend(
            [
                f"reader_proxy：{scene_card.reader_proxy or '无'}",
                f"proxy_function：{scene_card.proxy_function or '无'}",
                f"exit_state：{scene_card.exit_state}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _scene_from_text(scene_card: SceneCard, text: str) -> Scene:
        return Scene(
            id=scene_card.scene_id,
            title=scene_card.purpose,
            summary=scene_card.exit_state,
            blocks=[
                TextBlock(id=f"{scene_card.scene_id}.b{index:03d}", text=paragraph, purpose="paragraph")
                for index, paragraph in enumerate(WriterAgent._split_paragraphs(text), start=1)
            ],
        )

    @staticmethod
    def _chapter_scene_from_text(*, chapter_id: str, text: str) -> Scene:
        scene_id = f"{chapter_id}.sc_001"
        return Scene(
            id=scene_id,
            title="Chapter body",
            summary="Full chapter prose",
            blocks=[
                TextBlock(id=f"{scene_id}.b{index:03d}", text=paragraph, purpose="paragraph")
                for index, paragraph in enumerate(WriterAgent._split_paragraphs(text), start=1)
            ],
        )

    @staticmethod
    def _chapter_scene_from_chapter_beats(*, chapter_id: str, beats: list[ChapterBeat]) -> Scene:
        scene_id = f"{chapter_id}.sc_001"
        scene_blocks = [
            TextBlock(
                id=beat.block_id,
                text=beat.text,
                purpose=beat.purpose,
                metadata={
                    "chapter_id": beat.chapter_id,
                    "block_index": beat.block_index,
                    "characters": list(beat.characters),
                    "active_lines": list(beat.active_lines),
                    "active_twists": list(beat.active_twists),
                    "scene_goal": beat.scene_goal,
                    "must_reveal": list(beat.must_reveal),
                    "must_hide": list(beat.must_hide),
                    "emotional_tone": beat.emotional_tone,
                    "end_state": beat.end_state,
                    "human_reaction_target": list(beat.human_reaction_target),
                    "cost_shift": beat.cost_shift,
                    "reader_feeling_target": beat.reader_feeling_target,
                    "paragraph_budget": beat.paragraph_budget,
                    "micro_hook": beat.micro_hook,
                    "turn_type": beat.turn_type,
                    "paragraph_shape": list(beat.paragraph_shape),
                    "character_anchor_line": beat.character_anchor_line.model_dump(mode="json") if beat.character_anchor_line else None,
                    "style_risk_guard": list(beat.style_risk_guard),
                    "character_reentry_mode": beat.character_reentry_mode.model_dump(mode="json") if beat.character_reentry_mode else None,
                    "clue_reveal_mechanism": beat.clue_reveal_mechanism.model_dump(mode="json") if beat.clue_reveal_mechanism else None,
                    "status": beat.status,
                    "version": beat.version,
                },
            )
            for beat in beats
        ]
        return Scene(
            id=scene_id,
            title="Chapter beats",
            summary="Committed chapter beats",
            blocks=scene_blocks,
        )

    @staticmethod
    def _scene_text(scene: Scene) -> str:
        return "\n\n".join(block.text for block in scene.blocks if str(block.text or "").strip())

    @staticmethod
    def _locate_block(book: BookDocument, block_id: str) -> tuple[TextBlock, Chapter, Scene | None]:
        for volume in book.volumes:
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    for block in scene.blocks:
                        if block.id == block_id:
                            return block, chapter, scene
        raise ValueError(f"Block not found: {block_id}")

    @staticmethod
    def _locate_chapter(book: BookDocument, chapter_id: str) -> tuple[int, int, Chapter]:
        for volume_index, volume in enumerate(book.volumes):
            for chapter_index, chapter in enumerate(volume.chapters):
                if chapter.id == chapter_id:
                    return volume_index, chapter_index, chapter
        raise ValueError(f"Chapter not found: {chapter_id}")

    @staticmethod
    def _fallback_scene_card(scene_id: str) -> SceneCard:
        return SceneCard(
            scene_id=scene_id.split(".b")[0] if ".b" in scene_id else scene_id,
            purpose="局部重写",
            pov="当前受限视角",
            location="原场景",
            visible_goal="在不改事实的前提下重写文本",
            obstacle="不得越过本章信息边界",
            must_show=[],
            must_not_show=[],
            reader_proxy="",
            proxy_function="",
            exit_state="原段落功能保留",
        )

    @staticmethod
    def _chapter_full_text(chapter: Chapter) -> str:
        if chapter.is_finalized and str(chapter.final_text or "").strip():
            return str(chapter.final_text or "").strip()
        if chapter.content_blocks:
            return "\n\n".join(
                str(block.text or "").strip()
                for block in chapter.content_blocks
                if str(block.text or "").strip()
            ).strip()
        return "\n\n".join(
            text
            for text in (WriterAgent._scene_text(scene) for scene in chapter.scenes)
            if text
        ).strip()

    @staticmethod
    def _tail_text(text: str, *, max_chars: int) -> str:
        clean = str(text or "").strip()
        return clean[-max_chars:] if clean else ""

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not raw:
            return ["（正文为空）"]
        parts = [item.strip() for item in raw.split("\n\n") if item.strip()]
        return parts or [item.strip() for item in raw.split("\n") if item.strip()] or ["（正文为空）"]

    @staticmethod
    def _target_words_for_style(style_text: str) -> int:
        text = style_text.lower()
        if "短篇" in style_text or "short" in text:
            return 12000
        if "中篇" in style_text or "medium" in text or "mid" in text:
            return 40000
        return 100000
