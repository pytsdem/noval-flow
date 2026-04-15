from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
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
        self._current_previous_chapter: Chapter | None = None
        self._current_characters: list[CharacterCard] = []

    def build_blueprint(self, research_query: str, style_request: str = "") -> BookBlueprint:
        ev.emit("agent_start", agent="WriterAgent", title="Build blueprint", query=research_query)
        prompt = self.prompt_library.render(
            "writer/blueprint.txt",
            research_query=research_query,
            style_request=style_request or "未指定",
            seed_json="{}",
        )
        raw = self._generate_block_text(prompt=prompt)
        parsed = extract_json_object(raw)
        premise = StoryPremise.model_validate(parsed["premise"])
        characters = [CharacterCard.model_validate(item) for item in parsed["characters"]]
        chapter_plans = [ChapterPlan.model_validate(item) for item in parsed["chapter_plans"]]
        volume_titles = [str(item) for item in parsed["volume_titles"]]
        blueprint = BookBlueprint(
            blueprint_id=f"blueprint_{uuid4().hex[:10]}",
            premise=premise,
            characters=characters,
            volume_titles=volume_titles,
            chapter_plans=chapter_plans,
        )
        ev.emit(
            "blueprint_ready",
            agent="WriterAgent",
            title=f"Blueprint ready: {premise.title}",
            premise_title=premise.title,
            chapter_count=len(chapter_plans),
            character_count=len(characters),
        )
        return blueprint

    def revise_concept(
        self,
        book: BookDocument,
        *,
        scope: str,
        target_id: str | None,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Revise concept: {scope}", book_id=book.id, target_id=target_id or "")
        prompt = self.prompt_library.render(
            "writer/revise_concept.txt",
            scope=scope,
            target_id=target_id or "",
            guidance=guidance,
            book_json=book.model_dump_json(indent=2),
            reference_pack=reference_pack,
        )
        parsed = extract_json_object(self._generate_block_text(prompt=prompt))
        updated_book = deepcopy(book)
        if scope == "all":
            updated_book.title = str(parsed["title"])
            updated_book.premise = StoryPremise.model_validate(parsed["premise"])
            if book.characters:
                if "characters" in parsed:
                    updated_book.characters = [CharacterCard.model_validate(item) for item in parsed["characters"]]
            else:
                updated_book.characters = []
            if book.metadata.get("chapter_plans"):
                if "chapter_plans" in parsed:
                    plans = [ChapterPlan.model_validate(item) for item in parsed["chapter_plans"]]
                    updated_book.metadata["chapter_plans"] = [plan.model_dump(mode="json") for plan in plans]
            else:
                updated_book.metadata["chapter_plans"] = []
        elif scope == "premise":
            updated_book.premise = StoryPremise.model_validate(parsed["premise"])
            updated_book.title = updated_book.premise.title
        elif scope == "character":
            if not target_id:
                raise ValueError("target_id is required for character revision.")
            updated_book.characters = [
                CharacterCard.model_validate(parsed["character"]) if item.name == target_id else item
                for item in updated_book.characters
            ]
        elif scope == "chapter_plan":
            if not target_id:
                raise ValueError("target_id is required for chapter plan revision.")
            updated_book.metadata["chapter_plans"] = [
                ChapterPlan.model_validate(parsed["chapter_plan"]).model_dump(mode="json")
                if str(item.get("chapter_id", "")) == target_id
                else item
                for item in updated_book.metadata.get("chapter_plans", [])
            ]
        else:
            raise ValueError(f"Unsupported concept revision scope: {scope}")
        updated_book.updated_at = datetime.now(timezone.utc)
        ev.emit("concept_done", agent="WriterAgent", title=f"Concept revised: {scope}", scope=scope, target_id=target_id or "")
        return updated_book

    def create_book(self, blueprint: BookBlueprint, source_query: str, style_request: str = "") -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Initialize book shell: {blueprint.premise.title}")
        now = datetime.now(timezone.utc)
        volume_title = blueprint.volume_titles[0] if blueprint.volume_titles else "Volume 1"
        effective_style = style_request or blueprint.premise.target_style
        book = BookDocument(
            id=f"book_{uuid4().hex[:10]}",
            title=blueprint.premise.title,
            premise=blueprint.premise,
            characters=blueprint.characters,
            volumes=[
                Volume(
                    id="vol_001",
                    title=volume_title,
                    summary=blueprint.premise.central_conflict,
                    chapters=[],
                )
            ],
            metadata={
                "target_words": self._target_words_for_style(effective_style),
                "style": blueprint.premise.target_style,
                "style_request": style_request,
                "query": source_query,
                "blueprint_id": blueprint.blueprint_id,
                "chapter_plans": [plan.model_dump(mode="json") for plan in blueprint.chapter_plans],
                "next_chapter_index": 0,
                "completed_chapter_ids": [],
            },
            created_at=now,
            updated_at=now,
        )
        ev.emit(
            "book_created",
            agent="WriterAgent",
            title=f"Book shell ready: {book.title}",
            book_id=book.id,
            planned_chapter_count=len(blueprint.chapter_plans),
        )
        return book

    def write_next_chapter(self, book: BookDocument, reference_pack: str = "暂无额外参考资料。") -> tuple[BookDocument, Chapter]:
        chapter_plans = self._chapter_plans_from_book(book)
        next_index = int(book.metadata.get("next_chapter_index", 0))
        if next_index >= len(chapter_plans):
            raise ValueError(f"No remaining chapters to write for book {book.id}.")

        plan = chapter_plans[next_index]
        ev.emit(
            "agent_start",
            agent="WriterAgent",
            title=f"Write next chapter: {plan.title}",
            book_id=book.id,
            chapter_id=plan.chapter_id,
        )
        self._current_previous_chapter = book.volumes[0].chapters[-1] if book.volumes and book.volumes[0].chapters else None
        self._current_characters = book.characters
        chapter = self._create_chapter(plan, book.premise, reference_pack=reference_pack)
        self._current_previous_chapter = None
        self._current_characters = []

        updated_book = deepcopy(book)
        updated_book.volumes[0].chapters.append(chapter)
        completed_ids = list(updated_book.metadata.get("completed_chapter_ids", []))
        completed_ids.append(plan.chapter_id)
        updated_book.metadata["completed_chapter_ids"] = completed_ids
        updated_book.metadata["next_chapter_index"] = next_index + 1
        updated_book.metadata["last_written_chapter_id"] = plan.chapter_id
        updated_book.updated_at = datetime.now(timezone.utc)
        ev.emit(
            "chapter_done",
            agent="WriterAgent",
            title=f"Chapter written: {plan.title}",
            book_id=book.id,
            chapter_id=plan.chapter_id,
            next_chapter_index=updated_book.metadata["next_chapter_index"],
        )
        return updated_book, chapter

    def rewrite_unit(
        self,
        book: BookDocument,
        block_id: str,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Rewrite block {block_id}")
        block, chapter, plan = self._locate_block(book, block_id)
        replacement = self._generate_block_text(
            prompt=self.prompt_library.render(
                "writer/rewrite_unit.txt",
                block_id=block_id,
                guidance=guidance,
                block_text=block.text,
                block_purpose=block.purpose,
                chapter_json=json.dumps(chapter.model_dump(mode="json"), ensure_ascii=False, indent=2),
                chapter_plan_json=plan.model_dump_json(indent=2) if plan else "{}",
                premise_json=book.premise.model_dump_json(indent=2),
                characters_json=json.dumps([item.model_dump(mode="json") for item in book.characters], ensure_ascii=False, indent=2),
                reference_pack=reference_pack,
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

    def rewrite_chapter(
        self,
        book: BookDocument,
        chapter_id: str,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Rewrite chapter {chapter_id}", chapter_id=chapter_id)
        volume_index, chapter_index, chapter = self._locate_chapter(book, chapter_id)
        plan = self._chapter_plan_by_id(book, chapter_id)
        prompt = self.prompt_library.render(
            "writer/rewrite_chapter.txt",
            chapter_id=chapter_id,
            guidance=guidance,
            chapter_json=json.dumps(chapter.model_dump(mode="json"), ensure_ascii=False, indent=2),
            chapter_plan_json=plan.model_dump_json(indent=2) if plan else "{}",
            premise_json=book.premise.model_dump_json(indent=2),
            characters_json=json.dumps([item.model_dump(mode="json") for item in book.characters], ensure_ascii=False, indent=2),
            previous_chapter_json=self._chapter_before(book, chapter_id),
            reference_pack=reference_pack,
        )
        parsed = extract_json_object(self._generate_block_text(prompt=prompt))
        rewritten = Chapter.model_validate(parsed["chapter"])
        updated_book = deepcopy(book)
        updated_book.volumes[volume_index].chapters[chapter_index] = rewritten
        updated_book.updated_at = datetime.now(timezone.utc)
        ev.emit("chapter_rewritten", agent="WriterAgent", title=f"Chapter rewritten: {chapter_id}", chapter_id=chapter_id)
        return updated_book

    def patch_block(self, book: BookDocument, instruction: PatchInstruction) -> tuple[BookDocument, dict[str, Any]]:
        ev.emit(
            "patch_done",
            agent="WriterAgent",
            title=f"Patch block {instruction.target_block_id}",
            block_id=instruction.target_block_id,
            operation=instruction.operation,
        )
        patched_book, version = self.patch_executor.apply(book, instruction)
        return patched_book, {"patch_version": version.model_dump(mode="json")}

    def expand(
        self,
        book: BookDocument,
        block_id: str,
        expansion_goal: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        ev.emit("agent_start", agent="WriterAgent", title=f"Expand block {block_id}")
        addition = self._generate_block_text(
            prompt=self.prompt_library.render(
                "writer/expand.txt",
                block_id=block_id,
                expansion_goal=expansion_goal,
                reference_pack=reference_pack,
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
            book = self.create_book(
                blueprint=blueprint,
                source_query=kwargs.get("source_query", ""),
                style_request=str(kwargs.get("style_request", "")),
            )
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Initialized book shell.",
                payload={"book": book.model_dump(mode="json")},
            )
        if mode == WriterMode.WRITE_NEXT_CHAPTER:
            book = kwargs["book"]
            updated_book, chapter = self.write_next_chapter(book=book, reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")))
            return AgentResult(
                agent_name=self.name,
                success=True,
                message=f"Wrote chapter {chapter.id}.",
                payload={"book": updated_book.model_dump(mode="json"), "chapter": chapter.model_dump(mode="json")},
            )
        if mode == WriterMode.REWRITE_UNIT:
            book = kwargs["book"]
            rewritten_book = self.rewrite_unit(
                book=book,
                block_id=kwargs["block_id"],
                guidance=kwargs["guidance"],
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
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
            expanded_book = self.expand(
                book=book,
                block_id=kwargs["block_id"],
                expansion_goal=kwargs["expansion_goal"],
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(
                agent_name=self.name,
                success=True,
                message="Expanded target block.",
                payload={"book": expanded_book.model_dump(mode="json")},
            )
        raise ValueError(f"Unsupported writer mode: {mode}")

    def _create_chapter(self, plan: ChapterPlan, premise: StoryPremise, reference_pack: str = "暂无额外参考资料。") -> Chapter:
        premise_json = premise.model_dump_json(indent=2)
        chapter_plan_json = plan.model_dump_json(indent=2)
        characters_json = json.dumps(
            [character.model_dump(mode="json") for character in self._current_characters],
            ensure_ascii=False,
            indent=2,
        )
        previous_chapter_json = self._previous_chapter_json()

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
                            premise_json=premise_json,
                            chapter_plan_json=chapter_plan_json,
                            characters_json=characters_json,
                            previous_chapter_json=previous_chapter_json,
                            reference_pack=reference_pack,
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
                            premise_json=premise_json,
                            chapter_plan_json=chapter_plan_json,
                            characters_json=characters_json,
                            previous_chapter_json=previous_chapter_json,
                            reference_pack=reference_pack,
                        )
                    ),
                ),
            ]
            scenes.append(
                Scene(
                    id=scene_id,
                    title=f"{plan.title}-scene-{scene_index}",
                    summary=f"Advance chapter objective: {plan.objective}",
                    blocks=blocks,
                )
            )
        return Chapter(id=plan.chapter_id, title=plan.title, summary=plan.objective, scenes=scenes)

    def _chapter_plans_from_book(self, book: BookDocument) -> list[ChapterPlan]:
        raw_plans = book.metadata.get("chapter_plans", [])
        return [ChapterPlan.model_validate(item) for item in raw_plans]

    @staticmethod
    def _target_words_for_style(style_text: str) -> int:
        text = style_text.lower()
        if "短篇" in style_text or "short" in text:
            return 12000
        if "中篇" in style_text or "medium" in text or "mid" in text:
            return 40000
        return 100000

    def _chapter_plan_by_id(self, book: BookDocument, chapter_id: str) -> ChapterPlan | None:
        for item in self._chapter_plans_from_book(book):
            if item.chapter_id == chapter_id:
                return item
        return None

    def _locate_block(self, book: BookDocument, block_id: str) -> tuple[TextBlock, Chapter, ChapterPlan | None]:
        for volume in book.volumes:
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    for block in scene.blocks:
                        if block.id == block_id:
                            return block, chapter, self._chapter_plan_by_id(book, chapter.id)
        raise ValueError(f"Block not found: {block_id}")

    def _locate_chapter(self, book: BookDocument, chapter_id: str) -> tuple[int, int, Chapter]:
        for volume_index, volume in enumerate(book.volumes):
            for chapter_index, chapter in enumerate(volume.chapters):
                if chapter.id == chapter_id:
                    return volume_index, chapter_index, chapter
        raise ValueError(f"Chapter not found: {chapter_id}")

    def _chapter_before(self, book: BookDocument, chapter_id: str) -> str:
        previous: Chapter | None = None
        for volume in book.volumes:
            for chapter in volume.chapters:
                if chapter.id == chapter_id:
                    return json.dumps(previous.model_dump(mode="json"), ensure_ascii=False, indent=2) if previous else "{}"
                previous = chapter
        return "{}"

    def _previous_chapter_json(self) -> str:
        if self._current_previous_chapter is None:
            return "{}"
        return json.dumps(self._current_previous_chapter.model_dump(mode="json"), ensure_ascii=False, indent=2)

    def _generate_block_text(self, prompt: str) -> str:
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("writer/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        return self.llm_client.generate(messages=messages, temperature=0.8).strip()
