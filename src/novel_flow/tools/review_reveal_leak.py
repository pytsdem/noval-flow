from __future__ import annotations

import json

from novel_flow.models.schemas import BinaryReviewPayload
from novel_flow.tools._base import LLMChapterTool


class ReviewRevealLeakTool(LLMChapterTool):
    name = "review_reveal_leak"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/review_reveal_leak.txt",
            chapter_payload_text=payload["chapter_payload_text"],
            active_twists_json=json.dumps(payload.get("active_twists", []), ensure_ascii=False, indent=2),
            chapter_text=payload["chapter_text"],
        )
        return self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=BinaryReviewPayload,
        )
