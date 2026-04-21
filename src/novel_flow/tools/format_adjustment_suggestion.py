from __future__ import annotations

from novel_flow.models.schemas import FormatAdjustmentPayload
from novel_flow.tools._base import LLMChapterTool


SPLIT_PUNCTUATION = "\u3002\uff01\uff1f\uff1b"
SOFT_SPLIT_PUNCTUATION = "\uff0c\u3001\uff1a"
DIALOGUE_CLOSERS = "\u201d\u300d\u300f"


class FormatAdjustmentSuggestionTool(LLMChapterTool):
    name = "format_adjustment_suggestion"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        raw = str(payload.get("final_polished_text", "") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        paragraphs = self._extract_paragraphs(raw)
        adjusted: list[str] = []
        format_issues: list[str] = []

        for paragraph in paragraphs:
            cleaned = paragraph.strip()
            if not cleaned:
                continue
            normalized_parts = self._normalize_paragraph(cleaned)
            adjusted.extend(normalized_parts)
            if len(normalized_parts) > 1:
                if len(cleaned) > 180:
                    format_issues.append("Split one overlong paragraph without changing story facts.")
                else:
                    format_issues.append("Separated a dense paragraph to keep dialogue and action readable.")
            elif len(cleaned) > 180:
                format_issues.append("One paragraph still looks long after conservative formatting.")

        final_text = "\n\n".join(adjusted).strip()
        if final_text != raw:
            format_issues.append("Normalized blank lines and preserved readable paragraph rhythm.")
        return FormatAdjustmentPayload.model_validate(
            {
                "text": final_text,
                "format_issues": list(dict.fromkeys(format_issues)),
            }
        ).model_dump(mode="json")

    @staticmethod
    def _extract_paragraphs(text: str) -> list[str]:
        if not text:
            return []
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        if chunks:
            return chunks
        return [line.strip() for line in text.split("\n") if line.strip()]

    @classmethod
    def _normalize_paragraph(cls, paragraph: str) -> list[str]:
        dialogue_parts = cls._split_dialogue_paragraph(paragraph)
        normalized: list[str] = []
        for item in dialogue_parts:
            cleaned = item.strip()
            if not cleaned:
                continue
            if len(cleaned) > 180:
                normalized.extend(cls._split_long_paragraph(cleaned))
            else:
                normalized.append(cleaned)
        return normalized or [paragraph]

    @classmethod
    def _split_dialogue_paragraph(cls, paragraph: str) -> list[str]:
        if len(paragraph) <= 120 or not any(char in paragraph for char in DIALOGUE_CLOSERS):
            return [paragraph]
        parts: list[str] = []
        current = ""
        for index, char in enumerate(paragraph):
            current += char
            if char not in DIALOGUE_CLOSERS:
                continue
            has_more_text = bool(paragraph[index + 1 :].strip())
            if has_more_text:
                parts.append(current.strip())
                current = ""
        if current.strip():
            parts.append(current.strip())
        return parts if len(parts) > 1 else [paragraph]

    @classmethod
    def _split_long_paragraph(cls, paragraph: str) -> list[str]:
        parts: list[str] = []
        current = ""
        for char in paragraph:
            current += char
            if len(current) >= 90 and char in SPLIT_PUNCTUATION:
                parts.append(current.strip())
                current = ""
                continue
            if len(current) >= 120 and char in SOFT_SPLIT_PUNCTUATION:
                parts.append(current.strip())
                current = ""
        if current.strip():
            parts.append(current.strip())
        if len(parts) <= 1:
            midpoint = len(paragraph) // 2
            left = paragraph[:midpoint].strip()
            right = paragraph[midpoint:].strip()
            return [item for item in [left, right] if item]
        return parts
