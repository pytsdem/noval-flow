from __future__ import annotations

import json

from novel_flow.models.schemas import ActualChapterSummary
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.tools._base import LLMChapterTool


class SummarizeActualChapterTool(LLMChapterTool):
    name = "summarize_actual_chapter"

    def __init__(self, *, llm_client, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(llm_client=llm_client, prompt_library=prompt_library)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/summarize_actual_chapter.txt",
            chapter_text=payload["chapter_text"],
            chapter_brief_json=payload["chapter_brief_json"],
            chapter_payload_text=payload["chapter_payload_text"],
            time_anchor_text=payload.get("time_anchor_text", ""),
            active_twists_json=json.dumps(payload.get("active_twists", []), ensure_ascii=False, indent=2),
            story_lines_json=json.dumps(payload.get("active_story_lines", []), ensure_ascii=False, indent=2),
        )
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=ActualChapterSummary,
        )
