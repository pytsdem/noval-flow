from __future__ import annotations

from novel_flow.models.schemas import HumanityReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewHumanityTool(LLMChapterTool):
    name = "review_humanity"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt("writer/review_humanity.txt", **payload)
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=HumanityReviewPayload,
        )
