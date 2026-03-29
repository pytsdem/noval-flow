from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    AgentResult,
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterPlan,
    CriticReport,
    IssueCard,
    IssueLocation,
    IssueSeverity,
    PatchInstruction,
    PatchOperation,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_tools import extract_json_object


class CriticAgent(BaseAgent):
    def __init__(self, llm_client: LLMClient, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(name="CriticAgent")
        self.llm_client = llm_client
        self.prompt_library = prompt_library or PromptLibrary()

    def review_book(self, book: BookDocument) -> CriticReport:
        ev.emit("agent_start", agent="CriticAgent", title="Review current chapter", book_id=book.id)
        current_chapter = self._current_chapter(book)
        previous_chapter = self._previous_chapter(book, current_chapter.id)
        current_plan = self._current_chapter_plan(book, current_chapter.id)
        prompt = self.prompt_library.render(
            "critic/review.txt",
            premise_json=book.premise.model_dump_json(indent=2),
            characters_json=json.dumps([item.model_dump(mode="json") for item in book.characters], ensure_ascii=False, indent=2),
            chapter_plan_json=current_plan.model_dump_json(indent=2) if current_plan else "{}",
            previous_chapter_json=json.dumps(previous_chapter.model_dump(mode="json"), ensure_ascii=False, indent=2)
            if previous_chapter
            else "{}",
            current_chapter_json=json.dumps(current_chapter.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        raw = self._generate_json_text(prompt=prompt)
        parsed = extract_json_object(raw)
        issues = [
            IssueCard(
                issue_id=f"issue_{uuid4().hex[:10]}",
                severity=IssueSeverity(item["severity"]),
                title=str(item["title"]),
                problem_type=str(item["problem_type"]),
                location=IssueLocation(
                    book_id=book.id,
                    volume_id=str(item["location"]["volume_id"]),
                    chapter_id=str(item["location"]["chapter_id"]),
                    scene_id=str(item["location"]["scene_id"]),
                    block_id=str(item["location"]["block_id"]),
                ),
                evidence=str(item["evidence"]),
                impact=str(item["impact"]),
                recommendation=str(item["recommendation"]),
                acceptance_criteria=[str(criteria) for criteria in item["acceptance_criteria"]],
            )
            for item in parsed.get("issues", [])
        ]
        report = CriticReport(
            report_id=f"critic_{uuid4().hex[:10]}",
            summary=str(parsed.get("summary", "")),
            issues=issues,
        )
        ev.emit(
            "critic_done",
            agent="CriticAgent",
            title=f"Chapter critique finished: {len(issues)} issue(s)",
            issue_count=len(issues),
        )
        return report

    def review_blueprint(self, blueprint: BookBlueprint) -> dict[str, Any]:
        ev.emit("agent_start", agent="CriticAgent", title="Review blueprint", blueprint_id=blueprint.blueprint_id)
        prompt = self.prompt_library.render(
            "critic/review_blueprint.txt",
            blueprint_json=blueprint.model_dump_json(indent=2),
        )
        parsed = extract_json_object(self._generate_json_text(prompt=prompt))
        ev.emit(
            "blueprint_review_done",
            agent="CriticAgent",
            title=f"Blueprint review finished: {len(parsed.get('issues', []))} issue(s)",
            issue_count=len(parsed.get("issues", [])),
        )
        return {
            "summary": str(parsed.get("summary", "")),
            "issues": parsed.get("issues", []),
        }

    def build_patch_instruction(self, issue: IssueCard) -> PatchInstruction:
        ev.emit("agent_start", agent="CriticAgent", title="Build patch instruction", issue_id=issue.issue_id)
        prompt = self.prompt_library.render(
            "critic/patch_instruction.txt",
            issue_json=issue.model_dump_json(indent=2),
        )
        raw = self._generate_json_text(prompt=prompt)
        parsed = extract_json_object(raw)
        instruction = PatchInstruction(
            patch_id=f"patch_{uuid4().hex[:10]}",
            issue_id=issue.issue_id,
            target_block_id=issue.location.block_id,
            operation=PatchOperation(str(parsed.get("operation", "replace"))),
            reason=str(parsed.get("reason", issue.recommendation)),
            content=str(parsed.get("content", "")),
        )
        ev.emit(
            "patch_ready",
            agent="CriticAgent",
            title=f"Patch ready for {instruction.target_block_id}",
            target_block_id=instruction.target_block_id,
            operation=instruction.operation,
        )
        return instruction

    def run(self, **kwargs: Any) -> AgentResult:
        if "blueprint" in kwargs:
            review = self.review_blueprint(BookBlueprint.model_validate(kwargs["blueprint"]))
            return AgentResult(
                agent_name=self.name,
                success=True,
                message=f"Generated blueprint review with {len(review['issues'])} issue(s).",
                payload={"blueprint_review": review},
            )
        book = kwargs["book"]
        report = self.review_book(book=book)
        payload: dict[str, Any] = {"critic_report": report.model_dump(mode="json")}
        if report.issues:
            payload["patch_instruction"] = self.build_patch_instruction(report.issues[0]).model_dump(mode="json")
        return AgentResult(
            agent_name=self.name,
            success=True,
            message=f"Generated critic report with {len(report.issues)} issue(s).",
            payload=payload,
        )

    def _generate_json_text(self, prompt: str) -> str:
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("critic/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        return self.llm_client.generate(messages=messages, temperature=0.3).strip()

    @staticmethod
    def _current_chapter(book: BookDocument) -> Chapter:
        last_written_id = str(book.metadata.get("last_written_chapter_id", ""))
        for volume in book.volumes:
            for chapter in volume.chapters:
                if chapter.id == last_written_id:
                    return chapter
        for volume in reversed(book.volumes):
            if volume.chapters:
                return volume.chapters[-1]
        raise ValueError(f"Book {book.id} has no chapters to review.")

    @staticmethod
    def _previous_chapter(book: BookDocument, current_chapter_id: str) -> Chapter | None:
        previous: Chapter | None = None
        for volume in book.volumes:
            for chapter in volume.chapters:
                if chapter.id == current_chapter_id:
                    return previous
                previous = chapter
        return None

    @staticmethod
    def _current_chapter_plan(book: BookDocument, chapter_id: str) -> ChapterPlan | None:
        for item in book.metadata.get("chapter_plans", []):
            if str(item.get("chapter_id", "")) == chapter_id:
                return ChapterPlan.model_validate(item)
        return None
