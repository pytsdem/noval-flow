from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.llm.executor import run_llm_text
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_tools import extract_json_object


def safe_json_generate(
    llm_client: LLMClient,
    messages: list[LLMMessage],
    *,
    schema_name: str,
    schema_model: type[BaseModel] | None = None,
    repair_prompt_path: str = "writer/repair_json.txt",
    max_retries: int = 2,
) -> dict[str, Any]:
    prompt_library = PromptLibrary()
    schema_descriptor = schema_name
    if schema_model is not None:
        schema_descriptor = (
            f"{schema_name}\n"
            f"{json.dumps(schema_model.model_json_schema(), ensure_ascii=False, indent=2)}"
        )

    def _repair(bad_json: str) -> dict[str, Any]:
        repair_prompt = prompt_library.render(
            repair_prompt_path,
            schema_name=schema_descriptor,
            bad_json=bad_json,
        )
        repair_messages = [message for message in messages if message.role == "system"]
        repair_messages.append(LLMMessage(role="user", content=repair_prompt))
        repaired_raw = run_llm_text(llm_client, repair_messages, temperature=0.0)
        return extract_json_object(repaired_raw)

    raw = run_llm_text(llm_client, messages, temperature=0.2)
    parse_error: Exception | None = None
    parsed: dict[str, Any] | None = None
    for attempt in range(max_retries + 1):
        try:
            candidate = parsed if parsed is not None else extract_json_object(raw)
            if schema_model is None:
                return candidate
            validated = schema_model.model_validate(candidate)
            return validated.model_dump(mode="json")
        except ValidationError as exc:
            parse_error = exc
            if schema_model is None or attempt >= max_retries:
                break
            parsed = _repair(json.dumps(candidate, ensure_ascii=False, indent=2))
            raw = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception as exc:
            parse_error = exc
            if attempt >= max_retries:
                break
            parsed = _repair(raw)
            raw = json.dumps(parsed, ensure_ascii=False, indent=2)

    raise ValueError(f"{schema_name} JSON 生成失败：{parse_error}") from parse_error
