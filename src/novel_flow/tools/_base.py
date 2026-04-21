from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.json_generation import safe_json_generate


DEFAULT_SYSTEM_PROMPT = (
    "You are a disciplined fiction-writing tool. "
    "Follow the requested schema exactly and return only the requested content."
)


@dataclass
class LLMChapterTool:
    llm_client: LLMClient
    prompt_library: PromptLibrary | None = None

    def messages(self, prompt: str, *, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=prompt),
        ]

    def generate_json(self, *, prompt: str, schema_name: str, schema_model: Any) -> dict[str, Any]:
        return safe_json_generate(
            self.llm_client,
            self.messages(prompt),
            schema_name=schema_name,
            schema_model=schema_model,
        )

    def generate_text(self, *, prompt: str, temperature: float = 0.4) -> str:
        return self.llm_client.generate(messages=self.messages(prompt), temperature=temperature).strip()

    def render_prompt(self, relative_path: str, **kwargs: Any) -> str:
        library = self.prompt_library or PromptLibrary()
        return library.render(relative_path, **kwargs)
