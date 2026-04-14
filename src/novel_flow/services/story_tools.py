from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.models.schemas import (
    BlockPatchVersion,
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterPlan,
    DirectorAction,
    DirectorDecision,
    KnowledgeCard,
    ResearchReport,
    StoryPremise,
    ToolObservation,
)
from novel_flow.services.reference_library import ReferenceLibrary


@dataclass
class DirectedStorySession:
    run_id: str
    query: str
    style_request: str
    mode: str
    book: BookDocument | None = None
    research_report: ResearchReport | None = None
    blueprint: BookBlueprint | None = None
    blueprint_review: dict[str, Any] = field(default_factory=lambda: {"summary": "", "issues": []})
    chapter_written: Chapter | None = None
    critic_report: Any | None = None
    patch_instruction: Any | None = None
    patch_version: BlockPatchVersion | None = None
    reference_packs: dict[str, str] = field(default_factory=dict)
    reference_cards: dict[str, list[KnowledgeCard]] = field(default_factory=dict)
    reference_fetch_counts: dict[str, int] = field(default_factory=dict)
    observations: list[ToolObservation] = field(default_factory=list)

    def summary(self, *, stage_hint: str, focus_points: list[str] | None = None) -> dict[str, Any]:
        next_plan = self.next_chapter_plan()
        return {
            "query": self.query,
            "style_request": self.style_request,
            "mode": self.mode,
            "has_research_report": self.research_report is not None,
            "has_blueprint": self.blueprint is not None,
            "has_book": self.book is not None,
            "has_chapter_written": self.chapter_written is not None,
            "stage_hint": stage_hint,
            "focus_points": focus_points or [],
            "planning_reference_count": len(self.reference_cards.get("planning", [])),
            "writing_reference_count": len(self.reference_cards.get("writing", [])),
            "book_id": self.book.id if self.book else "",
            "book_title": self.book.title if self.book else "",
            "next_chapter_id": next_plan.chapter_id if next_plan else "",
            "next_chapter_title": next_plan.title if next_plan else "",
            "next_chapter_objective": next_plan.objective if next_plan else "",
            "next_chapter_tension": next_plan.tension if next_plan else "",
        }

    def next_chapter_plan(self) -> ChapterPlan | None:
        if self.book is None:
            return None
        raw_plans = self.book.metadata.get("chapter_plans", [])
        plans = [ChapterPlan.model_validate(item) for item in raw_plans]
        next_index = int(self.book.metadata.get("next_chapter_index", 0))
        if next_index >= len(plans):
            return None
        return plans[next_index]


class StoryToolRegistry:
    def __init__(
        self,
        *,
        research_agent: ResearchAgent,
        blueprint_agent: BlueprintAgent,
        writer_agent: WriterAgent,
        critic_agent: CriticAgent,
        memory_agent: MemoryAgent,
        reference_library: ReferenceLibrary,
        save_output: Callable[..., None],
    ) -> None:
        self.research_agent = research_agent
        self.blueprint_agent = blueprint_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent
        self.memory_agent = memory_agent
        self.reference_library = reference_library
        self.save_output = save_output

    def execute(self, *, decision: DirectorDecision, session: DirectedStorySession) -> ToolObservation:
        if decision.action == DirectorAction.RUN_RESEARCH:
            return self._run_research(session)
        if decision.action == DirectorAction.RETRIEVE_REFERENCES:
            return self._retrieve_references(session, decision)
        if decision.action == DirectorAction.BUILD_BLUEPRINT:
            return self._build_blueprint(session)
        if decision.action == DirectorAction.CREATE_BOOK:
            return self._create_book(session)
        if decision.action == DirectorAction.WRITE_CHAPTER:
            return self._write_chapter(session)
        raise ValueError(f"Unsupported tool action: {decision.action}")

    def _run_research(self, session: DirectedStorySession) -> ToolObservation:
        report = self.research_agent.collect_report(query=session.query)
        session.research_report = report
        self.memory_agent.save_research_report(report)
        self.save_output(
            run_id=session.run_id,
            agent="ResearchAgent",
            output_type="research_report",
            title="Research report",
            payload=report.model_dump(mode="json"),
        )
        return ToolObservation(
            tool_name="run_research",
            summary=f"Collected {len(report.trend_items)} trend items.",
            payload={"report_id": report.report_id, "sources": report.sources},
        )

    def _retrieve_references(self, session: DirectedStorySession, decision: DirectorDecision) -> ToolObservation:
        stage = str(decision.tool_input.get("stage", "planning"))
        query = str(decision.tool_input.get("query", session.query))
        focus = [str(item) for item in decision.tool_input.get("focus", [])]
        tags = [str(item) for item in decision.tool_input.get("tags", [])]
        cards = self.reference_library.retrieve(query=query, stage=stage, tags=tags, focus=focus, limit=4)
        session.reference_cards[stage] = cards
        session.reference_packs[stage] = self.reference_library.build_reference_pack(cards)
        session.reference_fetch_counts[stage] = session.reference_fetch_counts.get(stage, 0) + 1
        payload = {
            "stage": stage,
            "query": query,
            "focus": focus,
            "tags": tags,
            "reference_pack": session.reference_packs[stage],
            "cards": [card.model_dump(mode="json") for card in cards],
        }
        self.save_output(
            run_id=session.run_id,
            agent="ReferenceLibrary",
            output_type="reference_cards",
            title=f"Reference retrieval: {stage}",
            payload=payload,
        )
        return ToolObservation(
            tool_name="retrieve_references",
            summary=f"Retrieved {len(cards)} reference card(s) for {stage}.",
            payload={"stage": stage, "card_ids": [card.card_id for card in cards]},
        )

    def _build_blueprint(self, session: DirectedStorySession) -> ToolObservation:
        reference_pack = session.reference_packs.get("planning", "暂无额外参考资料。")
        max_rounds = 2
        blueprint: BookBlueprint | None = None
        blueprint_review: dict[str, Any] = {"summary": "", "issues": []}

        for round_index in range(1, max_rounds + 1):
            if round_index == 1:
                spine = self.blueprint_agent.build_story_spine(
                    session.query,
                    style_request=session.style_request,
                    reference_pack=reference_pack,
                )
                premise = StoryPremise.model_validate(spine["premise"])
                volume_titles = [str(item) for item in spine["volume_titles"]]
                characters = self.blueprint_agent.build_character_bible(
                    session.query,
                    premise,
                    volume_titles,
                    reference_pack=reference_pack,
                )
                chapter_plans = self.blueprint_agent.build_chapter_roadmap(
                    session.query,
                    premise,
                    characters,
                    volume_titles,
                    reference_pack=reference_pack,
                )
                blueprint = BookBlueprint(
                    blueprint_id=f"blueprint_{uuid4().hex[:10]}",
                    premise=premise,
                    characters=characters,
                    volume_titles=volume_titles,
                    chapter_plans=chapter_plans,
                )
                self.save_output(
                    run_id=session.run_id,
                    agent="BlueprintAgent",
                    output_type="story_spine",
                    title=f"Story spine round {round_index}",
                    payload={"premise": premise.model_dump(mode="json"), "volume_titles": volume_titles, "round_index": round_index},
                )
                self.save_output(
                    run_id=session.run_id,
                    agent="BlueprintAgent",
                    output_type="character_bible",
                    title=f"Character bible round {round_index}",
                    payload={"characters": [item.model_dump(mode="json") for item in characters], "round_index": round_index},
                )
                self.save_output(
                    run_id=session.run_id,
                    agent="BlueprintAgent",
                    output_type="chapter_roadmap",
                    title=f"Chapter roadmap round {round_index}",
                    payload={"chapter_plans": [item.model_dump(mode="json") for item in chapter_plans], "round_index": round_index},
                )
            else:
                blueprint = self.blueprint_agent.revise_blueprint(blueprint, blueprint_review, reference_pack=reference_pack)
                self.save_output(
                    run_id=session.run_id,
                    agent="BlueprintAgent",
                    output_type="blueprint_revised",
                    title=f"Blueprint revised round {round_index - 1}",
                    payload={**blueprint.model_dump(mode="json"), "round_index": round_index - 1},
                )

            blueprint_review = self.critic_agent.review_blueprint(blueprint)
            self.save_output(
                run_id=session.run_id,
                agent="CriticAgent",
                output_type="blueprint_review",
                title=f"Blueprint review round {round_index}",
                payload={**blueprint_review, "round_index": round_index},
            )
            self.save_output(
                run_id=session.run_id,
                agent="BlueprintAgent",
                output_type="blueprint",
                title=f"Blueprint round {round_index}",
                payload={**blueprint.model_dump(mode="json"), "round_index": round_index},
            )
            if not blueprint_review.get("issues") or round_index >= max_rounds:
                break

        session.blueprint = blueprint
        session.blueprint_review = blueprint_review
        return ToolObservation(
            tool_name="build_blueprint",
            summary=f"Built blueprint with {len(blueprint.chapter_plans)} chapter plans.",
            payload={"blueprint_id": blueprint.blueprint_id, "issue_count": len(blueprint_review.get('issues', []))},
        )

    def _create_book(self, session: DirectedStorySession) -> ToolObservation:
        if session.blueprint is None:
            raise ValueError("Blueprint is required before create_book.")
        book = self.writer_agent.create_book(
            blueprint=session.blueprint,
            source_query=session.query,
            style_request=session.style_request,
        )
        session.book = book
        self.memory_agent.save_book(book)
        self.save_output(
            run_id=session.run_id,
            agent="WriterAgent",
            output_type="book_shell",
            title="Book shell",
            payload=book.model_dump(mode="json"),
        )
        return ToolObservation(
            tool_name="create_book",
            summary=f"Initialized book shell {book.id}.",
            payload={"book_id": book.id, "title": book.title},
        )

    def _write_chapter(self, session: DirectedStorySession) -> ToolObservation:
        if session.book is None:
            raise ValueError("Book is required before write_chapter.")
        reference_pack = session.reference_packs.get("writing", "暂无额外参考资料。")
        updated_book, chapter = self.writer_agent.write_next_chapter(book=session.book, reference_pack=reference_pack)
        session.book = updated_book
        session.chapter_written = chapter
        self.memory_agent.save_book(updated_book)
        self.save_output(
            run_id=session.run_id,
            agent="WriterAgent",
            output_type="chapter_written",
            title=f"Chapter written: {chapter.title}",
            payload=chapter.model_dump(mode="json"),
        )
        return ToolObservation(
            tool_name="write_chapter",
            summary=f"Wrote chapter {chapter.id}.",
            payload={"chapter_id": chapter.id, "title": chapter.title},
        )
