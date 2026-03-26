from __future__ import annotations

from typing import Any

from novel_flow.agents.base import BaseAgent
from novel_flow.models.schemas import AgentResult, BlockPatchVersion, BookDocument, CriticReport, ResearchReport, WorkflowState
from novel_flow.storage.sqlite_store import SQLiteStore


class MemoryAgent(BaseAgent):
    def __init__(self, store: SQLiteStore) -> None:
        super().__init__(name="MemoryAgent")
        self.store = store

    def save_state(self, state: WorkflowState) -> None:
        self.store.save_workflow_state(state)

    def load_state(self, run_id: str) -> WorkflowState | None:
        return self.store.load_workflow_state(run_id)

    def save_research_report(self, report: ResearchReport) -> None:
        self.store.save_research_report(report)

    def load_research_report(self, report_id: str) -> ResearchReport | None:
        return self.store.load_research_report(report_id)

    def save_book(self, book: BookDocument) -> None:
        self.store.save_book(book)

    def load_book(self, book_id: str) -> BookDocument | None:
        return self.store.load_book(book_id)

    def save_critic_report(self, report: CriticReport) -> None:
        self.store.save_critic_report(report)

    def load_critic_report(self, report_id: str) -> CriticReport | None:
        return self.store.load_critic_report(report_id)

    def save_patch_version(self, version: BlockPatchVersion) -> None:
        self.store.save_patch_version(version)

    def list_patch_versions(self, book_id: str, block_id: str) -> list[BlockPatchVersion]:
        return self.store.list_patch_versions(book_id, block_id)

    def run(self, **kwargs: Any) -> AgentResult:
        action = kwargs.get("action", "noop")
        return AgentResult(
            agent_name=self.name,
            success=True,
            message=f"Memory action completed: {action}",
            payload={},
        )
