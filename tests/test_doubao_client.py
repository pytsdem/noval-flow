from __future__ import annotations

import unittest
from unittest import mock

import httpx

from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMMessage
from novel_flow.llm.doubao import DoubaoLLMClient


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self) -> list[str]:
        return list(self._lines)


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamingResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeStreamingResponse:
        return self._response

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class DoubaoLLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = DoubaoLLMClient(
            api_key="test-key",
            model="doubao-test-model",
            base_url="https://example.invalid/api/v3",
        )
        self.messages = [LLMMessage(role="user", content="请写一句测试文本")]

    def test_generate_retries_once_after_read_timeout(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_stream(method: str, url: str, **kwargs: object):
            calls.append({"method": method, "url": url, **kwargs})
            if len(calls) == 1:
                raise httpx.ReadTimeout("timed out")
            return _FakeStreamContext(
                _FakeStreamingResponse(
                    [
                        'data: {"choices":[{"delta":{"content":"测试"}}]}',
                        'data: {"choices":[{"delta":{"content":"通过"}}]}',
                        "data: [DONE]",
                    ]
                )
            )

        with mock.patch("novel_flow.llm.doubao.httpx.stream", side_effect=fake_stream):
            with mock.patch("novel_flow.llm.doubao.time.sleep", return_value=None):
                result = self.client.generate(self.messages)

        self.assertEqual(result, "测试通过")
        self.assertEqual(len(calls), 2)
        timeout = calls[0]["timeout"]
        self.assertIsInstance(timeout, httpx.Timeout)
        self.assertEqual(timeout.read, 900.0)

    def test_generate_raises_after_retry_budget_exhausted(self) -> None:
        with mock.patch(
            "novel_flow.llm.doubao.httpx.stream",
            side_effect=httpx.ReadTimeout("timed out"),
        ) as stream_mock:
            with mock.patch("novel_flow.llm.doubao.time.sleep", return_value=None):
                with self.assertRaises(AgentExecutionError) as ctx:
                    self.client.generate(self.messages)

        self.assertIn("timed out", str(ctx.exception))
        self.assertEqual(stream_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
