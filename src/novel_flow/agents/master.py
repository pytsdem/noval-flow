from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.models.schemas import (
    AgentResult,
    BlockPatchVersion,
    BookBlueprint,
    BookDocument,
    Chapter,
    CriticReport,
    PatchInstruction,
    ResearchReport,
    StoryPremise,
    WorkflowStage,
    WorkflowState,
)


class MasterAgent(BaseAgent):
    def __init__(
        self,
        memory_agent: MemoryAgent,
        research_agent: ResearchAgent,
        blueprint_agent: BlueprintAgent,
        writer_agent: WriterAgent,
        critic_agent: CriticAgent,
    ) -> None:
        super().__init__(name="MasterAgent")
        self.memory_agent = memory_agent
        self.research_agent = research_agent
        self.blueprint_agent = blueprint_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent

    def run_mock_pipeline(self, query: str, run_id: str | None = None) -> dict[str, Any]:
        return self.start_new_novel(query=query, run_id=run_id, mode="formal")

    def start_new_novel(self, query: str, run_id: str | None = None, mode: str = "formal") -> dict[str, Any]:
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(run_id=run_id, stage=WorkflowStage.RESEARCH, context={"query": query})
        self._save_state(state, mode=mode)

        ev.emit("stage", agent="MasterAgent", title="Stage: research", stage="research", run_id=run_id)
        ev.check_cancelled()
        research_report = self.research_agent.collect_report(query=query)
        ev.check_cancelled()
        self.memory_agent.save_research_report(research_report)
        self._save_output(
            run_id=run_id,
            agent="ResearchAgent",
            output_type="research_report",
            title="Research report",
            payload=research_report.model_dump(mode="json"),
        )

        self._transition(state, WorkflowStage.PLANNING, mode=mode, latest_research_report_id=research_report.report_id)
        ev.emit("stage", agent="MasterAgent", title="Stage: blueprint", stage="planning")
        ev.check_cancelled()
        blueprint, blueprint_review = self._build_and_review_blueprint(run_id=run_id, query=query)
        ev.check_cancelled()
        book = self.writer_agent.create_book(blueprint=blueprint, source_query=query)
        ev.check_cancelled()
        self.memory_agent.save_book(book)
        self._save_output(
            run_id=run_id,
            agent="WriterAgent",
            output_type="book_shell",
            title="Book shell",
            payload=book.model_dump(mode="json"),
        )

        self._transition(state, WorkflowStage.WRITING, mode=mode, current_book_id=book.id)
        ev.check_cancelled()
        written_book, chapter = self.writer_agent.write_next_chapter(book=book)
        ev.check_cancelled()
        self.memory_agent.save_book(written_book)
        self._save_output(
            run_id=run_id,
            agent="WriterAgent",
            output_type="chapter_written",
            title=f"Chapter written: {chapter.title}",
            payload=chapter.model_dump(mode="json"),
        )

        critique = self._critique_and_patch(run_id=run_id, state=state, book=written_book, mode=mode)
        final_book = critique["book"]
        return {
            "run_id": run_id,
            "research_report": research_report,
            "blueprint": blueprint,
            "chapter_written": chapter,
            "blueprint_review": blueprint_review,
            "critic_report": critique["critic_report"],
            "patch_instruction": critique["patch_instruction"],
            "patch_version": critique["patch_version"],
            "book_after_patch": final_book,
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
        run_id = run_id or f"run_{uuid4().hex[:10]}"
        state = WorkflowState(
            run_id=run_id,
            stage=WorkflowStage.WRITING,
            current_book_id=book.id,
            context={"continue": True, "query": book.metadata.get("query", ""), "book_title": book.title},
        )
        self._save_state(state, mode=mode)

        ev.emit("stage", agent="MasterAgent", title="Stage: continue writing", stage="writing", book_id=book.id)
        ev.check_cancelled()
        written_book, chapter = self.writer_agent.write_next_chapter(book=book)
        ev.check_cancelled()
        self.memory_agent.save_book(written_book)
        self._save_output(
            run_id=run_id,
            agent="WriterAgent",
            output_type="chapter_written",
            title=f"Chapter written: {chapter.title}",
            payload=chapter.model_dump(mode="json"),
        )

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

    def _build_and_review_blueprint(self, *, run_id: str, query: str) -> tuple[BookBlueprint, dict[str, Any]]:
        max_rounds = 2
        blueprint: BookBlueprint | None = None
        blueprint_review: dict[str, Any] = {"summary": "", "issues": []}

        for round_index in range(1, max_rounds + 1):
            if round_index == 1:
                spine = self.blueprint_agent.build_story_spine(research_query=query)
                ev.check_cancelled()
                premise = StoryPremise.model_validate(spine["premise"])
                volume_titles = [str(item) for item in spine["volume_titles"]]
                characters = self.blueprint_agent.build_character_bible(query, premise, volume_titles)
                ev.check_cancelled()
                chapter_plans = self.blueprint_agent.build_chapter_roadmap(query, premise, characters, volume_titles)
                ev.check_cancelled()
                blueprint = BookBlueprint(
                    blueprint_id=f"blueprint_{uuid4().hex[:10]}",
                    premise=premise,
                    characters=characters,
                    volume_titles=volume_titles,
                    chapter_plans=chapter_plans,
                )
                self._save_output(
                    run_id=run_id,
                    agent="BlueprintAgent",
                    output_type="story_spine",
                    title=f"Story spine round {round_index}",
                    payload={"premise": premise.model_dump(mode="json"), "volume_titles": volume_titles, "round_index": round_index},
                )
                self._save_output(
                    run_id=run_id,
                    agent="BlueprintAgent",
                    output_type="character_bible",
                    title=f"Character bible round {round_index}",
                    payload={"characters": [item.model_dump(mode="json") for item in characters], "round_index": round_index},
                )
                self._save_output(
                    run_id=run_id,
                    agent="BlueprintAgent",
                    output_type="chapter_roadmap",
                    title=f"Chapter roadmap round {round_index}",
                    payload={"chapter_plans": [item.model_dump(mode="json") for item in chapter_plans], "round_index": round_index},
                )
            else:
                ev.emit(
                    "stage",
                    agent="MasterAgent",
                    title=f"Stage: blueprint revise round {round_index - 1}",
                    stage="planning",
                    run_id=run_id,
                    round_index=round_index - 1,
                )
                ev.check_cancelled()
                blueprint = self.blueprint_agent.revise_blueprint(blueprint, blueprint_review)
                ev.check_cancelled()
                self._save_output(
                    run_id=run_id,
                    agent="BlueprintAgent",
                    output_type="blueprint_revised",
                    title=f"Blueprint revised round {round_index - 1}",
                    payload={**blueprint.model_dump(mode="json"), "round_index": round_index - 1},
                )

            blueprint_review = self.critic_agent.review_blueprint(blueprint)
            ev.check_cancelled()
            self._save_output(
                run_id=run_id,
                agent="CriticAgent",
                output_type="blueprint_review",
                title=f"Blueprint review round {round_index}",
                payload={**blueprint_review, "round_index": round_index},
            )
            self._save_output(
                run_id=run_id,
                agent="BlueprintAgent",
                output_type="blueprint",
                title=f"Blueprint round {round_index}",
                payload={**blueprint.model_dump(mode="json"), "round_index": round_index},
            )

            if not blueprint_review.get("issues") or round_index >= max_rounds:
                return blueprint, blueprint_review

        return blueprint, blueprint_review

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
            ev.emit(
                "stage",
                agent="MasterAgent",
                title=f"Stage: critique round {round_index}",
                stage="critique",
                run_id=run_id,
                round_index=round_index,
            )
            ev.check_cancelled()
            critic_report = self.critic_agent.review_book(book=final_book)
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
            patch_instruction = self.critic_agent.build_patch_instruction(critic_report.issues[0])
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
