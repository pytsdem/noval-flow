from __future__ import annotations

from novel_flow.models.schemas import BinaryReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewClueOriginTool(LLMChapterTool):
    name = "review_clue_origin"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt("writer/review_clue_origin.txt", **payload)
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=BinaryReviewPayload,
        )
