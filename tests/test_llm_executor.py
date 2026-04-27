from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.llm.executor import PromptLLMExecutor, build_messages, run_llm_text
from novel_flow.prompting.templates import PromptLibrary


class RecordingLLM(LLMClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("No fake response queued.")
        return self.responses.pop(0)


class LLMExecutorTests(unittest.TestCase):
    def test_build_messages_uses_standard_roles(self) -> None:
        messages = build_messages(system_prompt="system", prompt="user")

        self.assertEqual([message.role for message in messages], ["system", "user"])
        self.assertEqual([message.content for message in messages], ["system", "user"])

    def test_run_llm_text_strips_by_default(self) -> None:
        client = RecordingLLM(["  output  "])

        result = run_llm_text(client, build_messages(system_prompt="system", prompt="user"))

        self.assertEqual(result, "output")
        self.assertEqual(client.calls[0]["temperature"], 0.7)

    def test_prompt_executor_loads_system_prompt_from_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            prompt_dir = base_dir / "writer"
            prompt_dir.mkdir(parents=True)
            (prompt_dir / "system.txt").write_text("writer system", encoding="utf-8")
            library = PromptLibrary(base_dir=base_dir)
            client = RecordingLLM([" final text "])

            executor = PromptLLMExecutor(llm_client=client, prompt_library=library)
            result = executor.generate_prompt_text(
                system_path="writer/system.txt",
                prompt="chapter prompt",
                temperature=0.25,
            )

        self.assertEqual(result, "final text")
        self.assertEqual(client.calls[0]["temperature"], 0.25)
        messages = client.calls[0]["messages"]
        self.assertEqual([message.role for message in messages], ["system", "user"])
        self.assertEqual([message.content for message in messages], ["writer system", "chapter prompt"])


if __name__ == "__main__":
    unittest.main()
