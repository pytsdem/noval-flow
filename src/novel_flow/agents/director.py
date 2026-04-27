from __future__ import annotations

import json
from typing import Any

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient
from novel_flow.llm.executor import PromptLLMExecutor
from novel_flow.models.schemas import AgentResult, DirectorAction, DirectorDecision, ToolObservation
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_tools import extract_json_object


class DirectorAgent(BaseAgent):
    def __init__(self, llm_client: LLMClient, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(name="DirectorAgent")
        self.llm_client = llm_client
        self.prompt_library = prompt_library or PromptLibrary()
        self.llm_executor = PromptLLMExecutor(llm_client=self.llm_client, prompt_library=self.prompt_library)

    def decide(
        self,
        *,
        goal: str,
        session_summary: dict[str, Any],
        observations: list[ToolObservation],
        allowed_actions: list[DirectorAction],
    ) -> DirectorDecision:
        ev.emit("agent_start", agent=self.name, title="Decide next action", allowed_actions=[item.value for item in allowed_actions])
        prompt = self.prompt_library.render(
            "director/decide.txt",
            goal=goal,
            session_json=json.dumps(session_summary, ensure_ascii=False, indent=2),
            observations_json=json.dumps([item.model_dump(mode="json") for item in observations[-6:]], ensure_ascii=False, indent=2),
            allowed_actions_json=json.dumps([item.value for item in allowed_actions], ensure_ascii=False, indent=2),
        )
        try:
            parsed = extract_json_object(self._generate_json_text(prompt))
            action = DirectorAction(str(parsed.get("action", "")))
            if action not in allowed_actions:
                raise ValueError(f"Unsupported action returned by director: {action}")
            decision = DirectorDecision(
                action=action,
                reasoning=str(parsed.get("reasoning", "")),
                info_gaps=[str(item) for item in parsed.get("info_gaps", [])],
                tool_input=dict(parsed.get("tool_input", {})),
            )
        except Exception:
            decision = self._fallback_decision(goal=goal, session_summary=session_summary, allowed_actions=allowed_actions)

        ev.emit(
            "director_decision",
            agent=self.name,
            title=f"Director chose {decision.action.value}",
            action=decision.action.value,
            reasoning=decision.reasoning,
        )
        return decision

    def run(self, **kwargs: Any) -> AgentResult:
        observations = [ToolObservation.model_validate(item) for item in kwargs.get("observations", [])]
        allowed_actions = [DirectorAction(item) for item in kwargs.get("allowed_actions", [])]
        decision = self.decide(
            goal=str(kwargs["goal"]),
            session_summary=dict(kwargs["session_summary"]),
            observations=observations,
            allowed_actions=allowed_actions,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            message=f"Director chose {decision.action.value}.",
            payload={"decision": decision.model_dump(mode="json")},
        )

    def _generate_json_text(self, prompt: str) -> str:
        return self.llm_executor.generate_prompt_text(
            system_path="director/system.txt",
            prompt=prompt,
            temperature=0.2,
        )

    @staticmethod
    def _fallback_decision(
        *,
        goal: str,
        session_summary: dict[str, Any],
        allowed_actions: list[DirectorAction],
    ) -> DirectorDecision:
        action = allowed_actions[0]
        tool_input: dict[str, Any] = {}
        if action == DirectorAction.RETRIEVE_REFERENCES:
            tool_input = {
                "stage": str(session_summary.get("stage_hint", "planning")),
                "query": str(session_summary.get("query") or goal),
                "focus": list(session_summary.get("focus_points", [])),
            }
        return DirectorDecision(
            action=action,
            reasoning="Fallback decision based on current session state.",
            info_gaps=[],
            tool_input=tool_input,
        )
