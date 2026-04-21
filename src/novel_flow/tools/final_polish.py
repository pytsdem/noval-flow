from __future__ import annotations

from novel_flow.prompting.templates import PromptLibrary
from novel_flow.tools._base import LLMChapterTool


class FinalPolishTool(LLMChapterTool):
    name = "final_polish"

    def __init__(self, *, llm_client, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(llm_client=llm_client, prompt_library=prompt_library)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        prompt = self.render_prompt(
            "writer/chapter_final_polish.txt",
            chapter_payload_text=payload["chapter_payload_text"],
            style_card_text=payload["style_card_text"],
            chapter_text=payload["chapter_text"],
        )
        return {"chapter_text": self.generate_text(prompt=prompt, temperature=0.45)}
