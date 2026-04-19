from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.exceptions import AgentExecutionError
from novel_flow.llm.base import LLMClient, LLMMessage


class CodexCLIClient(LLMClient):
    """LLM client that delegates to the local Codex CLI (codex exec)."""
    _STREAM_CHUNK_SIZE = 900
    _POLL_INTERVAL_SECONDS = 0.4
    _TIMEOUT_SECONDS = 300

    def __init__(self, exe: str = "codex", model: str | None = None) -> None:
        self.exe = exe
        self.model = model
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        ev.check_cancelled()
        call_id = f"llm_{uuid4().hex[:10]}"
        prompt = self._build_prompt(messages)
        prompt_preview = prompt[:600]
        ev.emit(
            "llm_prompt",
            agent="CodexCLI",
            title="发送 Prompt",
            call_id=call_id,
            preview=prompt_preview,
            total_chars=len(prompt),
        )

        output_file = Path(tempfile.mktemp(suffix=".txt"))
        cmd = [
            self.exe, "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox", "read-only",
            "-o", str(output_file),
            "-",  # read prompt from stdin
        ]
        if self.model:
            cmd.extend(["-m", self.model])

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
            )
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()

            stream_offset = 0
            deadline = time.monotonic() + self._TIMEOUT_SECONDS
            while True:
                ev.check_cancelled()
                stream_offset = self._emit_new_output_chunks(output_file, call_id=call_id, start_offset=stream_offset)

                return_code = proc.poll()
                if return_code is not None:
                    if return_code not in (0, None) and not output_file.exists():
                        raise AgentExecutionError(f"codex exec failed (exit {return_code}).")
                    break

                if time.monotonic() > deadline:
                    proc.kill()
                    raise AgentExecutionError(f"codex exec timed out after {self._TIMEOUT_SECONDS}s.")

                time.sleep(self._POLL_INTERVAL_SECONDS)

            self._emit_new_output_chunks(output_file, call_id=call_id, start_offset=stream_offset)
            result = output_file.read_text(encoding="utf-8").strip() if output_file.exists() else ""
            if not result:
                raise AgentExecutionError("codex exec returned empty output.")

            ev.check_cancelled()
            ev.emit(
                "llm_reply",
                agent="CodexCLI",
                title="收到回复",
                call_id=call_id,
                preview=result[:600],
                length=len(result),
            )
            sys.stderr.write(result[:200] + "\n")
            sys.stderr.flush()
            return result
        except FileNotFoundError as exc:
            raise AgentExecutionError(
                f"codex CLI not found at '{self.exe}'. Set CODEX_EXE in .env."
            ) from exc
        except Exception:
            if "proc" in locals() and proc.poll() is None:
                proc.kill()
            raise
        finally:
            output_file.unlink(missing_ok=True)

    @staticmethod
    def _build_prompt(messages: list[LLMMessage]) -> str:
        """Combine system + user messages into a single Codex prompt.

        Codex is a coding agent by default, so we explicitly instruct it
        to respond with plain text only — no shell commands, no file writes.
        """
        parts: list[str] = [
            "IMPORTANT: You are a creative writing assistant. "
            "Respond with plain text only. Do NOT run any shell commands, "
            "do NOT create or modify files. Output only the requested content.\n"
        ]
        for msg in messages:
            if msg.role == "system":
                parts.append(f"[System Instructions]\n{msg.content}\n")
            elif msg.role == "user":
                parts.append(f"[Request]\n{msg.content}\n")
            else:
                parts.append(f"[{msg.role}]\n{msg.content}\n")
        parts.append("[Respond with the requested content only, no explanations about what you are doing]")
        return "\n".join(parts)

    def _emit_new_output_chunks(self, output_file: Path, *, call_id: str, start_offset: int) -> int:
        if not output_file.exists():
            return start_offset
        text = output_file.read_text(encoding="utf-8", errors="ignore")
        if start_offset >= len(text):
            return len(text)
        delta = text[start_offset:]
        for index in range(0, len(delta), self._STREAM_CHUNK_SIZE):
            chunk = delta[index:index + self._STREAM_CHUNK_SIZE]
            if chunk:
                ev.emit(
                    "llm_stream",
                    agent="CodexCLI",
                    title="流式输出",
                    call_id=call_id,
                    preview=chunk,
                )
        return len(text)
