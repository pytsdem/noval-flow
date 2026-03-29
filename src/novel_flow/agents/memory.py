from __future__ import annotations

from typing import Any

from novel_flow.agents.base import BaseAgent
from novel_flow.models.schemas import AgentResult, BlockPatchVersion, BookDocument, CriticReport, ResearchReport, WorkflowState
from novel_flow.storage.sqlite_store import SQLiteStore


class MemoryAgent(BaseAgent):
    def __init__(self, store: SQLiteStore) -> None:
        super().__init__(name="MemoryAgent")
        self.store = store

    def save_state(self, state: WorkflowState, mode: str = "formal") -> None:
        self.store.save_workflow_state(state, mode=mode)

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

    def list_books(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.store.list_books(limit=limit)

    def find_books_by_title(self, title: str, limit: int = 10) -> list[BookDocument]:
        return self.store.find_books_by_title(title=title, limit=limit)

    def delete_book(self, book_id: str) -> None:
        self.store.delete_book(book_id)

    def delete_run(self, run_id: str) -> None:
        self.store.delete_run(run_id)

    def latest_run_for_book(self, book_id: str) -> str | None:
        return self.store.latest_run_for_book(book_id)

    def list_runs(self, limit: int = 30, book_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_runs(limit=limit, book_id=book_id)

    def save_run_output(
        self,
        *,
        run_id: str,
        agent: str,
        output_type: str,
        title: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        self.store.save_run_output(
            run_id=run_id,
            agent=agent,
            output_type=output_type,
            title=title,
            payload=payload,
            created_at=created_at,
        )

    def list_run_outputs(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_run_outputs(run_id)

    def save_critic_report(self, report: CriticReport, book_id: str | None = None) -> None:
        self.store.save_critic_report(report, book_id=book_id)

    def load_critic_report(self, report_id: str) -> CriticReport | None:
        return self.store.load_critic_report(report_id)

    def load_latest_critic_report(self, book_id: str) -> CriticReport | None:
        return self.store.load_latest_critic_report(book_id)

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
