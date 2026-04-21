from __future__ import annotations

from novel_flow.models.schemas import EvidenceReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewCharacterIntegrityTool(LLMChapterTool):
    name = "review_character_integrity"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt_payload = dict(payload)
        prompt_payload.setdefault("review_scope_text", "Review the whole chapter.")
        prompt_payload.setdefault("block_card_text", "")
        prompt = self.render_prompt(
            "writer/review_character_integrity.txt",
            **prompt_payload,
        )
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=EvidenceReviewPayload,
        )
