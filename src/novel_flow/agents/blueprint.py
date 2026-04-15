from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.base import BaseAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import AgentResult, BookBlueprint, BookDocument, ChapterPlan, CharacterCard, StoryPremise
from novel_flow.prompting.templates import PromptLibrary
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
        reference_pack: str = "暂无额外参考资料。",
    ) -> dict[str, Any]:
        ev.emit("agent_start", agent=self.name, title="Build story spine", query=research_query)
        prompt = self.prompt_library.render(
            "writer/story_spine.txt",
            research_query=research_query,
            style_request=style_request or "未指定",
            seed_json="{}",
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="story_spine")
        parsed["premise"] = self._normalize_premise_payload(dict(parsed["premise"]))
        ev.emit("blueprint_spine_ready", agent=self.name, title="Story spine ready", premise_title=str(parsed["premise"]["title"]))
        return parsed

    def build_character_bible(
        self,
        research_query: str,
        premise: StoryPremise,
        volume_titles: list[str],
        reference_pack: str = "暂无额外参考资料。",
    ) -> list[CharacterCard]:
        ev.emit("agent_start", agent=self.name, title="Build character bible", query=research_query)
        prompt = self.prompt_library.render(
            "writer/character_bible.txt",
            research_query=research_query,
            premise_json=premise.model_dump_json(indent=2),
            volume_titles_json=str(volume_titles),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="character_bible")
        characters = [CharacterCard.model_validate(item) for item in parsed["characters"]]
        ev.emit("blueprint_characters_ready", agent=self.name, title="Character bible ready", character_count=len(characters))
        return characters

    def build_chapter_roadmap(
        self,
        research_query: str,
        premise: StoryPremise,
        characters: list[CharacterCard],
        volume_titles: list[str],
        reference_pack: str = "暂无额外参考资料。",
    ) -> list[ChapterPlan]:
        ev.emit("agent_start", agent=self.name, title="Build chapter roadmap", query=research_query)
        prompt = self.prompt_library.render(
            "writer/chapter_roadmap.txt",
            research_query=research_query,
            premise_json=premise.model_dump_json(indent=2),
            characters_json=self._json_dump([item.model_dump(mode="json") for item in characters]),
            volume_titles_json=str(volume_titles),
            reference_pack=reference_pack,
        )
        parsed = self._generate_json_payload(prompt, label="chapter_roadmap")
        parsed["chapter_plans"] = [self._normalize_chapter_plan_payload(dict(item)) for item in parsed["chapter_plans"]]
        chapter_plans = [ChapterPlan.model_validate(item) for item in parsed["chapter_plans"]]
        ev.emit("blueprint_roadmap_ready", agent=self.name, title="Chapter roadmap ready", chapter_count=len(chapter_plans))
        return chapter_plans

    def build_blueprint(
        self,
        research_query: str,
        style_request: str = "",
        reference_pack: str = "暂无额外参考资料。",
    ) -> BookBlueprint:
        ev.emit("agent_start", agent=self.name, title="Build blueprint", query=research_query)
        spine = self.build_story_spine(research_query, style_request=style_request, reference_pack=reference_pack)
        premise = StoryPremise.model_validate(spine["premise"])
        volume_titles = [str(item) for item in spine["volume_titles"]]
        characters = self.build_character_bible(research_query, premise, volume_titles, reference_pack=reference_pack)
        chapter_plans = self.build_chapter_roadmap(research_query, premise, characters, volume_titles, reference_pack=reference_pack)
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
        if action == "chapter_roadmap":
            premise = StoryPremise.model_validate(kwargs["premise"])
            characters = [CharacterCard.model_validate(item) for item in kwargs["characters"]]
            plans = self.build_chapter_roadmap(
                str(kwargs["research_query"]),
                premise,
                characters,
                list(kwargs["volume_titles"]),
                reference_pack=str(kwargs.get("reference_pack", "暂无额外参考资料。")),
            )
            return AgentResult(agent_name=self.name, success=True, message="Chapter roadmap built.", payload={"chapter_plans": [item.model_dump(mode="json") for item in plans]})
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

    def _generate_json_text(self, prompt: str) -> str:
        messages = [
            LLMMessage(role="system", content=self.prompt_library.load("writer/system.txt")),
            LLMMessage(role="user", content=prompt),
        ]
        return self.llm_client.generate(messages=messages, temperature=0.7).strip()

    def _generate_json_payload(self, prompt: str, *, label: str) -> dict[str, Any]:
        raw = self._generate_json_text(prompt)
        try:
            return extract_json_object(raw)
        except Exception as exc:
            ev.emit(
                "json_repair",
                agent=self.name,
                title=f"Repair JSON: {label}",
                error=str(exc),
                raw_preview=raw[:1000],
            )
            repair_prompt = self.prompt_library.render(
                "writer/repair_json.txt",
                source_prompt=prompt[:4000],
                error=str(exc),
                raw_text=raw[:12000],
            )
            repaired = self._generate_json_text(repair_prompt)
            return extract_json_object(repaired)

    @staticmethod
    def _json_dump(payload: Any) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @classmethod
    def _normalize_premise_payload(cls, premise: dict[str, Any]) -> dict[str, Any]:
        for key in ("escalation_path", "twist_blueprint", "stage_payoffs", "selling_points"):
            premise[key] = cls._ensure_list(premise.get(key, []))
        return premise

    @classmethod
    def _normalize_chapter_plan_payload(cls, plan: dict[str, Any]) -> dict[str, Any]:
        for key in ("phase", "story_function", "key_turn", "payoff", "next_route_hint"):
            if key in plan and plan[key] is None:
                plan[key] = ""
        return plan

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
