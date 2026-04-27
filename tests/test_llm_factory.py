from __future__ import annotations

import unittest

from novel_flow.config import Settings
from novel_flow.llm.factory import FallbackLLMClient, build_llm_client
from novel_flow.llm.openai import OpenAILLMClient


class LLMFactoryTests(unittest.TestCase):
    def test_build_llm_client_supports_deepseek_provider(self) -> None:
        client = build_llm_client(
            Settings(
                llm_provider="deepseek",
                deepseek_api_key="deepseek-key",
                deepseek_model="deepseek-v4-flash",
            )
        )

        self.assertIsInstance(client, OpenAILLMClient)
        self.assertEqual(client.api_key, "deepseek-key")
        self.assertEqual(client.model, "deepseek-v4-flash")
        self.assertEqual(client.base_url, "https://api.deepseek.com")

    def test_codex_can_fallback_to_deepseek(self) -> None:
        client = build_llm_client(
            Settings(
                llm_provider="codex",
                codex_exe="codex",
                deepseek_api_key="deepseek-key",
                deepseek_model="deepseek-v4-pro",
                deepseek_base_url="https://api.deepseek.com/v1",
            )
        )

        self.assertIsInstance(client, FallbackLLMClient)
        self.assertEqual(client.primary_name, "codex")
        self.assertEqual(client.fallback_name, "deepseek")
        self.assertIsInstance(client.fallback, OpenAILLMClient)
        self.assertEqual(client.fallback.model, "deepseek-v4-pro")
        self.assertEqual(client.fallback.base_url, "https://api.deepseek.com/v1")


if __name__ == "__main__":
    unittest.main()
