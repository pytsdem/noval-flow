from __future__ import annotations

from novel_flow.models.schemas import EvidenceReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewInstructionComplianceTool(LLMChapterTool):
    name = "review_instruction_compliance"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt("writer/review_instruction_compliance.txt", **payload)
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=EvidenceReviewPayload,
        )
