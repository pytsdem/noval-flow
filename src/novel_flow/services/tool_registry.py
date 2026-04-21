from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from novel_flow.llm.base import LLMClient
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.tools.final_judge import FinalJudgeTool
from novel_flow.tools.final_polish import FinalPolishTool
from novel_flow.tools.review_chapter_engine import ReviewChapterEngineTool
from novel_flow.tools.review_clue_origin import ReviewClueOriginTool
from novel_flow.tools.review_continuity import ReviewContinuityTool
from novel_flow.tools.review_hook_appearance import ReviewHookAppearanceTool
from novel_flow.tools.review_instruction import ReviewInstructionComplianceTool
from novel_flow.tools.review_plot_logic import ReviewPlotLogicTool
from novel_flow.tools.review_prose_quality import ReviewProseQualityTool
from novel_flow.tools.review_reveal_leak import ReviewRevealLeakTool
from novel_flow.tools.rewrite_by_plan import RewriteByPlanTool
from novel_flow.tools.summarize_actual_chapter import SummarizeActualChapterTool


class ToolProtocol(Protocol):
    name: str

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class ToolRegistry:
    tools: dict[str, ToolProtocol]

    @classmethod
    def build_default(cls, *, llm_client: LLMClient, prompt_library: PromptLibrary | None = None) -> "ToolRegistry":
        library = prompt_library or PromptLibrary()
        tool_list: list[ToolProtocol] = [
            ReviewInstructionComplianceTool(llm_client=llm_client),
            ReviewProseQualityTool(llm_client=llm_client),
            ReviewPlotLogicTool(llm_client=llm_client),
            ReviewRevealLeakTool(llm_client=llm_client),
            ReviewClueOriginTool(llm_client=llm_client),
            ReviewContinuityTool(llm_client=llm_client),
            ReviewHookAppearanceTool(llm_client=llm_client, prompt_library=library),
            ReviewChapterEngineTool(llm_client=llm_client, prompt_library=library),
            RewriteByPlanTool(llm_client=llm_client),
            FinalPolishTool(llm_client=llm_client, prompt_library=library),
            SummarizeActualChapterTool(llm_client=llm_client, prompt_library=library),
            FinalJudgeTool(),
        ]
        return cls(tools={tool.name: tool for tool in tool_list})

    def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.tools:
            raise KeyError(f"Unknown tool: {tool_name}")
        return self.tools[tool_name].run(payload)
