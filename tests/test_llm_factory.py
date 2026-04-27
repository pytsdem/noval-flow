from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from novel_flow.config import Settings
from novel_flow.llm.factory import FallbackLLMClient, build_llm_client
from novel_flow.llm.doubao import DoubaoLLMClient
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

    def test_codex_prefers_deepseek_fallback_over_doubao(self) -> None:
        client = build_llm_client(
            Settings(
                llm_provider="codex",
                codex_exe="codex",
                deepseek_api_key="deepseek-key",
                deepseek_model="deepseek-v4-pro",
                doubao_api_key="doubao-key",
                doubao_model="doubao-endpoint",
            )
        )

        self.assertIsInstance(client, FallbackLLMClient)
        self.assertEqual(client.fallback_name, "deepseek")
        self.assertIsInstance(client.fallback, OpenAILLMClient)


class SettingsDefaultsTests(unittest.TestCase):
    def test_settings_default_to_deepseek_v4_pro(self) -> None:
        settings = Settings()

        self.assertEqual(settings.llm_provider, "deepseek")
        self.assertEqual(settings.deepseek_model, "deepseek-v4-pro")

    def test_from_env_defaults_to_deepseek_v4_pro(self) -> None:
        previous = {key: os.environ.get(key) for key in ("LLM_PROVIDER", "DEEPSEEK_MODEL")}
        try:
            os.environ.pop("LLM_PROVIDER", None)
            os.environ.pop("DEEPSEEK_MODEL", None)
            with patch("dotenv.load_dotenv", return_value=False), patch.object(Settings, "_load_dotenv_fallback", return_value=None):
                settings = Settings.from_env(database_path="data/test.db")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.llm_provider, "deepseek")
        self.assertEqual(settings.deepseek_model, "deepseek-v4-pro")


if __name__ == "__main__":
    unittest.main()
