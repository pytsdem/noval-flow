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
        llm_pass = bool(result.get("pass"))
        remaining = list(result.get("remaining_issues") or [])
        introduced = list(result.get("newly_introduced_issues") or [])
        recommendation = str(result.get("recommendation") or "").strip()
        deterministic_pass = (
            llm_pass
            and not remaining
            and not introduced
            and not self._recommendation_requires_followup(recommendation)
        )
        result["llm_pass"] = llm_pass
        result["pass"] = deterministic_pass
        result["passed"] = deterministic_pass
        return result

    @staticmethod
    def _recommendation_requires_followup(recommendation: str) -> bool:
        normalized = str(recommendation or "").strip().lower()
        if not normalized:
            return False
        followup_markers = (
            "建议补",
            "继续补",
            "再补",
            "补一次",
            "继续 patch",
            "another patch",
            "retry patch",
            "patch again",
            "suggest deep",
            "切到 deep",
            "建议切到 deep",
            "need another patch",
        )
        return any(marker in normalized for marker in followup_markers)
