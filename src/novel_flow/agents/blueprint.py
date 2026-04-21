from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    AgentResult,
    BookBlueprint,
    BookDocument,
    ChapterBrief,
    ChapterBriefGenerationInput,
    ChapterBriefsPayload,
    ChapterPlan,
    CharacterCard,
    StoryLinesPayload,
    StoryPremise,
    TwistDesignsPayload,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_generation import safe_json_generate
from novel_flow.utils.json_tools import extract_json_object


class BlueprintAgent(BaseAgent):
    def __init__(self, llm_client: LLMClient, prompt_library: PromptLibrary | None = None) -> None:
        super().__init__(name="BlueprintAgent")
        self.llm_client = llm_client
        self.prompt_library = prompt_library or PromptLibrary()

    def build_story_spine(
        self,
        research_query: str,
        style_request: str = "",
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build story spine", query=research_query)
        self._emit_agent_input(
            "story spine",
            research_query=research_query,
            style_request=style_request or "未指定",
            planning_context=self._safe_json_loads(planning_context_json),
            seed={},
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_1_story_spine.txt",
            research_query=research_query,
            style_request=style_request or "未指定",
            planning_context_json=planning_context_json,
            seed_json="{}",
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="story_spine")
        parsed["volume_titles"] = [str(item) for item in parsed.get("volume_titles", []) if str(item).strip()] or ["Volume 1"]
        parsed.setdefault("story_blueprint", {})
        parsed["premise"] = self._normalize_premise_payload(dict(parsed["premise"]))
        parsed["story_blueprint"] = self._normalize_story_blueprint_payload(parsed.get("story_blueprint"))
        ev.emit("blueprint_spine_ready", agent=self.name, title="Story spine ready", premise_title=str(parsed["premise"]["title"]))
        return parsed

    def build_character_bible_step(
        self,
        research_query: str,
        premise: StoryPremise,
        volume_titles: list[str],
        story_blueprint: dict[str, Any] | None = None,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build character bible", query=research_query)
        self._emit_agent_input(
            "character bible",
            research_query=research_query,
            premise=premise.model_dump(mode="json"),
            volume_titles=volume_titles,
            story_blueprint=story_blueprint or {},
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_3_character_bible.txt",
            research_query=research_query,
            volume_titles_json=str(volume_titles),
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="character_bible")
        parsed["story_blueprint"] = self._normalize_story_blueprint_payload(parsed.get("story_blueprint"))
        characters = [CharacterCard.model_validate(item) for item in parsed.get("characters", [])]
        parsed["characters"] = [item.model_dump(mode="json") for item in characters]
        ev.emit("blueprint_characters_ready", agent=self.name, title="Character bible ready", character_count=len(characters))
        return parsed

    def build_character_bible(
        self,
        research_query: str,
        premise: StoryPremise,
        volume_titles: list[str],
        story_blueprint: dict[str, Any] | None = None,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> list[CharacterCard]:
        payload = self.build_character_bible_step(
            research_query,
            premise,
            volume_titles,
            story_blueprint=story_blueprint,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        return [CharacterCard.model_validate(item) for item in payload.get("characters", [])]

    def build_chapter_briefs_compat_plans(
        self,
        research_query: str,
        premise: StoryPremise,
        characters: list[CharacterCard],
        volume_titles: list[str],
        story_blueprint: dict[str, Any] | None = None,
        character_milestones: list[dict[str, Any]] | None = None,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> list[ChapterPlan]:
        payload = self.build_chapter_briefs_step(
            research_query=research_query,
            volume_titles=volume_titles,
            batch={
                "start_index": 0,
                "end_index": 0,
                "batch_size": 1,
                "total_chapters": 1,
                "chapter_ids": ["ch_001"],
            },
            story_spine={
                "premise": premise.model_dump(mode="json"),
                "story_engine": dict((story_blueprint or {}).get("story_engine", {}) or {}),
            },
            worldbuilding={"story_engine": dict((story_blueprint or {}).get("story_engine", {}) or {})},
            character_bible={"characters": [item.model_dump(mode="json") for item in characters]},
            event_timeline=list((story_blueprint or {}).get("event_timeline", []) or []),
            character_milestones=list(character_milestones or []),
            twist_designs=list((story_blueprint or {}).get("twist_designs", []) or []),
            story_lines=list((story_blueprint or {}).get("story_lines", []) or []),
            previous_chapter_briefs=[],
            target_chapter_count=1,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        payload["chapter_plans"] = [
            self._normalize_chapter_plan_payload(self._chapter_plan_from_brief(dict(item)))
            for item in payload.get("chapter_briefs", [])
            if isinstance(item, dict)
        ]
        chapter_plans = [ChapterPlan.model_validate(item) for item in payload["chapter_plans"]]
        ev.emit("blueprint_chapter_briefs_ready", agent=self.name, title="Chapter briefs compat plans ready", chapter_count=len(chapter_plans))
        return chapter_plans

    def build_blueprint(
        self,
        research_query: str,
        style_request: str = "",
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookBlueprint:
        ev.emit("agent_start", agent=self.name, title="Build blueprint", query=research_query)
        spine = self.build_story_spine(
            research_query,
            style_request=style_request,
            planning_context_json="{}",
            reference_pack=reference_pack,
        )
        premise = StoryPremise.model_validate(spine["premise"])
        volume_titles = [str(item) for item in spine["volume_titles"]]
        characters = self.build_character_bible(
            research_query,
            premise,
            volume_titles,
            story_blueprint=dict(spine.get("story_blueprint", {})),
            planning_context_json="{}",
            reference_pack=reference_pack,
        )
        chapter_plans = self.build_chapter_briefs_compat_plans(
            research_query,
            premise,
            characters,
            volume_titles,
            story_blueprint=dict(spine.get("story_blueprint", {})),
            character_milestones=[],
            planning_context_json="{}",
            reference_pack=reference_pack,
        )
        blueprint = BookBlueprint(
            blueprint_id=f"blueprint_{uuid4().hex[:10]}",
            premise=premise,
            characters=characters,
            volume_titles=volume_titles,
            chapter_plans=chapter_plans,
        )
        ev.emit(
            "blueprint_ready",
            agent=self.name,
            title=f"Blueprint ready: {premise.title}",
            premise_title=premise.title,
            chapter_count=len(chapter_plans),
            character_count=len(characters),
        )
        return blueprint

    def add_character(
        self,
        book: BookDocument,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> CharacterCard:
        ev.emit("agent_start", agent=self.name, title="Add character", book_id=book.id)
        prompt = self.prompt_library.render(
            "writer/add_character.txt",
            research_query=str(book.metadata.get("query") or book.title),
            guidance=guidance,
            premise_json=book.premise.model_dump_json(indent=2),
            existing_characters_json=self._json_dump([c.model_dump(mode="json") for c in book.characters]),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="add_character")
        character = CharacterCard.model_validate(parsed["character"])
        ev.emit("blueprint_character_added", agent=self.name, title=f"Character added: {character.name}", name=character.name)
        return character

    def build_character_milestones(
        self,
        research_query: str,
        premise: StoryPremise,
        characters: list[CharacterCard],
        story_blueprint: dict[str, Any],
        chapter_plans: list[ChapterPlan] | None = None,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> list[dict[str, Any]]:
        ev.emit("agent_start", agent=self.name, title="Build character milestones", query=research_query)
        self._emit_agent_input(
            "character milestones",
            research_query=research_query,
            premise=premise.model_dump(mode="json"),
            characters=[item.model_dump(mode="json") for item in characters],
            story_blueprint=story_blueprint,
            chapter_plans=[item.model_dump(mode="json") for item in (chapter_plans or [])],
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_5_character_milestones.txt",
            research_query=research_query,
            premise_json=premise.model_dump_json(indent=2),
            characters_json=self._json_dump([item.model_dump(mode="json") for item in characters]),
            story_blueprint_json=self._json_dump(story_blueprint),
            chapter_plans_json=self._json_dump([item.model_dump(mode="json") for item in (chapter_plans or [])]),
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="character_milestones")
        milestones = self._normalize_character_milestones(parsed.get("character_milestones", []))
        ev.emit(
            "blueprint_milestones_ready",
            agent=self.name,
            title="Character milestones ready",
            character_count=len(milestones),
        )
        return milestones

    def build_single_character_milestone(
        self,
        *,
        research_query: str,
        character: CharacterCard,
        premise: StoryPremise,
        story_engine: dict[str, Any],
        user_guidance: str = "",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        name = str(character.name or "").strip() or "未命名"
        ev.emit("agent_start", agent=self.name, title=f"Build milestone: {name}", query=research_query)
        self._emit_agent_input(
            f"single character milestone: {name}",
            research_query=research_query,
            user_guidance=user_guidance or "无",
            character=character.model_dump(mode="json"),
            premise=premise.model_dump(mode="json"),
            story_engine=story_engine,
        )
        prompt = self.prompt_library.render(
            "writer/step_5_single_character_milestone.txt",
            research_query=research_query,
            user_guidance=user_guidance or "无",
            character_json=self._json_dump(character.model_dump(mode="json")),
            premise_json=premise.model_dump_json(indent=2),
            story_engine_json=self._json_dump(story_engine),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="single_character_milestone", allow_repair=False)
        candidate = parsed.get("character_milestone")
        if candidate is None and isinstance(parsed.get("character_milestones"), list):
            items = parsed["character_milestones"]
            candidate = next((i for i in items if isinstance(i, dict) and str(i.get("character_name", "")).strip() == name), None) or (items[0] if items else None)
        if candidate is None:
            candidate = parsed
        normalized = self._normalize_character_milestones([candidate] if isinstance(candidate, dict) else [])
        if not normalized:
            raise ValueError(f"角色 {name} 的发展线为空，模型未返回有效数据。")
        milestone = dict(normalized[0])
        milestone["character_name"] = name
        ev.emit(
            "blueprint_milestone_ready",
            agent=self.name,
            title=f"Milestone ready: {name}",
            character_name=name,
        )
        return milestone

    def add_character_milestone(
        self,
        *,
        research_query: str,
        premise: StoryPremise,
        characters: list[CharacterCard],
        story_blueprint: dict[str, Any],
        character_milestones: list[dict[str, Any]] | None = None,
        guidance: str = "",
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Add character milestone", query=research_query)
        self._emit_agent_input(
            "add character milestone",
            research_query=research_query,
            premise=premise.model_dump(mode="json"),
            characters=[item.model_dump(mode="json") for item in characters],
            story_blueprint=story_blueprint,
            character_milestones=character_milestones or [],
            guidance=guidance,
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_5_add_character_milestone.txt",
            research_query=research_query,
            premise_json=premise.model_dump_json(indent=2),
            characters_json=self._json_dump([item.model_dump(mode="json") for item in characters]),
            story_blueprint_json=self._json_dump(story_blueprint),
            character_milestones_json=self._json_dump(character_milestones or []),
            user_guidance=guidance,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="add_character_milestone")
        candidate = parsed.get("character_milestone")
        if candidate is None:
            candidate = parsed.get("milestone")
        if candidate is None and isinstance(parsed.get("character_milestones"), list):
            items = parsed.get("character_milestones") or []
            candidate = items[0] if items else None
        if candidate is None:
            candidate = parsed
        normalized = self._normalize_character_milestones([candidate])
        if not normalized:
            raise ValueError("新增角色发展线为空，请调整指令后重试。")
        milestone = normalized[0]
        ev.emit(
            "blueprint_milestone_added",
            agent=self.name,
            title=f"Character milestone added: {milestone.get('character_name') or '未命名角色'}",
            character_name=milestone.get("character_name", ""),
        )
        return milestone

    def build_worldbuilding_step(
        self,
        *,
        research_query: str,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build worldbuilding step", query=research_query)
        self._emit_agent_input(
            "worldbuilding step",
            research_query=research_query,
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_2_worldbuilding.txt",
            research_query=research_query,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="worldbuilding_step")
        parsed["story_blueprint"] = self._normalize_story_blueprint_payload(parsed.get("story_blueprint"))
        ev.emit("blueprint_sections_ready", agent=self.name, title="Worldbuilding step ready")
        return parsed

    def build_event_timeline_step(
        self,
        *,
        research_query: str,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build event timeline step", query=research_query)
        self._emit_agent_input(
            "event timeline step",
            research_query=research_query,
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_4_event_timeline.txt",
            research_query=research_query,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="event_timeline_step")
        parsed["story_blueprint"] = self._normalize_story_blueprint_payload(parsed.get("story_blueprint"))
        ev.emit("blueprint_sections_ready", agent=self.name, title="Event timeline step ready")
        return parsed

    def build_twist_designs_step(
        self,
        *,
        research_query: str,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build twist designs step", query=research_query)
        self._emit_agent_input(
            "twist designs step",
            research_query=research_query,
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_6_twist_designs.txt",
            research_query=research_query,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(
            prompt,
            label="twist_designs_step",
            schema_model=TwistDesignsPayload,
        )
        ev.emit("blueprint_sections_ready", agent=self.name, title="Twist designs step ready")
        return parsed

    def build_story_lines_step(
        self,
        *,
        research_query: str,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build story lines step", query=research_query)
        self._emit_agent_input(
            "story lines step",
            research_query=research_query,
            planning_context=self._safe_json_loads(planning_context_json),
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/step_7_story_lines.txt",
            research_query=research_query,
            planning_context_json=planning_context_json,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(
            prompt,
            label="story_lines_step",
            schema_model=StoryLinesPayload,
        )
        ev.emit("blueprint_sections_ready", agent=self.name, title="Story lines step ready")
        return parsed

    def build_chapter_briefs_step(
        self,
        *,
        research_query: str,
        volume_titles: list[str],
        batch: dict[str, Any] | None = None,
        story_spine: dict[str, Any] | None = None,
        worldbuilding: dict[str, Any] | None = None,
        character_bible: dict[str, Any] | None = None,
        event_timeline: list[dict[str, Any]] | None = None,
        character_milestones: list[dict[str, Any]] | None = None,
        twist_designs: list[dict[str, Any]] | None = None,
        story_lines: list[dict[str, Any]] | None = None,
        previous_chapter_briefs: list[dict[str, Any]] | list[ChapterBrief] | None = None,
        target_chapter_count: int | None = None,
        planning_context_json: str = "{}",
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        inferred_total = max(int(target_chapter_count or 0), 1)
        batch_payload = batch or {
            "start_index": 0,
            "end_index": max(inferred_total - 1, 0),
            "batch_size": inferred_total,
            "total_chapters": inferred_total,
            "chapter_ids": [f"ch_{index + 1:03d}" for index in range(inferred_total)],
        }
        step_input = ChapterBriefGenerationInput.model_validate(
            {
                "batch": batch_payload,
                "research_query": research_query,
                "volume_titles_json": volume_titles,
                "story_spine_json": story_spine or {},
                "worldbuilding_json": worldbuilding or {},
                "character_bible_json": character_bible or {},
                "event_timeline_json": event_timeline or [],
                "character_milestones_json": character_milestones or [],
                "twist_designs_json": twist_designs or [],
                "story_lines_json": story_lines or [],
                "previous_chapter_briefs_json": previous_chapter_briefs or [],
                "target_chapter_count": int(target_chapter_count or batch_payload.get("total_chapters") or 1),
                "reference_pack": reference_pack,
            }
        )
        ev.emit("agent_start", agent=self.name, title="Build chapter briefs step", query=research_query)
        self._emit_agent_input(
            "chapter briefs step",
            step8_input=step_input.model_dump(mode="json"),
            planning_context=self._safe_json_loads(planning_context_json),
        )
        prompt = self.prompt_library.render(
            "writer/step_8_chapter_briefs.txt",
            research_query=step_input.research_query,
            volume_titles_json=self._json_dump(step_input.volume_titles_json),
            story_spine_json=self._json_dump(step_input.story_spine_json),
            worldbuilding_json=self._json_dump(step_input.worldbuilding_json),
            character_bible_json=self._json_dump(step_input.character_bible_json),
            event_timeline_json=self._json_dump(step_input.event_timeline_json),
            character_milestones_json=self._json_dump(step_input.character_milestones_json),
            twist_designs_json=self._json_dump(step_input.twist_designs_json),
            story_lines_json=self._json_dump(step_input.story_lines_json),
            previous_chapter_briefs_json=self._json_dump([item.model_dump(mode="json") for item in step_input.previous_chapter_briefs_json]),
            target_chapter_count=step_input.target_chapter_count,
            batch_window_json=self._json_dump(step_input.batch.model_dump(mode="json")),
            reference_pack=step_input.reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="chapter_briefs_step", schema_model=ChapterBriefsPayload)
        parsed = ChapterBriefsPayload.model_validate({**parsed, "batch": step_input.batch.model_dump(mode="json")}).model_dump(mode="json")
        ev.emit(
            "blueprint_chapter_briefs_ready",
            agent=self.name,
            title="Chapter briefs ready",
            chapter_count=len(parsed.get("chapter_briefs", [])),
        )
        return parsed

    def expand_story_blueprint_sections(
        self,
        *,
        task_name: str,
        research_query: str,
        style_request: str = "",
        book: BookDocument | None = None,
        task_requirements: str,
        output_contract: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title=f"Expand story blueprint: {task_name}", query=research_query)
        self._emit_agent_input(
            f"expand story blueprint: {task_name}",
            research_query=research_query,
            style_request=style_request or "未指定",
            book=book.model_dump(mode="json") if book else {},
            current_story_blueprint=(book.metadata or {}).get("story_blueprint", {}) if book else {},
            task_requirements=task_requirements,
            output_contract=output_contract,
            reference_pack=reference_pack,
        )
        prompt = self.prompt_library.render(
            "writer/expand_story_blueprint_sections.txt",
            task_name=task_name,
            research_query=research_query,
            style_request=style_request or "未指定",
            book_json=book.model_dump_json(indent=2) if book else "{}",
            current_story_blueprint_json=self._json_dump((book.metadata or {}).get("story_blueprint", {}) if book else {}),
            task_requirements=task_requirements,
            output_contract=output_contract,
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label=f"expand_story_blueprint:{task_name}")
        if "premise" in parsed and isinstance(parsed["premise"], dict):
            parsed["premise"] = self._normalize_premise_payload(dict(parsed["premise"]))
        if "story_blueprint" in parsed:
            parsed["story_blueprint"] = self._normalize_story_blueprint_payload(parsed.get("story_blueprint"))
        if "chapter_plans" in parsed and isinstance(parsed["chapter_plans"], list):
            parsed["chapter_plans"] = [self._normalize_chapter_plan_payload(dict(item)) for item in parsed["chapter_plans"] if isinstance(item, dict)]
        ev.emit("blueprint_sections_ready", agent=self.name, title=f"Blueprint sections ready: {task_name}")
        return parsed

    @staticmethod
    def _safe_json_loads(value: str) -> Any:
        try:
            return json.loads(value)
        except Exception:
            return value

    def _emit_agent_input(self, label: str, **payload: Any) -> None:
        ev.emit("agent_input", agent=self.name, title=f"Agent input: {label}", **payload)

    def revise_concept(
        self,
        book: BookDocument,
        *,
        scope: str,
        target_id: str | None,
        guidance: str,
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookDocument:
        ev.emit("agent_start", agent=self.name, title=f"Revise concept: {scope}", book_id=book.id, target_id=target_id or "")
        prompt = self.prompt_library.render(
            "writer/revise_concept.txt",
            scope=scope,
            target_id=target_id or "",
            guidance=guidance,
            book_json=book.model_dump_json(indent=2),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label=f"revise_concept:{scope}")
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
        elif scope == "chapter_brief":
            if not target_id:
                raise ValueError("target_id is required for chapter brief revision.")
            story_blueprint = dict(updated_book.metadata.get("story_blueprint", {}) or {})
            existing_briefs = list(story_blueprint.get("chapter_briefs", []) or [])
            story_blueprint["chapter_briefs"] = [
                ChapterBrief.model_validate(parsed["chapter_brief"]).model_dump(mode="json")
                if str(item.get("chapter_id", "")) == target_id
                else item
                for item in existing_briefs
            ]
            updated_book.metadata["story_blueprint"] = story_blueprint
        else:
            raise ValueError(f"Unsupported concept revision scope: {scope}")
        updated_book.updated_at = datetime.now(timezone.utc)
        ev.emit("concept_done", agent=self.name, title=f"Concept revised: {scope}", scope=scope, target_id=target_id or "")
        return updated_book

    def revise_blueprint(
        self,
        blueprint: BookBlueprint,
        review: dict[str, Any],
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookBlueprint:
        ev.emit("agent_start", agent=self.name, title="Revise blueprint from review", blueprint_id=blueprint.blueprint_id)
        prompt = self.prompt_library.render(
            "writer/revise_blueprint.txt",
            blueprint_json=blueprint.model_dump_json(indent=2),
            review_json=self._json_dump(review),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="revise_blueprint")
        parsed["premise"] = self._normalize_premise_payload(dict(parsed["premise"]))
        chapter_briefs: list[dict[str, Any]] = []
        if "chapter_briefs" in parsed and isinstance(parsed["chapter_briefs"], list):
            chapter_briefs = [item for item in self._normalize_chapter_briefs(parsed["chapter_briefs"]) if isinstance(item, dict)]
            parsed["chapter_plans"] = [
                self._normalize_chapter_plan_payload(self._chapter_plan_from_brief(dict(item)))
                for item in chapter_briefs
            ]
        else:
            parsed["chapter_plans"] = [self._normalize_chapter_plan_payload(dict(item)) for item in parsed["chapter_plans"]]
        revised = BookBlueprint(
            blueprint_id=f"blueprint_{uuid4().hex[:10]}",
            premise=StoryPremise.model_validate(parsed["premise"]),
            characters=[CharacterCard.model_validate(item) for item in parsed["characters"]],
            volume_titles=[str(item) for item in parsed["volume_titles"]],
            chapter_plans=[ChapterPlan.model_validate(item) for item in parsed["chapter_plans"]],
        )
        ev.emit("blueprint_revised", agent=self.name, title=f"Blueprint revised: {revised.premise.title}", blueprint_id=revised.blueprint_id)
        return revised

    def run(self, **kwargs: Any) -> AgentResult:
        action = str(kwargs.get("action", "build"))
        if action == "story_spine":
            payload = self.build_story_spine(
                research_query=str(kwargs["research_query"]),
                style_request=str(kwargs.get("style_request", "")),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Story spine built.", payload=payload)
        if action == "character_bible":
            premise = StoryPremise.model_validate(kwargs["premise"])
            characters = self.build_character_bible(
                str(kwargs["research_query"]),
                premise,
                list(kwargs["volume_titles"]),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Character bible built.", payload={"characters": [item.model_dump(mode="json") for item in characters]})
        if action == "chapter_briefs":
            premise = StoryPremise.model_validate(kwargs["premise"])
            characters = [CharacterCard.model_validate(item) for item in kwargs["characters"]]
            plans = self.build_chapter_briefs_compat_plans(
                str(kwargs["research_query"]),
                premise,
                characters,
                list(kwargs["volume_titles"]),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Chapter briefs compatibility plans built.", payload={"chapter_plans": [item.model_dump(mode="json") for item in plans]})
        if action == "build":
            blueprint = self.build_blueprint(
                research_query=str(kwargs["research_query"]),
                style_request=str(kwargs.get("style_request", "")),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Blueprint built.", payload={"blueprint": blueprint.model_dump(mode="json")})
        if action == "revise_blueprint":
            blueprint = BookBlueprint.model_validate(kwargs["blueprint"])
            revised = self.revise_blueprint(
                blueprint,
                dict(kwargs["review"]),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Blueprint revised from review.", payload={"blueprint": revised.model_dump(mode="json")})
        if action == "revise":
            book = kwargs["book"]
            updated = self.revise_concept(
                book,
                scope=str(kwargs["scope"]),
                target_id=kwargs.get("target_id"),
                guidance=str(kwargs["guidance"]),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Concept revised.", payload={"book": updated.model_dump(mode="json")})
        raise ValueError(f"Unsupported blueprint action: {action}")

    def _generate_json_text(self, prompt: str, *, temperature: float = 0.2) -> str:
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("writer/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        return self.llm_client.generate(messages=messages, temperature=temperature).strip()

    @classmethod
    def _normalize_story_blueprint_payload(cls, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        return {
            "story_engine": cls._normalize_story_engine(payload.get("story_engine", {})),
            "core_theme": payload.get("core_theme", {}),
            "event_timeline": cls._normalize_event_timeline(payload.get("event_timeline", [])),
            "structure_blueprint": payload.get("structure_blueprint", {}),
            "setpiece_library": payload.get("setpiece_library", []),
            "writing_constraints": payload.get("writing_constraints", []),
            "twist_designs": cls._normalize_twist_designs(payload.get("twist_designs", [])),
            "story_lines": cls._normalize_story_lines(payload.get("story_lines", [])),
            "chapter_briefs": cls._normalize_chapter_briefs(payload.get("chapter_briefs", [])),
        }

    def _generate_json_payload(
        self,
        prompt: str,
        *,
        label: str,
        allow_repair: bool = True,
        schema_model: type[Any] | None = None,
    ) -> dict[str, Any]:
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("writer/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        if not allow_repair:
            raw = self.llm_client.generate(messages=messages, temperature=0.2).strip()
            return extract_json_object(raw)
        return safe_json_generate(
            self.llm_client,
            messages,
            schema_name=label,
            schema_model=schema_model,
        )

    @staticmethod
    def _json_dump(payload: Any) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 3:
                cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned

    @classmethod
    def _coerce_non_object_json(cls, text: str, *, label: str) -> dict[str, Any] | None:
        import json

        candidate = cls._strip_code_fence(text)
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            if label in {"character_milestones", "add_character_milestone"}:
                key = "character_milestones" if label == "character_milestones" else "character_milestone"
                if key == "character_milestone":
                    first = parsed[0] if parsed else {}
                    return {"character_milestone": first if isinstance(first, dict) else {}}
                return {"character_milestones": [item for item in parsed if isinstance(item, dict)]}
            if label == "chapter_briefs_compat_plans":
                return {"chapter_plans": [item for item in parsed if isinstance(item, dict)]}
            return {"items": parsed}
        return None

    @classmethod
    def _normalize_premise_payload(cls, premise: dict[str, Any]) -> dict[str, Any]:
        for key in (
            "title",
            "high_concept",
            "theme_statement",
            "story_summary",
            "genre",
            "target_style",
            "emotional_hook",
            "central_conflict",
            "core_hook",
            "ending_payoff",
        ):
            premise[key] = cls._ensure_text(premise.get(key, ""))
        for key in ("escalation_path", "twist_blueprint", "selling_points"):
            premise[key] = cls._ensure_list(premise.get(key, []))
        return premise

    @classmethod
    def _normalize_chapter_plan_payload(cls, plan: dict[str, Any]) -> dict[str, Any]:
        summary_text = cls._ensure_text(plan.get("summary"))
        if not cls._ensure_text(plan.get("objective")) and summary_text:
            plan["objective"] = summary_text
        plan["chapter_id"] = cls._ensure_text(plan.get("chapter_id"))
        plan["title"] = cls._ensure_text(plan.get("title"))
        plan["objective"] = cls._ensure_text(plan.get("objective"))
        plan["tension"] = cls._ensure_text(plan.get("tension"))
        plan["cliffhanger"] = cls._ensure_text(plan.get("cliffhanger"))
        for key in ("phase", "story_function", "key_turn", "payoff", "next_route_hint", "target_words", "scene_density"):
            if key in plan and plan[key] is None:
                plan[key] = ""
        plan["target_words"] = cls._ensure_text(plan.get("target_words"))
        plan["scene_density"] = cls._ensure_text(plan.get("scene_density"))
        scene_beats = plan.get("scene_beats", [])
        if not isinstance(scene_beats, list):
            scene_beats = []
        normalized_beats: list[dict[str, str]] = []
        for beat in scene_beats:
            if not isinstance(beat, dict):
                continue
            normalized_beats.append(
                {
                    "scene_id": cls._ensure_text(beat.get("scene_id")),
                    "objective": cls._ensure_text(beat.get("objective")),
                    "conflict": cls._ensure_text(beat.get("conflict")),
                    "info_reveal": cls._ensure_text(beat.get("info_reveal")),
                    "emotional_shift": cls._ensure_text(beat.get("emotional_shift")),
                    "end_state": cls._ensure_text(beat.get("end_state")),
                }
            )
        plan["scene_beats"] = normalized_beats
        return plan

    @classmethod
    def _chapter_plan_from_brief(cls, brief: dict[str, Any]) -> dict[str, Any]:
        chapter_id = cls._ensure_text(brief.get("chapter_id"))
        title = cls._ensure_text(brief.get("title"))
        objective = cls._ensure_text(brief.get("summary"))
        tension = cls._ensure_text(brief.get("reader_emotion") or brief.get("emotional_turn") or brief.get("world_limit"))
        cliffhanger = cls._ensure_text(brief.get("ending_pull"))
        return {
            "chapter_id": chapter_id,
            "title": title,
            "objective": objective,
            "tension": tension,
            "cliffhanger": cliffhanger,
            "phase": cls._ensure_text(brief.get("chapter_type")),
            "story_function": cls._ensure_text(brief.get("scene_engine")),
            "key_turn": cls._ensure_text(brief.get("relationship_reprice") or brief.get("character_shift")),
            "payoff": cls._ensure_text(brief.get("small_payoff")),
            "next_route_hint": cliffhanger,
            "target_words": cls._ensure_text(brief.get("info_budget")),
            "scene_density": "",
            "scene_beats": [],
        }

    @staticmethod
    def _ensure_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        numbered = re.split(r"(?:^|\n)\s*\d+[\.、]\s*", text)
        candidates = [item.strip(" \n-;；。") for item in numbered if item.strip(" \n-;；。")]
        if len(candidates) > 1:
            return candidates
        lines = [line.strip(" -;；。") for line in text.splitlines() if line.strip(" -;；。")]
        if len(lines) > 1:
            return lines
        parts = [part.strip(" ;；。") for part in re.split(r"[;；]", text) if part.strip(" ;；。")]
        if len(parts) > 1:
            return parts
        return [text]

    @classmethod
    def _ensure_text(cls, value: Any) -> str:
        if isinstance(value, list):
            items = cls._ensure_list(value)
            return " / ".join(items) if items else ""
        if isinstance(value, dict):
            pairs = []
            for key, item in value.items():
                text = cls._ensure_text(item)
                if text:
                    pairs.append(f"{key}: {text}")
            return "；".join(pairs)
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _normalize_story_engine(cls, value: Any) -> dict[str, str]:
        data = value if isinstance(value, dict) else {}
        return {
            "engine_sentence": cls._ensure_text(data.get("engine_sentence")),
            "default_track": cls._ensure_text(data.get("default_track") or data.get("default_trajectory") or data.get("default_path")),
            "world_rules": cls._ensure_text(data.get("world_rules") or data.get("rules") or data.get("rule_system")),
            "power_structure": cls._ensure_text(data.get("power_structure") or data.get("power_system") or data.get("power_logic")),
            "world_map": cls._ensure_text(data.get("world_map") or data.get("regional_map") or data.get("locations_map")),
            "structural_inertia": cls._ensure_text(data.get("structural_inertia") or data.get("inertia")),
            "rebound_mechanism": cls._ensure_text(data.get("rebound_mechanism") or data.get("backlash_mechanism") or data.get("feedback_mechanism")),
            "story_trigger": cls._ensure_text(data.get("story_trigger") or data.get("start_condition") or data.get("starting_condition") or data.get("story_start_condition") or data.get("inciting_condition") or data.get("story_launch_condition")),
            "objective_conditions": cls._ensure_text(data.get("objective_conditions") or data.get("objective_conditions_and_opportunity_structure") or data.get("opportunity_structure") or data.get("conditions_and_opportunities")),
            "narrative_mode": cls._ensure_text(data.get("narrative_mode")),
            "viewpoint_strategy": cls._ensure_text(data.get("viewpoint_strategy")),
            "reveal_strategy": cls._ensure_text(data.get("reveal_strategy")),
            "hook_strategy": cls._ensure_text(data.get("hook_strategy")),
        }

    @classmethod
    def _normalize_event_timeline(cls, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "event_id": cls._ensure_text(item.get("event_id") or f"event_{index:02d}"),
                    "title": cls._ensure_text(item.get("title")),
                    "time_label": cls._ensure_text(item.get("time_label")),
                    "description": cls._ensure_text(item.get("description")),
                    "trigger": cls._ensure_text(item.get("trigger")),
                    "consequence": cls._ensure_text(item.get("consequence")),
                    "affected_characters": cls._ensure_list(item.get("affected_characters")),
                }
            )
        return normalized

    @classmethod
    def _normalize_twist_designs(cls, value: Any) -> list[dict[str, str]]:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        normalized: list[dict[str, str]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "twist_id": cls._ensure_text(item.get("twist_id") or f"twist_{index:02d}"),
                    "title": cls._ensure_text(item.get("title") or item.get("twist_name")),
                    "setup": cls._ensure_text(item.get("setup")),
                    "false_expectation": cls._ensure_text(item.get("false_expectation")),
                    "reveal": cls._ensure_text(item.get("reveal")),
                    "emotional_impact": cls._ensure_text(item.get("emotional_impact")),
                    "aftermath": cls._ensure_text(item.get("aftermath") or item.get("aftershock")),
                }
            )
        return normalized

    @classmethod
    def _normalize_story_lines(cls, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key_progressions_raw = item.get("key_progressions", [])
            if not isinstance(key_progressions_raw, list):
                key_progressions_raw = []
            key_progressions: list[dict[str, str]] = []
            for index, progression in enumerate(key_progressions_raw, start=1):
                if not isinstance(progression, dict):
                    continue
                key_progressions.append(
                    {
                        "chapter_id": cls._ensure_text(progression.get("chapter_id") or f"ch_{index:03d}"),
                        "plot": cls._ensure_text(progression.get("plot") or progression.get("milestone") or progression.get("event")),
                    }
                )
            normalized.append(
                {
                    "name": cls._ensure_text(item.get("name") or item.get("line_name")),
                    "visibility": cls._ensure_text(item.get("visibility") or item.get("line_visibility")),
                    "line_type": cls._ensure_text(item.get("line_type")),
                    "line_goal": cls._ensure_text(item.get("line_goal")),
                    "start_state": cls._ensure_text(item.get("start_state")),
                    "midpoint_shift": cls._ensure_text(item.get("midpoint_shift")),
                    "end_state": cls._ensure_text(item.get("end_state")),
                    "core_question": cls._ensure_text(item.get("core_question")),
                    "key_progressions": key_progressions,
                }
            )
        return normalized

    @classmethod
    def _normalize_chapter_briefs(cls, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            reentry_focus = item.get("character_reentry_focus", {})
            if not isinstance(reentry_focus, dict):
                reentry_focus = {}
            normalized.append(
                {
                    "chapter_id": cls._ensure_text(item.get("chapter_id") or f"ch_{index:03d}"),
                    "title": cls._ensure_text(item.get("title")),
                    "chapter_type": cls._ensure_text(item.get("chapter_type")),
                    "active_lines": cls._ensure_list(item.get("active_lines")),
                    "active_twists": cls._ensure_list(item.get("active_twists")),
                    "summary": cls._ensure_text(item.get("summary")),
                    "incoming_hook": cls._ensure_text(item.get("incoming_hook")),
                    "opening_hook": cls._ensure_text(item.get("opening_hook")),
                    "core_scene": cls._ensure_text(item.get("core_scene")),
                    "chapter_object": cls._ensure_text(item.get("chapter_object")),
                    "reader_emotion": cls._ensure_text(item.get("reader_emotion")),
                    "reader_belief": cls._ensure_text(item.get("reader_belief")),
                    "allowed_info": cls._ensure_list(item.get("allowed_info")),
                    "allowed_clues": cls._ensure_list(item.get("allowed_clues")),
                    "forbidden": cls._ensure_list(item.get("forbidden")),
                    "world_limit": cls._ensure_text(item.get("world_limit")),
                    "character_focus": cls._ensure_list(item.get("character_focus")),
                    "character_shift": cls._ensure_text(item.get("character_shift")),
                    "relationship_reprice": cls._ensure_text(item.get("relationship_reprice")),
                    "emotional_turn": cls._ensure_text(item.get("emotional_turn")),
                    "backstory_trigger": cls._ensure_text(item.get("backstory_trigger")),
                    "scene_engine": cls._ensure_text(item.get("scene_engine") or "opening_pressure"),
                    "clue_reveal_style": cls._ensure_text(item.get("clue_reveal_style")),
                    "character_reentry_focus": {
                        cls._ensure_text(key): cls._ensure_text(value)
                        for key, value in reentry_focus.items()
                        if cls._ensure_text(key) and cls._ensure_text(value)
                    },
                    "human_pain_anchor": cls._ensure_text(item.get("human_pain_anchor")),
                    "small_payoff": cls._ensure_text(item.get("small_payoff")),
                    "ending_pull": cls._ensure_text(item.get("ending_pull")),
                    "info_budget": cls._ensure_text(item.get("info_budget")),
                }
            )
        return normalized

    @classmethod
    def _normalize_character_milestones(cls, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            axes_raw = item.get("axes", [])
            if not isinstance(axes_raw, list):
                axes_raw = []
            # Compatibility: allow compact schema
            # {"character_name":"A","milestone_list":[{"axis":"情感","stages":["阶段一","阶段二","阶段三"]}]}
            if not axes_raw:
                milestone_list = item.get("milestone_list", [])
                if isinstance(milestone_list, list):
                    converted_axes: list[dict[str, Any]] = []
                    for milestone in milestone_list:
                        if not isinstance(milestone, dict):
                            continue
                        axis_name = cls._ensure_text(milestone.get("axis"))
                        stages_raw = milestone.get("stages", [])
                        if isinstance(stages_raw, str):
                            stages_raw = cls._ensure_list(stages_raw)
                        if not isinstance(stages_raw, list):
                            stages_raw = []
                        phases = [
                            {
                                "phase": f"阶段{idx}",
                                "label": cls._ensure_text(stage),
                                "scenes": [],
                            }
                            for idx, stage in enumerate(stages_raw, start=1)
                            if cls._ensure_text(stage)
                        ]
                        converted_axes.append({"axis": axis_name, "phases": phases})
                    axes_raw = converted_axes
            axes: list[dict[str, Any]] = []
            milestone_list: list[dict[str, Any]] = []
            for axis_item in axes_raw:
                if not isinstance(axis_item, dict):
                    continue
                phases_raw = axis_item.get("phases", [])
                if not isinstance(phases_raw, list):
                    phases_raw = []
                phases: list[dict[str, Any]] = []
                for phase_item in phases_raw:
                    if not isinstance(phase_item, dict):
                        continue
                    scenes_raw = phase_item.get("scenes", [])
                    if not isinstance(scenes_raw, list):
                        scenes_raw = []
                    scenes: list[dict[str, str]] = []
                    for scene_item in scenes_raw:
                        if not isinstance(scene_item, dict):
                            continue
                        scenes.append(
                            {
                                "title": cls._ensure_text(scene_item.get("title")),
                                "trigger": cls._ensure_text(scene_item.get("trigger")),
                                "psychology": cls._ensure_text(scene_item.get("psychology")),
                                "outcome": cls._ensure_text(scene_item.get("outcome")),
                            }
                        )
                    phases.append(
                        {
                            "phase": cls._ensure_text(phase_item.get("phase")),
                            "label": cls._ensure_text(phase_item.get("label")),
                            "scenes": scenes,
                        }
                    )
                axes.append({"axis": cls._ensure_text(axis_item.get("axis")), "phases": phases})
                milestone_list.append(
                    {
                        "axis": cls._ensure_text(axis_item.get("axis")),
                        "stages": [cls._ensure_text(phase_item.get("label")) for phase_item in phases if cls._ensure_text(phase_item.get("label"))],
                    }
                )
            card_name = cls._ensure_text(item.get("character_card_name"))
            card_index_raw = item.get("character_card_index")
            card_index = card_index_raw if isinstance(card_index_raw, int) else -1
            normalized.append(
                {
                    "character_name": cls._ensure_text(item.get("character_name")),
                    "character_card_name": card_name,
                    "character_card_index": card_index,
                    "milestone_list": milestone_list,
                    "axes": axes,
                }
            )
        return normalized

