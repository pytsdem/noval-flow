from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from novel_flow.agents.base import BaseAgent
from novel_flow.constants.mock_data import MOCK_BLUEPRINT_SEED
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    AgentResult,
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterPlan,
    CharacterCard,
    PatchInstruction,
    PatchOperation,
    Scene,
    StoryPremise,
    TextBlock,
    Volume,
    WriterMode,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.patcher import PatchExecutor
from novel_flow.utils.json_tools import extract_json_object


class WriterAgent(BaseAgent):
    def __init__(
        self,
        llm_client: LLMClient,
        patch_executor: PatchExecutor,
        prompt_library: PromptLibrary | None = None,
    ) -> None:
        super().__init__(name="WriterAgent")
        self.llm_client = llm_client
        self.patch_executor = patch_executor
        self.prompt_library = prompt_library or PromptLibrary()

    def build_blueprint(self, research_query: str) -> BookBlueprint:
        prompt = self.prompt_library.render(
            "writer/blueprint.txt",
            research_query=research_query,
            seed_json=json.dumps(MOCK_BLUEPRINT_SEED, ensure_ascii=False, indent=2),
        )
        try:
            raw = self._generate_block_text(prompt=prompt)
            parsed = extract_json_object(raw)
            premise = StoryPremise.model_validate(parsed["premise"])
            characters = [CharacterCard.model_validate(item) for item in parsed["characters"]]
            chapter_plans = [ChapterPlan.model_validate(item) for item in parsed["chapter_plans"]]
            volume_titles = [str(item) for item in parsed["volume_titles"]]
        except Exception as exc:
            self.logger.warning("Blueprint generation fell back to mock seed: %s", exc)
            premise = StoryPremise.model_validate(MOCK_BLUEPRINT_SEED["premise"])
            characters = [CharacterCard.model_validate(item) for item in MOCK_BLUEPRINT_SEED["characters"]]
            chapter_plans = [ChapterPlan.model_validate(item) for item in MOCK_BLUEPRINT_SEED["chapter_plans"]]
            volume_titles = [str(item) for item in MOCK_BLUEPRINT_SEED["volume_titles"]]
        return BookBlueprint(
            blueprint_id=f"blueprint_{uuid4().hex[:10]}",
            premise=premise,
            characters=characters,
            volume_titles=volume_titles,
            chapter_plans=chapter_plans,
        )

    def create_book(self, blueprint: BookBlueprint, source_query: str) -> BookDocument:
        volume = Volume(
            id="vol_001",
            title=blueprint.volume_titles[0],
            summary="从婚礼羞辱到结盟反击的第一阶段。",
            chapters=[self._create_chapter(plan, blueprint.premise) for plan in blueprint.chapter_plans],
        )
        now = datetime.now(timezone.utc)
        return BookDocument(
            id=f"book_{uuid4().hex[:10]}",
            title=blueprint.premise.title,
            premise=blueprint.premise,
            characters=blueprint.characters,
            volumes=[volume],
            metadata={"target_words": 100000, "style": blueprint.premise.target_style, "query": source_query},
            created_at=now,
            updated_at=now,
        )

    def rewrite_unit(self, book: BookDocument, block_id: str, guidance: str) -> BookDocument:
        replacement = self._generate_block_text(
            prompt=self.prompt_library.render(
                "writer/rewrite_unit.txt",
                block_id=block_id,
                guidance=guidance,
            )
        )
        patched_book, _ = self.patch_executor.apply(
            book,
            PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation.REPLACE,
                reason=guidance,
                content=replacement,
            ),
        )
        return patched_book

    def patch_block(self, book: BookDocument, instruction: PatchInstruction) -> tuple[BookDocument, dict[str, Any]]:
        patched_book, version = self.patch_executor.apply(book, instruction)
        return patched_book, {"patch_version": version.model_dump(mode="json")}

    def expand(self, book: BookDocument, block_id: str, expansion_goal: str) -> BookDocument:
        addition = self._generate_block_text(
            prompt=self.prompt_library.render(
                "writer/expand.txt",
                block_id=block_id,
                expansion_goal=expansion_goal,
            )
        )
        patched_book, _ = self.patch_executor.apply(
            book,
            PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation.APPEND,
                reason=expansion_goal,
                content=addition,
            ),
        )
        return patched_book

    def run(self, **kwargs: Any) -> AgentResult:
        mode = WriterMode(kwargs["mode"])
        if mode == WriterMode.CREATE:
            blueprint = kwargs["blueprint"]
            book = self.create_book(blueprint=blueprint, source_query=kwargs.get("source_query", ""))
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Created initial book structure.",
                payload={"book": book.model_dump(mode="json")},
            )
        if mode == WriterMode.REWRITE_UNIT:
            book = kwargs["book"]
            rewritten_book = self.rewrite_unit(book=book, block_id=kwargs["block_id"], guidance=kwargs["guidance"])
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Rewrote target block.",
                payload={"book": rewritten_book.model_dump(mode="json")},
            )
        if mode == WriterMode.PATCH_BLOCK:
            book = kwargs["book"]
            patched_book, extra = self.patch_block(book=book, instruction=kwargs["instruction"])
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Patched target block.",
                payload={"book": patched_book.model_dump(mode="json"), **extra},
            )
        if mode == WriterMode.EXPAND:
            book = kwargs["book"]
            expanded_book = self.expand(book=book, block_id=kwargs["block_id"], expansion_goal=kwargs["expansion_goal"])
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Expanded target block.",
                payload={"book": expanded_book.model_dump(mode="json")},
            )
        raise ValueError(f"Unsupported writer mode: {mode}")

    def _create_chapter(self, plan: ChapterPlan, premise: StoryPremise) -> Chapter:
        scenes: list[Scene] = []
        for scene_index in range(1, plan.planned_scene_count + 1):
            scene_id = f"{plan.chapter_id}.sc_{scene_index:03d}"
            blocks = [
                TextBlock(
                    id=f"{scene_id}.b001",
                    purpose="hook",
                    text=self._generate_block_text(
                        prompt=self.prompt_library.render(
                            "writer/create_hook.txt",
                            chapter_title=plan.title,
                            scene_index=scene_index,
                            high_concept=premise.high_concept,
                            chapter_objective=plan.objective,
                            chapter_tension=plan.tension,
                        )
                    ),
                ),
                TextBlock(
                    id=f"{scene_id}.b002",
                    purpose="turn",
                    text=self._generate_block_text(
                        prompt=self.prompt_library.render(
                            "writer/create_turn.txt",
                            chapter_title=plan.title,
                            chapter_objective=plan.objective,
                            chapter_cliffhanger=plan.cliffhanger,
                        )
                    ),
                ),
            ]
            scenes.append(
                Scene(
                    id=scene_id,
                    title=f"{plan.title}-场景{scene_index}",
                    summary=f"围绕 {plan.objective} 推进冲突。",
                    blocks=blocks,
                )
            )
        return Chapter(id=plan.chapter_id, title=plan.title, summary=plan.objective, scenes=scenes)

    def _generate_block_text(self, prompt: str) -> str:
        # create / rewrite_unit / expand 都会在这里真正调用大模型
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("writer/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        return self.llm_client.generate(messages=messages, temperature=0.8).strip()
