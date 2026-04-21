from __future__ import annotations

from novel_flow.models.schemas import FormatAdjustmentPayload
from novel_flow.tools._base import LLMChapterTool


class FormatAdjustmentSuggestionTool(LLMChapterTool):
    name = "format_adjustment_suggestion"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        raw = str(payload.get("final_polished_text", "") or "")
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = [item.strip() for item in text.split("\n") if item.strip()]
        adjusted: list[str] = []
        format_issues: list[str] = []
        for paragraph in paragraphs:
            clean = " ".join(paragraph.split())
            if len(clean) > 180:
                split_parts = []
                buffer = ""
                for char in clean:
                    buffer += char
                    if len(buffer) >= 90 and char in "。！？；":
                        split_parts.append(buffer.strip())
                        buffer = ""
                if buffer.strip():
                    split_parts.append(buffer.strip())
                adjusted.extend(part for part in split_parts if part)
                format_issues.append("拆分了超长自然段。")
            else:
                adjusted.append(clean)
        final_text = "\n\n".join(adjusted).strip()
        if final_text != raw.strip():
            format_issues.append("清理了空白并统一了段落间距。")
        return FormatAdjustmentPayload.model_validate(
            {
                "text": final_text,
                "format_issues": list(dict.fromkeys(format_issues)),
            }
        ).model_dump(mode="json")
