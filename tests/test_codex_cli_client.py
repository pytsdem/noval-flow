from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMMessage
from novel_flow.llm.codex_cli import CodexCLIClient


class _BrokenPipeStdin:
    def write(self, _: str) -> None:
        raise BrokenPipeError()

    def close(self) -> None:
        return None


class _ImmediateStdin:
    def write(self, _: str) -> None:
        return None

    def close(self) -> None:
        return None


class _BrokenPipeProc:
    def __init__(self) -> None:
        self.stdin = _BrokenPipeStdin()

    def poll(self) -> int:
        return 1

    def kill(self) -> None:
        return None


class _ImmediateProc:
    def __init__(self, *, return_code: int = 1) -> None:
        self.stdin = _ImmediateStdin()
        self._return_code = return_code

    def poll(self) -> int:
        return self._return_code

    def kill(self) -> None:
        return None


class CodexCLIClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = CodexCLIClient(exe="codex", model="gpt-5.2")
        self.temp_root = Path.cwd() / "data" / "test_codex_cli_tmp"
        self.original_tmp_dir = CodexCLIClient._TMP_DIR
        CodexCLIClient._TMP_DIR = Path("data") / "test_codex_cli_tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        CodexCLIClient._TMP_DIR = self.original_tmp_dir
        for child in self.temp_root.glob("*"):
            child.unlink(missing_ok=True)
        if self.temp_root.exists():
            self.temp_root.rmdir()

    def test_reserve_temp_file_uses_workspace_data_dir(self) -> None:
        path = self.client._reserve_temp_file(suffix=".txt")
        self.assertEqual(path.parent, self.temp_root.resolve())
        self.assertTrue(path.exists())
        path.unlink(missing_ok=True)

    def test_generate_includes_stderr_when_stdin_breaks(self) -> None:
        messages = [LLMMessage(role="user", content="write a paragraph")]

        def fake_popen(cmd: list[str], **kwargs: object) -> _BrokenPipeProc:
            stderr_sink = kwargs["stderr"]
            stderr_sink.write("Error: access denied")
            stderr_sink.flush()
            return _BrokenPipeProc()

        with mock.patch("novel_flow.llm.codex_cli.subprocess.Popen", side_effect=fake_popen):
            with self.assertRaises(AgentExecutionError) as ctx:
                self.client.generate(messages)

        self.assertIn("closed stdin before reading the prompt", str(ctx.exception))
        self.assertIn("access denied", str(ctx.exception))

    def test_generate_accepts_output_file_even_with_nonzero_exit(self) -> None:
        messages = [LLMMessage(role="user", content="write a paragraph")]

        def fake_popen(cmd: list[str], **kwargs: object) -> _ImmediateProc:
            output_path = Path(cmd[cmd.index("-o") + 1])
            output_path.write_text("生成成功", encoding="utf-8")
            return _ImmediateProc(return_code=1)

        with mock.patch("novel_flow.llm.codex_cli.subprocess.Popen", side_effect=fake_popen):
            result = self.client.generate(messages)

        self.assertEqual(result, "生成成功")


if __name__ == "__main__":
    unittest.main()
