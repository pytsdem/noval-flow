from __future__ import annotations

from novel_flow.models.schemas import BinaryReviewPayload
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.tools._base import LLMChapterTool


class ReviewChapterEngineTool(LLMChapterTool):
    name = "review_chapter_engine"

    def __init__(self, *, llm_client, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(llm_client=llm_client, prompt_library=prompt_library)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "critic/check_chapter_engine.txt",
            chapter_payload_text=payload["chapter_payload_text"],
            chapter_brief_json=payload["chapter_brief_json"],
            scene_or_chapter_text=payload["chapter_text"],
        )
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=BinaryReviewPayload,
        )
