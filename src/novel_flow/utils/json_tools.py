from __future__ import annotations

import json
import re


def _cleanup_json_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r",(?=\s*[}\]])", "", cleaned)
    return cleaned


def extract_json_object(raw_text: str) -> dict[str, object]:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        cleaned = _cleanup_json_text(candidate)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("Unable to parse JSON object", text, 0)
