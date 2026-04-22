from __future__ import annotations

from novel_flow.models.schemas import ChapterTargetedReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewProseAndHumanityTool(LLMChapterTool):
    name = "review_prose_and_humanity"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt("writer/review_prose_and_humanity.txt", **payload)
        raw = self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=ChapterTargetedReviewPayload,
        )
        result = ChapterTargetedReviewPayload.model_validate(raw).model_dump(mode="json", by_alias=True)
        result["passed"] = bool(result.get("pass"))
        return result
