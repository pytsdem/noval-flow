from __future__ import annotations

from novel_flow.models.schemas import FormatAdjustmentPayload
from novel_flow.tools._base import LLMChapterTool


SPLIT_PUNCTUATION = "。！？；"
SOFT_SPLIT_PUNCTUATION = "，、："


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
            if len(cleaned) > 180:
                split_parts = self._split_long_paragraph(cleaned)
                if len(split_parts) > 1:
                    adjusted.extend(split_parts)
                    format_issues.append("Split one overlong paragraph without changing story facts.")
                else:
                    adjusted.append(cleaned)
                    format_issues.append("One paragraph still looks long after conservative formatting.")
            else:
                adjusted.append(cleaned)

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
