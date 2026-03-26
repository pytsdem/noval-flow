from __future__ import annotations
from typing import Any
from uuid import uuid4

from novel_flow.agents.base import BaseAgent
from novel_flow.constants.mock_data import MOCK_CRITIC_ISSUE_SEED, MOCK_PATCH_CONTENT
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    AgentResult,
    BookDocument,
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
        prompt = self.prompt_library.render(
            "critic/review.txt",
            book_json=book.model_dump_json(indent=2),
        )
        try:
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
            return CriticReport(
                report_id=f"critic_{uuid4().hex[:10]}",
                summary=str(parsed.get("summary", "模型已完成结构化审稿。")),
                issues=issues,
            )
        except Exception as exc:
            self.logger.warning("Critic review fell back to mock seed: %s", exc)
            fallback_issue = MOCK_CRITIC_ISSUE_SEED["issue"]
            target_block = self._find_first_review_target(book)
            issues = [
                IssueCard(
                    issue_id=f"issue_{uuid4().hex[:10]}",
                    severity=IssueSeverity(str(fallback_issue["severity"])),
                    title=str(fallback_issue["title"]),
                    problem_type=str(fallback_issue["problem_type"]),
                    location=IssueLocation(
                        book_id=book.id,
                        volume_id=target_block["volume_id"],
                        chapter_id=target_block["chapter_id"],
                        scene_id=target_block["scene_id"],
                        block_id=target_block["block_id"],
                    ),
                    evidence=str(fallback_issue["evidence"]),
                    impact=str(fallback_issue["impact"]),
                    recommendation=str(fallback_issue["recommendation"]),
                    acceptance_criteria=[str(item) for item in fallback_issue["acceptance_criteria"]],
                )
            ]
            return CriticReport(
                report_id=f"critic_{uuid4().hex[:10]}",
                summary=str(MOCK_CRITIC_ISSUE_SEED["summary"]),
                issues=issues,
            )

    def build_patch_instruction(self, issue: IssueCard) -> PatchInstruction:
        prompt = self.prompt_library.render(
            "critic/patch_instruction.txt",
            issue_json=issue.model_dump_json(indent=2),
        )
        try:
            raw = self._generate_json_text(prompt=prompt)
            parsed = extract_json_object(raw)
            operation = PatchOperation(str(parsed.get("operation", "replace")))
            reason = str(parsed.get("reason", issue.recommendation))
            content = str(parsed.get("content", MOCK_PATCH_CONTENT))
        except Exception as exc:
            self.logger.warning("Patch instruction fell back to mock seed: %s", exc)
            operation = PatchOperation.REPLACE
            reason = issue.recommendation
            content = MOCK_PATCH_CONTENT
        return PatchInstruction(
            patch_id=f"patch_{uuid4().hex[:10]}",
            issue_id=issue.issue_id,
            target_block_id=issue.location.block_id,
            operation=operation,
            reason=reason,
            content=content,
        )

    def run(self, **kwargs: Any) -> AgentResult:
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
    def _find_first_review_target(book: BookDocument) -> dict[str, str]:
        for volume in book.volumes:
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    for block in scene.blocks:
                        return {
                            "volume_id": volume.id,
                            "chapter_id": chapter.id,
                            "scene_id": scene.id,
                            "block_id": block.id,
                        }
        raise ValueError("No blocks available for critique target.")
