from __future__ import annotations

from pathlib import Path

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_generation import safe_json_generate

from evals.romance.models import RomanceEvalCase, RomanceJudgePayload
from evals.romance.genre_profiles import genre_profile_json, tone_profile_json


class RomanceChapterJudge:
    def __init__(self, llm_client: LLMClient) -> None:
        base_dir = Path(__file__).resolve().parents[1] / "prompts"
        self.llm_client = llm_client
        self.prompt_library = PromptLibrary(base_dir=base_dir)

    def judge(
        self,
        *,
        case: RomanceEvalCase,
        writer_context_json: str,
        chapter_execution_json: str,
        chapter_text: str,
    ) -> RomanceJudgePayload:
        prompt = self.prompt_library.render(
            "romance_chapter_judge.txt",
            case_json=case.model_dump_json(indent=2),
            writer_context_json=writer_context_json,
            chapter_execution_json=chapter_execution_json,
            chapter_text=chapter_text,
            genre_profile_json=genre_profile_json(case.genre_profile),
            tone_profile_json=tone_profile_json(case.tone_profile),
        )
        payload = safe_json_generate(
            self.llm_client,
            [
                LLMMessage(
                    role="system",
                    content=(
                        "You are a specialized Chinese romance-fiction evaluator. "
                        "Judge chapter reading pull, relationship movement, emotional aftertaste, "
                        "and serialized desirability. Return JSON only."
                    ),
                ),
                LLMMessage(role="user", content=prompt),
            ],
            schema_name="romance_chapter_judge",
            schema_model=RomanceJudgePayload,
        )
        return RomanceJudgePayload.model_validate(payload)
