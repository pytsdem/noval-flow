from __future__ import annotations

from dataclasses import dataclass

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.prompting.templates import PromptLibrary


def build_messages(*, system_prompt: str, prompt: str) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=prompt),
    ]


def run_llm_text(
    llm_client: LLMClient,
    messages: list[LLMMessage],
    *,
    temperature: float = 0.7,
    strip: bool = True,
) -> str:
    response = llm_client.generate(messages=messages, temperature=temperature)
    return response.strip() if strip else response


@dataclass(slots=True)
class PromptLLMExecutor:
    llm_client: LLMClient
    prompt_library: PromptLibrary

    def build_prompt_messages(self, *, system_path: str, prompt: str) -> list[LLMMessage]:
        return build_messages(system_prompt=self.prompt_library.load(system_path), prompt=prompt)

    def generate_prompt_text(
        self,
        *,
        system_path: str,
        prompt: str,
        temperature: float = 0.7,
        strip: bool = True,
    ) -> str:
        return run_llm_text(
            self.llm_client,
            self.build_prompt_messages(system_path=system_path, prompt=prompt),
            temperature=temperature,
            strip=strip,
        )
