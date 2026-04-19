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
    NewCharacterCandidate,
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
        self._current_write_brief: dict[str, Any] = {}
        self._current_story_blueprint: dict[str, Any] = {}
        self._current_completed_chapter_summary_bundle: str = ""

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
        self._current_write_brief = self._build_chapter_write_brief(book, plan, reference_pack=reference_pack)
        chapter = self._create_chapter(plan, book.premise, reference_pack=reference_pack)
        self._current_previous_chapter = None
        self._current_characters = []
        self._current_write_brief = {}
        self._current_story_blueprint = {}
        self._current_completed_chapter_summary_bundle = ""

        updated_book = deepcopy(book)
        updated_book.volumes[0].chapters.append(chapter)
        completed_ids = list(updated_book.metadata.get("completed_chapter_ids", []))
        completed_ids.append(plan.chapter_id)
        updated_book.metadata["completed_chapter_ids"] = completed_ids
        updated_book.metadata["next_chapter_index"] = next_index + 1
        updated_book.metadata["last_written_chapter_id"] = plan.chapter_id
        updated_book.metadata.setdefault("scene_only_characters", [])
        updated_book.metadata["new_character_candidates"] = self._merge_new_character_candidates(
            existing=updated_book.metadata.get("new_character_candidates", []),
            new_items=self._extract_new_character_candidates(book=updated_book, chapter=chapter, plan=plan, reference_pack=reference_pack),
            existing_character_names={item.name for item in updated_book.characters},
        )
        updated_book.updated_at = datetime.now(timezone.utc)
        ev.emit(
            "chapter_done",
            agent="WriterAgent",
            title=f"Chapter written: {plan.title}",
            book_id=book.id,
            chapter_id=plan.chapter_id,
            next_chapter_index=updated_book.metadata["next_chapter_index"],
            new_character_candidate_count=len(updated_book.metadata.get("new_character_candidates", [])),
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
            story_blueprint_json=json.dumps(book.metadata.get("story_blueprint", {}), ensure_ascii=False, indent=2),
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
        story_blueprint_json = json.dumps(self._current_story_blueprint or {}, ensure_ascii=False, indent=2)
        characters_json = json.dumps(
            [character.model_dump(mode="json") for character in self._current_characters],
            ensure_ascii=False,
            indent=2,
        )
        previous_chapter_json = self._previous_chapter_json()
        chapter_write_brief_json = json.dumps(self._current_write_brief or {}, ensure_ascii=False, indent=2)
        completed_chapter_summary_bundle = self._current_completed_chapter_summary_bundle or "暂无已完成章节。"

        scenes: list[Scene] = []
        total_scenes = max(plan.planned_scene_count, len(plan.scene_beats))
        for scene_index in range(1, total_scenes + 1):
            scene_id = f"{plan.chapter_id}.sc_{scene_index:03d}"
            scene_beat = plan.scene_beats[scene_index - 1] if scene_index - 1 < len(plan.scene_beats) else {}
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
                            story_blueprint_json=story_blueprint_json,
                            chapter_plan_json=chapter_plan_json,
                            chapter_write_brief_json=chapter_write_brief_json,
                            scene_beat_json=json.dumps(scene_beat, ensure_ascii=False, indent=2),
                            characters_json=characters_json,
                            previous_chapter_json=previous_chapter_json,
                            completed_chapter_summary_bundle=completed_chapter_summary_bundle,
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
                            story_blueprint_json=story_blueprint_json,
                            chapter_plan_json=chapter_plan_json,
                            chapter_write_brief_json=chapter_write_brief_json,
                            scene_beat_json=json.dumps(scene_beat, ensure_ascii=False, indent=2),
                            characters_json=characters_json,
                            previous_chapter_json=previous_chapter_json,
                            completed_chapter_summary_bundle=completed_chapter_summary_bundle,
                            reference_pack=reference_pack,
                        )
                    ),
                ),
            ]
            scenes.append(
                Scene(
                    id=scene_id,
                    title=f"{plan.title}-scene-{scene_index}",
                    summary=scene_beat.get("objective") or f"Advance chapter objective: {plan.objective}",
                    blocks=blocks,
                )
            )
        return Chapter(id=plan.chapter_id, title=plan.title, summary=plan.objective, scenes=scenes)

    def _chapter_plans_from_book(self, book: BookDocument) -> list[ChapterPlan]:
        raw_plans = book.metadata.get("chapter_plans", [])
        return [ChapterPlan.model_validate(item) for item in raw_plans]

    def _build_chapter_write_brief(self, book: BookDocument, plan: ChapterPlan, reference_pack: str = "暂无额外参考资料。") -> dict[str, Any]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        self._current_story_blueprint = story_blueprint
        chapter_briefs = [item for item in story_blueprint.get("chapter_briefs", []) if str(item.get("chapter_id", "")) == plan.chapter_id]
        recent_briefs = self._recent_completed_chapter_briefs(book, limit=10)
        completed_summary_bundle = self._completed_chapter_summary_bundle(book, limit=10)
        self._current_completed_chapter_summary_bundle = completed_summary_bundle
        active_lines: set[str] = set()
        for item in chapter_briefs:
            for line_name in item.get("active_lines", []) or []:
                line_name = str(line_name).strip()
                if line_name:
                    active_lines.add(line_name)
        relevant_story_lines = [item for item in story_blueprint.get("story_lines", []) if str(item.get("name", "")) in active_lines]
        relevant_relationships = self._relevant_relationships(book, plan, active_lines)
        relevant_twists = self._relevant_twists(story_blueprint, plan)
        relevant_milestones = self._relevant_milestones(book, plan)
        prompt = self.prompt_library.render(
            "writer/chapter_write_brief.txt",
            premise_json=book.premise.model_dump_json(indent=2),
            chapter_plan_json=plan.model_dump_json(indent=2),
            chapter_briefs_json=json.dumps(chapter_briefs, ensure_ascii=False, indent=2),
            recent_chapter_briefs_json=json.dumps(recent_briefs, ensure_ascii=False, indent=2),
            story_lines_json=json.dumps(relevant_story_lines, ensure_ascii=False, indent=2),
            relationship_network_json=json.dumps(relevant_relationships[:8], ensure_ascii=False, indent=2),
            twist_designs_json=json.dumps(relevant_twists[:6], ensure_ascii=False, indent=2),
            character_milestones_json=json.dumps(relevant_milestones[:8], ensure_ascii=False, indent=2),
            previous_chapter_json=self._previous_chapter_json(),
            completed_chapter_summary_bundle=completed_summary_bundle,
            reference_pack=reference_pack,
        )
        try:
            parsed = extract_json_object(self._generate_block_text(prompt=prompt))
        except Exception:
            parsed = {}
        brief = {
            "chapter_goal": str(parsed.get("chapter_goal", plan.objective)),
            "narrative_mode": str(parsed.get("narrative_mode", "")),
            "viewpoint_strategy": str(parsed.get("viewpoint_strategy", "")),
            "reveal_strategy": str(parsed.get("reveal_strategy", "")),
            "must_land": [str(item) for item in parsed.get("must_land", [])] if isinstance(parsed.get("must_land", []), list) else [],
            "must_avoid": [str(item) for item in parsed.get("must_avoid", [])] if isinstance(parsed.get("must_avoid", []), list) else [],
            "retention_hook": str(parsed.get("retention_hook", plan.cliffhanger)),
            "language_notes": str(parsed.get("language_notes", "")),
            "scene_focus": [str(item) for item in parsed.get("scene_focus", [])] if isinstance(parsed.get("scene_focus", []), list) else [],
        }
        ev.emit(
            "chapter_write_brief_ready",
            agent="WriterAgent",
            title=f"Chapter write brief ready: {plan.title}",
            chapter_id=plan.chapter_id,
            chapter_goal=brief["chapter_goal"],
            retention_hook=brief["retention_hook"],
        )
        return brief

    def _extract_new_character_candidates(
        self,
        *,
        book: BookDocument,
        chapter: Chapter,
        plan: ChapterPlan,
        reference_pack: str,
    ) -> list[dict[str, Any]]:
        prompt = self.prompt_library.render(
            "writer/extract_new_character_candidates.txt",
            premise_json=book.premise.model_dump_json(indent=2),
            chapter_plan_json=plan.model_dump_json(indent=2),
            chapter_json=json.dumps(chapter.model_dump(mode="json"), ensure_ascii=False, indent=2),
            characters_json=json.dumps([item.model_dump(mode="json") for item in book.characters], ensure_ascii=False, indent=2),
            story_blueprint_json=json.dumps(book.metadata.get("story_blueprint", {}), ensure_ascii=False, indent=2),
            reference_pack=reference_pack,
        )
        try:
            parsed = extract_json_object(self._generate_block_text(prompt=prompt))
        except Exception:
            return []
        raw_items = parsed.get("new_character_candidates", [])
        if not isinstance(raw_items, list):
            return []
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload["candidate_id"] = str(payload.get("candidate_id") or f"cand_{uuid4().hex[:10]}")
            payload["name"] = str(payload.get("name") or "").strip()
            payload["first_appearance_chapter"] = str(payload.get("first_appearance_chapter") or plan.chapter_id)
            if not payload["name"]:
                continue
            try:
                candidate = NewCharacterCandidate.model_validate(payload)
            except Exception:
                continue
            normalized.append(candidate.model_dump(mode="json"))
        if normalized:
            ev.emit(
                "new_character_candidates_ready",
                agent="WriterAgent",
                title=f"New character candidates: {plan.title}",
                chapter_id=plan.chapter_id,
                candidate_count=len(normalized),
            )
        return normalized

    @staticmethod
    def _merge_new_character_candidates(
        *,
        existing: Any,
        new_items: list[dict[str, Any]],
        existing_character_names: set[str],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_names = {name.strip() for name in existing_character_names if name and name.strip()}
        seen_candidate_names: set[str] = set()
        for item in existing or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in seen_names or name in seen_candidate_names:
                continue
            seen_candidate_names.add(name)
            merged.append(item)
        for item in new_items:
            name = str(item.get("name") or "").strip()
            if not name or name in seen_names or name in seen_candidate_names:
                continue
            seen_candidate_names.add(name)
            merged.append(item)
        return merged

    def _recent_completed_chapter_briefs(self, book: BookDocument, limit: int = 10) -> list[dict[str, Any]]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        brief_map = {
            str(item.get("chapter_id", "")): item
            for item in story_blueprint.get("chapter_briefs", []) or []
            if isinstance(item, dict) and item.get("chapter_id")
        }
        completed_ids = [str(item) for item in book.metadata.get("completed_chapter_ids", []) or [] if str(item).strip()]
        selected_ids = completed_ids[-limit:]
        return [brief_map[chapter_id] for chapter_id in selected_ids if chapter_id in brief_map]

    def _completed_chapter_summary_bundle(self, book: BookDocument, limit: int = 10) -> str:
        chapter_plan_map = {
            plan.chapter_id: plan
            for plan in self._chapter_plans_from_book(book)
        }
        completed: list[str] = []
        for volume in book.volumes:
            for chapter in volume.chapters:
                completed.append(self._chapter_context_summary(chapter, chapter_plan_map.get(chapter.id)))
        if not completed:
            return "暂无已完成章节。"
        selected = completed[-limit:]
        return "\n\n".join(selected)

    def _chapter_context_summary(self, chapter: Chapter, plan: ChapterPlan | None) -> str:
        summary_parts = [
            f"{chapter.id}《{chapter.title}》",
            chapter.summary.strip() if chapter.summary else "",
            f"关键转折：{plan.key_turn}" if plan and plan.key_turn else "",
            f"章节悬念：{plan.cliffhanger}" if plan and plan.cliffhanger else "",
            f"兑现：{plan.payoff}" if plan and plan.payoff else "",
        ]
        combined = "；".join(part for part in summary_parts if part)
        return self._trim_context_text(combined, 220)

    @staticmethod
    def _trim_context_text(text: str, limit: int) -> str:
        clean = " ".join(str(text or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 1)].rstrip() + "…"

    @staticmethod
    def _relevant_twists(story_blueprint: dict[str, Any], plan: ChapterPlan) -> list[dict[str, Any]]:
        relevant: list[dict[str, Any]] = []
        tokens = [plan.title, plan.key_turn, plan.payoff, plan.cliffhanger]
        for twist in story_blueprint.get("twist_designs", []) or []:
            text = json.dumps(twist, ensure_ascii=False)
            if any(token and token in text for token in tokens):
                relevant.append(twist)
        return relevant

    @staticmethod
    def _relevant_milestones(book: BookDocument, plan: ChapterPlan) -> list[dict[str, Any]]:
        relevant: list[dict[str, Any]] = []
        tokens = [plan.title, plan.objective, plan.key_turn, plan.payoff]
        for item in book.metadata.get("character_milestones", []) or []:
            text = json.dumps(item, ensure_ascii=False)
            if any(token and token in text for token in tokens):
                relevant.append(item)
        return relevant

    @staticmethod
    def _relevant_relationships(book: BookDocument, plan: ChapterPlan, active_lines: set[str]) -> list[dict[str, Any]]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        relevant: list[dict[str, Any]] = []
        tokens = set(active_lines)
        tokens.update(character.name for character in book.characters if character.name)
        tokens.update(token for token in [plan.title, plan.objective, plan.key_turn] if token)
        for relation in story_blueprint.get("relationship_network", []) or []:
            text = json.dumps(relation, ensure_ascii=False)
            if any(token and token in text for token in tokens):
                relevant.append(relation)
        return relevant

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
