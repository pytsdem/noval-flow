from __future__ import annotations

from novel_flow.models.schemas import PatchJudgePayload
from novel_flow.tools._base import LLMChapterTool


class JudgePatchedChapterTool(LLMChapterTool):
    name = "judge_patched_chapter"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/judge_patched_chapter.txt",
            merged_chapter_text=payload.get("merged_chapter_text", ""),
            patch_plan_json=payload.get("patch_plan_json", "{}"),
            patched_block_contexts_json=payload.get("patched_block_contexts_json", "[]"),
            minimal_context_text=payload.get("minimal_context_text", ""),
        )
        raw = self.generate_json(
            prompt=prompt,
            schema_name=self.name,
            schema_model=PatchJudgePayload,
        )
        result = PatchJudgePayload.model_validate(raw).model_dump(mode="json", by_alias=True)
        result["passed"] = bool(result.get("pass"))
        return result
