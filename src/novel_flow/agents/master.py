from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from novel_flow.agents.base import BaseAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.models.schemas import (
    AgentResult,
    BlockPatchVersion,
    BookBlueprint,
    BookDocument,
    CriticReport,
    PatchInstruction,
    ResearchReport,
    WorkflowStage,
    WorkflowState,
)


class MasterAgent(BaseAgent):
    def __init__(
        self,
        memory_agent: MemoryAgent,
        research_agent: ResearchAgent,
        writer_agent: WriterAgent,
        critic_agent: CriticAgent,
    ) -> None:
        super().__init__(name="MasterAgent")
        self.memory_agent = memory_agent
        self.research_agent = research_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent

    def run_mock_pipeline(self, query: str) -> dict[str, Any]:
        run_id = f"run_{uuid4().hex[:10]}"
        state = WorkflowState(run_id=run_id, stage=WorkflowStage.RESEARCH, context={"query": query})
        self._save_state(state)

        research_report = self.research_agent.collect_report(query=query)
        self.memory_agent.save_research_report(research_report)

        self._transition(state, WorkflowStage.PLANNING, latest_research_report_id=research_report.report_id)
        blueprint = self.writer_agent.build_blueprint(research_query=query)
        book_before_patch = self.writer_agent.create_book(blueprint=blueprint, source_query=query)
        self.memory_agent.save_book(book_before_patch)

        self._transition(state, WorkflowStage.WRITING, current_book_id=book_before_patch.id)
        critic_report = self.critic_agent.review_book(book=book_before_patch)
        self.memory_agent.save_critic_report(critic_report)

        self._transition(state, WorkflowStage.CRITIQUE, latest_critic_report_id=critic_report.report_id)

        patch_instruction: PatchInstruction | None = None
        book_after_patch = book_before_patch
        patch_version: BlockPatchVersion | None = None
        if critic_report.issues:
            patch_instruction = self.critic_agent.build_patch_instruction(critic_report.issues[0])
            book_after_patch, patch_payload = self.writer_agent.patch_block(book=book_before_patch, instruction=patch_instruction)
            patch_version = BlockPatchVersion.model_validate(patch_payload["patch_version"])
            self.memory_agent.save_patch_version(patch_version)
            self.memory_agent.save_book(book_after_patch)
            self._transition(state, WorkflowStage.PATCHING)

        self._transition(state, WorkflowStage.COMPLETE)
        return {
            "run_id": run_id,
            "research_report": research_report,
            "blueprint": blueprint,
            "book_before_patch": book_before_patch,
            "critic_report": critic_report,
            "patch_instruction": patch_instruction,
            "patch_version": patch_version,
            "book_after_patch": book_after_patch,
            "state": state,
        }

    def _transition(self, state: WorkflowState, stage: WorkflowStage, **extra: Any) -> None:
        state.stage = stage
        state.updated_at = datetime.now(timezone.utc)
        for key, value in extra.items():
            setattr(state, key, value)
        self._save_state(state)

    def _save_state(self, state: WorkflowState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        self.memory_agent.save_state(state)

    def run(self, **kwargs: Any) -> AgentResult:
        query = str(kwargs.get("query", "知乎体高热度都市情感反转"))
        result = self.run_mock_pipeline(query=query)
        research_report: ResearchReport = result["research_report"]
        blueprint: BookBlueprint = result["blueprint"]
        critic_report: CriticReport = result["critic_report"]
        book: BookDocument = result["book_after_patch"]
        return AgentResult(
            agent_name=self.name,
            success=True,
            message="Mock pipeline completed.",
            payload={
                "run_id": result["run_id"],
                "research_report": research_report.model_dump(mode="json"),
                "blueprint": blueprint.model_dump(mode="json"),
                "critic_report": critic_report.model_dump(mode="json"),
                "book": book.model_dump(mode="json"),
                "workflow_state": result["state"].model_dump(mode="json"),
            },
        )
