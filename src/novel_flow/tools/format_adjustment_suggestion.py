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
                    format_issues.append("Split one paragraph over 180 Chinese characters at a dialogue, action, or reaction boundary when possible.")
                else:
                    format_issues.append("Separated a dense paragraph to keep dialogue or reaction beats readable without changing plot facts.")
            elif len(cleaned) > 180:
                format_issues.append("One paragraph still looks long after conservative formatting.")

        final_text = "\n\n".join(adjusted).strip()
        if final_text != raw:
            format_issues.append("Normalized blank lines while preserving short-paragraph rhythm and emotional pacing.")
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
        remaining = paragraph.strip()
        while remaining:
            if len(remaining) <= 180:
                parts.append(remaining)
                break
            split_index = cls._choose_split_index(remaining)
            if split_index <= 0 or split_index >= len(remaining):
                midpoint = len(remaining) // 2
                left = remaining[:midpoint].strip()
                right = remaining[midpoint:].strip()
                parts.extend(item for item in [left, right] if item)
                break
            head = remaining[:split_index].strip()
            remaining = remaining[split_index:].strip()
            if head:
                parts.append(head)
        if len(parts) <= 1:
            midpoint = len(paragraph) // 2
            left = paragraph[:midpoint].strip()
            right = paragraph[midpoint:].strip()
            return [item for item in [left, right] if item]
        return parts

    @classmethod
    def _choose_split_index(cls, paragraph: str) -> int:
        preferred_min = 60
        preferred_max = 120
        fallback_max = 160
        candidates: list[tuple[int, int]] = []
        for index, char in enumerate(paragraph):
            cut = index + 1
            if cut < preferred_min:
                continue
            if char in DIALOGUE_CLOSERS and paragraph[cut:].strip():
                candidates.append((0, cut))
            elif char in SPLIT_PUNCTUATION:
                candidates.append((1, cut))
            elif char in SOFT_SPLIT_PUNCTUATION:
                candidates.append((2, cut))
        for priority in (0, 1, 2):
            preferred = [cut for score, cut in candidates if score == priority and preferred_min <= cut <= preferred_max]
            if preferred:
                return preferred[-1]
        for priority in (0, 1, 2):
            fallback = [cut for score, cut in candidates if score == priority and preferred_min <= cut <= fallback_max]
            if fallback:
                return fallback[-1]
        return 0
