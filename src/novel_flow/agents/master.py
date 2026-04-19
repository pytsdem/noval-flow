from __future__ import annotations

import json

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.director import DirectorAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.models.schemas import (
    AgentResult,
    BlockPatchVersion,
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterPlan,
    CriticReport,
    DirectorAction,
    DirectorDecision,
    PatchInstruction,
    ResearchReport,
    StoryPremise,
    ToolObservation,
    Volume,
    WorkflowStage,
    WorkflowState,
)
from novel_flow.services.reference_library import ReferenceLibrary
from novel_flow.services.story_tools import DirectedStorySession, StoryToolRegistry


class MasterAgent(BaseAgent):
    def __init__(
        self,
        memory_agent: MemoryAgent,
        research_agent: ResearchAgent,
        blueprint_agent: BlueprintAgent,
        writer_agent: WriterAgent,
        critic_agent: CriticAgent,
        director_agent: DirectorAgent | None = None,
        reference_library: ReferenceLibrary | None = None,
    ) -> None:
        super().__init__(name="MasterAgent")
        self.memory_agent = memory_agent
        self.research_agent = research_agent
        self.blueprint_agent = blueprint_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent
        self.director_agent = director_agent or DirectorAgent(llm_client=self.blueprint_agent.llm_client)
        self.reference_library = reference_library or ReferenceLibrary()

    def run_mock_pipeline(self, query: str, run_id: str | None = None, style_request: str = "") -> dict[str, Any]:
        return self.start_new_novel(query=query, run_id=run_id, mode="formal", style_request=style_request)

    def start_new_outline(
        self,
        query: str,
        run_id: str | None = None,
        mode: str = "formal",
        style_request: str = "",
    ) -> dict[str, Any]:
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(run_id=run_id, stage=WorkflowStage.RESEARCH, context={"query": query, "style_request": style_request, "action": "outline"})
        self._save_state(state, mode=mode)

        ev.emit("stage", agent="MasterAgent", title="Stage: research for outline", stage="research", run_id=run_id)
        research_report = self.research_agent.collect_report(query=query)
        self.memory_agent.save_research_report(research_report)
        self._save_output(
            run_id=run_id,
            agent="ResearchAgent",
            output_type="research_report",
            title="Research report",
            payload=research_report.model_dump(mode="json"),
        )
        self._transition(state, WorkflowStage.PLANNING, mode=mode, latest_research_report_id=research_report.report_id)

        focus = [query, style_request, "故事总策划", "情节完整", "人物成立", *research_report.writing_recommendations[:3]]
        reference_pack = self._retrieve_reference_pack(run_id=run_id, query=query, stage="planning", focus=focus, tags=["故事结构", "人物塑造"])
        spine = self.blueprint_agent.build_story_spine(query, style_request=style_request, reference_pack=reference_pack)
        premise = StoryPremise.model_validate(spine["premise"])
        volume_titles = [str(item) for item in spine["volume_titles"]]
        story_blueprint = dict(spine.get("story_blueprint", {}))
        blueprint = BookBlueprint(
            blueprint_id=f"blueprint_{uuid4().hex[:10]}",
            premise=premise,
            characters=[],
            volume_titles=volume_titles,
            chapter_plans=[],
        )
        book = self.writer_agent.create_book(blueprint=blueprint, source_query=query, style_request=style_request)
        book.metadata["planning_phase"] = "outline"
        book.metadata["volume_titles"] = volume_titles
        book.metadata["story_blueprint"] = story_blueprint
        book.metadata["chapter_plans"] = []
        book.metadata["next_chapter_index"] = 0

        self.memory_agent.save_book(book)
        self._save_output(
            run_id=run_id,
            agent="BlueprintAgent",
            output_type="story_spine",
            title="Story spine",
            payload={"premise": premise.model_dump(mode="json"), "volume_titles": volume_titles, "story_blueprint": story_blueprint},
        )
        self._save_output(
            run_id=run_id,
            agent="BlueprintAgent",
            output_type="story_blueprint",
            title="Full story blueprint",
            payload={"story_blueprint": story_blueprint},
        )
        self._save_output(
            run_id=run_id,
            agent="WriterAgent",
            output_type="book_shell",
            title="Outline draft book shell",
            payload=book.model_dump(mode="json"),
        )
        self._transition(state, WorkflowStage.COMPLETE, mode=mode, current_book_id=book.id)
        ev.emit("stage", agent="MasterAgent", title="Stage: outline complete", stage="complete", book_id=book.id)
        return {
            "run_id": run_id,
            "research_report": research_report,
            "blueprint": blueprint,
            "book_after_patch": book,
            "state": state,
        }

    def start_new_novel(
        self,
        query: str,
        run_id: str | None = None,
        mode: str = "formal",
        style_request: str = "",
    ) -> dict[str, Any]:
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(run_id=run_id, stage=WorkflowStage.RESEARCH, context={"query": query, "style_request": style_request})
        self._save_state(state, mode=mode)
        session = self._run_directed_creation_loop(run_id=run_id, query=query, style_request=style_request, state=state, mode=mode)
        self._transition(state, WorkflowStage.COMPLETE, mode=mode, current_book_id=session.book.id if session.book else None)
        ev.emit("stage", agent="MasterAgent", title="Stage: novel created", stage="complete", book_id=session.book.id if session.book else "")
        return {
            "run_id": run_id,
            "research_report": session.research_report,
            "blueprint": session.blueprint,
            "blueprint_review": session.blueprint_review,
            "book_after_patch": session.book,
            "state": state,
        }

    def continue_novel(
        self,
        *,
        book_id: str | None = None,
        title: str | None = None,
        run_id: str | None = None,
        mode: str = "formal",
    ) -> dict[str, Any]:
        book = self._resolve_book(book_id=book_id, title=title)
        if not book.characters:
            raise ValueError("请先生成或填写角色设定，再续写正文。")
        if not book.metadata.get("chapter_plans"):
            raise ValueError("请先生成或填写章节规划，再续写正文。")
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(
            run_id=run_id,
            stage=WorkflowStage.WRITING,
            current_book_id=book.id,
            context={"continue": True, "query": book.metadata.get("query", ""), "book_title": book.title},
        )
        self._save_state(state, mode=mode)
        session = self._run_directed_continue_loop(run_id=run_id, book=book, state=state, mode=mode)
        written_book = session.book
        chapter = session.chapter_written
        if written_book is None:
            raise ValueError("Director continue loop ended without writing a chapter.")

        critique = self._critique_and_patch(run_id=run_id, state=state, book=written_book, mode=mode)
        final_book = critique["book"]
        return {
            "run_id": run_id,
            "book_before_patch": written_book,
            "chapter_written": chapter,
            "critic_report": critique["critic_report"],
            "patch_instruction": critique["patch_instruction"],
            "patch_version": critique["patch_version"],
            "book_after_patch": final_book,
            "state": state,
        }

    def list_books(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.memory_agent.list_books(limit=limit)

    def generate_characters_for_book(
        self,
        *,
        book_id: str,
        run_id: str | None = None,
        mode: str = "formal",
    ) -> dict[str, Any]:
        book = self._resolve_book(book_id=book_id, title=None)
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(
            run_id=run_id,
            stage=WorkflowStage.PLANNING,
            current_book_id=book.id,
            context={"action": "generate_characters", "query": book.metadata.get("query", ""), "book_title": book.title},
        )
        self._save_state(state, mode=mode)

        topic = str(book.metadata.get("user_topic") or "").strip()
        base_query = str(book.metadata.get("query") or book.title)
        query = f"题材：{topic}\n需求：{base_query}" if topic and base_query else (topic or base_query)
        volume_titles = [str(item) for item in book.metadata.get("volume_titles", [])] or [volume.title for volume in book.volumes] or ["Volume 1"]
        focus = [
            query,
            book.premise.high_concept,
            book.premise.central_conflict,
            "人物塑造",
            "角色关系",
            "人物弧光",
            "行为逻辑",
            *book.premise.selling_points[:3],
        ]
        reference_pack = self._retrieve_reference_pack(
            run_id=run_id,
            query=query,
            stage="planning",
            focus=focus,
            tags=["人物塑造", "角色关系"],
        )
        reference_pack = self._augment_reference_pack(book, reference_pack)
        characters = self.blueprint_agent.build_character_bible(query, book.premise, volume_titles, reference_pack=reference_pack)
        book.characters = characters
        book.metadata["planning_phase"] = "characters"
        book.updated_at = datetime.now(timezone.utc)
        self.memory_agent.save_book(book)
        self._save_output(
            run_id=run_id,
            agent="BlueprintAgent",
            output_type="character_bible",
            title="Character bible",
            payload={"characters": [item.model_dump(mode="json") for item in characters]},
        )
        self._transition(state, WorkflowStage.COMPLETE, mode=mode, current_book_id=book.id)
        ev.emit("stage", agent="MasterAgent", title="Stage: characters complete", stage="complete", book_id=book.id)
        return {"run_id": run_id, "book_after_patch": book, "state": state}

    def generate_chapter_roadmap_for_book(
        self,
        *,
        book_id: str,
        run_id: str | None = None,
        mode: str = "formal",
    ) -> dict[str, Any]:
        book = self._resolve_book(book_id=book_id, title=None)
        if not book.characters:
            raise ValueError("请先生成或填写角色设定，再生成章节规划。")
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(
            run_id=run_id,
            stage=WorkflowStage.PLANNING,
            current_book_id=book.id,
            context={"action": "generate_chapter_roadmap", "query": book.metadata.get("query", ""), "book_title": book.title},
        )
        self._save_state(state, mode=mode)

        topic = str(book.metadata.get("user_topic") or "").strip()
        base_query = str(book.metadata.get("query") or book.title)
        query = f"题材：{topic}\n需求：{base_query}" if topic and base_query else (topic or base_query)
        volume_titles = [str(item) for item in book.metadata.get("volume_titles", [])] or [volume.title for volume in book.volumes] or ["Volume 1"]
        focus = [
            query,
            book.premise.core_hook,
            book.premise.central_conflict,
            "情节完整",
            "章节规划",
            "冲突升级",
            "人物关系推进",
            *book.premise.escalation_path[:3],
            *book.premise.twist_blueprint[:3],
        ]
        reference_pack = self._retrieve_reference_pack(
            run_id=run_id,
            query=query,
            stage="planning",
            focus=focus,
            tags=["故事结构", "章节规划", "人物关系"],
        )
        reference_pack = self._augment_reference_pack(book, reference_pack)
        chapter_plans = self.blueprint_agent.build_chapter_roadmap(
            query,
            book.premise,
            book.characters,
            volume_titles,
            reference_pack=reference_pack,
        )
        book.metadata["chapter_plans"] = [plan.model_dump(mode="json") for plan in chapter_plans]
        book.metadata["next_chapter_index"] = min(int(book.metadata.get("next_chapter_index", 0)), len(chapter_plans))
        book.metadata["planning_phase"] = "roadmap"
        book.updated_at = datetime.now(timezone.utc)
        self.memory_agent.save_book(book)

        blueprint = BookBlueprint(
            blueprint_id=str(book.metadata.get("blueprint_id") or f"blueprint_{uuid4().hex[:10]}"),
            premise=book.premise,
            characters=book.characters,
            volume_titles=volume_titles,
            chapter_plans=chapter_plans,
        )
        blueprint_review = self.critic_agent.review_blueprint(blueprint, reference_pack=reference_pack)
        self._save_output(
            run_id=run_id,
            agent="BlueprintAgent",
            output_type="chapter_roadmap",
            title="Chapter roadmap",
            payload={"chapter_plans": [item.model_dump(mode="json") for item in chapter_plans]},
        )
        self._save_output(
            run_id=run_id,
            agent="CriticAgent",
            output_type="blueprint_review",
            title="Blueprint review",
            payload=blueprint_review,
        )
        self._transition(state, WorkflowStage.COMPLETE, mode=mode, current_book_id=book.id)
        ev.emit("stage", agent="MasterAgent", title="Stage: chapter roadmap complete", stage="complete", book_id=book.id)
        return {"run_id": run_id, "book_after_patch": book, "blueprint_review": blueprint_review, "state": state}

    def _run_directed_creation_loop(
        self,
        *,
        run_id: str,
        query: str,
        style_request: str,
        state: WorkflowState,
        mode: str,
    ) -> DirectedStorySession:
        session = DirectedStorySession(run_id=run_id, query=query, style_request=style_request, mode=mode)
        registry = self._tool_registry()
        max_steps = 6

        for _ in range(max_steps):
            ev.check_cancelled()
            allowed_actions, stage_hint, focus_points = self._allowed_creation_actions(session)
            style_hint = f"，风格要求为“{style_request}”" if style_request else ""
            decision = self._director_decision(
                goal=f"为题材“{query}”{style_hint}准备足够的资料并写出第一章。",
                session=session,
                observations=session.observations,
                allowed_actions=allowed_actions,
                stage_hint=stage_hint,
                focus_points=focus_points,
                run_id=run_id,
            )
            self._transition_for_decision(state, decision, session, mode=mode)
            observation = registry.execute(decision=decision, session=session)
            session.observations.append(observation)
            self._save_output(
                run_id=run_id,
                agent="MasterAgent",
                output_type="tool_observation",
                title=f"Observation: {observation.tool_name}",
                payload=observation.model_dump(mode="json"),
            )
            if session.research_report is not None:
                state.latest_research_report_id = session.research_report.report_id
            if session.book is not None:
                state.current_book_id = session.book.id
            self._save_state(state, mode=mode)
            if session.book is not None:
                return session

        raise ValueError("Director loop ended before the book was created.")

    def _run_directed_continue_loop(
        self,
        *,
        run_id: str,
        book: BookDocument,
        state: WorkflowState,
        mode: str,
    ) -> DirectedStorySession:
        query = str(book.metadata.get("query", book.title))
        session = DirectedStorySession(
            run_id=run_id,
            query=query,
            style_request=str(book.metadata.get("style_request", book.premise.target_style)),
            mode=mode,
            book=book,
        )
        registry = self._tool_registry()
        max_steps = 3

        for _ in range(max_steps):
            ev.check_cancelled()
            allowed_actions, stage_hint, focus_points = self._allowed_continue_actions(session)
            decision = self._director_decision(
                goal=f"继续创作小说《{book.title}》的下一章。",
                session=session,
                observations=session.observations,
                allowed_actions=allowed_actions,
                stage_hint=stage_hint,
                focus_points=focus_points,
                run_id=run_id,
            )
            self._transition_for_decision(state, decision, session, mode=mode)
            observation = registry.execute(decision=decision, session=session)
            session.observations.append(observation)
            self._save_output(
                run_id=run_id,
                agent="MasterAgent",
                output_type="tool_observation",
                title=f"Observation: {observation.tool_name}",
                payload=observation.model_dump(mode="json"),
            )
            if session.book is not None:
                state.current_book_id = session.book.id
            self._save_state(state, mode=mode)
            if session.chapter_written is not None:
                return session

        raise ValueError("Director loop ended before the next chapter was written.")

    def _allowed_creation_actions(
        self,
        session: DirectedStorySession,
    ) -> tuple[list[DirectorAction], str, list[str]]:
        if session.research_report is None:
            focus = [session.query]
            if session.style_request:
                focus.append(session.style_request)
            return [DirectorAction.RUN_RESEARCH], "planning", focus
        if session.blueprint is None:
            planning_focus = list(session.research_report.writing_recommendations[:3]) if session.research_report else [session.query]
            if session.style_request:
                planning_focus.append(session.style_request)
            if session.reference_fetch_counts.get("planning", 0) == 0:
                return [DirectorAction.RETRIEVE_REFERENCES], "planning", planning_focus
            return [DirectorAction.BUILD_BLUEPRINT], "planning", planning_focus
        return [DirectorAction.CREATE_BOOK], "planning", [session.blueprint.premise.core_hook]

    def _allowed_continue_actions(
        self,
        session: DirectedStorySession,
    ) -> tuple[list[DirectorAction], str, list[str]]:
        next_plan = session.next_chapter_plan()
        writing_focus = [
            next_plan.title if next_plan else "",
            next_plan.objective if next_plan else "",
            next_plan.tension if next_plan else "",
            next_plan.cliffhanger if next_plan else "",
        ]
        if session.reference_fetch_counts.get("writing", 0) == 0:
            return [DirectorAction.RETRIEVE_REFERENCES], "writing", [item for item in writing_focus if item]
        return [DirectorAction.WRITE_CHAPTER], "writing", [item for item in writing_focus if item]

    def _director_decision(
        self,
        *,
        goal: str,
        session: DirectedStorySession,
        observations: list[ToolObservation],
        allowed_actions: list[DirectorAction],
        stage_hint: str,
        focus_points: list[str],
        run_id: str,
    ) -> DirectorDecision:
        decision = self.director_agent.decide(
            goal=goal,
            session_summary=session.summary(stage_hint=stage_hint, focus_points=focus_points),
            observations=observations,
            allowed_actions=allowed_actions,
        )
        self._save_output(
            run_id=run_id,
            agent="DirectorAgent",
            output_type="director_decision",
            title=f"Director decision: {decision.action.value}",
            payload=decision.model_dump(mode="json"),
        )
        return decision

    def _transition_for_decision(
        self,
        state: WorkflowState,
        decision: DirectorDecision,
        session: DirectedStorySession,
        *,
        mode: str,
    ) -> None:
        stage = self._stage_for_action(decision.action)
        ev.emit(
            "stage",
            agent="MasterAgent",
            title=f"Director step: {decision.action.value}",
            stage=stage.value,
            action=decision.action.value,
            reason=decision.reasoning,
        )
        extra: dict[str, Any] = {}
        if session.book is not None:
            extra["current_book_id"] = session.book.id
        if session.research_report is not None:
            extra["latest_research_report_id"] = session.research_report.report_id
        self._transition(state, stage, mode=mode, **extra)

    @staticmethod
    def _stage_for_action(action: DirectorAction) -> WorkflowStage:
        if action == DirectorAction.RUN_RESEARCH:
            return WorkflowStage.RESEARCH
        if action in (DirectorAction.RETRIEVE_REFERENCES, DirectorAction.BUILD_BLUEPRINT, DirectorAction.CREATE_BOOK):
            return WorkflowStage.PLANNING
        if action == DirectorAction.WRITE_CHAPTER:
            return WorkflowStage.WRITING
        if action == DirectorAction.CRITIQUE:
            return WorkflowStage.CRITIQUE
        if action == DirectorAction.PATCH:
            return WorkflowStage.PATCHING
        return WorkflowStage.COMPLETE

    @staticmethod
    def _story_blueprint_json(book: BookDocument | None) -> str:
        if book is None:
            return "{}"
        story_blueprint = book.metadata.get("story_blueprint", {})
        return json.dumps(story_blueprint, ensure_ascii=False, indent=2) if story_blueprint else "{}"

    @classmethod
    def _augment_reference_pack(cls, book: BookDocument | None, reference_pack: str) -> str:
        story_blueprint_json = cls._story_blueprint_json(book)
        if story_blueprint_json == "{}":
            return reference_pack
        return f"{reference_pack}\n\n[Full Story Blueprint - Must Be Respected]\n{story_blueprint_json}"

    def _tool_registry(self) -> StoryToolRegistry:
        return StoryToolRegistry(
            research_agent=self.research_agent,
            blueprint_agent=self.blueprint_agent,
            writer_agent=self.writer_agent,
            critic_agent=self.critic_agent,
            memory_agent=self.memory_agent,
            reference_library=self.reference_library,
            save_output=self._save_output,
        )

    def _retrieve_reference_pack(
        self,
        *,
        run_id: str,
        query: str,
        stage: str,
        focus: list[str],
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> str:
        cards = self.reference_library.retrieve(query=query, stage=stage, tags=tags or [], focus=focus, limit=limit)
        reference_pack = self.reference_library.build_reference_pack(cards)
        self._save_output(
            run_id=run_id,
            agent="ReferenceLibrary",
            output_type="reference_cards",
            title=f"Reference retrieval: {stage}",
            payload={
                "stage": stage,
                "query": query,
                "focus": focus,
                "tags": tags or [],
                "reference_pack": reference_pack,
                "cards": [card.model_dump(mode="json") for card in cards],
            },
        )
        return reference_pack

    def _critique_and_patch(
        self,
        *,
        run_id: str,
        state: WorkflowState,
        book: BookDocument,
        mode: str,
    ) -> dict[str, Any]:
        max_review_rounds = 2
        final_book = book
        critic_report: CriticReport | None = None
        patch_instruction: PatchInstruction | None = None
        patch_version: BlockPatchVersion | None = None

        for round_index in range(1, max_review_rounds + 1):
            current_plan = None
            if final_book.metadata.get("last_written_chapter_id"):
                for item in final_book.metadata.get("chapter_plans", []):
                    if str(item.get("chapter_id", "")) == str(final_book.metadata.get("last_written_chapter_id", "")):
                        current_plan = item
                        break
            reference_pack = self._retrieve_reference_pack(
                run_id=run_id,
                query=str(final_book.metadata.get("query") or final_book.title),
                stage="critique",
                focus=[
                    final_book.premise.core_hook,
                    final_book.premise.central_conflict,
                    str(current_plan or ""),
                    "审稿",
                    "人物行为逻辑",
                    "情节张力",
                ],
                tags=["审稿", "人物塑造", "情节"],
            )
            reference_pack = self._augment_reference_pack(final_book, reference_pack)
            ev.emit(
                "stage",
                agent="MasterAgent",
                title=f"Stage: critique round {round_index}",
                stage="critique",
                run_id=run_id,
                round_index=round_index,
            )
            ev.check_cancelled()
            critic_report = self.critic_agent.review_book(book=final_book, reference_pack=reference_pack)
            ev.check_cancelled()
            self.memory_agent.save_critic_report(critic_report, book_id=final_book.id)
            self._save_output(
                run_id=run_id,
                agent="CriticAgent",
                output_type="critic_report",
                title=f"Critic report round {round_index}",
                payload={**critic_report.model_dump(mode="json"), "round_index": round_index},
            )
            self._transition(state, WorkflowStage.CRITIQUE, mode=mode, latest_critic_report_id=critic_report.report_id)

            if not critic_report.issues:
                break

            if round_index >= max_review_rounds:
                break

            ev.emit(
                "stage",
                agent="MasterAgent",
                title=f"Stage: patch round {round_index}",
                stage="patching",
                run_id=run_id,
                round_index=round_index,
            )
            ev.check_cancelled()
            patch_instruction = self.critic_agent.build_patch_instruction(critic_report.issues[0], reference_pack=reference_pack)
            ev.check_cancelled()
            final_book, patch_payload = self.writer_agent.patch_block(book=final_book, instruction=patch_instruction)
            patch_version = BlockPatchVersion.model_validate(patch_payload["patch_version"])
            ev.check_cancelled()
            self.memory_agent.save_patch_version(patch_version)
            self.memory_agent.save_book(final_book)
            self._save_output(
                run_id=run_id,
                agent="CriticAgent",
                output_type="patch_instruction",
                title=f"Patch instruction round {round_index}",
                payload={**patch_instruction.model_dump(mode="json"), "round_index": round_index},
            )
            self._save_output(
                run_id=run_id,
                agent="WriterAgent",
                output_type="patch_version",
                title=f"Patch applied round {round_index}: {patch_instruction.target_block_id}",
                payload={**patch_version.model_dump(mode="json"), "round_index": round_index},
            )
            self._transition(state, WorkflowStage.PATCHING, mode=mode)

        self._transition(state, WorkflowStage.COMPLETE, mode=mode)
        ev.emit("stage", agent="MasterAgent", title="Stage: complete", stage="complete", book_id=final_book.id)
        return {
            "book": final_book,
            "critic_report": critic_report,
            "patch_instruction": patch_instruction,
            "patch_version": patch_version,
        }

    def _resolve_book(self, *, book_id: str | None, title: str | None) -> BookDocument:
        if book_id:
            book = self.memory_agent.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            return book
        if title:
            matches = self.memory_agent.find_books_by_title(title=title, limit=5)
            if not matches:
                raise ValueError(f"No book found for title: {title}")
            return matches[0]
        raise ValueError("Either book_id or title is required to continue a novel.")

    def _transition(self, state: WorkflowState, stage: WorkflowStage, mode: str = "formal", **extra: Any) -> None:
        state.stage = stage
        state.updated_at = datetime.now(timezone.utc)
        for key, value in extra.items():
            setattr(state, key, value)
        self._save_state(state, mode=mode)

    def _save_state(self, state: WorkflowState, mode: str = "formal") -> None:
        state.updated_at = datetime.now(timezone.utc)
        self.memory_agent.save_state(state, mode=mode)

    def _save_output(self, *, run_id: str, agent: str, output_type: str, title: str, payload: dict[str, Any]) -> None:
        self.memory_agent.save_run_output(
            run_id=run_id,
            agent=agent,
            output_type=output_type,
            title=title,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def run(self, **kwargs: Any) -> AgentResult:
        if kwargs.get("continue_book"):
            result = self.continue_novel(book_id=kwargs.get("book_id"), title=kwargs.get("title"))
        else:
            query = str(kwargs.get("query", "research-debug-query"))
            result = self.start_new_novel(query=query)

        payload: dict[str, Any] = {
            "run_id": result["run_id"],
            "book": result["book_after_patch"].model_dump(mode="json"),
            "workflow_state": result["state"].model_dump(mode="json"),
        }
        if "blueprint" in result:
            payload["blueprint"] = result["blueprint"].model_dump(mode="json")
        if "blueprint_review" in result:
            payload["blueprint_review"] = result["blueprint_review"]
        if "research_report" in result:
            payload["research_report"] = result["research_report"].model_dump(mode="json")
        if result.get("critic_report") is not None:
            payload["critic_report"] = result["critic_report"].model_dump(mode="json")
        if result.get("chapter_written") is not None:
            payload["chapter_written"] = result["chapter_written"].model_dump(mode="json")

        return AgentResult(
            agent_name=self.name,
            success=True,
            message="Master pipeline completed.",
            payload=payload,
        )
