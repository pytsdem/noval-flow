from __future__ import annotations

import re

from novel_flow.models.schemas import BlockQuickReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewBlockQuickTool(LLMChapterTool):
    name = "review_block_quick"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        block_text = str(payload.get("block_text", "") or "").strip()
        chapter_payload = str(payload.get("chapter_payload_text", "") or "")
        block_card = str(payload.get("block_card_text", "") or "")
        paragraph_warnings: list[str] = []
        issues: list[str] = []
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", block_text) if item.strip()]
        for index, paragraph in enumerate(paragraphs, start=1):
            if len(paragraph) > 180:
                paragraph_warnings.append(f"第 {index} 段过长，建议拆分。")
        too_outline_like = block_text.count("：") >= 4 and len(paragraphs) <= 2
        if too_outline_like:
            issues.append("文本过于像大纲归纳，现场感不足。")
        must_hide: list[str] = []
        in_must_hide = False
        for line in block_card.splitlines():
            stripped = line.strip()
            if stripped == "must_hide:":
                in_must_hide = True
                continue
            if stripped.endswith(":") and stripped != "must_hide:":
                in_must_hide = False
            if in_must_hide and stripped.startswith("- "):
                must_hide.append(stripped[2:].strip())
        leak_hits = [item for item in must_hide if item and item in block_text]
        if leak_hits:
            issues.append(f"疑似触及必须隐藏信息：{'；'.join(leak_hits[:3])}")
        if "Forbidden content:" in chapter_payload:
            forbidden_lines = [
                line[2:].strip()
                for line in chapter_payload.splitlines()
                if line.startswith("- ")
            ]
            exact_hits = [item for item in forbidden_lines if item and item in block_text]
            if exact_hits:
                issues.append(f"疑似直接复现禁写内容：{'；'.join(exact_hits[:3])}")
        purpose_completed = len(block_text) >= 60
        if not purpose_completed:
            issues.append("block 内容偏少，可能还没有完成当前 purpose。")
        rewrite_needed = bool(paragraph_warnings or too_outline_like or leak_hits)
        leak_risk = "high" if leak_hits else "low"
        return BlockQuickReviewPayload.model_validate(
            {
                "passed": not rewrite_needed,
                "purpose_completed": purpose_completed,
                "leak_risk": leak_risk,
                "time_conflict": False,
                "too_outline_like": too_outline_like,
                "paragraph_warnings": paragraph_warnings,
                "issues": issues,
                "rewrite_needed": rewrite_needed,
                "rewrite_guidance": "把长段拆开，保留当前 block 目的，避免直接碰触 must_hide 信息。" if rewrite_needed else "",
            }
        ).model_dump(mode="json")
