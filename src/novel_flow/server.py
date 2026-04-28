from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from novel_flow import events as ev
from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.config import Settings
from novel_flow.events import EventBus, PipelineEvent, RunCancelledError, check_cancelled
from novel_flow.llm.base import LLMClient
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import (
    ActualChapterSummary,
    BookBlueprint,
    BookDocument,
    ChapterBatchWindow,
    ChapterBrief,
    ChapterBriefGenerationInput,
    CharacterCard,
    CriticReport,
    NewCharacterCandidate,
    PatchInstruction,
    PatchOperation,
    StoryLine,
    StoryPremise,
    TwistDesign,
    Volume,
    WorkflowStage,
    WorkflowState,
)
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.patcher import PatchExecutor
from novel_flow.services.reference_library import ReferenceLibrary
from novel_flow.services.selectors import (
    get_character_card_by_name,
)
from novel_flow.services.style_cards import list_novel_type_options, resolve_style_profile

if TYPE_CHECKING:
    from novel_flow.storage.sqlite_store import SQLiteStore

@dataclass
class AppStores:
    formal: SQLiteStore
    test: SQLiteStore
    settings: Settings

@dataclass
class RunHandle:
    run_id: str
    mode: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class NovelApp:
    _STEP_TITLES = {
        "step_1": "1 大纲+蓝图",
        "step_2": "2 背景系+世界观",
        "step_3": "3 角色卡",
        "step_4": "4 客观事件时间线",
        "step_5": "5 角色发展线",
        "step_6": "6 反转设计",
        "step_7": "7 明线暗线发展线",
        "step_8": "8 章节摘要规划",
    }
    _STEP_STORY_BLUEPRINT_FIELDS = {
        "step_2": "story_engine",
        "step_4": "event_timeline",
        "step_6": "twist_designs",
        "step_7": "story_lines",
        "step_8": "chapter_briefs",
    }
    _STEP_METADATA_FIELDS = {
        "step_5": "character_milestones",
    }

    def __init__(self, stores: AppStores) -> None:
        self.stores = stores
        self._run_handles: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _chapter_ids_from_book(book: BookDocument) -> list[str]:
        chapter_ids: list[str] = []
        for volume in book.volumes:
            for chapter in volume.chapters:
                chapter_id = str(chapter.id or "").strip()
                if chapter_id:
                    chapter_ids.append(chapter_id)
        return chapter_ids

    @classmethod
    def _prune_book_chapter_metadata(cls, book: BookDocument) -> bool:
        existing_ids = cls._chapter_ids_from_book(book)
        existing_set = set(existing_ids)
        changed = False

        def _set_meta(key: str, value: Any) -> None:
            nonlocal changed
            if book.metadata.get(key) != value:
                book.metadata[key] = value
                changed = True

        def _drop_meta(key: str) -> None:
            nonlocal changed
            if key in book.metadata:
                book.metadata.pop(key, None)
                changed = True

        for deprecated_key in ("planning_phase", "style", "scene_plans", "blueprint_review", "scene_only_characters"):
            _drop_meta(deprecated_key)

        completed_ids = [str(item) for item in book.metadata.get("completed_chapter_ids", []) if str(item).strip()]
        _set_meta("completed_chapter_ids", [item for item in completed_ids if item in existing_set])

        actual_summaries = list(book.metadata.get("actual_chapter_summaries", []) or [])
        _set_meta(
            "actual_chapter_summaries",
            [
                item
                for item in actual_summaries
                if isinstance(item, dict) and str(item.get("chapter_id", "")).strip() in existing_set
            ],
        )

        for metadata_key in ("writing_chapter_runs", "writer_context_debug", "critic_reports"):
            existing = book.metadata.get(metadata_key)
            if isinstance(existing, dict):
                cleaned = {
                    str(key): value
                    for key, value in existing.items()
                    if str(key).strip() in existing_set
                }
                _set_meta(metadata_key, cleaned)

        last_written = str(book.metadata.get("last_written_chapter_id", "")).strip()
        if last_written not in existing_set:
            _set_meta("last_written_chapter_id", existing_ids[-1] if existing_ids else "")

        critic_reports_map = (
            dict(book.metadata.get("critic_reports", {}) or {})
            if isinstance(book.metadata.get("critic_reports"), dict)
            else {}
        )
        latest_critic_payload = None
        preferred_ids: list[str] = []
        current_last_written = str(book.metadata.get("last_written_chapter_id", "")).strip()
        if current_last_written:
            preferred_ids.append(current_last_written)
        preferred_ids.extend(chapter_id for chapter_id in reversed(existing_ids) if chapter_id not in preferred_ids)
        for chapter_id in preferred_ids:
            report_bundle = critic_reports_map.get(chapter_id)
            if not isinstance(report_bundle, dict):
                continue
            aggregate = report_bundle.get("aggregate")
            if isinstance(aggregate, dict):
                latest_critic_payload = aggregate
                break
        if latest_critic_payload is None and existing_ids:
            current_latest_critic = book.metadata.get("latest_critic_report")
            if isinstance(current_latest_critic, dict):
                latest_critic_payload = current_latest_critic
        _set_meta("latest_critic_report", latest_critic_payload)
        return changed

    def list_novels(self, mode: str) -> list[dict[str, Any]]:
        store = self._store(mode)
        novels = store.list_books()
        for item in novels:
            item["latest_run_id"] = store.latest_run_for_book(item["book_id"])
        return novels

    def get_novel(self, mode: str, book_id: str) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            return {}
        if self._prune_book_chapter_metadata(book):
            book.updated_at = datetime.now(timezone.utc)
            store.save_book(book)
        chapter_ids = self._chapter_ids_from_book(book)
        latest_run_id = store.latest_run_for_book(book_id)
        latest_stage = None
        if latest_run_id:
            state = store.load_workflow_state(latest_run_id)
            if state is not None:
                latest_stage = state.stage.value
        blueprint_review = None
        if latest_run_id:
            for row in reversed(store.list_run_outputs(latest_run_id)):
                if row["output_type"] == "blueprint_review":
                    blueprint_review = self._parse_json(row["payload_json"])
                    break
        critic = None
        metadata_critic = book.metadata.get("latest_critic_report")
        if isinstance(metadata_critic, dict):
            try:
                critic = CriticReport.model_validate(metadata_critic)
            except Exception:  # noqa: BLE001
                critic = None
        if critic is None and chapter_ids:
            critic = store.load_latest_critic_report(book_id)
        return {
            "book": book.model_dump(mode="json"),
            "critic": critic.model_dump(mode="json") if critic else None,
            "blueprint_review": blueprint_review,
            "latest_run_id": latest_run_id,
            "latest_stage": latest_stage,
            "runs": self.list_runs(mode, book_id),
        }

    def list_runs(self, mode: str, book_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._store(mode).list_runs(book_id=book_id, limit=50)
        for row in rows:
            handle = self._handle(str(row["run_id"]))
            row["is_running"] = bool(handle and handle.is_running)
            row["cancel_requested"] = bool(handle and handle.cancel_event.is_set())
        return rows

    def get_run(self, mode: str, run_id: str) -> dict[str, Any]:
        store = self._store(mode)
        state = store.load_workflow_state(run_id)
        handle = self._handle(run_id)
        outputs = [
            {
                "id": row["id"],
                "agent": row["agent"],
                "output_type": row["output_type"],
                "title": row["title"],
                "created_at": row["created_at"],
                "payload": self._parse_json(row["payload_json"]),
            }
            for row in store.list_run_outputs(run_id)
        ]
        events = []
        for row in store.list_recent_events(run_id, limit=2000):
            item = dict(row)
            item["payload"] = self._parse_json(item["payload_json"])
            events.append(item)
        chapter_blocks = store.list_chapter_blocks(run_id=run_id, latest_only=True)
        chapter_preview = self._build_chapter_preview(outputs=outputs, chapter_blocks=chapter_blocks)
        return {
            "run_id": run_id,
            "stage": state.stage.value if state else None,
            "current_book_id": state.current_book_id if state else None,
            "context": dict(state.context or {}) if state else {},
            "updated_at": state.updated_at.isoformat() if state else None,
            "is_running": bool(handle and handle.is_running),
            "cancel_requested": bool(handle and handle.cancel_event.is_set()),
            "outputs": outputs,
            "events": events,
            "chapter_blocks": chapter_blocks,
            "chapter_preview": chapter_preview,
        }

    @staticmethod
    def _build_chapter_preview(
        *,
        outputs: list[dict[str, Any]],
        chapter_blocks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for item in reversed(outputs):
            if str(item.get("output_type") or "") != "chapter_live_preview":
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            content_blocks = payload.get("content_blocks")
            if not isinstance(content_blocks, list):
                content_blocks = []
            character_mindsets = payload.get("character_mindsets")
            if not isinstance(character_mindsets, list):
                character_mindsets = []
            final_version_raw = payload.get("final_version", 0)
            try:
                final_version = max(int(final_version_raw), 0)
            except (TypeError, ValueError):
                final_version = 0
            return {
                "chapter_id": str(payload.get("chapter_id") or ""),
                "chapter_title": str(payload.get("chapter_title") or payload.get("chapter_id") or ""),
                "is_finalized": bool(payload.get("is_finalized")),
                "final_text": str(payload.get("final_text") or ""),
                "final_version": final_version,
                "content_blocks": content_blocks,
                "character_mindsets": character_mindsets,
                "preview_mode": str(payload.get("preview_mode") or ""),
            }
        if chapter_blocks:
            first = chapter_blocks[0]
            return {
                "chapter_id": first["chapter_id"],
                "chapter_title": first["chapter_title"],
                "is_finalized": False,
                "final_text": "",
                "final_version": 0,
                "content_blocks": [item["payload"] for item in chapter_blocks],
                "character_mindsets": [],
                "preview_mode": "content_blocks",
            }
        return None

    def delete_novel(self, mode: str, book_id: str) -> None:
        self._store(mode).delete_book(book_id)

    @staticmethod
    def _clean_user_text(value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n").rstrip()

    def list_novel_type_options(self) -> list[dict[str, str]]:
        return list_novel_type_options()

    def create_novel_shell(
        self,
        mode: str,
        *,
        query: str,
        style_request: str = "",
        title: str = "",
        novel_type: str = "",
    ) -> dict[str, Any]:
        store = self._store(mode)
        now = datetime.now(timezone.utc)
        clean_query = self._clean_user_text(query)
        clean_style = self._clean_user_text(style_request)
        clean_title = self._clean_user_text(title).strip()
        title_hint = clean_title or (clean_query.strip().splitlines()[0][:24] or "Untitled Novel").strip()
        style_profile = resolve_style_profile(novel_type=novel_type, style_request=clean_style)
        premise = StoryPremise(
            title=title_hint,
            high_concept="TBD",
            story_summary="",
            genre=style_profile["genre_label"],
            target_style=style_profile["effective_style_request"],
            emotional_hook="TBD",
            central_conflict="TBD",
            core_hook="TBD",
            ending_payoff="TBD",
        )
        book = BookDocument(
            id=f"book_{uuid4().hex[:10]}",
            title=title_hint,
            premise=premise,
            characters=[],
            volumes=[Volume(id="vol_001", title="Volume 1", summary="", chapters=[])],
            metadata={
                "query": clean_query,
                "original_query": clean_query,
                "user_topic": "",
                "style_request": clean_style,
                "effective_style_request": style_profile["effective_style_request"],
                "novel_type": style_profile["novel_type"],
                "novel_type_label": style_profile["novel_type_label"],
                "style_direction": style_profile["style_direction"],
                "assistant_persona_prompt": "",
                "target_words": 100000,
                "total_word_target": "10万字左右",
                "chapter_count_target": "40章左右",
                "chapter_word_target": "2500-3500字",
                "pace_notes": "",
                "volume_titles": ["Volume 1"],
                "character_milestones": [],
                "new_character_candidates": [],
                "story_blueprint": {},
                "next_chapter_index": 0,
                "completed_chapter_ids": [],
                "actual_chapter_summaries": [],
                "latest_critic_report": None,
                "critic_reports": {},
                "writer_context_debug": {},
            },
            created_at=now,
            updated_at=now,
        )
        store.save_book(book)
        return book.model_dump(mode="json")

    def update_novel_concept(
        self,
        mode: str,
        *,
        book_id: str,
        title: str | None,
        premise: dict[str, Any] | None,
        characters: list[dict[str, Any]] | None,
        query: str | None = None,
        user_topic: str | None = None,
        style_request: str | None = None,
        assistant_persona_prompt: str | None = None,
        total_word_target: str | None = None,
        chapter_count_target: str | None = None,
        chapter_word_target: str | None = None,
        pace_notes: str | None = None,
    ) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")

        if premise is not None:
            book.premise = StoryPremise.model_validate(premise)
        if title:
            cleaned_title = self._clean_user_text(title).strip()
            book.title = cleaned_title
            book.premise.title = cleaned_title or book.premise.title
        elif premise is not None:
            book.title = book.premise.title
        if query is not None:
            book.metadata["query"] = self._clean_user_text(query)
        if user_topic is not None:
            book.metadata["user_topic"] = self._clean_user_text(user_topic)
        if style_request is not None:
            cleaned_style = self._clean_user_text(style_request)
            book.metadata["style_request"] = cleaned_style
            if premise is None:
                book.premise.target_style = cleaned_style or "TBD"
        if assistant_persona_prompt is not None:
            book.metadata["assistant_persona_prompt"] = self._clean_user_text(assistant_persona_prompt)
        if total_word_target is not None:
            cleaned_total = self._clean_user_text(total_word_target)
            book.metadata["total_word_target"] = cleaned_total
            digits = "".join(ch for ch in cleaned_total if ch.isdigit())
            if digits:
                try:
                    book.metadata["target_words"] = int(digits)
                except ValueError:
                    pass
        if chapter_count_target is not None:
            book.metadata["chapter_count_target"] = self._clean_user_text(chapter_count_target)
        if chapter_word_target is not None:
            book.metadata["chapter_word_target"] = self._clean_user_text(chapter_word_target)
        if pace_notes is not None:
            book.metadata["pace_notes"] = self._clean_user_text(pace_notes)
        if characters is not None:
            book.characters = [CharacterCard.model_validate(item) for item in characters]
        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return book.model_dump(mode="json")

    def resolve_character_candidate(self, mode: str, *, book_id: str, candidate_id: str, action: str) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        candidates = [
            NewCharacterCandidate.model_validate(item)
            for item in book.metadata.get("new_character_candidates", [])
            if isinstance(item, dict)
        ]
        target = next((item for item in candidates if item.candidate_id == candidate_id), None)
        if target is None:
            raise ValueError(f"Character candidate not found: {candidate_id}")
        remaining = [item for item in candidates if item.candidate_id != candidate_id]
        if action == "add":
            if all(item.name != target.name for item in book.characters):
                book.characters.append(
                    CharacterCard(
                        name=target.name,
                        role=target.role_in_scene or "新增角色",
                        personality=" / ".join(target.provisional_traits),
                        motivation=target.why_needed,
                        relationships="；".join(
                            f"{link.target}：{link.relation}".strip("：")
                            for link in target.links_to_existing_characters
                        ),
                    )
                )
        else:
            raise ValueError(f"Unsupported character candidate action: {action}")
        book.metadata["new_character_candidates"] = [item.model_dump(mode="json") for item in remaining]
        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return {"book": book.model_dump(mode="json")}

    @staticmethod
    def _planning_query(book: BookDocument) -> str:
        topic = str(book.metadata.get("user_topic") or "").strip()
        query = str(book.metadata.get("query") or book.metadata.get("original_query") or book.title).strip()
        if topic and query:
            return f"题材：{topic}\n需求：{query}"
        return topic or query or book.title

    @classmethod
    def _planning_context_payload(cls, book: BookDocument) -> dict[str, Any]:
        step_payload = lambda key: cls._step_payload_from_book(book, key)
        return {
            "book_title": book.title,
            "original_requirement": str(book.metadata.get("original_query") or ""),
            "current_requirement": str(book.metadata.get("query") or ""),
            "user_topic": str(book.metadata.get("user_topic") or ""),
            "style_request": str(book.metadata.get("style_request") or ""),
            "assistant_persona_prompt": str(book.metadata.get("assistant_persona_prompt") or ""),
            "writing_requirements": {
                "total_word_target": str(book.metadata.get("total_word_target") or ""),
                "chapter_count_target": str(book.metadata.get("chapter_count_target") or ""),
                "chapter_word_target": str(book.metadata.get("chapter_word_target") or ""),
                "pace_notes": str(book.metadata.get("pace_notes") or ""),
            },
            "premise": book.premise.model_dump(mode="json"),
            "step_outputs": {
                "step_1_outline_blueprint": step_payload("step_1"),
                "step_2_worldbuilding": step_payload("step_2"),
                "step_3_characters": step_payload("step_3"),
                "step_4_event_timeline": step_payload("step_4"),
                "step_5_character_milestones": step_payload("step_5"),
                "step_6_twist_designs": step_payload("step_6"),
                "step_7_story_lines": step_payload("step_7"),
                "step_8_chapter_briefs": step_payload("step_8"),
            },
        }

    @classmethod
    def _planning_context_json(cls, book: BookDocument) -> str:
        return json.dumps(cls._planning_context_payload(book), ensure_ascii=False, indent=2)

    @classmethod
    def _planning_context_json_for_step(
        cls,
        book: BookDocument,
        step_key: str,
        *,
        slim: bool = False,
        lean: bool = False,
    ) -> str:
        payload = cls._planning_context_payload(book)
        order = {
            "step_1": 1,
            "step_2": 2,
            "step_3": 3,
            "step_4": 4,
            "step_5": 5,
            "step_6": 6,
            "step_7": 7,
            "step_8": 8,
        }
        target_order = order.get(step_key, 99)
        step_outputs = dict(payload.pop("step_outputs", {}) or {})
        payload["target_step"] = step_key
        if slim:
            # slim=True: omit step_outputs, premise, and large text fields since caller passes them directly
            payload.pop("premise", None)
            payload.pop("original_requirement", None)
            payload.pop("current_requirement", None)
        elif lean:
            # lean=True: keep previous_step_outputs, but trim duplicated top-level fields
            # because caller already provides query/style and previous outputs are the hard constraints.
            payload.pop("premise", None)
            payload.pop("original_requirement", None)
            payload.pop("current_requirement", None)
            payload["previous_step_outputs"] = {
                k: v
                for k, v in step_outputs.items()
                if (int(str(k).split("_")[1])) < target_order
            }
        else:
            payload["previous_step_outputs"] = {
                k: v
                for k, v in step_outputs.items()
                if (int(str(k).split("_")[1])) < target_order
            }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _resolve_target_chapter_count(book: BookDocument, story_blueprint: dict[str, Any] | None = None) -> int:
        story_blueprint = dict(story_blueprint or book.metadata.get("story_blueprint", {}) or {})

        def parse_count(text: str) -> int | None:
            digits = "".join(ch for ch in str(text or "") if ch.isdigit())
            if not digits:
                return None
            try:
                return max(1, int(digits))
            except Exception:
                return None

        for candidate in (
            book.metadata.get("chapter_count_target"),
            book.metadata.get("query"),
            book.metadata.get("original_query"),
            book.metadata.get("user_topic"),
        ):
            parsed = parse_count(str(candidate or "").strip())
            if parsed is not None:
                return parsed
        existing_count = len(story_blueprint.get("chapter_briefs", []) or [])
        return max(existing_count, 1)

    @staticmethod
    def _volume_titles_for_book(book: BookDocument) -> list[str]:
        return [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [
            getattr(volume, "title", "Volume 1") for volume in book.volumes
        ] or ["Volume 1"]

    @staticmethod
    def _step8_batch_window(*, total_chapters: int, start_index: int, batch_size: int) -> dict[str, Any]:
        safe_total = max(int(total_chapters or 1), 1)
        safe_start = max(int(start_index or 0), 0)
        safe_batch = max(int(batch_size or 1), 1)
        if safe_start >= safe_total:
            raise ValueError("章节摘要已全部生成完成。")
        end_exclusive = min(safe_start + safe_batch, safe_total)
        return ChapterBatchWindow.model_validate(
            {
                "start_index": safe_start,
                "end_index": end_exclusive - 1,
                "batch_size": end_exclusive - safe_start,
                "total_chapters": safe_total,
                "chapter_ids": [f"ch_{index + 1:03d}" for index in range(safe_start, end_exclusive)],
            }
        ).model_dump(mode="json")

    @classmethod
    def _step8_input_payload(cls, book: BookDocument, *, batch: dict[str, Any], reference_pack: str) -> dict[str, Any]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        batch_model = ChapterBatchWindow.model_validate(batch)
        story_engine = dict(story_blueprint.get("story_engine", {}) or {})
        premise = book.premise

        story_engine_signals = {
            key: value
            for key, value in {
                "engine_sentence": story_engine.get("engine_sentence", ""),
                "default_track": story_engine.get("default_track", ""),
                "narrative_mode": story_engine.get("narrative_mode", ""),
                "viewpoint_strategy": story_engine.get("viewpoint_strategy", ""),
                "reveal_strategy": story_engine.get("reveal_strategy", ""),
                "hook_strategy": story_engine.get("hook_strategy", ""),
            }.items()
            if value
        }
        story_spine = {
            "title": premise.title,
            "high_concept": premise.high_concept,
            "theme_statement": premise.theme_statement,
            "story_summary": premise.story_summary,
            "genre": premise.genre,
            "target_style": premise.target_style,
            "emotional_hook": premise.emotional_hook,
            "central_conflict": premise.central_conflict,
            "core_hook": premise.core_hook,
            "escalation_path": premise.escalation_path,
            "twist_blueprint": premise.twist_blueprint,
            "ending_payoff": premise.ending_payoff,
            "selling_points": premise.selling_points,
            "story_engine_signals": story_engine_signals,
        }

        worldbuilding = {
            key: value
            for key, value in {
                "world_rules": story_engine.get("world_rules", ""),
                "power_structure": story_engine.get("power_structure", ""),
                "world_map": story_engine.get("world_map", ""),
                "structural_inertia": story_engine.get("structural_inertia", ""),
                "rebound_mechanism": story_engine.get("rebound_mechanism", ""),
                "story_trigger": story_engine.get("story_trigger", ""),
                "objective_conditions": story_engine.get("objective_conditions", ""),
            }.items()
            if value
        }
        for key in ("core_theme", "structure_blueprint"):
            value = story_blueprint.get(key)
            if value:
                worldbuilding[key] = value

        character_bible = {
            "characters": [
                {
                    "name": card.name,
                    "identity": card.role,
                    "age_range": "",
                    "occupation": card.occupation,
                    "social_background": card.social_background,
                    "appearance_anchor": card.appearance,
                    "personality_base": card.personality,
                    "speaking_style": "",
                    "behavior_rule": card.behavior_pattern,
                    "initial_state": card.initial_state,
                    "motivation": card.motivation,
                }
                for card in book.characters
            ]
        }

        def chapter_order(chapter_id: str) -> int:
            digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
            return int(digits or "0")

        previous_chapter_briefs: list[dict[str, Any]] = []
        for item in story_blueprint.get("chapter_briefs", []) or []:
            if not isinstance(item, dict):
                continue
            try:
                brief = ChapterBrief.model_validate(item)
            except Exception:
                continue
            if chapter_order(brief.chapter_id) <= batch_model.start_index:
                previous_chapter_briefs.append(brief.model_dump(mode="json"))
        previous_chapter_briefs.sort(key=lambda item: chapter_order(str(item.get("chapter_id", ""))))

        return ChapterBriefGenerationInput.model_validate(
            {
                "batch": batch_model.model_dump(mode="json"),
                "research_query": cls._planning_query(book)[:500],
                "volume_titles_json": cls._volume_titles_for_book(book),
                "story_spine_json": story_spine,
                "worldbuilding_json": worldbuilding,
                "character_bible_json": character_bible,
                "event_timeline_json": [item for item in story_blueprint.get("event_timeline", []) or [] if isinstance(item, dict)],
                "character_milestones_json": [item for item in book.metadata.get("character_milestones", []) or [] if isinstance(item, dict)],
                "twist_designs_json": [item for item in story_blueprint.get("twist_designs", []) or [] if isinstance(item, dict)],
                "story_lines_json": [item for item in story_blueprint.get("story_lines", []) or [] if isinstance(item, dict)],
                "previous_chapter_briefs_json": previous_chapter_briefs,
                "target_chapter_count": batch_model.total_chapters,
                "reference_pack": reference_pack,
            }
        ).model_dump(mode="json")

    @staticmethod
    def _step_title(step_key: str) -> str:
        if step_key not in NovelApp._STEP_TITLES:
            raise ValueError(f"Unsupported step key: {step_key}")
        return NovelApp._STEP_TITLES[step_key]

    @classmethod
    def _step_payload_from_book(cls, book: BookDocument, step_key: str) -> dict[str, Any]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if step_key == "step_1":
            return {
                "premise": book.premise.model_dump(mode="json"),
                "story_engine": story_blueprint.get("story_engine", {}),
            }
        if step_key == "step_3":
            return {"characters": [item.model_dump(mode="json") for item in book.characters]}
        field = cls._STEP_STORY_BLUEPRINT_FIELDS.get(step_key)
        if field is not None:
            return {field: story_blueprint.get(field, {} if field == "story_engine" else [])}
        field = cls._STEP_METADATA_FIELDS.get(step_key)
        if field is not None:
            return {field: book.metadata.get(field, [])}
        raise ValueError(f"Unsupported step key: {step_key}")

    @staticmethod
    def _normalize_step_model_list(
        payload: dict[str, Any],
        *,
        key: str,
        model: type[Any],
        array_error: str,
    ) -> list[dict[str, Any]]:
        raw_items = payload.get(key, [])
        if not isinstance(raw_items, list):
            raise ValueError(array_error)
        return [model.model_validate(item).model_dump(mode="json") for item in raw_items if isinstance(item, dict)]

    @classmethod
    def _normalize_step_payload(cls, step_key: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("步骤结果必须是 JSON 对象。")
        if step_key == "step_1":
            premise_raw = payload.get("premise", {})
            if not isinstance(premise_raw, dict):
                raise ValueError("step_1.premise 必须是 JSON 对象。")
            premise = StoryPremise.model_validate(BlueprintAgent._normalize_premise_payload(dict(premise_raw)))
            return {
                "premise": premise.model_dump(mode="json"),
                "story_engine": BlueprintAgent._normalize_story_engine(payload.get("story_engine", {})),
            }
        if step_key == "step_3":
            characters_raw = payload.get("characters", [])
            if not isinstance(characters_raw, list):
                raise ValueError("step_3.characters 必须是 JSON 数组。")
            valid_characters: list[CharacterCard] = []
            for item in characters_raw:
                if not isinstance(item, dict):
                    continue
                if not str(item.get("name", "")).strip() and not str(item.get("role", "")).strip():
                    continue
                try:
                    valid_characters.append(CharacterCard.model_validate(item))
                except Exception:
                    continue
            if characters_raw and not valid_characters:
                raise ValueError("step_3.characters 中没有可保存的有效角色（至少需要 name 或 role）。")
            return {"characters": [item.model_dump(mode="json") for item in valid_characters]}
        if step_key == "step_7":
            if "chapter_briefs" in payload:
                raise ValueError("step_7 只接受 story_lines，不接受 chapter_briefs。")
        if step_key == "step_8":
            if "chapter_plans" in payload or "scene_beats" in payload:
                raise ValueError("step_8 已升级为 chapter_briefs，请删除旧 chapter_plans / scene_beats 后重新生成。")
        normalizers = {
            "step_2": lambda data: {"story_engine": BlueprintAgent._normalize_story_engine(data.get("story_engine", {}))},
            "step_4": lambda data: {"event_timeline": BlueprintAgent._normalize_event_timeline(data.get("event_timeline", []))},
            "step_5": lambda data: {"character_milestones": BlueprintAgent._normalize_character_milestones(data.get("character_milestones", []))},
            "step_6": lambda data: {
                "twist_designs": cls._normalize_step_model_list(
                    data,
                    key="twist_designs",
                    model=TwistDesign,
                    array_error="step_6.twist_designs 必须是 JSON 数组。",
                )
            },
            "step_7": lambda data: {
                "story_lines": cls._normalize_step_model_list(
                    data,
                    key="story_lines",
                    model=StoryLine,
                    array_error="step_7.story_lines 必须是 JSON 数组。",
                )
            },
            "step_8": lambda data: {
                "chapter_briefs": cls._normalize_step_model_list(
                    data,
                    key="chapter_briefs",
                    model=ChapterBrief,
                    array_error="step_8.chapter_briefs 必须是 JSON 数组。",
                )
            },
        }
        normalizer = normalizers.get(step_key)
        if normalizer is not None:
            return normalizer(payload)
        raise ValueError(f"Unsupported step key: {step_key}")

    @classmethod
    def _apply_step_payload(cls, book: BookDocument, step_key: str, payload: dict[str, Any]) -> None:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if step_key == "step_1":
            premise = StoryPremise.model_validate(payload["premise"])
            book.premise = premise
            book.title = premise.title or book.title
            story_blueprint["story_engine"] = payload.get("story_engine", {})
        elif step_key == "step_3":
            book.characters = [CharacterCard.model_validate(item) for item in payload.get("characters", [])]
            story_blueprint.pop("relationship_network", None)
        elif step_key in cls._STEP_METADATA_FIELDS:
            field = cls._STEP_METADATA_FIELDS[step_key]
            book.metadata[field] = payload.get(field, [])
        elif step_key in cls._STEP_STORY_BLUEPRINT_FIELDS:
            field = cls._STEP_STORY_BLUEPRINT_FIELDS[step_key]
            story_blueprint[field] = payload.get(field, {} if field == "story_engine" else [])
            if step_key == "step_8":
                next_index = int(book.metadata.get("next_chapter_index", 0))
                book.metadata["next_chapter_index"] = min(next_index, len(story_blueprint["chapter_briefs"]))
                completed = set(book.metadata.get("completed_chapter_ids", []))
                book.metadata["completed_chapter_ids"] = [
                    item["chapter_id"]
                    for item in story_blueprint["chapter_briefs"]
                    if str(item.get("chapter_id", "")) in completed
                ]
                book.metadata.pop("chapter_plans", None)
        else:
            raise ValueError(f"Unsupported step key: {step_key}")
        book.metadata["story_blueprint"] = story_blueprint

    def save_step_result(self, mode: str, *, book_id: str, step_key: str, payload_text: str) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"步骤结果不是合法 JSON：{exc}") from exc
        normalized = self._normalize_step_payload(step_key, payload)
        if step_key == "step_3":
            old_count = len(book.characters or [])
            new_count = len(normalized.get("characters", []) or [])
            if old_count > 0 and new_count == 0:
                raise ValueError("检测到角色卡将被清空，已阻止保存。请刷新页面后重试，或确认至少保留一个有效角色（name/role）。")
        self._apply_step_payload(book, step_key, normalized)
        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return {
            "book": book.model_dump(mode="json"),
            "step_payload": self._step_payload_from_book(book, step_key),
        }

    def delete_chapter(self, mode: str, *, book_id: str, chapter_id: str) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        target_chapter_id = str(chapter_id or "").strip()
        if not target_chapter_id:
            raise ValueError("chapter_id is required")

        removed = False
        for volume in book.volumes:
            original = list(volume.chapters)
            filtered = [chapter for chapter in original if chapter.id != target_chapter_id]
            if len(filtered) != len(original):
                volume.chapters = filtered
                removed = True
        if not removed:
            raise ValueError(f"Chapter not found: {target_chapter_id}")

        completed_ids = [str(item) for item in book.metadata.get("completed_chapter_ids", []) if str(item).strip()]
        book.metadata["completed_chapter_ids"] = [item for item in completed_ids if item != target_chapter_id]
        all_written_ids = [chapter.id for volume in book.volumes for chapter in volume.chapters if chapter.id]
        if str(book.metadata.get("last_written_chapter_id", "")) == target_chapter_id:
            book.metadata["last_written_chapter_id"] = all_written_ids[-1] if all_written_ids else ""

        chapter_order_ids: list[str] = []
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        for item in story_blueprint.get("chapter_briefs", []) or []:
            if isinstance(item, dict) and str(item.get("chapter_id", "")).strip():
                chapter_order_ids.append(str(item.get("chapter_id")))
        target_index = None
        for idx, chapter_id in enumerate(chapter_order_ids):
            if chapter_id == target_chapter_id:
                target_index = idx
                break
        current_next = int(book.metadata.get("next_chapter_index", 0))
        if target_index is not None:
            book.metadata["next_chapter_index"] = min(current_next, target_index)
        else:
            book.metadata["next_chapter_index"] = min(current_next, len(chapter_order_ids))
        self._prune_book_chapter_metadata(book)

        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return {"book": book.model_dump(mode="json")}

    def revise_step_result(
        self,
        mode: str,
        *,
        book_id: str,
        step_key: str,
        payload_text: str,
        revision_mode: str,
        guidance: str = "",
    ) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"当前步骤草稿不是合法 JSON：{exc}") from exc
        normalized_current = self._normalize_step_payload(step_key, payload)
        step_title = self._step_title(step_key)
        blueprint_agent = self._build_blueprint_agent()
        user_guidance = self._clean_user_text(guidance or "")
        revision_label = "璐ㄦ淇敼" if revision_mode == "review" else "鎸囦护淇敼"
        prompt = f"""
浣犳鍦ㄥ府鍔╀綔鑰呬慨璁㈠皬璇磋鍒掍腑鐨勫崟涓楠ょ粨鏋溿€?涓嶈鍐欐鏂囷紝涓嶈杈撳嚭 Markdown锛屽彧杈撳嚭鍚堟硶 JSON銆?
姝ラ鏍囪瘑: {step_key}
姝ラ鍚嶇О: {step_title}
淇妯″紡: {revision_label}

鍘熷闇€姹備笌鍓嶅簭姝ラ涓婁笅鏂?JSON:
{self._planning_context_json(book)}

褰撳墠姝ラ缁撴灉 JSON:
{json.dumps(normalized_current, ensure_ascii=False, indent=2)}

用户额外指令:
{user_guidance or "无。若是质检修改，请先审查合理性，再给出更稳妥的修正版。"}

宸ヤ綔瑕佹眰:
1. 鍙慨璁㈠綋鍓嶆楠わ紝涓嶈瓒婄晫鏀瑰啓鍏朵粬姝ラ銆?2. 淇濈暀宸茬粡鍚堢悊鐨勫唴瀹癸紝鍙慨琛ユ槑鏄句笉娓呮櫚銆佷笉涓€鑷淬€佷笉鍙惤鍦般€佸瓧娈电己澶辨垨琛ㄨ揪杩囧急鐨勯儴鍒嗐€?3. 蹇呴』鍏呭垎鍙傝€冨師濮嬮渶姹傦紝浠ュ強鍓嶉潰姝ラ宸叉湁浜х墿銆?4. 濡傛灉鏄€滆川妫€淇敼鈥濓紝鍏堝仛绠€鐭鏌ワ紝鎸囧嚭褰撳墠缁撴灉鏈€闇€瑕佹敼鐨勭偣锛屽啀缁欏嚭淇鐗堛€?5. 濡傛灉鏄€滄寚浠や慨鏀光€濓紝浼樺厛钀藉疄鐢ㄦ埛鎸囦护锛屽悓鏃朵繚鎸佸拰鍓嶅簭姝ラ涓€鑷淬€?6. revised_payload 鐨勯《灞傜粨鏋勫繀椤讳笌褰撳墠姝ラ涓€鑷淬€?
鍙緭鍑哄涓?JSON:
{{
  "review_notes": ["寤鸿1", "寤鸿2"],
  "revised_payload": {json.dumps(normalized_current, ensure_ascii=False, indent=2)}
}}
""".strip()
        parsed = blueprint_agent._generate_json_payload(prompt, label=f"revise_step_result:{step_key}:{revision_mode}")
        review_notes = BlueprintAgent._ensure_list(parsed.get("review_notes", []))
        revised_payload = self._normalize_step_payload(step_key, parsed.get("revised_payload", normalized_current))
        return {
            "step_key": step_key,
            "step_title": step_title,
            "review_notes": review_notes,
            "step_payload": revised_payload,
            "draft_json": json.dumps(revised_payload, ensure_ascii=False, indent=2),
        }

    def revise_single_character(
        self,
        mode: str,
        *,
        book_id: str,
        payload_text: str,
        character_index: int,
        guidance: str = "",
    ) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"当前步骤草稿不是合法 JSON：{exc}") from exc
        normalized_current = self._normalize_step_payload("step_3", payload)
        characters_raw = normalized_current.get("characters", [])
        if not isinstance(characters_raw, list) or not characters_raw:
            raise ValueError("当前角色列表为空，无法执行单角色指令修改。")
        if character_index < 0 or character_index >= len(characters_raw):
            raise ValueError(f"角色索引超出范围：{character_index}")

        current_character = CharacterCard.model_validate(characters_raw[character_index])
        planning = self._planning_context_payload(book)
        step_outputs = planning.get("step_outputs", {})
        step_1 = step_outputs.get("step_1_outline_blueprint", {})
        step_2 = step_outputs.get("step_2_worldbuilding", {})
        user_guidance = self._clean_user_text(guidance or "")

        prompt = PromptLibrary().render(
            "writer/revise_single_character.txt",
            step1_json=json.dumps(step_1, ensure_ascii=False, indent=2),
            step2_json=json.dumps(step_2, ensure_ascii=False, indent=2),
            current_character_json=json.dumps(current_character.model_dump(mode="json"), ensure_ascii=False, indent=2),
            user_guidance=user_guidance or "无，保持当前角色优势并补强短板。",
        )
        blueprint_agent = self._build_blueprint_agent()
        parsed = blueprint_agent._generate_json_payload(prompt, label="revise_single_character")
        revised_character = CharacterCard.model_validate(parsed.get("revised_character", current_character.model_dump(mode="json")))
        review_notes = BlueprintAgent._ensure_list(parsed.get("review_notes", []))

        revised_payload = dict(normalized_current)
        revised_characters = [CharacterCard.model_validate(item).model_dump(mode="json") for item in characters_raw]
        revised_characters[character_index] = revised_character.model_dump(mode="json")
        revised_payload["characters"] = revised_characters

        return {
            "step_key": "step_3",
            "step_title": self._step_title("step_3"),
            "review_notes": review_notes,
            "step_payload": revised_payload,
            "draft_json": json.dumps(revised_payload, ensure_ascii=False, indent=2),
            "revised_character": revised_character.model_dump(mode="json"),
            "character_index": character_index,
        }

    def revise_single_character_milestone(
        self,
        mode: str,
        *,
        book_id: str,
        payload_text: str,
        character_index: int,
        guidance: str = "",
    ) -> dict[str, Any]:
        store = self._store(mode)
        book = store.load_book(book_id)
        if book is None:
            raise ValueError(f"Book not found: {book_id}")
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"当前步骤草稿不是合法 JSON：{exc}") from exc
        normalized_current = self._normalize_step_payload("step_5", payload)
        milestones_raw = normalized_current.get("character_milestones", [])
        if not isinstance(milestones_raw, list) or not milestones_raw:
            raise ValueError("当前角色发展线为空，无法执行单角色指令调整。")
        if character_index < 0 or character_index >= len(milestones_raw):
            raise ValueError(f"角色发展线索引超出范围：{character_index}")
        current_milestone = milestones_raw[character_index] if isinstance(milestones_raw[character_index], dict) else {}
        target_name = str(current_milestone.get("character_name") or "").strip()
        linked_card_index = current_milestone.get("character_card_index")
        linked_card_name = str(current_milestone.get("character_card_name") or "").strip()

        named_characters = [item for item in book.characters if str(item.name or "").strip()]
        target_character: CharacterCard | None = None
        if isinstance(linked_card_index, int) and 0 <= linked_card_index < len(named_characters):
            target_character = named_characters[linked_card_index]
        if target_character is None:
            target_character = get_character_card_by_name(named_characters, linked_card_name)
        if target_character is None:
            target_character = get_character_card_by_name(named_characters, target_name)
        if target_character is None and character_index < len(named_characters):
            target_character = named_characters[character_index]
        if target_character is None:
            raise ValueError("未找到可对应的角色卡，无法调整该角色发展线。")

        matched_name = str(target_character.name or "").strip()
        user_guidance = self._clean_user_text(guidance or "")
        query = self._planning_query(book)
        query_500 = query[:500]
        planning = self._planning_context_payload(book)
        step_outputs = planning.get("step_outputs", {})
        first_three_step_inputs = {
            "step_1_outline_blueprint": step_outputs.get("step_1_outline_blueprint", {}),
            "step_2_worldbuilding": step_outputs.get("step_2_worldbuilding", {}),
            "step_3_characters": step_outputs.get("step_3_characters", {}),
        }
        research_query = (
            f"{query_500}\n"
            f"当前角色：{matched_name}"
        )

        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        story_engine = dict(story_blueprint.get("story_engine") or {})
        blueprint_agent = self._build_blueprint_agent()
        revised_milestone = blueprint_agent.build_single_character_milestone(
            research_query=research_query,
            character=target_character,
            premise=book.premise,
            story_engine=story_engine,
            user_guidance=user_guidance or "无，保持当前发展线优势并补强短板。",
        )
        revised_milestone["character_name"] = matched_name
        revised_milestone["character_card_name"] = matched_name
        revised_milestone["character_card_index"] = (
            named_characters.index(target_character) if target_character in named_characters else character_index
        )

        revised_payload = dict(normalized_current)
        revised_items = [dict(item) if isinstance(item, dict) else {} for item in milestones_raw]
        revised_items[character_index] = revised_milestone
        revised_payload["character_milestones"] = BlueprintAgent._normalize_character_milestones(revised_items)

        return {
            "step_key": "step_5",
            "step_title": self._step_title("step_5"),
            "review_notes": [f"已按指令重生成角色「{matched_name}」的发展线草稿，请确认后保存。"],
            "step_payload": revised_payload,
            "draft_json": json.dumps(revised_payload, ensure_ascii=False, indent=2),
            "character_index": character_index,
            "character_name": matched_name,
            "first_three_step_inputs": first_three_step_inputs,
        }

    def revise_step_result_run(
        self,
        mode: str,
        *,
        book_id: str,
        step_key: str,
        payload_text: str,
        revision_mode: str,
        guidance: str = "",
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={
                    "action": "revise_step_result",
                    "step_key": step_key,
                    "revision_mode": revision_mode,
                },
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                result = self.revise_step_result(
                    mode,
                    book_id=book_id,
                    step_key=step_key,
                    payload_text=payload_text,
                    revision_mode=revision_mode,
                    guidance=guidance,
                )
                check_cancelled()
                revision_label = "Review revision draft" if revision_mode == "review" else "Instruction revision draft"
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "step_revision_draft",
                    revision_label,
                    result,
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def revise_single_character_run(
        self,
        mode: str,
        *,
        book_id: str,
        payload_text: str,
        character_index: int,
        guidance: str = "",
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={
                    "action": "revise_single_character",
                    "step_key": "step_3",
                    "revision_mode": "instruction",
                    "character_index": character_index,
                },
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                result = self.revise_single_character(
                    mode,
                    book_id=book_id,
                    payload_text=payload_text,
                    character_index=character_index,
                    guidance=guidance,
                )
                check_cancelled()
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "step_revision_draft",
                    "Step 3 single character instruction revision draft",
                    result,
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def revise_single_character_milestone_run(
        self,
        mode: str,
        *,
        book_id: str,
        payload_text: str,
        character_index: int,
        guidance: str = "",
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={
                    "action": "revise_single_character_milestone",
                    "step_key": "step_5",
                    "revision_mode": "instruction",
                    "character_index": character_index,
                },
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                result = self.revise_single_character_milestone(
                    mode,
                    book_id=book_id,
                    payload_text=payload_text,
                    character_index=character_index,
                    guidance=guidance,
                )
                check_cancelled()
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "step_revision_draft",
                    "Step 5 single character milestone instruction revision draft",
                    result,
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def add_character_run(
        self,
        mode: str,
        *,
        book_id: str,
        guidance: str,
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={"action": "add_character", "step_key": "step_3", "revision_mode": "instruction"},
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(
                    memory,
                    run_id=run_id,
                    book=book,
                    stage="planning",
                    focus=[guidance, "add character", "step_3", book.title],
                    tags=["character", "story structure"],
                )
                new_character = blueprint_agent.add_character(book=book, guidance=guidance, reference_pack=reference_pack)
                check_cancelled()
                if all(item.name != new_character.name for item in book.characters):
                    book.characters.append(new_character)
                else:
                    # 名字冲突时也保留新增意图，防止覆盖旧角色
                    suffix = 2
                    base_name = str(new_character.name).strip() or "新角色"
                    existing_names = {item.name for item in book.characters}
                    unique_name = base_name
                    while unique_name in existing_names:
                        unique_name = f"{base_name}_{suffix}"
                        suffix += 1
                    cloned = CharacterCard.model_validate({**new_character.model_dump(mode="json"), "name": unique_name})
                    book.characters.append(cloned)
                    new_character = cloned
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "character_added",
                    "Step 3 add one character",
                    {"character": new_character.model_dump(mode="json"), "character_count": len(book.characters)},
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def add_character_milestone_run(
        self,
        mode: str,
        *,
        book_id: str,
        guidance: str,
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={"action": "add_character_milestone", "step_key": "step_5", "revision_mode": "instruction"},
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                story_blueprint = dict(book.metadata.get("story_blueprint") or {})
                current_milestones = BlueprintAgent._normalize_character_milestones(book.metadata.get("character_milestones", []))
                planning_context = self._planning_context_json_for_step(book, "step_5", slim=True)
                reference_pack = self._reference_pack_for_book(
                    memory,
                    run_id=run_id,
                    book=book,
                    stage="planning",
                    focus=[guidance, "step_5", "character milestones", "add one line", book.title],
                    tags=["character", "character arc", "story structure"],
                )
                blueprint_agent = self._build_blueprint_agent()
                new_milestone = blueprint_agent.add_character_milestone(
                    research_query=str(book.metadata.get("query") or book.title),
                    premise=book.premise,
                    characters=book.characters,
                    story_blueprint=story_blueprint,
                    character_milestones=current_milestones,
                    guidance=self._clean_user_text(guidance),
                    planning_context_json=planning_context,
                    reference_pack=reference_pack,
                )
                check_cancelled()

                merged = list(current_milestones)
                target_name = str(new_milestone.get("character_name") or "").strip()
                named_characters = [item for item in book.characters if str(item.name or "").strip()]
                if target_name:
                    matched_character = get_character_card_by_name(named_characters, target_name)
                    linked_index = named_characters.index(matched_character) if matched_character in named_characters else -1
                    new_milestone["character_card_name"] = target_name
                    new_milestone["character_card_index"] = linked_index
                target_axes = list(new_milestone.get("axes") or [])
                merged_into_existing = False
                if target_name:
                    for item in merged:
                        if str(item.get("character_name") or "").strip() != target_name:
                            continue
                        existing_axes = list(item.get("axes") or [])
                        existing_axis_names = {str(axis.get("axis") or "").strip() for axis in existing_axes}
                        for axis in target_axes:
                            axis_name = str(axis.get("axis") or "").strip()
                            if axis_name and axis_name in existing_axis_names:
                                continue
                            existing_axes.append(axis)
                            if axis_name:
                                existing_axis_names.add(axis_name)
                        item["axes"] = existing_axes
                        merged_into_existing = True
                        break
                if not merged_into_existing:
                    merged.append(new_milestone)
                merged = BlueprintAgent._normalize_character_milestones(merged)
                revised_payload = {"character_milestones": merged}
                result = {
                    "step_key": "step_5",
                    "step_title": self._step_title("step_5"),
                    "review_notes": ["已新增 1 条角色发展线草稿，请确认后点击保存。"],
                    "step_payload": revised_payload,
                    "draft_json": json.dumps(revised_payload, ensure_ascii=False, indent=2),
                    "added_character_milestone": new_milestone,
                }
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "step_revision_draft",
                    "Step 5 add one character milestone draft",
                    result,
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def stop_run(self, mode: str, run_id: str) -> None:
        handle = self._handle(run_id)
        if handle and handle.mode == mode and handle.is_running:
            handle.cancel_event.set()
        self._store(mode).delete_run(run_id)

    def ai_update_concept(
        self,
        mode: str,
        *,
        book_id: str,
        scope: str,
        target_id: str | None,
        guidance: str,
        llm_provider: str | None = None,
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={"action": "ai_update_concept", "scope": scope, "target_id": target_id or "", "llm_provider": provider or self.stores.settings.llm_provider},
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(
                    memory,
                    run_id=run_id,
                    book=book,
                    stage="planning",
                    focus=[
                        guidance,
                        scope,
                        target_id or "",
                        book.title,
                        book.premise.core_hook,
                        book.premise.central_conflict,
                        "人物塑造",
                        "情节完整",
                    ],
                    tags=["人物塑造", "情节", "故事结构"],
                )
                updated_book = blueprint_agent.revise_concept(book, scope=scope, target_id=target_id, guidance=guidance, reference_pack=reference_pack)
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "BlueprintAgent", "concept_updated", "AI concept update", updated_book.model_dump(mode="json"))
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def ai_update_text(
        self,
        mode: str,
        *,
        book_id: str,
        scope: str,
        target_id: str,
        guidance: str,
        llm_provider: str | None = None,
    ) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PATCHING,
                current_book_id=book.id,
                context={"action": "ai_update_text", "scope": scope, "target_id": target_id, "llm_provider": provider or self.stores.settings.llm_provider},
            )
            memory.save_state(state, mode=mode)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(
                    memory,
                    run_id=run_id,
                    book=book,
                    stage="writing",
                    focus=[
                        guidance,
                        scope,
                        target_id,
                        book.title,
                        book.premise.core_hook,
                        book.premise.central_conflict,
                        "姝ｆ枃鏀瑰啓",
                        "浜虹墿琛屼负閫昏緫",
                        "鎯呰妭寮犲姏",
                    ],
                    tags=["人物塑造", "情节", "正文"],
                )
                if scope == "block":
                    updated_book = writer.rewrite_unit(book=book, block_id=target_id, guidance=guidance, reference_pack=reference_pack)
                elif scope == "chapter":
                    updated_book = writer.rewrite_chapter(book=book, chapter_id=target_id, guidance=guidance, reference_pack=reference_pack)
                else:
                    raise ValueError(f"Unsupported text update scope: {scope}")
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "text_updated", "AI text update", updated_book.model_dump(mode="json"))
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode=mode)

        return self._launch_run(mode, run_id, task)

    def start_formal_novel(
        self,
        query: str,
        style_request: str = "",
        *,
        novel_type: str = "",
        llm_provider: str | None = None,
    ) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            memory = MemoryAgent(store=store)
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                context={"action": "create_novel_shell", "llm_provider": provider or self.stores.settings.llm_provider},
            )
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                book = BookDocument.model_validate(
                    self.create_novel_shell(
                        "formal",
                        query=query,
                        style_request=style_request,
                        novel_type=novel_type,
                    )
                )
                self._save_output(
                    memory,
                    run_id,
                    "WriterAgent",
                    "book_shell",
                    "Formal novel shell",
                    book.model_dump(mode="json"),
                )
                state.stage = WorkflowStage.COMPLETE
                state.current_book_id = book.id
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_outline(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_outline", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, style_request, "outline", "blueprint"], tags=["story structure", "plot"])
                payload = blueprint_agent.build_story_spine(
                    query,
                    style_request=style_request,
                    planning_context_json=self._planning_context_json_for_step(book, "step_1"),
                    reference_pack=reference_pack,
                )
                existing_title = str(book.title or "").strip()
                book.premise = StoryPremise.model_validate(payload["premise"])
                if existing_title:
                    book.title = existing_title
                    book.premise.title = existing_title
                else:
                    book.title = book.premise.title
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "outline_blueprint", "Step 1 outline + blueprint", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_worldbuilding(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_worldbuilding", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "worldbuilding", "power structure"], tags=["worldbuilding", "plot"])
                payload = blueprint_agent.build_worldbuilding_step(
                    research_query=query,
                    planning_context_json=self._planning_context_json_for_step(book, "step_2", lean=True),
                    reference_pack=reference_pack,
                )
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "worldbuilding", "Step 2 worldbuilding", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_characters(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            volume_titles = [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [getattr(volume, "title", "Volume 1") for volume in book.volumes] or ["Volume 1"]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_characters", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "character bible", "character dynamics"], tags=["character", "relationship", "story structure"])
                payload = blueprint_agent.build_character_bible_step(
                    query,
                    book.premise,
                    volume_titles,
                    story_blueprint=dict(book.metadata.get("story_blueprint", {})),
                    planning_context_json=self._planning_context_json_for_step(book, "step_3", lean=True),
                    reference_pack=reference_pack,
                )
                book.characters = [CharacterCard.model_validate(item) for item in payload.get("characters", [])]
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "character_bible", "Step 3 character bible", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_chapter_briefs(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            if not book.characters:
                raise ValueError("请先生成角色卡，再生成章节摘要。")
            story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
            planning_query = self._planning_query(book)[:500]
            total_target_chapters = self._resolve_target_chapter_count(book, story_blueprint)
            batch = self._step8_batch_window(total_chapters=total_target_chapters, start_index=0, batch_size=total_target_chapters)
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_chapter_briefs", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[planning_query, "chapter briefs", "chapter sequencing"], tags=["chapter briefs", "story structure", "plot"])
                step8_input = self._step8_input_payload(book, batch=batch, reference_pack=reference_pack)
                payload = blueprint_agent.build_chapter_briefs_step(
                    research_query=str(step8_input.get("research_query", "")),
                    volume_titles=[str(item) for item in step8_input.get("volume_titles_json", [])],
                    batch=dict(step8_input.get("batch", {}) or {}),
                    story_spine=dict(step8_input.get("story_spine_json", {}) or {}),
                    worldbuilding=dict(step8_input.get("worldbuilding_json", {}) or {}),
                    character_bible=dict(step8_input.get("character_bible_json", {}) or {}),
                    event_timeline=[item for item in step8_input.get("event_timeline_json", []) if isinstance(item, dict)],
                    character_milestones=[item for item in step8_input.get("character_milestones_json", []) if isinstance(item, dict)],
                    twist_designs=[item for item in step8_input.get("twist_designs_json", []) if isinstance(item, dict)],
                    story_lines=[item for item in step8_input.get("story_lines_json", []) if isinstance(item, dict)],
                    previous_chapter_briefs=[item for item in step8_input.get("previous_chapter_briefs_json", []) if isinstance(item, dict)],
                    target_chapter_count=int(step8_input.get("target_chapter_count") or total_target_chapters),
                    planning_context_json=self._planning_context_json_for_step(book, "step_8", lean=True),
                    reference_pack=str(step8_input.get("reference_pack", reference_pack)),
                )
                story_blueprint["chapter_briefs"] = payload.get("chapter_briefs", [])
                book.metadata["story_blueprint"] = story_blueprint
                book.metadata.pop("chapter_plans", None)
                book.metadata["next_chapter_index"] = min(int(book.metadata.get("next_chapter_index", 0)), len(payload.get("chapter_briefs", [])))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                saved_payload = dict(payload)
                saved_payload["merged_chapter_brief_count"] = len(payload.get("chapter_briefs", []))
                self._save_output(memory, run_id, "BlueprintAgent", "chapter_briefs", "Step 8 chapter briefs", saved_payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_chapter_briefs_batch(
        self,
        *,
        book_id: str,
        batch_size: int = 10,
        start_index: int | None = None,
        llm_provider: str | None = None,
    ) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)
        safe_batch_size = max(1, min(int(batch_size or 10), 30))

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            if not book.characters:
                raise ValueError("请先生成角色卡，再生成章节摘要。")

            story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
            total_target_chapters = self._resolve_target_chapter_count(book, story_blueprint)

            existing_by_id: dict[str, ChapterBrief] = {}
            for item in story_blueprint.get("chapter_briefs", []) or []:
                try:
                    plan = ChapterBrief.model_validate(item)
                except Exception:
                    continue
                if plan.chapter_id:
                    existing_by_id[str(plan.chapter_id)] = plan
            first_missing_index = 0
            for idx in range(total_target_chapters):
                if f"ch_{idx + 1:03d}" not in existing_by_id:
                    first_missing_index = idx
                    break
            else:
                first_missing_index = total_target_chapters
            start = int(start_index) if start_index is not None else first_missing_index
            if start < 0:
                start = 0
            batch = self._step8_batch_window(total_chapters=total_target_chapters, start_index=start, batch_size=safe_batch_size)
            batch_chapter_ids = [str(item) for item in batch.get("chapter_ids", [])]
            state = WorkflowState(
                run_id=run_id,
                stage=WorkflowStage.PLANNING,
                current_book_id=book.id,
                context={
                    "action": "generate_chapter_briefs_batch",
                    "llm_provider": provider or self.stores.settings.llm_provider,
                    "batch_size": int(batch.get("batch_size", safe_batch_size)),
                    "start_index": int(batch.get("start_index", start)),
                    "end_index": int(batch.get("end_index", start)),
                    "total_chapters": total_target_chapters,
                },
            )
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                end = int(batch.get("end_index", start)) + 1
                planning_query = self._planning_query(book)[:500]
                reference_pack = self._reference_pack_for_book(
                    memory,
                    run_id=run_id,
                    book=book,
                    stage="planning",
                    focus=[planning_query, f"chapter briefs batch {start + 1}-{end}", "chapter sequencing"],
                    tags=["chapter briefs", "story structure", "plot"],
                )
                step8_input = self._step8_input_payload(book, batch=batch, reference_pack=reference_pack)
                payload = blueprint_agent.build_chapter_briefs_step(
                    research_query=str(step8_input.get("research_query", "")),
                    volume_titles=[str(item) for item in step8_input.get("volume_titles_json", [])],
                    batch=dict(step8_input.get("batch", {}) or {}),
                    story_spine=dict(step8_input.get("story_spine_json", {}) or {}),
                    worldbuilding=dict(step8_input.get("worldbuilding_json", {}) or {}),
                    character_bible=dict(step8_input.get("character_bible_json", {}) or {}),
                    event_timeline=[item for item in step8_input.get("event_timeline_json", []) if isinstance(item, dict)],
                    character_milestones=[item for item in step8_input.get("character_milestones_json", []) if isinstance(item, dict)],
                    twist_designs=[item for item in step8_input.get("twist_designs_json", []) if isinstance(item, dict)],
                    story_lines=[item for item in step8_input.get("story_lines_json", []) if isinstance(item, dict)],
                    previous_chapter_briefs=[item for item in step8_input.get("previous_chapter_briefs_json", []) if isinstance(item, dict)],
                    target_chapter_count=int(step8_input.get("target_chapter_count") or total_target_chapters),
                    planning_context_json=self._planning_context_json_for_step(book, "step_8", lean=True),
                    reference_pack=str(step8_input.get("reference_pack", reference_pack)),
                )
                generated_briefs = [ChapterBrief.model_validate(item) for item in payload.get("chapter_briefs", []) if isinstance(item, dict)]
                briefs_by_chapter_id = {str(item.chapter_id): item for item in generated_briefs if str(item.chapter_id).strip()}
                batch_briefs: list[ChapterBrief] = []
                for index, chapter_id in enumerate(batch_chapter_ids):
                    source_brief = briefs_by_chapter_id.get(chapter_id)
                    if source_brief is None and index < len(generated_briefs):
                        source_brief = generated_briefs[index]
                    if source_brief is None:
                        raise ValueError(f"步骤8 未返回 {chapter_id} 对应的 chapter_brief。")
                    brief_payload = source_brief.model_dump(mode="json")
                    brief_payload["chapter_id"] = chapter_id
                    batch_briefs.append(ChapterBrief.model_validate(brief_payload))

                for brief in batch_briefs:
                    existing_by_id[str(brief.chapter_id)] = brief
                ordered_ids = [f"ch_{idx + 1:03d}" for idx in range(total_target_chapters)]
                merged_briefs: list[ChapterBrief] = [existing_by_id[chapter_id] for chapter_id in ordered_ids if chapter_id in existing_by_id]
                for chapter_id, plan in existing_by_id.items():
                    if chapter_id not in ordered_ids:
                        merged_briefs.append(plan)

                story_blueprint["chapter_briefs"] = [item.model_dump(mode="json") for item in merged_briefs]
                book.metadata["story_blueprint"] = story_blueprint
                book.metadata.pop("chapter_plans", None)
                book.metadata["next_chapter_index"] = min(int(book.metadata.get("next_chapter_index", 0)), len(merged_briefs))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(
                    memory,
                    run_id,
                    "BlueprintAgent",
                    "chapter_briefs",
                    f"Step 8 chapter briefs batch {start + 1}-{end}",
                    {
                        "batch": dict(payload.get("batch", batch)),
                        "chapter_briefs": [plan.model_dump(mode="json") for plan in batch_briefs],
                        "merged_chapter_brief_count": len(merged_briefs),
                    },
                )
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_milestones(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            query_500 = query[:500]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_milestones", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                try:
                    reference_pack = self._reference_pack_for_book(
                        memory,
                        run_id=run_id,
                        book=book,
                        stage="planning",
                        focus=[query, "character milestones", "character arcs", "serialize by major character"],
                        tags=["character", "story structure"],
                    )
                except Exception as exc:  # noqa: BLE001
                    ev.emit(
                        "stage_error",
                        agent="ReferenceLibrary",
                        title="Step 5 reference retrieval failed, continue without references",
                        stage="step_5",
                        error=str(exc),
                    )
                    reference_pack = "暂无额外参考资料。"
                story_blueprint = dict(book.metadata.get("story_blueprint", {}))
                story_engine = dict(story_blueprint.get("story_engine") or {})
                # Step 5: prioritize the first 7 characters from step 3 so milestone cards
                # can map one-to-one to character cards in later targeted revisions.
                named_characters: list[CharacterCard] = []
                seen_names: set[str] = set()
                for character in list(book.characters)[:7]:
                    name = str(character.name or "").strip()
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    named_characters.append(character)
                major_characters = named_characters
                if not major_characters:
                    raise ValueError("步骤5 需要先有至少 1 个已命名角色（最多取前 7 个）再生成角色发展线。")

                milestones_by_name: dict[str, dict[str, Any]] = {}
                ordered_names = [str(c.name or "").strip() for c in major_characters if str(c.name or "").strip()]

                def flush_milestones_progress() -> None:
                    book.metadata["character_milestones"] = [
                        milestones_by_name[name]
                        for name in ordered_names
                        if name in milestones_by_name
                    ]
                    book.updated_at = datetime.now(timezone.utc)
                    try:
                        memory.save_book(book)
                    except Exception as exc:  # noqa: BLE001
                        ev.emit(
                            "stage_error",
                            agent="MemoryAgent",
                            title="Step 5 flush partial milestones failed",
                            stage="step_5",
                            error=str(exc),
                        )

                # Serialize generation: one major character per model call.
                for character in major_characters:
                    check_cancelled()
                    name = str(character.name or "").strip()
                    if not name:
                        continue
                    try:
                        matched = blueprint_agent.build_single_character_milestone(
                            research_query=f"{query_500}\n当前角色：{name}",
                            character=character,
                            premise=book.premise,
                            story_engine=story_engine,
                            user_guidance="无",
                            reference_pack=reference_pack,
                        )
                    except Exception as exc:  # noqa: BLE001
                        ev.emit(
                            "stage_error",
                            agent="BlueprintAgent",
                            title=f"Step 5 single character failed: {name}",
                            stage="step_5",
                            character=name,
                            error=str(exc),
                        )
                        continue
                    matched["character_card_name"] = name
                    matched_character = get_character_card_by_name(named_characters, name)
                    matched["character_card_index"] = named_characters.index(matched_character) if matched_character in named_characters else -1
                    milestones_by_name[name] = matched
                    flush_milestones_progress()
                    self._save_output(
                        memory,
                        run_id,
                        "BlueprintAgent",
                        "character_milestones_partial",
                        f"Step 5 milestones partial · {name}",
                        {"character_name": name, "character_milestone": matched},
                    )

                milestones = [milestones_by_name[name] for name in ordered_names if name in milestones_by_name]
                if not milestones:
                    # 保底：本次全失败时不覆盖历史数据，避免用户感知为“被清空”。
                    milestones = BlueprintAgent._normalize_character_milestones(book.metadata.get("character_milestones", []))
                book.metadata["character_milestones"] = milestones
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "character_milestones", "Step 5 character milestones", {"character_milestones": milestones})
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_event_timeline(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_event_timeline", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "event timeline", "cause and effect"], tags=["plot", "story structure"])
                payload = blueprint_agent.build_event_timeline_step(
                    research_query=query,
                    planning_context_json=self._planning_context_json_for_step(book, "step_4", lean=True),
                    reference_pack=reference_pack,
                )
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "event_timeline", "Step 4 event timeline", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_twist_designs(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            query_500 = query[:500]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_twist_designs", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query_500, "twist designs", "emotional reversals"], tags=["plot", "twist", "story structure"])
                payload = blueprint_agent.build_twist_designs_step(
                    research_query=query_500,
                    planning_context_json=self._planning_context_json_for_step(book, "step_6", lean=True),
                    reference_pack=reference_pack,
                )
                story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
                story_blueprint["twist_designs"] = payload.get("twist_designs", [])
                book.metadata["story_blueprint"] = story_blueprint
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "twist_designs", "Step 6 twist designs", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_story_lines(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            query_500 = query[:500]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_story_lines", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query_500, "story lines", "chapter titles"], tags=["plot", "chapter briefs", "story structure"])
                payload = blueprint_agent.build_story_lines_step(
                    research_query=query_500,
                    planning_context_json=self._planning_context_json_for_step(book, "step_7", lean=True),
                    reference_pack=reference_pack,
                )
                story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
                story_blueprint["story_lines"] = payload.get("story_lines", [])
                book.metadata["story_blueprint"] = story_blueprint
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "story_lines", "Step 7 story lines", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def review_formal_blueprint(self, *, book_id: str, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            critic = self._build_critic(llm_provider=provider)
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.CRITIQUE, current_book_id=book.id, context={"action": "review_blueprint", "llm_provider": provider or self.stores.settings.llm_provider})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[book.title, "blueprint review", "consistency"], tags=["plot", "story structure", "character"])
                volume_titles = [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [getattr(volume, "title", "Volume 1") for volume in book.volumes]
                blueprint = BookBlueprint(
                    blueprint_id=f"blueprint_{book.id}",
                    premise=book.premise,
                    characters=book.characters,
                    volume_titles=volume_titles or ["Volume 1"],
                    chapter_briefs=[
                        ChapterBrief.model_validate(item)
                        for item in list((book.metadata.get("story_blueprint", {}) or {}).get("chapter_briefs", []) or [])
                        if isinstance(item, dict)
                    ],
                )
                review = critic.review_blueprint(blueprint, reference_pack=reference_pack)
                self._save_output(memory, run_id, "CriticAgent", "blueprint_review", "Blueprint review", review)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def continue_formal_novel(self, *, book_id: str | None = None, title: str | None = None, llm_provider: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"
        provider = self._normalize_llm_provider(llm_provider)

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer(llm_provider=provider)
            memory = MemoryAgent(store=store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                book = None
                if book_id:
                    book = memory.load_book(book_id)
                elif title:
                    matches = memory.find_books_by_title(title=title, limit=1)
                    book = matches[0] if matches else None
                if book is None:
                    raise ValueError(f"Book not found: {book_id or title}")
                state = WorkflowState(
                    run_id=run_id,
                    stage=WorkflowStage.WRITING,
                    current_book_id=book.id,
                    context={"action": "continue_formal_novel", "llm_provider": provider or self.stores.settings.llm_provider},
                )
                memory.save_state(state, mode="formal")
                updated_book, chapter = writer.write_next_chapter(book=book, runtime_store=store, run_id=run_id)
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "chapter_written", f"Chapter written: {chapter.title}", chapter.model_dump(mode="json"))
                chapter_run = (
                    dict(updated_book.metadata.get("writing_chapter_runs", {}) or {}).get(chapter.id)
                    if isinstance(updated_book.metadata.get("writing_chapter_runs"), dict)
                    else None
                )
                if isinstance(chapter_run, dict):
                    content_blocks = chapter_run.get("content_blocks")
                    if isinstance(content_blocks, list):
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_blocks", "Chapter blocks", {"chapter_id": chapter.id, "blocks": content_blocks})
                    final_text = chapter_run.get("final_text")
                    if isinstance(final_text, str) and final_text.strip():
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_final_text", "Final chapter text", {"chapter_id": chapter.id, "final_text": final_text, "final_version": chapter_run.get("final_version", 1)})
                    actual_summary = chapter_run.get("actual_chapter_summary")
                    if isinstance(actual_summary, dict):
                        self._save_output(memory, run_id, "WritingChapterAgent", "actual_chapter_summary", "Actual chapter summary", actual_summary)
                    stage_log = chapter_run.get("stage_log")
                    if isinstance(stage_log, list):
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_stage_log", "Chapter stage log", {"chapter_id": chapter.id, "stage_log": stage_log})
                critic_payload = updated_book.metadata.get("latest_critic_report")
                if isinstance(critic_payload, dict):
                    from novel_flow.models.schemas import CriticReport

                    critic_report = CriticReport.model_validate(critic_payload)
                    memory.save_critic_report(critic_report, book_id=updated_book.id)
                    self._save_output(memory, run_id, "WriterAgent", "critic_report", "Latest chapter critics", critic_report.model_dump(mode="json"))
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def test_blueprint(self, query: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, context={"query": query, "action": "blueprint"})
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                blueprint = blueprint_agent.build_blueprint(research_query=query)
                check_cancelled()
                writer = self._build_writer()
                book = writer.create_book(blueprint=blueprint, source_query=query)
                check_cancelled()
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "blueprint", "Blueprint", blueprint.model_dump(mode="json"))
                self._save_output(memory, run_id, "WriterAgent", "book_shell", "Book shell", book.model_dump(mode="json"))
                state.current_book_id = book.id
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_write_chapter(self, query: str | None = None, book_id: str | None = None) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                if book_id:
                    book = memory.load_book(book_id)
                    if book is None:
                        raise ValueError(f"Book not found: {book_id}")
                else:
                    if not query:
                        raise ValueError("Query is required when starting a new test novel.")
                    blueprint = self._build_blueprint_agent().build_blueprint(research_query=query)
                    check_cancelled()
                    book = writer.create_book(blueprint=blueprint, source_query=query)
                    check_cancelled()
                    memory.save_book(book)
                    self._save_output(memory, run_id, "BlueprintAgent", "blueprint", "Blueprint", blueprint.model_dump(mode="json"))
                updated_book, chapter = writer.write_next_chapter(book, runtime_store=store, run_id=run_id)
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "chapter_written", f"Chapter written: {chapter.title}", chapter.model_dump(mode="json"))
                chapter_run = (
                    dict(updated_book.metadata.get("writing_chapter_runs", {}) or {}).get(chapter.id)
                    if isinstance(updated_book.metadata.get("writing_chapter_runs"), dict)
                    else None
                )
                if isinstance(chapter_run, dict):
                    content_blocks = chapter_run.get("content_blocks")
                    if isinstance(content_blocks, list):
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_blocks", "Chapter blocks", {"chapter_id": chapter.id, "blocks": content_blocks})
                    final_text = chapter_run.get("final_text")
                    if isinstance(final_text, str) and final_text.strip():
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_final_text", "Final chapter text", {"chapter_id": chapter.id, "final_text": final_text, "final_version": chapter_run.get("final_version", 1)})
                    actual_summary = chapter_run.get("actual_chapter_summary")
                    if isinstance(actual_summary, dict):
                        self._save_output(memory, run_id, "WritingChapterAgent", "actual_chapter_summary", "Actual chapter summary", actual_summary)
                    stage_log = chapter_run.get("stage_log")
                    if isinstance(stage_log, list):
                        self._save_output(memory, run_id, "WritingChapterAgent", "chapter_stage_log", "Chapter stage log", {"chapter_id": chapter.id, "stage_log": stage_log})
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.WRITING, current_book_id=updated_book.id, context={"action": "write_chapter"})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_critique(self, book_id: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            critic = self._build_critic()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                report = critic.review_book(book=book)
                check_cancelled()
                memory.save_critic_report(report, book_id=book.id)
                self._save_output(memory, run_id, "CriticAgent", "critic_report", "Critic report", report.model_dump(mode="json"))
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.CRITIQUE, current_book_id=book.id, latest_critic_report_id=report.report_id, context={"action": "critique"})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def test_patch(self, *, book_id: str, block_id: str, operation: str, patch_content: str, reason: str) -> str:
        run_id = f"test_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            instruction = PatchInstruction(
                patch_id=f"patch_{uuid4().hex[:10]}",
                target_block_id=block_id,
                operation=PatchOperation(operation),
                reason=reason,
                content=patch_content,
            )
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                patched_book, payload = writer.patch_block(book=book, instruction=instruction)
                check_cancelled()
                memory.save_book(patched_book)
                self._save_output(memory, run_id, "WriterAgent", "patch_version", f"Patch applied: {instruction.target_block_id}", payload["patch_version"])
                state = WorkflowState(run_id=run_id, stage=WorkflowStage.PATCHING, current_book_id=patched_book.id, context={"action": "patch", "block_id": block_id})
                memory.save_state(state, mode="test")

        return self._launch_run("test", run_id, task)

    def _launch_run(self, mode: str, run_id: str, task: Callable[[SQLiteStore, RunHandle], None]) -> str:
        store = self._store(mode)
        handle = RunHandle(run_id=run_id, mode=mode)
        store.save_event(
            PipelineEvent(
                run_id=run_id,
                event_type="run_created",
                agent="Server",
                title="Run created",
                payload={"mode": mode, "summary": "运行已启动，正在准备请求模型。"},
            )
        )

        def runner() -> None:
            try:
                task(store, handle)
            except RunCancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                store.save_event(PipelineEvent(run_id=run_id, event_type="error", agent="Server", title="Run failed", payload={"error": str(exc)}))
            finally:
                if handle.cancel_event.is_set():
                    store.delete_run(run_id)
                with self._lock:
                    self._run_handles.pop(run_id, None)

        thread = threading.Thread(target=runner, daemon=True)
        handle.thread = thread
        with self._lock:
            self._run_handles[run_id] = handle
        thread.start()
        return run_id

    def _save_output(self, memory: MemoryAgent, run_id: str, agent: str, output_type: str, title: str, payload: dict[str, Any]) -> None:
        memory.save_run_output(
            run_id=run_id,
            agent=agent,
            output_type=output_type,
            title=title,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _handle(self, run_id: str) -> RunHandle | None:
        with self._lock:
            return self._run_handles.get(run_id)

    def _store(self, mode: str) -> SQLiteStore:
        return self.stores.test if mode == "test" else self.stores.formal

    def _normalize_llm_provider(self, llm_provider: str | None) -> str | None:
        if llm_provider is None:
            return None
        provider = str(llm_provider).strip().lower()
        if not provider:
            return None
        if provider not in {"deepseek", "doubao", "openai", "codex"}:
            raise ValueError("Unsupported llm_provider. Use 'deepseek', 'doubao', 'openai', or 'codex'.")
        return provider

    def _build_llm(self, llm_provider: str | None = None) -> LLMClient:
        provider = self._normalize_llm_provider(llm_provider)
        if provider is None:
            return build_llm_client(self.stores.settings)
        scoped_settings = self.stores.settings.model_copy(update={"llm_provider": provider})
        return build_llm_client(scoped_settings)

    def _build_writer(self, llm_provider: str | None = None) -> WriterAgent:
        return WriterAgent(llm_client=self._build_llm(llm_provider=llm_provider), patch_executor=PatchExecutor())

    def _build_blueprint_agent(self, llm_provider: str | None = None) -> BlueprintAgent:
        return BlueprintAgent(llm_client=self._build_llm(llm_provider=llm_provider))

    def _build_critic(self, llm_provider: str | None = None) -> CriticAgent:
        return CriticAgent(llm_client=self._build_llm(llm_provider=llm_provider))

    def _reference_pack_for_book(
        self,
        memory: MemoryAgent,
        *,
        run_id: str,
        book: Any,
        stage: str,
        focus: list[str],
        tags: list[str],
        limit: int = 5,
    ) -> str:
        query = self._planning_query(book)
        library = ReferenceLibrary()
        cards = library.retrieve(query=query, stage=stage, tags=tags, focus=focus, limit=limit)
        reference_pack = library.build_reference_pack(cards)
        self._save_output(
            memory,
            run_id,
            "ReferenceLibrary",
            "reference_cards",
            f"Reference retrieval: {stage}",
            {
                "stage": stage,
                "query": query,
                "focus": focus,
                "tags": tags,
                "reference_pack": reference_pack,
                "cards": [card.model_dump(mode="json") for card in cards],
            },
        )
        return reference_pack

    @staticmethod
    def _merge_story_blueprint(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in (patch or {}).items():
            if key == "relationship_network":
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = NovelApp._merge_story_blueprint(dict(merged.get(key, {})), value)
            elif isinstance(value, list) and not value and isinstance(merged.get(key), list) and merged.get(key):
                # Keep earlier non-empty planning output when a later step returns an empty placeholder list.
                continue
            elif isinstance(value, str) and not value.strip() and isinstance(merged.get(key), str):
                # Keep earlier non-empty planning output when a later step returns an empty placeholder.
                continue
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _parse_json(data: str) -> dict[str, Any]:
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": data}


class _Handler(BaseHTTPRequestHandler):
    app: NovelApp

    def log_message(self, *args: object) -> None:
        pass

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/":
            self._html(_HTML_PAGE)
            return
        if parsed.path == "/api/novels":
            self._json(self.app.list_novels(qs.get("mode", ["formal"])[0]))
            return
        if parsed.path == "/api/novel-types":
            self._json({"ok": True, "items": self.app.list_novel_type_options()})
            return
        if parsed.path == "/api/novel":
            self._json(self.app.get_novel(qs.get("mode", ["formal"])[0], qs.get("book_id", [""])[0]))
            return
        if parsed.path == "/api/runs":
            self._json(self.app.list_runs(qs.get("mode", ["formal"])[0], qs.get("book_id", [None])[0]))
            return
        if parsed.path == "/api/run":
            self._json(self.app.get_run(qs.get("mode", ["formal"])[0], qs.get("run_id", [""])[0]))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        llm_provider = payload.get("llm_provider")
        llm_provider_text = str(llm_provider) if llm_provider is not None else None
        try:
            if parsed.path == "/api/novels/create":
                self._json(
                    {
                        "ok": True,
                        "book": self.app.create_novel_shell(
                            str(payload.get("mode", "formal")),
                            query=str(payload.get("query", "")),
                            style_request=str(payload.get("style_request", "")),
                            title=str(payload.get("title", "")),
                            novel_type=str(payload.get("novel_type", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/start":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.start_formal_novel(
                            str(payload.get("query", "")),
                            str(payload.get("style_request", "")),
                            novel_type=str(payload.get("novel_type", "")),
                            llm_provider=llm_provider_text,
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/generate_outline":
                self._json({"ok": True, "run_id": self.app.generate_formal_outline(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_worldbuilding":
                self._json({"ok": True, "run_id": self.app.generate_formal_worldbuilding(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_characters":
                self._json({"ok": True, "run_id": self.app.generate_formal_characters(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_milestones":
                self._json({"ok": True, "run_id": self.app.generate_formal_milestones(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_event_timeline":
                self._json({"ok": True, "run_id": self.app.generate_formal_event_timeline(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_twist_designs":
                self._json({"ok": True, "run_id": self.app.generate_formal_twist_designs(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_story_lines":
                self._json({"ok": True, "run_id": self.app.generate_formal_story_lines(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_chapter_briefs":
                self._json({"ok": True, "run_id": self.app.generate_formal_chapter_briefs(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/generate_chapter_briefs_batch":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.generate_formal_chapter_briefs_batch(
                            book_id=str(payload.get("book_id", "")),
                            batch_size=int(payload.get("batch_size", 10)),
                            start_index=int(payload.get("start_index")) if payload.get("start_index") is not None else None,
                            llm_provider=llm_provider_text,
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/review_blueprint":
                self._json({"ok": True, "run_id": self.app.review_formal_blueprint(book_id=str(payload.get("book_id", "")), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/continue":
                self._json({"ok": True, "run_id": self.app.continue_formal_novel(book_id=payload.get("book_id"), title=payload.get("title"), llm_provider=llm_provider_text)})
                return
            if parsed.path == "/api/novels/delete":
                self.app.delete_novel(str(payload.get("mode", "formal")), str(payload.get("book_id", "")))
                self._json({"ok": True})
                return
            if parsed.path == "/api/novels/update_concept":
                book = self.app.update_novel_concept(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    title=payload.get("title"),
                    premise=payload.get("premise"),
                    characters=payload.get("characters"),
                    query=payload.get("query"),
                    user_topic=payload.get("user_topic"),
                    style_request=payload.get("style_request"),
                    assistant_persona_prompt=payload.get("assistant_persona_prompt"),
                    total_word_target=payload.get("total_word_target"),
                    chapter_count_target=payload.get("chapter_count_target"),
                    chapter_word_target=payload.get("chapter_word_target"),
                    pace_notes=payload.get("pace_notes"),
                )
                self._json({"ok": True, "book": book})
                return
            if parsed.path == "/api/novels/resolve_character_candidate":
                result = self.app.resolve_character_candidate(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    candidate_id=str(payload.get("candidate_id", "")),
                    action=str(payload.get("action", "")),
                )
                self._json({"ok": True, **result})
                return
            if parsed.path == "/api/novels/save_step_result":
                result = self.app.save_step_result(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    step_key=str(payload.get("step_key", "")),
                    payload_text=str(payload.get("payload_text", "")),
                )
                self._json({"ok": True, **result})
                return
            if parsed.path == "/api/novels/delete_chapter":
                result = self.app.delete_chapter(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    chapter_id=str(payload.get("chapter_id", "")),
                )
                self._json({"ok": True, **result})
                return
            if parsed.path == "/api/novels/revise_step_result":
                result = self.app.revise_step_result(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    step_key=str(payload.get("step_key", "")),
                    payload_text=str(payload.get("payload_text", "")),
                    revision_mode=str(payload.get("revision_mode", "review")),
                    guidance=str(payload.get("guidance", "")),
                )
                self._json({"ok": True, **result})
                return
            if parsed.path == "/api/novels/revise_single_character":
                result = self.app.revise_single_character(
                    str(payload.get("mode", "formal")),
                    book_id=str(payload.get("book_id", "")),
                    payload_text=str(payload.get("payload_text", "")),
                    character_index=int(payload.get("character_index", -1)),
                    guidance=str(payload.get("guidance", "")),
                )
                self._json({"ok": True, **result})
                return
            if parsed.path == "/api/novels/revise_single_character_run":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.revise_single_character_run(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            payload_text=str(payload.get("payload_text", "")),
                            character_index=int(payload.get("character_index", -1)),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/revise_single_character_milestone_run":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.revise_single_character_milestone_run(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            payload_text=str(payload.get("payload_text", "")),
                            character_index=int(payload.get("character_index", -1)),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/add_character":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.add_character_run(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/add_character_milestone":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.add_character_milestone_run(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/revise_step_result_run":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.revise_step_result_run(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            step_key=str(payload.get("step_key", "")),
                            payload_text=str(payload.get("payload_text", "")),
                            revision_mode=str(payload.get("revision_mode", "review")),
                            guidance=str(payload.get("guidance", "")),
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/ai_update_concept":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.ai_update_concept(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            scope=str(payload.get("scope", "all")),
                            target_id=payload.get("target_id"),
                            guidance=str(payload.get("guidance", "")),
                            llm_provider=llm_provider_text,
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/ai_update_text":
                self._json(
                    {
                        "ok": True,
                        "run_id": self.app.ai_update_text(
                            str(payload.get("mode", "formal")),
                            book_id=str(payload.get("book_id", "")),
                            scope=str(payload.get("scope", "block")),
                            target_id=str(payload.get("target_id", "")),
                            guidance=str(payload.get("guidance", "")),
                            llm_provider=llm_provider_text,
                        ),
                    }
                )
                return
            if parsed.path == "/api/runs/stop":
                self.app.stop_run(str(payload.get("mode", "formal")), str(payload.get("run_id", "")))
                self._json({"ok": True})
                return
            if parsed.path == "/api/test/blueprint":
                self._json({"ok": True, "run_id": self.app.test_blueprint(str(payload.get("query", "")))})
                return
            if parsed.path == "/api/test/write":
                self._json({"ok": True, "run_id": self.app.test_write_chapter(query=payload.get("query"), book_id=payload.get("book_id"))})
                return
            if parsed.path == "/api/test/critique":
                self._json({"ok": True, "run_id": self.app.test_critique(str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/test/patch":
                self._json({"ok": True, "run_id": self.app.test_patch(book_id=str(payload.get("book_id", "")), block_id=str(payload.get("block_id", "")), operation=str(payload.get("operation", "replace")), patch_content=str(payload.get("patch_content", "")), reason=str(payload.get("reason", "manual test patch")))})
                return
            self.send_response(404)
            self.end_headers()
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, status=400)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def _html(self, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def start_server(*, formal_store: SQLiteStore, test_store: SQLiteStore, settings: Settings, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    _Handler.app = NovelApp(AppStores(formal=formal_store, test=test_store, settings=settings))
    server = ThreadingHTTPServer((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_HTML_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='UTF-8'><title>Novel Flow</title><style>
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft YaHei",sans-serif;background:#0f1115;color:#e6e9ef;height:100vh;display:flex;flex-direction:column}
#hdr{position:sticky;top:0;z-index:5;display:flex;flex-direction:column;gap:10px;padding:12px 16px;background:rgba(20,25,35,.96);border-bottom:1px solid #232834;backdrop-filter:blur(10px)}
#hdr h1{margin:0;font-size:18px;font-weight:700;color:#9db6ff;letter-spacing:.01em;white-space:nowrap}
.hdr-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.hdr-brand{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.hdr-selects{display:flex;gap:8px;align-items:center;flex-wrap:wrap;min-width:0;flex:1}
.hdr-primary{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hdr-steps{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
#modeSel{min-width:112px}
#modelSel{min-width:120px}
#novelSel{min-width:280px;max-width:420px;flex:1}
select,button,input,textarea{background:#1b2130;color:#eef2ff;border:1px solid #323b52;border-radius:8px;padding:7px 11px;font-size:12px;transition:border-color .16s ease,background .16s ease,transform .16s ease}
button{cursor:pointer}
button:hover,select:hover,input:hover,textarea:hover{border-color:#425173}
button:hover{background:#212a3d}
button:active{transform:translateY(1px)}
textarea:focus,input:focus,select:focus,button:focus{outline:none;border-color:#6b88d9;box-shadow:0 0 0 2px rgba(107,136,217,.14)}
.danger{border-color:#6a2b3b;color:#ffcad5}
.danger:hover{background:#2a1820;border-color:#8a4257}
.ghost{background:transparent}
.step-btn{padding:6px 9px;font-size:11px}
.modal{position:fixed;inset:0;background:rgba(3,6,14,.76);display:none;align-items:center;justify-content:center;z-index:20;padding:28px;backdrop-filter:blur(4px)}
.modal-card{width:min(920px,calc(100vw - 56px));max-height:calc(100vh - 56px);display:flex;flex-direction:column;background:#151a23;border:1px solid #303a52;border-radius:18px;box-shadow:0 24px 90px rgba(0,0,0,.52);overflow:hidden}
.modal-head{padding:18px 22px;border-bottom:1px solid #263047;background:linear-gradient(135deg,#171f31,#131824)}
.modal-title{font-size:17px;color:#eef2ff;margin-bottom:4px}
.modal-desc{font-size:12px;color:#8997b8;line-height:1.6}
.modal-body{padding:20px 22px;overflow:auto}
.modal-section{border:1px solid #263047;background:#111722;border-radius:14px;padding:16px;margin-bottom:14px}
.modal-section-title{font-size:12px;color:#8ea1d8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}
.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.field{display:flex;flex-direction:column;gap:6px}
.field.full{grid-column:1/-1}
.field label{color:#dce3fb;font-size:12px}
.field textarea,.field input,.field select{width:100%;font-size:13px}
.field textarea{min-height:132px;resize:vertical}
.field input{height:36px}
.field-help{color:#7f8aa3;font-size:11px;line-height:1.55}
.config-placeholder{border:1px dashed #34405f;border-radius:12px;padding:12px;color:#7f8aa3;font-size:12px;line-height:1.7;background:#0f141f}
.modal-actions{display:flex;justify-content:flex-end;gap:8px;padding:14px 22px;border-top:1px solid #263047;background:#111722}
#stage-pill{padding:5px 10px;border-radius:999px;border:1px solid #34405f;color:#9fb2eb;font-size:11px;background:#171f2f}
#main{display:flex;flex:1;min-height:0;overflow:hidden}
#left{width:37%;min-width:340px;max-width:560px;border-right:1px solid #232834;display:flex;flex-direction:column;background:#10151d}
#right{flex:1;min-width:0;display:flex;flex-direction:column;background:#0f1115}
#subhdr{padding:12px 16px;border-bottom:1px solid #232834;color:#8390ad;font-size:12px;line-height:1.6;background:#121823}
#evs{flex:1;overflow:auto;padding:14px}
.run{background:#151a23;border:1px solid #242b3b;border-radius:12px;margin-bottom:12px;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.16)}
.head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 14px;background:#171d29;cursor:pointer}
.ts{margin-left:auto;color:#6f7a95;font-size:10px}
.tag{font-size:10px;padding:3px 7px;border-radius:999px;background:#222a3d;color:#b9c8ff}
.live{background:#253b2c;color:#9fe2b0}
.stop{background:#4a2230;color:#ffc4d2}
.body{padding:12px 14px;border-top:1px solid #242b3b}
.box{background:#121722;border:1px solid #242b3b;border-radius:10px;margin-bottom:10px;overflow:hidden}
.box summary{list-style:none;cursor:pointer;padding:11px 12px;color:#eef2ff;font-size:12px;display:flex;align-items:center;gap:8px}
.box summary::-webkit-details-marker{display:none}
.box .payload{padding:0 12px 12px 12px}
.box.task-box{border-color:#28324a;transition:border-color .16s ease,box-shadow .16s ease}
.box.task-box.active{border-color:#4e628f;box-shadow:0 0 0 1px rgba(78,98,143,.22)}
.box.task-box.active summary{background:#182031}
.title{font-size:12px;color:#eef2ff;margin-bottom:0}
.payload{font-size:11px;color:#93a0bf;white-space:pre-wrap;word-break:break-word;line-height:1.7}
.stream-shell{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
.stream-card{background:#0d1220;border:1px solid #28324a;border-radius:8px;padding:10px}
.stream-card.live{border-color:#315b4b;background:linear-gradient(135deg,#111b24,#102018)}
.stream-meta{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px}
.stream-title{font-size:11px;color:#eef2ff;font-weight:600}
.stream-status{font-size:10px;color:#8fb8a0}
.stream-card.live .stream-status{color:#a7e0b8}
.stream-prompt{margin-bottom:6px;font-size:10px;line-height:1.6;color:#8ea1d8}
.stream-text{font-size:11px;color:#dce3fb;white-space:pre-wrap;word-break:break-word;line-height:1.75;max-height:420px;overflow:auto}
.chapter-live-blocks{margin-top:12px;padding-top:12px;border-top:1px dashed #2a3448}
.live-draft-shell{display:flex;flex-direction:column;gap:14px}
.live-draft-text{max-height:420px;overflow:auto}
.live-draft-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.block-badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.block-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;font-size:10px;border:1px solid #2b3752;background:#1a2234;color:#d5e0ff}
.block-badge.patched{border-color:#2f5a45;background:#173126;color:#aee0bf}
.block-badge.status{border-color:#3f4d6a;background:#1c2332;color:#b9c8ff}
.block.patched{border-left-color:#56b483;background:linear-gradient(135deg,#101922,#13241b)}
.task-note{font-size:11px;color:#8ea1d8;line-height:1.7}
.empty{padding:56px 24px;text-align:center;color:#7f8aa3;border:1px dashed #273247;border-radius:14px;background:#121722}
.agent-view{display:flex;flex-direction:column;gap:8px}
.kv{display:grid;grid-template-columns:78px 1fr;gap:8px;align-items:start;font-size:11px;line-height:1.6;color:#dce3fb}
.kv .k{color:#8ea1d8}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:#1a2234;border:1px solid #2b3752;color:#d5e0ff;font-size:10px}
.subsec{margin-top:2px;font-size:10px;color:#7e8ba8;text-transform:uppercase;letter-spacing:.08em}
.subbox{background:#0f131c;border:1px solid #20293b;border-radius:8px;padding:8px}
.mini-list{display:flex;flex-direction:column;gap:6px}
.mini-item{background:#0f131c;border:1px solid #20293b;border-radius:8px;padding:8px;font-size:11px;line-height:1.6;color:#dce3fb}
.mini-title{font-size:11px;color:#eef2ff;margin-bottom:4px}
.muted{font-size:11px;color:#7f8aa3;line-height:1.6}
.pre{font-size:11px;color:#93a0bf;white-space:pre-wrap;word-break:break-word;line-height:1.7}
.json{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
#tabs{display:flex;gap:4px;padding:10px 14px 0;border-bottom:1px solid #232834;background:#141923}
.tab{padding:11px 14px;cursor:pointer;color:#8b96af;font-size:12px;border:1px solid transparent;border-bottom:none;border-top-left-radius:10px;border-top-right-radius:10px}
.tab.active{color:#dfe6ff;border-color:#2b3750;background:#1a2231}
#tc{flex:1;overflow:auto;padding:18px}
.pnl{display:none}
.pnl.active{display:block}
.card{background:#151a23;border:1px solid #242b3b;border-radius:14px;padding:16px;margin-bottom:12px;box-shadow:0 10px 32px rgba(0,0,0,.14)}
.sec{font-size:11px;color:#7e8ba8;text-transform:uppercase;letter-spacing:.08em;margin:12px 0 8px}
.row{margin:7px 0;font-size:13px;color:#dce3fb;line-height:1.7}
.row strong{color:#8ea1d8;margin-right:6px}
.input-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.input-toolbar .title-wrap{display:flex;flex-direction:column;gap:4px}
.input-toolbar h3{margin:0;font-size:22px;color:#eef2ff;letter-spacing:.01em}
.input-toolbar .meta{font-size:12px;color:#7f8aa3}
.input-toolbar .actions{display:flex;gap:8px;flex-wrap:wrap}
.input-hero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;margin-bottom:16px;padding:18px 20px;border:1px solid #283149;border-radius:14px;background:linear-gradient(135deg,#171e2c,#121822)}
.input-hero-copy{display:flex;flex-direction:column;gap:10px;min-width:260px;flex:1}
.input-hero-kicker{font-size:11px;color:#89a0d8;text-transform:uppercase;letter-spacing:.12em}
.input-hero-title-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.input-hero-title{margin:0;font-size:34px;line-height:1.05;color:#f2f5ff;letter-spacing:-.02em;font-weight:700}
.input-hero-badge{padding:5px 10px;border-radius:999px;border:1px solid #33415f;background:#1a2436;color:#b7c7f5;font-size:11px;white-space:nowrap}
.input-hero-desc{font-size:13px;line-height:1.75;color:#b8c5e6;max-width:900px}
.title-field{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.title-field label{font-size:12px;color:#8ea1d8}
.title-field input{max-width:420px;height:42px;font-size:18px;font-weight:600}
.panel-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.panel-toolbar .title-wrap{display:flex;flex-direction:column;gap:4px}
.panel-toolbar .panel-title{margin:0;font-size:18px;color:#eef2ff}
.panel-toolbar .panel-meta{font-size:12px;color:#7f8aa3}
.panel-toolbar .actions{display:flex;gap:8px;flex-wrap:wrap}
.input-blocks{display:flex;flex-direction:column;gap:12px}
.input-block{background:#121722;border:1px solid #29324a;border-radius:12px;overflow:hidden}
.input-block summary{list-style:none;cursor:pointer;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.input-block summary::-webkit-details-marker{display:none}
.input-block summary:hover{background:#171e2c}
.input-block .summary-text{display:flex;flex-direction:column;gap:4px;min-width:0}
.input-block .summary-title{font-size:13px;color:#e8eeff;font-weight:600}
.input-block .summary-desc{font-size:11px;color:#7f8aa3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.input-block .summary-arrow{font-size:11px;color:#8ea1d8;flex:none}
.input-block .block-body{padding:0 16px 16px}
.writing-req-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:12px}
.writing-req-grid .field{display:flex;flex-direction:column;gap:6px}
.writing-req-grid .field input{width:100%;height:36px}
.writing-req-full{display:flex;flex-direction:column;gap:6px}
.input-block textarea{width:100%;min-height:220px;resize:vertical;white-space:pre-wrap;line-height:1.7;font-size:13px}
.input-block textarea[readonly]{opacity:.92}
.input-block .block-help{margin-top:8px;font-size:11px;color:#7f8aa3;line-height:1.6}
.section-card{background:#151a23;border:1px solid #242b3b;border-radius:14px;margin-bottom:12px;overflow:hidden;box-shadow:0 10px 32px rgba(0,0,0,.14)}
.section-card summary{list-style:none;cursor:pointer;padding:16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.section-card summary::-webkit-details-marker{display:none}
.section-card summary:hover{background:#1a202d}
.section-card .summary-text{display:flex;flex-direction:column;gap:4px;min-width:0}
.section-card .summary-title{font-size:14px;color:#eef2ff;font-weight:600}
.section-card .summary-desc{font-size:11px;color:#7f8aa3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.section-card .summary-arrow{font-size:16px;color:#4e628f;flex:none;transition:transform .2s;display:inline-block}
.section-card[open]>.summary>.summary-arrow{transform:rotate(90deg)}
.section-card .summary-toolbar{display:flex;align-items:center;gap:6px;flex:none}
.section-card .summary-toolbar .ghost{padding:4px 10px;font-size:11px}
.dirty-dot{color:#f59e0b;font-size:10px;margin-right:4px;vertical-align:middle}
.section-card .section-body{padding:0 16px 16px}
.step-editor{margin:4px 0 16px 0;background:#111723;border:1px solid #232c3d;border-radius:12px;overflow:hidden}
.step-editor-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 14px 0 14px;margin-bottom:10px}
.step-editor-title{font-size:12px;color:#8ea1d8;font-weight:600}
.step-editor-actions{display:flex;gap:8px;flex-wrap:wrap}
.step-editor-body{padding:0 14px 14px 14px}
.step-editor-notes{margin:0 0 10px 18px;padding:0;color:#d6def1}
.step-editor-notes li{margin:6px 0;line-height:1.6}
.step-editor-empty{font-size:12px;color:#7f8aa3;margin-bottom:10px}
.step-editor-hint{margin-top:8px;font-size:11px;color:#7f8aa3;line-height:1.6}
.step-inline-root{display:grid;gap:12px}
.step-inline-field{display:grid;gap:6px}
.step-inline-field>label{font-size:12px;color:#8ea1d8;font-weight:600}
.step-inline-input,.step-inline-textarea{width:100%;background:#161d2b;border:1px solid #2a3448;border-radius:10px;color:#eef2ff;padding:10px 12px;font-size:13px;line-height:1.7}
.step-inline-textarea{min-height:96px;resize:vertical;white-space:pre-wrap}
.step-inline-stack{display:grid;gap:10px}
.step-inline-card{background:#121722;border:1px solid #242b3b;border-radius:10px;padding:12px}
.step-inline-card-title{font-size:12px;color:#8ea1d8;font-weight:700;margin-bottom:8px}
.step-inline-empty{font-size:12px;color:#7f8aa3;padding:8px 0}
.step-readback{margin-top:14px;padding-top:14px;border-top:1px dashed #2a3448}
.step-readback-title{font-size:12px;color:#8ea1d8;font-weight:600;margin-bottom:10px}
.relationship-stack{display:flex;flex-direction:column;gap:14px;margin-top:12px}
.relationship-group-title{font-size:13px;font-weight:700;color:#9fb4ff;margin:6px 0 2px}
.relationship-card{background:#111723;border:1px solid #232c3d;border-radius:14px;padding:14px}
.relationship-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap;margin-bottom:10px}
.relationship-title{font-size:16px;font-weight:700;color:#eef2ff}
.relationship-pair{font-size:12px;color:#8ea1d8}
.relationship-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:12px 0}
.relationship-block{background:#0f141d;border:1px solid #1e2635;border-radius:10px;padding:12px}
.relationship-block .subsec{margin-top:0}
.relationship-plain{white-space:pre-wrap;line-height:1.72;color:#d6def1}
.relationship-list{margin:8px 0 0 18px;padding:0;color:#d6def1}
.relationship-list li{margin:6px 0;line-height:1.6}
.relationship-empty{color:#7f8aa3;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.mini{background:#121722;border:1px solid #242b3b;border-radius:10px;padding:12px}
.mini h4{margin:0 0 8px 0;color:#eef2ff;font-size:13px}
.chapter,.issue{background:#121722;border:1px solid #242b3b;border-radius:10px;padding:12px;margin-bottom:10px}
.block{background:#0f131c;border-left:2px solid #4e628f;border-radius:8px;padding:12px;margin:8px 0;white-space:pre-wrap;line-height:1.85;font-size:12px}
.field-block{background:#0f131c;border-left:2px solid #4e628f;border-radius:8px;padding:10px 12px;margin:8px 0}
.field-row{display:flex;gap:6px;padding:3px 0;line-height:1.6;font-size:13px;color:#c8d0e0;align-items:baseline}
.field-dot{color:#4e628f;flex:none;font-size:14px}
.field-label{color:#8ea1d8;flex:none;font-weight:500}
.field-val{white-space:pre-wrap;word-break:break-word}
.editor label{display:block;margin:10px 0 6px;color:#8ea1d8;font-size:12px}
.editor textarea{width:100%;min-height:140px;resize:vertical}
.editor input{width:100%}
.editor .hint{color:#7f8aa3;font-size:11px;margin-top:6px}
@media (max-width: 1280px){#left{width:34%;min-width:300px}.hdr-selects{flex-basis:100%}#novelSel{max-width:none}}
@media (max-width: 980px){#main{flex-direction:column}#left{width:100%;max-width:none;min-width:0;border-right:none;border-bottom:1px solid #232834;max-height:42vh}#tabs{padding-top:8px}#tc{padding:14px}.field-grid{grid-template-columns:1fr}}
</style></head><body>
<div id='hdr'><div class='hdr-row'><div class='hdr-brand'><h1>Novel Flow</h1><span id='boot-pill' class='tag'>前端待初始化</span></div><div class='hdr-selects'><select id='modeSel' onchange='changeMode()'><option value='formal'>正式模式</option><option value='test'>测试模式</option></select><select id='modelSel' onchange='changeModel()'><option value='deepseek'>DeepSeek V4-Pro</option><option value='doubao'>豆包</option><option value='openai'>OpenAI</option><option value='codex'>Codex CLI</option></select><select id='novelSel' onchange='selectNovel(this.value)'><option value=''>选择小说</option></select><span id='stage-pill'>未开始</span></div><div class='hdr-primary'><button id='btnNew' onclick='openNewNovelDialog()'>新建小说</button><button id='btnContinue' onclick='continueFormal()'>写下一章</button><button id='btnStop' class='ghost' onclick='stopCurrentRun()' style='display:none'>停止运行</button><button class='danger' onclick='deleteNovel()'>删除小说</button><button id='btnBlueprint' onclick='testBlueprint()' style='display:none'>测试大纲</button><button id='btnWrite' onclick='testWrite()' style='display:none'>测试写正文</button><button id='btnCritique' onclick='testCritique()' style='display:none'>测试评价</button><button id='btnPatch' onclick='testPatch()' style='display:none'>测试修改</button></div></div><div class='hdr-row hdr-steps'><button id='btnStep1' class='step-btn' onclick=\"startConfiguredPlanningRun('step_1')\">1 大纲+蓝图</button><button id='btnStep2' class='step-btn' onclick=\"startConfiguredPlanningRun('step_2')\">2 背景系+世界观</button><button id='btnStep3' class='step-btn' onclick=\"startConfiguredPlanningRun('step_3')\">3 角色卡</button><button id='btnStep4' class='step-btn' onclick=\"startConfiguredPlanningRun('step_4')\">4 客观事件时间线</button><button id='btnStep5' class='step-btn' onclick=\"startConfiguredPlanningRun('step_5')\">5 角色发展线</button><button id='btnStep6' class='step-btn' onclick=\"startConfiguredPlanningRun('step_6')\">6 反转设计</button><button id='btnStep7' class='step-btn' onclick=\"startConfiguredPlanningRun('step_7')\">7 明线暗线发展线</button><button id='btnStep8' class='step-btn' onclick=\"startConfiguredPlanningRun('step_8')\">8 续生成一章摘要</button><button id='btnBlueprintReview' class='step-btn' onclick=\"startConfiguredPlanningRun('blueprint_review')\">Critic Blueprint</button></div></div>
<div id='newNovelModal' class='modal'><div class='modal-card'><div class='modal-head'><div class='modal-title'>新建小说</div><div class='modal-desc'>这里先保存小说标题、原始题材需求、小说类型和可选风格，不会自动继续到大纲生成。创建后请手动点击“1 大纲+蓝图”。</div></div><div class='modal-body'><div class='modal-section'><div class='modal-section-title'>基础信息</div><div class='field-grid'><div class='field full'><label>小说标题</label><input id='newTitleInput' placeholder='例如：她非良母' /><div class='field-help'>这里是书名，后续会显示在左上角小说切换列表里，也可以在用户输入页继续修改。</div></div><div class='field full'><label>题材/需求</label><textarea id='newQueryInput' placeholder='例如：都市情感反转，女主发现丈夫隐藏身份后反击'></textarea><div class='field-help'>写清题材、主角处境、核心冲突，或者你最想看到的关键局面。</div></div><div class='field full'><label>小说类型</label><select id='newTypeSelect' onchange='updateNovelTypeHint()'><option value='auto'>加载中...</option></select><div id='newTypeHint' class='field-help'>不选也可以，系统会按题材需求和额外风格要求自动判断。</div></div><div class='field full'><label>风格要求（可留空）</label><textarea id='newStyleInput' placeholder='例如：古言权谋、轻喜剧、短篇悬疑、第三人称群像；留空则按所选类型自动匹配风格层'></textarea><div class='field-help'>这里是额外风格偏好。正文主流程不变，风格差异只走独立的风格层提示词。</div></div></div></div><div class='modal-section'><div class='modal-section-title'>扩展配置</div><div class='config-placeholder'>后续可以在这里增加目标体量、章节数、叙事视角、禁用元素、参考卡片范围等配置。当前版本先使用系统默认决策。</div></div></div><div class='modal-actions'><button class='ghost' onclick='closeNewNovelDialog()'>取消</button><button onclick='startFormalFromDialog()'>保存需求</button></div></div></div>
<div id='main'><div id='left'><div id='subhdr'>左侧显示当前小说的历史运行记录，当前运行默认展开</div><div id='evs'><div class='empty'>选择小说或发起一次运行后查看过程</div></div></div><div id='right'><div id='tabs'><div class='tab active' onclick="showTab('input')">用户输入</div><div class='tab' onclick="showTab('blueprint')">小说信息</div><div class='tab' onclick="showTab('text')">小说正文</div><div class='tab' onclick="showTab('critic')">评价结果</div></div><div id='tc'><div id='pnl-input' class='pnl active'><div class='empty'>等待加载用户输入</div></div><div id='pnl-blueprint' class='pnl'><div class='empty'>等待加载小说信息</div></div><div id='pnl-text' class='pnl'><div class='empty'>等待加载小说正文</div></div><div id='pnl-critic' class='pnl'><div class='empty'>等待加载评价结果</div></div></div></div></div>
<script>
let mode='formal',llmProvider='deepseek',bookId='',pendingRunId='',runsCache=[],expandedRuns=new Set(),boxStates={},detailStates={},currentBook=null,pendingStepRevision=null,lastRightRenderKey='',lastLivePreviewKey='',runActiveItemKeys={};
let refreshPaused=false,refreshPauseReason='',refreshPauseTimer=null,isMouseSelecting=false;
const LLM_PROVIDER_STORAGE_KEY='novel_flow_llm_provider';
const DEFAULT_STYLE_PLACEHOLDER='例如：古言权谋、轻喜剧、短篇悬疑、第三人称群像；留空则按所选类型自动匹配风格层';
const STAGES={research:'调研中',planning:'大纲中',writing:'写作中',critique:'评价中',patching:'修改中',complete:'已完成'};
const stageText=v=>STAGES[v]||v||'未开始',esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),shortTs=v=>v?String(v).replace('T',' ').slice(0,19):'';
async function api(path,opt){const r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json'}},opt||{}));return await r.json();}
function ensureOk(r){if(r&&r.ok===false){alert(r.error||'请求失败');return false;}return true;}
const validLlmProvider=v=>['deepseek','doubao','openai','codex'].includes(String(v||'').toLowerCase());
function currentLlmProvider(){return validLlmProvider(llmProvider)?llmProvider:'deepseek';}
function withLlmProvider(payload){return Object.assign({},payload||{}, {llm_provider:currentLlmProvider()});}
function changeModel(){llmProvider=validLlmProvider(modelSel.value)?modelSel.value:'deepseek';try{localStorage.setItem(LLM_PROVIDER_STORAGE_KEY,llmProvider);}catch{}}
let novelTypeOptions=[];
let stepDrafts={},stepDraftDirty={},stepReviewNotes={},stepDraftBookId='';
let stepDraftObjects={};
function deepClone(value){return JSON.parse(JSON.stringify(value??{}));}
function resetStepDraftCache(targetBookId=''){stepDraftBookId=targetBookId;stepDrafts={};stepDraftDirty={};stepReviewNotes={};stepDraftObjects={};}
const STEP_STORY_BLUEPRINT_FIELDS={step_2:'story_engine',step_4:'event_timeline',step_6:'twist_designs',step_7:'story_lines',step_8:'chapter_briefs'};
const STEP_METADATA_FIELDS={step_5:'character_milestones'};
const STEP_RUN_CONFIGS={
  step_1:{path:'/api/novels/generate_outline',pendingMessage:'大纲+蓝图生成中',taskLabel:'步骤1 大纲+蓝图'},
  step_2:{path:'/api/novels/generate_worldbuilding',pendingMessage:'世界观+背景体系生成中',taskLabel:'步骤2 背景体系+世界观'},
  step_3:{path:'/api/novels/generate_characters',pendingMessage:'角色卡生成中',taskLabel:'步骤3 角色卡'},
  step_4:{path:'/api/novels/generate_event_timeline',pendingMessage:'事件时间线生成中',taskLabel:'步骤4 客观事件时间线'},
  step_5:{path:'/api/novels/generate_milestones',pendingMessage:'角色发展线生成中',taskLabel:'步骤5 角色发展线'},
  step_6:{path:'/api/novels/generate_twist_designs',pendingMessage:'反转设计生成中',taskLabel:'步骤6 反转设计'},
  step_7:{path:'/api/novels/generate_story_lines',pendingMessage:'明线暗线发展线生成中',taskLabel:'步骤7 明线暗线发展线'},
  step_8:{path:'/api/novels/generate_chapter_briefs_batch',pendingMessage:'步骤8 生成中（当前 1 章）',taskLabel:'步骤8 续写一章摘要',payload:{batch_size:1}},
  blueprint_review:{path:'/api/novels/review_blueprint',pendingMessage:'Blueprint Critic 评审中',taskLabel:'Critic Blueprint 评审'},
};
const STEP_SPECIAL_PAYLOAD_READERS={
  step_1:(book,storyBlueprint)=>({premise:book?.premise||{},story_engine:readStoryStepFieldValue(storyBlueprint,'story_engine')}),
  step_3:(book)=>({characters:Array.isArray(book?.characters)?book.characters:[]}),
};
const STEP_SPECIAL_EMPTY_PAYLOADS={step_1:{premise:{},story_engine:{}},step_3:{characters:[]}};
function readStoryStepFieldValue(storyBlueprint,field){
  if(field==='story_engine'){
    const value=storyBlueprint?.story_engine;
    return value&&typeof value==='object'&&!Array.isArray(value)?value:{};
  }
  const value=storyBlueprint?.[field];
  return Array.isArray(value)?value:[];
}
function emptyStepFieldValue(field){return field==='story_engine'?{}:[];}
function stepPayloadFromBook(book,stepKey){
  const storyBlueprint=book?.metadata?.story_blueprint||{};
  const specialReader=STEP_SPECIAL_PAYLOAD_READERS[stepKey];
  if(specialReader)return specialReader(book,storyBlueprint);
  const storyField=STEP_STORY_BLUEPRINT_FIELDS[stepKey];
  if(storyField){
    return{[storyField]:readStoryStepFieldValue(storyBlueprint,storyField)};
  }
  const metaField=STEP_METADATA_FIELDS[stepKey];
  if(metaField)return{[metaField]:Array.isArray(book?.metadata?.[metaField])?book.metadata[metaField]:[]};
  return{};
}
function emptyStepPayload(stepKey){
  const special=STEP_SPECIAL_EMPTY_PAYLOADS[stepKey];
  if(special)return deepClone(special);
  const storyField=STEP_STORY_BLUEPRINT_FIELDS[stepKey];
  if(storyField)return{[storyField]:emptyStepFieldValue(storyField)};
  const metaField=STEP_METADATA_FIELDS[stepKey];
  if(metaField)return{[metaField]:[]};
  return{};
}
function ensureStepDraft(stepKey,payloadObj){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const serialized=JSON.stringify(payloadObj??{},null,2);if(!(stepKey in stepDrafts)||!stepDraftDirty[stepKey]){stepDrafts[stepKey]=serialized;stepDraftObjects[stepKey]=deepClone(payloadObj??{});}return stepDrafts[stepKey];}
function ensureStepObject(stepKey,payloadObj){ensureStepDraft(stepKey,payloadObj);if(!(stepKey in stepDraftObjects))stepDraftObjects[stepKey]=deepClone(payloadObj??{});return stepDraftObjects[stepKey];}
function updateStepDraft(stepKey,value){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=value;stepDraftDirty[stepKey]=true;try{stepDraftObjects[stepKey]=JSON.parse(value);}catch{}}
function markStepDraftSaved(stepKey,payloadObj,notes){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=JSON.stringify(payloadObj??{},null,2);stepDraftObjects[stepKey]=deepClone(payloadObj??{});stepDraftDirty[stepKey]=false;stepReviewNotes[stepKey]=Array.isArray(notes)?notes:[];}
function sanitizeCharactersDraft(chars){if(!Array.isArray(chars))return[];return chars.filter(item=>item&&typeof item==='object'&&Object.keys(item).length>0&&(String(item.name||'').trim()||String(item.role||'').trim()));}
function sanitizeStep3DraftObject(obj){if(!obj||typeof obj!=='object')return obj;const next=deepClone(obj);if(Array.isArray(next.characters))next.characters=sanitizeCharactersDraft(next.characters);return next;}
function applyStepRevisionDraft(result){if(!result||!result.step_key)return;const stepKey=result.step_key;const revisedText=result.draft_json||JSON.stringify(result.step_payload||{},null,2);stepDrafts[stepKey]=revisedText;try{stepDraftObjects[stepKey]=JSON.parse(revisedText);}catch{stepDraftObjects[stepKey]=deepClone(result.step_payload||{});}if(stepKey==='step_3'){stepDraftObjects[stepKey]=sanitizeStep3DraftObject(stepDraftObjects[stepKey]||{});stepDrafts[stepKey]=JSON.stringify(stepDraftObjects[stepKey]||{},null,2);}stepDraftDirty[stepKey]=true;stepReviewNotes[stepKey]=Array.isArray(result.review_notes)?result.review_notes:[];if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function latestOutputByType(runData,outputType){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){if(outs[i]?.output_type===outputType)return outs[i].payload||null;}return null;}
function latestChapterPreviewByMode(runData,previewMode){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){const item=outs[i];if(item?.output_type!=='chapter_live_preview')continue;const payload=item?.payload||{};if(String(payload?.preview_mode||'')!==String(previewMode||''))continue;return{payload,createdAt:item?.created_at||''};}return null;}
function mergeChapterBlocksText(blocks,fallbackText=''){const arr=Array.isArray(blocks)?blocks:[];const merged=arr.map(block=>String(block?.text||'').trim()).filter(Boolean).join('\\n\\n').trim();return merged||String(fallbackText||'').trim();}
function parsePatchRound(stageName){const match=String(stageName||'').match(/patch_round_(\\d+)_/);return match?Number(match[1]||0):0;}
function latestPatchedBlockIds(runData){const evts=Array.isArray(runData?.events)?runData.events:[];for(let i=evts.length-1;i>=0;i-=1){const payload=evts[i]?.payload||{};const stage=String(payload?.stage||'');if(!stage.includes('_rewrite_done'))continue;const patchedBlocks=Array.isArray(payload?.rewrite_result?.patched_blocks)?payload.rewrite_result.patched_blocks:[];const ids=patchedBlocks.map(item=>String(item?.block_id||'').trim()).filter(Boolean);if(ids.length)return ids;}return [];}
function collectChapterTaskOutputs(runData){
  const runId=String(runData?.run_id||'run');
  const chapterPreview=runData?.chapter_preview&&typeof runData.chapter_preview==='object'?runData.chapter_preview:{};
  const chapterId=String(chapterPreview?.chapter_id||'').trim();
  const stageEvents=(Array.isArray(runData?.events)?runData.events:[]).filter(event=>event?.event_type==='stage'&&event?.payload&&typeof event.payload==='object');
  const items=[];
  const draft=latestChapterPreviewByMode(runData,'chapter_draft');
  if(draft&&String(draft.payload?.final_text||'').trim()){
    items.push({
      key:`${runId}:task:draft`,
      title:'正文任务 · 整章手稿',
      kind:'output',
      outputType:'chapter_draft_task',
      rawPayload:{chapter_id:chapterId||String(draft.payload?.chapter_id||''),draft_preview:draft.payload},
      sortTs:draft.createdAt||'',
    });
  }
  const reviewEvents=stageEvents.filter(event=>String(event?.payload?.stage||'')==='review_iteration_1_tool_done'&&String(event?.payload?.tool_name||'').trim()&&event?.payload?.tool_result&&typeof event.payload.tool_result==='object');
  if(reviewEvents.length){
    items.push({
      key:`${runId}:task:review`,
      title:'正文任务 · 轻量 Review',
      kind:'output',
      outputType:'chapter_review_bundle',
      rawPayload:{
        chapter_id:chapterId,
        reviews:reviewEvents.map(event=>({tool_name:String(event?.payload?.tool_name||''),tool_result:event?.payload?.tool_result||{},stage:String(event?.payload?.stage||''),ts:event?.ts||''})),
      },
      sortTs:String(reviewEvents[reviewEvents.length-1]?.ts||''),
    });
  }
  stageEvents.forEach(event=>{
    const payload=event?.payload||{};
    const stageName=String(payload?.stage||'');
    const patchRound=parsePatchRound(stageName);
    if(stageName.endsWith('_plan_done')&&payload?.patch_plan&&typeof payload.patch_plan==='object'){
      items.push({
        key:`${runId}:task:plan:${patchRound||items.length}`,
        title:`正文任务 · Patch Plan${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_plan_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,patch_plan:payload.patch_plan},
        sortTs:String(event?.ts||''),
      });
    }
    if(stageName.endsWith('_rewrite_done')&&payload?.rewrite_result&&typeof payload.rewrite_result==='object'){
      items.push({
        key:`${runId}:task:rewrite:${patchRound||items.length}`,
        title:`正文任务 · 修改后的 Block${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_rewrite_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,rewrite_result:payload.rewrite_result},
        sortTs:String(event?.ts||''),
      });
    }
    if(stageName.endsWith('_judge')&&payload?.judge_result&&typeof payload.judge_result==='object'){
      items.push({
        key:`${runId}:task:judge:${patchRound||items.length}`,
        title:`正文任务 · Patch Judge${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_judge_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,judge_result:payload.judge_result,final_judge:payload?.final_judge||{}},
        sortTs:String(event?.ts||''),
      });
    }
  });
  return items;
}
function stepFieldLabel(key){const labels={premise:'大纲主体',story_engine:'写作架构',characters:'角色卡',event_timeline:'客观事件时间线',character_milestones:'角色发展线',twist_designs:'反转设计',story_lines:'故事线',chapter_briefs:'章节摘要',title:'标题',high_concept:'高概念',theme_statement:'立意',story_summary:'故事简介',genre:'题材',target_style:'风格',emotional_hook:'情绪钩子',central_conflict:'核心冲突',core_hook:'核心看点',escalation_path:'升级路径',twist_blueprint:'反转蓝图',ending_payoff:'结尾兑现',selling_points:'卖点',engine_sentence:'故事驱动句',narrative_mode:'叙事结构',viewpoint_strategy:'视角策略',reveal_strategy:'信息揭示策略',hook_strategy:'前三章留人策略',default_track:'默认轨道',world_rules:'世界规则',power_structure:'权力结构',world_map:'世界地图',structural_inertia:'结构惯性',rebound_mechanism:'反弹机制',story_trigger:'故事启动条件',objective_conditions:'客观条件与机会结构',twist_id:'反转编号',false_belief:'表层误导认知',truth:'真实真相',reader_alignment:'读者站位',seed_from:'埋线起点',reveal_at:'揭示章节',allowed_clues:'允许埋下的线索',forbidden_reveals:'禁止提前揭示',pov_lock:'视角锁',related_characters:'关联角色',payoff_effect:'兑现效果',line_id:'故事线编号',name:'名称',visibility:'明暗线',line_type:'线类型',reader_hook_mode:'读者钩子方式',line_rules:'线规则',carried_twists:'承载反转',line_goal:'线目标',key_progressions:'关键推进章节',plot:'关键情节',start_state:'起点状态',midpoint_shift:'中段变化',end_state:'终点状态',core_question:'核心问题',chapter_id:'章节编号',active_lines:'挂线',active_twists:'激活反转',summary:'章节摘要',chapter_type:'章型',incoming_hook:'承接钩子',opening_hook:'开篇钩子',core_scene:'核心场面',chapter_object:'章节目标物',reader_emotion:'读者情绪',reader_belief:'读者当前认知',allowed_info:'允许释放的信息',forbidden:'禁止出现',world_limit:'世界/规则限制',character_focus:'角色焦点',character_shift:'角色变化',relationship_reprice:'关系重估',emotional_turn:'情绪转折',backstory_trigger:'触发的前史',scene_engine:'场景引擎',clue_reveal_mechanism:'线索露出机制',character_reentry_focus:'人物再出场锚点',human_pain_anchor:'人味痛点锚',romance_seed:'言情危险种子',small_payoff:'小兑现',ending_pull:'结尾牵引',info_budget:'信息预算',objective:'章节摘要',tension:'张力',phase:'阶段',story_function:'剧情功能',key_turn:'关键转折',payoff:'兑现',next_route_hint:'下一步提示',target_words:'目标字数',scene_density:'场景密度',scene_id:'场景编号',conflict:'冲突',info_reveal:'信息释放',emotional_shift:'情绪变化',appearance:'外貌'};return labels[key]||String(key).replaceAll('_',' ');}
function orderedStepObjectEntries(stepKey,path,obj){
  const rawEntries=Object.entries(obj||{});
  const orderMap={
    step_6:['twist_id','title','false_belief','truth','reader_alignment','seed_from','reveal_at','allowed_clues','forbidden_reveals','pov_lock','related_characters','payoff_effect'],
    step_7:['line_id','name','line_type','visibility','core_question','reader_hook_mode','start_state','midpoint_shift','end_state','carried_twists','line_rules'],
    step_8:['chapter_id','title','chapter_type','active_lines','active_twists','summary','incoming_hook','opening_hook','core_scene','chapter_object','reader_emotion','reader_belief','allowed_info','allowed_clues','forbidden','world_limit','character_focus','character_shift','relationship_reprice','emotional_turn','backstory_trigger','scene_engine','clue_reveal_mechanism','character_reentry_focus','human_pain_anchor','romance_seed','small_payoff','ending_pull','info_budget']
  };
  const isStep6Item=stepKey==='step_6'&&path.length===2&&String(path[0])==='twist_designs'&&typeof path[1]==='number';
  const isStep7Item=stepKey==='step_7'&&path.length===2&&String(path[0])==='story_lines'&&typeof path[1]==='number';
  const isStep8Item=stepKey==='step_8'&&path.length===2&&String(path[0])==='chapter_briefs'&&typeof path[1]==='number';
  if(!isStep6Item&&!isStep7Item&&!isStep8Item)return rawEntries;
  const wanted=orderMap[stepKey]||[];
  if(!wanted.length)return rawEntries;
  const entryMap=new Map(rawEntries);
  const ordered=wanted.filter(key=>entryMap.has(key)).map(key=>[key,entryMap.get(key)]);
  rawEntries.forEach(([key,val])=>{if(!wanted.includes(key))ordered.push([key,val]);});
  return ordered;
}
function parseStepPath(pathText){return String(pathText||'').split('.').filter(Boolean).map(part=>/^[0-9]+$/.test(part)?Number(part):part);}
function setStepValueByPath(root,path,value){if(!path.length)return value;let cursor=root;for(let i=0;i<path.length-1;i+=1){const key=path[i],nextKey=path[i+1];if(Array.isArray(cursor)&&typeof key==='number'){while(cursor.length<=key)cursor.push(typeof nextKey==='number'?[]:{});if(cursor[key]===null||cursor[key]===undefined)cursor[key]=typeof nextKey==='number'?[]:{};cursor=cursor[key];continue;}if(cursor[key]===undefined||cursor[key]===null){cursor[key]=typeof nextKey==='number'?[]:{};}cursor=cursor[key];}const finalKey=path[path.length-1];if(Array.isArray(cursor)&&typeof finalKey==='number'){while(cursor.length<finalKey)cursor.push(null);while(cursor.length<=finalKey)cursor.push('');cursor[finalKey]=value;return root;}cursor[finalKey]=value;return root;}
function updateStepEditorValue(stepKey,pathText,kind,rawValue){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const basePayload=stepPayloadFromBook(currentBook,stepKey);const state=ensureStepObject(stepKey,basePayload);const path=parseStepPath(pathText);let value=rawValue;if(kind==='string_array'){value=normalizeMultiline(rawValue).split('\\n').map(item=>item.trim()).filter(Boolean);}else if(kind==='number'){const trimmed=String(rawValue??'').trim();value=trimmed===''?'':Number(trimmed);}else if(kind==='boolean'){value=!!rawValue;}setStepValueByPath(state,path,value);stepDrafts[stepKey]=JSON.stringify(state,null,2);stepDraftDirty[stepKey]=true;}
function characterKey(item,index){const name=String(item?.name||'').trim();if(name)return `name:${name}`;const role=String(item?.role||'').trim();if(role)return `role:${role}:${index}`;return `index:${index}`;}
function summarizeStep3Diff(oldChars,newChars){const safeOld=Array.isArray(oldChars)?oldChars.filter(x=>x&&typeof x==='object'):[];const safeNew=Array.isArray(newChars)?newChars.filter(x=>x&&typeof x==='object'):[];const oldMap=new Map();safeOld.forEach((item,index)=>oldMap.set(characterKey(item,index),item));const newMap=new Map();safeNew.forEach((item,index)=>newMap.set(characterKey(item,index),item));const removed=[];const added=[];let changed=0;for(const [k,v] of oldMap.entries()){if(!newMap.has(k)){removed.push(String(v?.name||v?.role||k));continue;}if(JSON.stringify(v)!==JSON.stringify(newMap.get(k)))changed+=1;}for(const [k,v] of newMap.entries()){if(!oldMap.has(k))added.push(String(v?.name||v?.role||k));}return{oldCount:safeOld.length,newCount:safeNew.length,removed,added,changed};}
function step3DiffConfirmMessage(diff){const cap=(arr)=>arr.slice(0,5).join('、');let msg=`即将保存角色卡\\n原有：${diff.oldCount} 个\\n当前：${diff.newCount} 个\\n修改：${diff.changed} 个\\n新增：${diff.added.length} 个\\n删除：${diff.removed.length} 个`;if(diff.added.length)msg+=`\\n新增示例：${cap(diff.added)}${diff.added.length>5?' …':''}`;if(diff.removed.length)msg+=`\\n删除示例：${cap(diff.removed)}${diff.removed.length>5?' …':''}`;msg+='\\n\\n确认保存吗？';return msg;}
function stepArrayItemTitle(stepKey,path,item,index){
  const fallback=`${stepFieldLabel(String(path[path.length-1]||'item'))} ${index+1}`;
  if(!(item&&typeof item==='object'))return fallback;
  if(stepKey==='step_4'&&path.length===1&&String(path[0])==='event_timeline'){
    const timeLabel=String(item.time_label||'').trim()||'未标注时间';
    const title=String(item.title||'').trim()||'未命名事件';
    return `${timeLabel}：${title}`;
  }
  if(stepKey==='step_5'){
    const tail=String(path[path.length-1]||'');
    if(path.length===1&&String(path[0])==='character_milestones'){
      return String(item.character_name||'未命名角色').trim()||`角色 ${index+1}`;
    }
    if(tail==='axes'){
      return String(item.axis||'未命名线').trim()||`线 ${index+1}`;
    }
    if(tail==='phases'){
      const phaseNo=String(item.phase||'').trim();
      const label=String(item.label||'').trim();
      return `${phaseNo?`阶段${phaseNo}`:`阶段${index+1}`}${label?`：${label}`:''}`;
    }
  }
  if(stepKey==='step_6'&&path.length===1&&String(path[0])==='twist_designs'){
    return String(item.title||'').trim()||`反转设计 ${index+1}`;
  }
  if(stepKey==='step_7'&&path.length===1&&String(path[0])==='story_lines'){
    const name=String(item.name||'').trim();
    if(name)return name;
    const visibility=String(item.visibility||'').trim();
    return visibility?`${visibility} ${index+1}`:`明线暗线 ${index+1}`;
  }
  if(stepKey==='step_8'&&path.length===1&&String(path[0])==='chapter_briefs'){
    const chapterId=String(item.chapter_id||'').trim()||`ch_${String(index+1).padStart(3,'0')}`;
    const title=String(item.title||'').trim();
    return title?`${chapterId} · ${title}`:chapterId;
  }
  return fallback;
}
function renderStepEditorField(stepKey,path,value){
  const pathText=path.join('.');
  if(
    stepKey==='step_5' &&
    Array.isArray(value) &&
    String(path[path.length-1]||'')==='phases'
  ){
    if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    return `<div class='step-inline-stack'>${value.map((phase,phaseIndex)=>{
      const phaseNo=String(phase?.phase||'').trim();
      const phaseLabel=String(phase?.label||'').trim();
      const scenes=Array.isArray(phase?.scenes)?phase.scenes:[];
      const blockLines=[`${phaseNo?`阶段${phaseNo}`:`阶段${phaseIndex+1}`}${phaseLabel?`：${phaseLabel}`:''}`];
      scenes.forEach((scene)=>{
        const title=String(scene?.title||'未命名场景').trim();
        const trigger=String(scene?.trigger||'').trim();
        const psychology=String(scene?.psychology||'').trim();
        const outcome=String(scene?.outcome||'').trim();
        blockLines.push(`• ${title}`);
        if(trigger)blockLines.push(`  - 触发：${trigger}`);
        if(psychology)blockLines.push(`  - 心理：${psychology}`);
        if(outcome)blockLines.push(`  - 结果：${outcome}`);
      });
      return `<div class='step-inline-card'><div class='pre'>${esc(blockLines.join('\\n'))}</div></div>`;
    }).join('')}</div>`;
  }
  if(Array.isArray(value)){
    if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    if(stepKey==='step_8'&&path.length===1&&String(path[0])==='chapter_briefs'){
      return `<div class='step-inline-stack'>${value.map((item,index)=>{
        const detailKey=`inline:${stepKey}:${[...path,index].join('.')}`;
        const title=stepArrayItemTitle(stepKey,path,item,index);
        const toolbar=`<div style='display:flex;justify-content:flex-end;gap:8px;padding:8px 0 0 0'><button class='ghost' onclick='event.stopPropagation();saveSingleChapterBrief(${index})'>保存</button><button class='ghost' onclick='event.stopPropagation();reviseSingleChapterBriefByInstruction(${index})'>指令调整</button><button class='ghost' onclick='event.stopPropagation();deleteSingleChapterBrief(${index})'>删除</button></div>`;
        return `<details class='step-inline-card' data-detail-key='${esc(detailKey)}' ${isDetailOpen(detailKey,false)?'open':''} ontoggle="toggleDetailState('${esc(detailKey)}', this.open)"><summary class='step-inline-card-title'>${esc(title)}</summary>${toolbar}${renderStepEditorField(stepKey,[...path,index],item)}</details>`;
      }).join('')}</div>`;
    }
    const primitiveArray=value.every(item=>item===null||['string','number','boolean'].includes(typeof item));
    if(primitiveArray){
      return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string_array', this.value)">${esc(value.map(item=>String(item??'')).join('\\n'))}</textarea>`;
    }
    return `<div class='step-inline-stack'>${value.map((item,index)=>{
      const detailKey=`inline:${stepKey}:${[...path,index].join('.')}`;
      const defaultOpen = stepKey==='step_5';
      return `<details class='step-inline-card' data-detail-key='${esc(detailKey)}' ${isDetailOpen(detailKey,defaultOpen)?'open':''} ontoggle="toggleDetailState('${esc(detailKey)}', this.open)"><summary class='step-inline-card-title'>${esc(stepArrayItemTitle(stepKey,path,item,index))}</summary>${renderStepEditorField(stepKey,[...path,index],item)}</details>`;
    }).join('')}</div>`;
  }
  if(value&&typeof value==='object'){
    if(
      stepKey==='step_5' &&
      path.length===2 &&
      String(path[0])==='character_milestones' &&
      typeof path[1]==='number'
    ){
      const axesVal=Array.isArray(value.axes)?value.axes:[];
      return `<div class='step-inline-root'><div class='step-inline-field'><label>axes</label>${renderStepEditorField(stepKey,[...path,'axes'],axesVal)}</div></div>`;
    }
    if(
      stepKey==='step_5' &&
      path.length===4 &&
      String(path[0])==='character_milestones' &&
      String(path[2])==='axes' &&
      typeof path[1]==='number' &&
      typeof path[3]==='number'
    ){
      const phasesVal=Array.isArray(value.phases)?value.phases:[];
      return `<div class='step-inline-root'><div class='step-inline-field'><label>phases</label>${renderStepEditorField(stepKey,[...path,'phases'],phasesVal)}</div></div>`;
    }
    const entries=orderedStepObjectEntries(stepKey,path,value);
    if(!entries.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    return `<div class='step-inline-root'>${entries.map(([key,val])=>`<div class='step-inline-field'><label>${esc(stepFieldLabel(key))}</label>${renderStepEditorField(stepKey,[...path,key],val)}</div>`).join('')}</div>`;
  }
  if(typeof value==='number'){
    return `<input class='step-inline-input' type='number' value='${esc(value)}' oninput="updateStepEditorValue('${stepKey}','${pathText}','number', this.value)" />`;
  }
  if(typeof value==='boolean'){
    return `<label class='row'><input type='checkbox' ${value?'checked':''} onchange="updateStepEditorValue('${stepKey}','${pathText}','boolean', this.checked)" /> ${value?'是':'否'}</label>`;
  }
  return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string', this.value)">${esc(value??'')}</textarea>`;
}
function renderStepEditor(stepKey,stepTitle,payloadObj){const notes=Array.isArray(stepReviewNotes[stepKey])?stepReviewNotes[stepKey]:[];const state=ensureStepObject(stepKey,payloadObj);return `<div class='step-editor'><div class='step-editor-toolbar'><div class='step-editor-title'>${esc(stepTitle)} 直接编辑</div><div class='step-editor-actions'><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button></div></div><div class='step-editor-body'>${notes.length?`<ul class='step-editor-notes'>${notes.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:`<div class='step-editor-empty'>可以直接在这个模块里改内容；按 Enter 会换行，点右上角“保存修改”才会真正写回。</div>`}${renderStepEditorField(stepKey,[],state)}<div class='step-editor-hint'>这里是当前步骤的结构化编辑区。质检修改和指令修改会先生成建议稿并回填到这里，确认后再保存。</div></div></div>`;}
function getStepPayloadText(stepKey,payloadObj){const state=ensureStepObject(stepKey,payloadObj);return JSON.stringify(state??{},null,2);}
async function saveConcept(){
  if(!bookId)return alert('请先选择一部小说。');
  const title=(document.getElementById('concept-title')?.value||'').trim();
  const query=normalizeMultiline(document.getElementById('concept-query')?.value||'');
  const user_topic=normalizeMultiline(document.getElementById('concept-user-topic')?.value||'');
  const style_request=normalizeMultiline(document.getElementById('concept-style-request')?.value||'');
  const assistant_persona_prompt=normalizeMultiline(document.getElementById('concept-assistant-persona')?.value||'');
  const total_word_target=(document.getElementById('concept-total-word-target')?.value||'').trim();
  const chapter_count_target=(document.getElementById('concept-chapter-count-target')?.value||'').trim();
  const chapter_word_target=(document.getElementById('concept-chapter-word-target')?.value||'').trim();
  const pace_notes=normalizeMultiline(document.getElementById('concept-pace-notes')?.value||'');
  const result=await api('/api/novels/update_concept',{
    method:'POST',
    body:JSON.stringify({
      mode,
      book_id:bookId,
      title,
      query,
      user_topic,
      style_request,
      assistant_persona_prompt,
      total_word_target,
      chapter_count_target,
      chapter_word_target,
      pace_notes
    })
  });
  if(!ensureOk(result))return;
  currentBook=result.book;
  renderInputPanel(currentBook);
  renderBlueprint(currentBook);
  renderText(currentBook);
  await loadNovels();
  alert('小说基础信息已保存。');
}
async function saveStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');if(stepKey==='step_3'){const draft=ensureStepObject('step_3',stepPayloadFromBook(currentBook,'step_3'));const sanitized=sanitizeStep3DraftObject(draft||{});stepDraftObjects['step_3']=sanitized||{};stepDrafts['step_3']=JSON.stringify(stepDraftObjects['step_3'],null,2);const oldChars=Array.isArray(currentBook?.characters)?currentBook.characters:[];const newChars=Array.isArray(stepDraftObjects['step_3']?.characters)?stepDraftObjects['step_3'].characters:[];const diff=summarizeStep3Diff(oldChars,newChars);if(diff.changed>0||diff.added.length>0||diff.removed.length>0||diff.oldCount!==diff.newCount){if(!confirm(step3DiffConfirmMessage(diff)))return;}}const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));const result=await api('/api/novels/save_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text})});if(!ensureOk(result))return;currentBook=result.book;markStepDraftSaved(stepKey,result.step_payload||stepPayloadFromBook(result.book,stepKey),stepReviewNotes[stepKey]||[]);renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();alert('当前步骤修改已保存。');}
function clearStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认清空当前步骤草稿？该操作不会立即写库，需点击保存才生效。'))return;const empty=emptyStepPayload(stepKey);stepDraftObjects[stepKey]=deepClone(empty);stepDrafts[stepKey]=JSON.stringify(empty,null,2);stepDraftDirty[stepKey]=true;if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
async function reviseStepDraft(stepKey,revisionMode){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));let guidance='';if(revisionMode==='instruction'){guidance=prompt('描述你希望这一步结果怎么改：');if(!guidance)return;}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text,revision_mode:revisionMode,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:stepKey,revision_mode:revisionMode,payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};const taskLabel=`${stepKey.toUpperCase()} ${revisionMode==='review'?'质检修改':'指令修改'}`;runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:taskLabel,pending_message:revisionMode==='review'?'步骤质检修改已启动。':'步骤指令修改已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addCharacterByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述新角色需求（身份、作用、和谁形成关系）：');if(!extra)return;const guidance=`仅新增 1 个角色，不要改写已有角色；新角色要与现有核心角色形成明确关系并推动后续剧情。\n用户要求：${extra}`;const r=await api('/api/novels/add_character',{method:'POST',body:JSON.stringify({mode,book_id:bookId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision=null;expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:'步骤3 增加角色',pending_message:'新增角色任务已启动（仅追加新角色，不重算整包）。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addMilestoneLine(){if(!bookId)return alert('请先选择一部小说。');const guidance=String(prompt('描述新增角色发展线需求（角色名、线名、阶段重点）：')||'').trim();if(!guidance)return;const r=await api('/api/novels/add_character_milestone',{method:'POST',body:JSON.stringify({mode,book_id:bookId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_5',revision_mode:'instruction',payload_text:'',guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:'步骤5 增加角色发展线',pending_message:'新增角色发展线任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleCharacterByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const r=await api('/api/novels/revise_single_character_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance:extra};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤3 单角色指令修改（角色 ${index+1}）`,pending_message:`角色 ${index+1} 指令修改任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleMilestoneByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色发展线如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_5',stepPayloadFromBook(currentBook,'step_5'));const r=await api('/api/novels/revise_single_character_milestone_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_5',revision_mode:'instruction',payload_text,guidance:extra};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤5 单角色发展线指令调整（角色 ${index+1}）`,pending_message:`角色 ${index+1} 发展线指令调整任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function saveSingleChapterBrief(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];if(index<0||index>=plans.length)return alert('章节索引无效。');await saveStepDraft('step_8');}
async function reviseSingleChapterBriefByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];const target=plans[index]||{};const chapterId=String(target?.chapter_id||'').trim()||`第${index+1}章`;const chapterTitle=String(target?.title||'').trim();const extra=prompt(`描述你希望如何调整 ${chapterTitle?`《${chapterTitle}》`:chapterId} 的章节摘要：`);if(!extra)return;const payload_text=getStepPayloadText('step_8',step8);const guidance=`只调整 chapter_briefs 中第 ${index+1} 条（chapter_id=${chapterId}${chapterTitle?`, title=${chapterTitle}`:''}），其他章节保持不变。\n用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_8',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_8',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤8 单章指令调整（第 ${index+1} 章）`,pending_message:`第 ${index+1} 章指令调整任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
function deleteSingleChapterBrief(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];if(index<0||index>=plans.length)return alert('章节索引无效。');const target=plans[index]||{};const label=String(target?.title||target?.chapter_id||`第${index+1}章`);if(!confirm(`确认删除章节摘要：${label}？`))return;const draft=ensureStepObject('step_8',step8);if(!Array.isArray(draft.chapter_briefs))draft.chapter_briefs=[];draft.chapter_briefs.splice(index,1);stepDraftObjects['step_8']=draft;stepDrafts['step_8']=JSON.stringify(draft,null,2);stepDraftDirty['step_8']=true;if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function toggleButtons(){const t=mode==='test';btnNew.style.display=t?'none':'inline-block';btnStep1.style.display=t?'none':'inline-block';btnStep2.style.display=t?'none':'inline-block';btnStep3.style.display=t?'none':'inline-block';btnStep4.style.display=t?'none':'inline-block';btnStep5.style.display=t?'none':'inline-block';btnStep6.style.display=t?'none':'inline-block';btnStep7.style.display=t?'none':'inline-block';btnStep8.style.display=t?'none':'inline-block';btnBlueprintReview.style.display=t?'none':'inline-block';btnContinue.style.display=t?'none':'inline-block';btnBlueprint.style.display=t?'inline-block':'none';btnWrite.style.display=t?'inline-block':'none';btnCritique.style.display=t?'inline-block':'none';btnPatch.style.display=t?'inline-block':'none';}
function updateStopButton(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);btnStop.style.display=a?'inline-block':'none';}
async function loadNovels(){const novels=await api('/api/novels?mode='+mode);novelSel.innerHTML="<option value=''>选择小说</option>";novels.forEach(n=>{const o=document.createElement('option');o.value=n.book_id;o.textContent=n.title||n.book_id;novelSel.appendChild(o);});if(bookId)novelSel.value=bookId;}
async function loadRuns(){if(!bookId){runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];return renderRuns();}runsCache=await api(`/api/runs?mode=${mode}&book_id=${bookId}`);const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();}
function renderEmptyRightPanels(){document.getElementById('pnl-input').innerHTML="<div class='empty'>等待加载用户输入</div>";document.getElementById('pnl-blueprint').innerHTML="<div class='empty'>等待加载小说信息</div>";document.getElementById('pnl-text').innerHTML="<div class='empty'>等待加载小说正文</div>";document.getElementById('pnl-critic').innerHTML="<div class='empty'>等待加载评价结果</div>";showTab('input');}
async function changeMode(){mode=modeSel.value;bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();boxStates={};lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};resetStepDraftCache('');evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';toggleButtons();updateStopButton();await loadNovels();}
async function selectNovel(id){bookId=id;currentBook=null;pendingRunId='';pendingStepRevision=null;expandedRuns=new Set();boxStates={};lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};resetStepDraftCache(id||'');if(!bookId){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';updateStopButton();return;}await refreshNovel();}
async function refreshNovel(){if(!bookId)return;const d=await api(`/api/novel?mode=${mode}&book_id=${bookId}`);if(!d.book)return;if(stepDraftBookId!==d.book.id)resetStepDraftCache(d.book.id);const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);const scrollState=captureScrollState();currentBook=d.book;lastLivePreviewKey='';const rightRenderKey=[String(d.book?.id||''),String(d.book?.updated_at||''),String(d.latest_run_id||''),String(d.latest_stage||''),String(d.critic?.report_id||d.critic?.created_at||''),String(d.blueprint_review?.summary||'')].join('|');if(!editingInRight&&rightRenderKey!==lastRightRenderKey){snapshotPanelDetailStates('pnl-input');snapshotPanelDetailStates('pnl-blueprint');snapshotPanelDetailStates('pnl-text');snapshotPanelDetailStates('pnl-critic');renderInputPanel(d.book);renderBlueprint(d.book,d.blueprint_review);renderText(d.book,null);renderCritic(d.critic);lastRightRenderKey=rightRenderKey;}stagePill.textContent=stageText(d.latest_stage);runsCache=d.runs||[];const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();await loadNovels();restoreScrollState(scrollState);}
async function refreshPendingRun(){if(!pendingRunId)return;const trackedRunId=pendingRunId;const prev=runsCache.find(x=>x.run_id===trackedRunId)||{};const d=await api(`/api/run?mode=${mode}&run_id=${trackedRunId}`);const scrollState=captureScrollState();const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);stagePill.textContent=stageText(d.stage||'writing');const running=d.is_running!==false;if(running){runsCache=[{run_id:trackedRunId,is_running:true,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),task_label:prev.task_label||'',pending_message:'运行中，等待模型返回更多内容。'},...runsCache.filter(x=>x.run_id!==trackedRunId)];expandedRuns.add(trackedRunId);if(currentBook&&d.chapter_preview){const previewKey=JSON.stringify(d.chapter_preview||null);if(!editingInRight&&previewKey!==lastLivePreviewKey){snapshotPanelDetailStates('pnl-text');renderText(currentBook,d.chapter_preview,d);lastLivePreviewKey=previewKey;}}await renderRuns({[trackedRunId]:d});updateStopButton();restoreScrollState(scrollState);return;}let revisionPayload=latestOutputByType(d,'step_revision_draft');const completedRevision=pendingStepRevision&&pendingStepRevision.run_id===trackedRunId?pendingStepRevision:null;pendingRunId='';pendingStepRevision=null;lastLivePreviewKey='';delete runActiveItemKeys[trackedRunId];if(!revisionPayload&&completedRevision&&completedRevision.step_key&&completedRevision.payload_text){const fallback=await api('/api/novels/revise_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:completedRevision.step_key,payload_text:completedRevision.payload_text,revision_mode:completedRevision.revision_mode||'instruction',guidance:completedRevision.guidance||''})});if(ensureOk(fallback)){revisionPayload=fallback;}}if(revisionPayload)applyStepRevisionDraft(revisionPayload);if(d.current_book_id){bookId=d.current_book_id;novelSel.value=bookId;await refreshNovel();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}return;}runsCache=[{run_id:trackedRunId,is_running:false,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),task_label:prev.task_label||'',pending_message:'运行已结束，查看下方最新事件。'}];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();restoreScrollState(scrollState);if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}}
function boxHtml(key,title,payloadHtml,isOpen,extraClass=''){const klass=['box',extraClass].filter(Boolean).join(' ');return `<details class='${klass}' ${isOpen?'open':''} ontoggle="toggleBox('${key}', this.open)"><summary><span class='title'>${title}</span></summary><div class='payload'>${payloadHtml}</div></details>`}
function toggleBox(key,isOpen){boxStates[key]=isOpen;}
const toArray=v=>Array.isArray(v)?v.filter(Boolean):[];
const jsonHtml=v=>`<div class='pre json'>${esc(JSON.stringify(v??{},null,2))}</div>`;
const chipsHtml=v=>{const items=toArray(v);return items.length?`<div class='chips'>${items.map(item=>`<span class='chip'>${esc(item)}</span>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
const linesHtml=v=>{const items=toArray(v);return items.length?`<div class='mini-list'>${items.map(item=>`<div class='mini-item'>${esc(item)}</div>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
function infoRow(label,value){if(value===undefined||value===null||value==='')return '';return `<div class='kv'><div class='k'>${esc(label)}</div><div>${esc(value)}</div></div>`}
function sectionHtml(label,body){return `<div class='subsec'>${esc(label)}</div>${body}`}
function renderBlockCards(blocks,options={}){
  const arr=Array.isArray(blocks)?blocks:[];
  const label=String(options?.label||'内容块');
  const highlightSet=new Set((Array.isArray(options?.highlightIds)?options.highlightIds:[]).map(item=>String(item||'').trim()).filter(Boolean));
  return arr.map((block,index)=>{
    const purpose=String(block?.purpose||'').trim();
    const blockId=String(block?.block_id||block?.id||'').trim();
    const endState=String(block?.end_state||block?.metadata?.end_state||'').trim();
    const status=String(block?.status||block?.metadata?.status||'').trim();
    const version=Number(block?.version||block?.metadata?.version||1);
    const blockIndex=Number(block?.block_index||index+1);
    const isPatched=highlightSet.has(blockId);
    const metaBits=[purpose,blockId].filter(Boolean).join(' · ');
    const badges=[];
    if(isPatched)badges.push("<span class='block-badge patched'>本轮已更新</span>");
    if(status)badges.push(`<span class='block-badge status'>${esc(status)}</span>`);
    if(Number.isFinite(version))badges.push(`<span class='block-badge status'>v${Number(version)}</span>`);
    return `<div class='block ${isPatched?'patched':''}'><div class='row'><strong>${esc(label)} ${blockIndex}</strong>${metaBits?` <span class='muted'>${esc(metaBits)}</span>`:''}</div>${endState?`<div class='muted' style='margin-top:4px'>落点：${esc(endState)}</div>`:''}${badges.length?`<div class='block-badges'>${badges.join('')}</div>`:''}<div style='margin-top:6px'>${esc(block?.text||'')}</div></div>`;
  }).join('')||"<div class='relationship-empty'>暂无内容块</div>";
}
function renderCharacterMindsetsBlock(characterMindsets){
  const items=(Array.isArray(characterMindsets)?characterMindsets:[]).filter(item=>item&&typeof item==='object');
  if(!items.length)return '';
  const renderAttitudes=(attitudes)=>{
    const rows=Object.entries(attitudes&&typeof attitudes==='object'?attitudes:{}).filter(([key,value])=>String(key||'').trim()&&String(value||'').trim());
    return rows.length
      ? `<div class='mini-list'>${rows.map(([key,value])=>`<div class='mini-item'><strong>${esc(key)}</strong>：${esc(value)}</div>`).join('')}</div>`
      : "<div class='relationship-empty'>暂无关键他人态度</div>";
  };
  const cards=items.map((item,index)=>{
    const title=String(item?.character_name||item?.character_id||`角色 ${index+1}`).trim()||`角色 ${index+1}`;
    const emotionSummary=[String(item?.surface_emotion||'').trim(),String(item?.core_emotion||'').trim()].filter(Boolean).join(' / ')||'暂无情绪摘要';
    return `<div style='border:1px solid #2a3447;border-radius:12px;padding:12px;background:#0d1420'>
      <div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'>
        <div>
          <div class='subsec'>${esc(title)}</div>
          <div class='muted'>${esc(emotionSummary)}</div>
        </div>
        <span class='block-badge status'>${esc(item?.self_control_level||'medium')}</span>
      </div>
      ${infoRow('表层情绪', item?.surface_emotion||'')}
      ${infoRow('核心情绪', item?.core_emotion||'')}
      ${infoRow('主要目标', item?.primary_goal||'')}
      ${infoRow('隐藏需求', item?.hidden_need||'')}
      ${infoRow('恐惧', item?.fear||'')}
      ${infoRow('临界点提示', item?.breaking_point_hint||'')}
      ${infoRow('知道但未说', item?.known_but_unspoken||'')}
      ${infoRow('误判', item?.misbelief||'')}
      ${infoRow('本章变化提示', item?.chapter_change_hint||'')}
      <div class='subsec' style='margin-top:10px'>关键他人态度</div>
      ${renderAttitudes(item?.attitude_to_key_others)}
    </div>`;
  }).join('');
  return `<div class='relationship-card'><div class='subsec'>角色心智</div><div class='task-note'>仅维护本章前两个角色的章节心智，和章节本身绑定展示。</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:12px'>${cards}</div></div>`;
}
function renderChapterDraftTask(payload){
  const preview=payload?.draft_preview&&typeof payload.draft_preview==='object'?payload.draft_preview:{};
  const finalText=String(preview?.final_text||'').trim();
  const contentBlocks=Array.isArray(preview?.content_blocks)?preview.content_blocks:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||preview?.chapter_id||'');
  html+=infoRow('阶段', '整章首稿');
  if(finalText)html+=sectionHtml('整章手稿', `<div class='subbox pre'>${esc(finalText)}</div>`);
  if(contentBlocks.length)html+=sectionHtml('首稿 block 视图', `<div class='mini-list'>${renderBlockCards(contentBlocks,{label:'内容块'})}</div>`);
  html+="</div>";
  return html;
}
function renderChapterReviewBundle(payload){
  const reviews=Array.isArray(payload?.reviews)?payload.reviews:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(!reviews.length){html+="<div class='muted'>暂无 review 输出</div></div>";return html;}
  html+=sectionHtml('Review 输出', `<div class='mini-list'>${reviews.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.tool_name||'review')}</div>${reviewReportSummaryHtml(String(item?.tool_name||'review'),item?.tool_result||{})}<div style='margin-top:8px'>${jsonHtml(item?.tool_result||{})}</div></div>`).join('')}</div>`);
  html+="</div>";
  return html;
}
function renderChapterPatchPlanTask(payload){
  const patchPlan=payload?.patch_plan&&typeof payload.patch_plan==='object'?payload.patch_plan:{};
  const patchTargets=Array.isArray(patchPlan?.patch_targets)?patchPlan.patch_targets:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=sectionHtml('Patch 目标', patchTargets.length?`<div class='mini-list'>${patchTargets.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.target_id||'未命中 block')}</div>${infoRow('问题类型', item?.problem_type||'')}${infoRow('修补目标', item?.goal||'')}${toArray(item?.instructions).length?sectionHtml('执行指令', linesHtml(item.instructions)):''}${toArray(item?.local_context_needed).length?sectionHtml('局部上下文', chipsHtml(item.local_context_needed)):''}</div>`).join('')}</div>`:"<div class='muted'>暂无 patch 目标</div>");
  if(toArray(patchPlan?.unchanged_blocks).length)html+=sectionHtml('保持不动的 block', chipsHtml(patchPlan.unchanged_blocks));
  if(toArray(patchPlan?.global_constraints).length)html+=sectionHtml('全局约束', linesHtml(patchPlan.global_constraints));
  html+="</div>";
  return html;
}
function renderChapterPatchRewriteTask(payload){
  const rewriteResult=payload?.rewrite_result&&typeof payload.rewrite_result==='object'?payload.rewrite_result:{};
  const patchedBlocks=Array.isArray(rewriteResult?.patched_blocks)?rewriteResult.patched_blocks:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=sectionHtml('修改后的 block', patchedBlocks.length?`<div class='mini-list'>${patchedBlocks.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.block_id||'未命名 block')}</div>${item?.old_summary?infoRow('修改前摘要', item.old_summary):''}<div class='subbox pre'>${esc(item?.new_text||'')}</div></div>`).join('')}</div>`:"<div class='muted'>暂无 block 改写结果</div>");
  if(toArray(rewriteResult?.patch_report).length)html+=sectionHtml('Patch 报告', `<div class='mini-list'>${rewriteResult.patch_report.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.block_id||'未命名 block')}</div>${infoRow('是否应用', item?.applied?'是':'否')}${infoRow('说明', item?.notes||'')}</div>`).join('')}</div>`);
  if(String(rewriteResult?.merged_chapter_text||'').trim())html+=sectionHtml('当前拼接正文', `<div class='subbox pre'>${esc(rewriteResult.merged_chapter_text)}</div>`);
  html+="</div>";
  return html;
}
function renderChapterPatchJudgeTask(payload){
  const judgeResult=payload?.judge_result&&typeof payload.judge_result==='object'?payload.judge_result:{};
  const finalJudge=payload?.final_judge&&typeof payload.final_judge==='object'?payload.final_judge:{};
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=infoRow('Judge 结论', judgeResult?.pass||judgeResult?.passed?'通过':'未通过');
  if(toArray(judgeResult?.remaining_issues).length)html+=sectionHtml('未修干净的问题', `<div class='mini-list'>${judgeResult.remaining_issues.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.problem_type||'问题')}</div>${toArray(item?.target_blocks).length?sectionHtml('命中 block', chipsHtml(item.target_blocks)):''}${infoRow('原因', item?.reason||'')}</div>`).join('')}</div>`);
  if(toArray(judgeResult?.newly_introduced_issues).length)html+=sectionHtml('新引入的问题', `<div class='mini-list'>${judgeResult.newly_introduced_issues.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.problem_type||'问题')}</div>${toArray(item?.target_blocks).length?sectionHtml('命中 block', chipsHtml(item.target_blocks)):''}${infoRow('原因', item?.reason||'')}</div>`).join('')}</div>`);
  if(judgeResult?.recommendation)html+=sectionHtml('建议', `<div class='task-note'>${esc(judgeResult.recommendation)}</div>`);
  if(finalJudge&&Object.keys(finalJudge).length)html+=sectionHtml('闭环判断', jsonHtml(finalJudge));
  html+="</div>";
  return html;
}
function renderDirectorDecision(payload){
  const infoGaps=toArray(payload&&payload.info_gaps);
  const toolInput=payload&&typeof payload.tool_input==='object'&&payload.tool_input?payload.tool_input:{};
  const query=toolInput.query||'';
  const stage=toolInput.stage||'';
  const focus=toArray(toolInput.focus);
  const tags=toArray(toolInput.tags);
  const extras=Object.entries(toolInput).filter(([key])=>!['query','stage','focus','tags'].includes(key));
  let html="<div class='agent-view'>";
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('理由', payload&&payload.reasoning||'');
  if(stage)html+=infoRow('阶段', stage);
  if(query)html+=infoRow('查询', query);
  if(focus.length)html+=sectionHtml('焦点', chipsHtml(focus));
  if(tags.length)html+=sectionHtml('标签', chipsHtml(tags));
  if(infoGaps.length)html+=sectionHtml('信息缺口', linesHtml(infoGaps));
  if(extras.length)html+=sectionHtml('其他', jsonHtml(Object.fromEntries(extras)));
  html+="</div>";
  return html;
}
function renderReferenceCards(payload){
  const cards=toArray(payload&&payload.cards);
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('查询', payload&&payload.query||'');
  const focus=toArray(payload&&payload.focus);
  const tags=toArray(payload&&payload.tags);
  if(focus.length)html+=sectionHtml('关注点', chipsHtml(focus));
  if(tags.length)html+=sectionHtml('筛选标签', chipsHtml(tags));
  if(cards.length){
    html+=sectionHtml('参考卡片', `<div class='mini-list'>${cards.map(card=>`<div class='mini-item'><div class='mini-title'>${esc(card.title||card.card_id||'未命名')}</div><div class='muted'>${esc(card.summary||'')}</div>${toArray(card.tags).length?`<div style='margin-top:6px'>${chipsHtml(card.tags.slice(0,5))}</div>`:''}</div>`).join('')}</div>`);
  }else{
    html+=sectionHtml('参考卡片', "<div class='muted'>暂无卡片</div>");
  }
  if(payload&&payload.reference_pack)html+=sectionHtml('参考 Prompt 包', `<div class='subbox pre'>${esc(payload.reference_pack)}</div>`);
  html+="</div>";
  return html;
}
function renderToolObservation(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('工具', payload&&payload.tool_name||'');
  html+=infoRow('摘要', payload&&payload.summary||'');
  if(payload&&payload.payload&&Object.keys(payload.payload).length)html+=sectionHtml('详情', jsonHtml(payload.payload));
  html+="</div>";
  return html;
}
function reviewReportSummaryHtml(toolName,report){
  if(!report||typeof report!=='object')return "<div class='muted'>暂无结果</div>";
  const level=String(report.level||'').trim();
  const issues=toArray(report.issues);
  const metrics=[];
  if(typeof report.passed==='boolean')metrics.push(`passed=${report.passed?'yes':'no'}`);
  if(level)metrics.push(`level=${level}`);
  if(Number.isFinite(Number(report.prose_score)))metrics.push(`prose=${Number(report.prose_score)}`);
  if(Number.isFinite(Number(report.tension_score)))metrics.push(`tension=${Number(report.tension_score)}`);
  if(Number.isFinite(Number(report.exposition_score)))metrics.push(`exposition=${Number(report.exposition_score)}`);
  let html=`<div class='mini-item'><div class='mini-title'>${esc(toolName)}</div>`;
  if(metrics.length)html+=`<div class='muted'>${esc(metrics.join(' | '))}</div>`;
  if(issues.length)html+=`<div style='margin-top:6px'>${linesHtml(issues.slice(0,6))}</div>`;
  if(report.rewrite_guidance)html+=`<div class='subbox pre' style='margin-top:6px'>${esc(report.rewrite_guidance)}</div>`;
  html+='</div>';
  return html;
}
function renderActualChapterSummary(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload&&payload.chapter_id||'');
  html+=sectionHtml('实际发生', linesHtml(payload&&payload.actual_events));
  html+=sectionHtml('读者现在知道', linesHtml(payload&&payload.reader_now_knows));
  html+=sectionHtml('读者现在相信', linesHtml(payload&&payload.reader_now_believes));
  html+=sectionHtml('未解问题', linesHtml(payload&&payload.open_questions));
  html+=sectionHtml('角色状态', linesHtml(payload&&payload.character_states));
  html+=sectionHtml('关系状态', linesHtml(payload&&payload.relationship_state));
  html+=sectionHtml('已埋线索', linesHtml(payload&&payload.seeded_clues));
  html+=sectionHtml('仍锁住的真相', linesHtml(payload&&payload.locked_truths));
  html+="</div>";
  return html;
}
function renderChapterStageLog(payload){
  const chapterId=String(payload&&payload.chapter_id||'').trim();
  const stages=toArray(payload&&payload.stage_log);
  let html="<div class='agent-view'>";
  if(chapterId)html+=infoRow('章节', chapterId);
  if(!stages.length){html+="<div class='muted'>暂无 stage log</div></div>";return html;}
  html+=sectionHtml('正文闭环', `<div class='mini-list'>${stages.map((entry,index)=>{
    const stageName=String(entry&&entry.stage||`stage_${index+1}`);
    const skills=toArray(entry&&entry.skill_ids);
    const toolCalls=toArray(entry&&entry.tool_calls).map(item=>typeof item==='string'?item:String(item&&item.tool_name||'').trim()).filter(Boolean);
    const reviewReports=(entry&&typeof entry.review_reports==='object'&&entry.review_reports)?entry.review_reports:{};
    const finalJudge=(entry&&typeof entry.final_judge==='object'&&entry.final_judge)?entry.final_judge:null;
    const revisionPlan=(entry&&typeof entry.revision_plan==='object'&&entry.revision_plan)?entry.revision_plan:null;
    let block=`<div class='mini-item'><div class='mini-title'>WritingChapterAgent · ${esc(stageName)}</div>`;
    if(skills.length)block+=`<div style='margin-top:6px'>${chipsHtml(skills)}</div>`;
    if(toolCalls.length)block+=sectionHtml('Tool 调用', chipsHtml(toolCalls));
    if(Number.isFinite(Number(entry&&entry.chapter_length)))block+=infoRow('正文长度', `${Number(entry.chapter_length)} 字符`);
    if(entry&&entry.current_chapter_draft_tail)block+=sectionHtml('当前草稿尾部', `<div class='subbox pre'>${esc(entry.current_chapter_draft_tail)}</div>`);
    const reportEntries=Object.entries(reviewReports);
    if(reportEntries.length)block+=sectionHtml('Tool 输出', `<div class='mini-list'>${reportEntries.map(([toolName,report])=>reviewReportSummaryHtml(toolName,report)).join('')}</div>`);
    if(revisionPlan){
      block+=sectionHtml('修订计划', `<div class='mini-list'>${[
        revisionPlan.summary?`<div class='mini-item'><div class='mini-title'>摘要</div><div class='muted'>${esc(revisionPlan.summary)}</div></div>`:'',
        toArray(revisionPlan.must_fix).length?`<div class='mini-item'><div class='mini-title'>必须修</div>${linesHtml(revisionPlan.must_fix)}</div>`:'',
        toArray(revisionPlan.should_fix).length?`<div class='mini-item'><div class='mini-title'>建议修</div>${linesHtml(revisionPlan.should_fix)}</div>`:'',
        toArray(revisionPlan.keep).length?`<div class='mini-item'><div class='mini-title'>保留</div>${linesHtml(revisionPlan.keep)}</div>`:'',
        toArray(revisionPlan.hard_constraints).length?`<div class='mini-item'><div class='mini-title'>硬约束</div>${linesHtml(revisionPlan.hard_constraints)}</div>`:''
      ].filter(Boolean).join('')}</div>`);
    }
    if(finalJudge){
      const reasons=toArray(finalJudge.blocking_reasons);
      const metrics=finalJudge.metrics&&typeof finalJudge.metrics==='object'?finalJudge.metrics:{};
      block+=sectionHtml('Final Judge', `<div class='mini-list'>${[
        `<div class='mini-item'><div class='mini-title'>结论</div><div class='muted'>${esc(finalJudge.passed?'通过':'未通过')}</div></div>`,
        reasons.length?`<div class='mini-item'><div class='mini-title'>阻塞原因</div>${linesHtml(reasons)}</div>`:'',
        Object.keys(metrics).length?`<div class='mini-item'><div class='mini-title'>指标</div>${jsonHtml(metrics)}</div>`:''
      ].filter(Boolean).join('')}</div>`);
    }
    block+='</div>';
    return block;
  }).join('')}</div>`);
  html+="</div>";
  return html;
}
function renderStageEvent(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('原因', payload&&payload.reason||'');
  if(payload&&payload.chapter_id)html+=infoRow('章节', payload.chapter_id);
  if(Number.isFinite(Number(payload&&payload.iteration)))html+=infoRow('轮次', `第 ${Number(payload.iteration)} 轮`);
  const contextKeys=toArray(payload&&payload.context_keys);
  const skillIds=toArray(payload&&payload.skill_ids);
  const toolCalls=toArray(payload&&payload.tool_calls).map(item=>typeof item==='string'?item:String(item&&item.tool_name||'').trim()).filter(Boolean);
  if(contextKeys.length)html+=sectionHtml('固定信息包', chipsHtml(contextKeys));
  if(skillIds.length)html+=sectionHtml('已加载 Skills', chipsHtml(skillIds));
  if(toolCalls.length)html+=sectionHtml('计划调用 Tools', chipsHtml(toolCalls));
  if(payload&&payload.tool_name)html+=infoRow('当前 Tool', payload.tool_name);
  if(Number.isFinite(Number(payload&&payload.chapter_length)))html+=infoRow('正文长度', `${Number(payload.chapter_length)} 字符`);
  if(payload&&payload.current_chapter_draft_tail)html+=sectionHtml('当前草稿尾部', `<div class='subbox pre'>${esc(payload.current_chapter_draft_tail)}</div>`);
  const toolResult=payload&&payload.tool_result&&typeof payload.tool_result==='object'?payload.tool_result:null;
  if(toolResult){
    html+=sectionHtml('Tool 输出', reviewReportSummaryHtml(String(payload&&payload.tool_name||'tool'), toolResult));
    html+=sectionHtml('Tool 输出详情', jsonHtml(toolResult));
  }
  const reviewReports=payload&&payload.review_reports&&typeof payload.review_reports==='object'?payload.review_reports:null;
  if(reviewReports&&Object.keys(reviewReports).length){
    html+=sectionHtml('本轮 Review 汇总', `<div class='mini-list'>${Object.entries(reviewReports).map(([toolName,report])=>reviewReportSummaryHtml(toolName,report)).join('')}</div>`);
  }
  const revisionPlan=payload&&payload.revision_plan&&typeof payload.revision_plan==='object'?payload.revision_plan:null;
  if(revisionPlan){
    html+=sectionHtml('修订计划', `<div class='mini-list'>${[
      revisionPlan.summary?`<div class='mini-item'><div class='mini-title'>摘要</div><div class='muted'>${esc(revisionPlan.summary)}</div></div>`:'',
      toArray(revisionPlan.must_fix).length?`<div class='mini-item'><div class='mini-title'>必须修</div>${linesHtml(revisionPlan.must_fix)}</div>`:'',
      toArray(revisionPlan.should_fix).length?`<div class='mini-item'><div class='mini-title'>建议修</div>${linesHtml(revisionPlan.should_fix)}</div>`:'',
      toArray(revisionPlan.keep).length?`<div class='mini-item'><div class='mini-title'>保留</div>${linesHtml(revisionPlan.keep)}</div>`:'',
      toArray(revisionPlan.hard_constraints).length?`<div class='mini-item'><div class='mini-title'>硬约束</div>${linesHtml(revisionPlan.hard_constraints)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  const finalJudge=payload&&payload.final_judge&&typeof payload.final_judge==='object'?payload.final_judge:null;
  if(finalJudge){
    const reasons=toArray(finalJudge.blocking_reasons);
    const metrics=finalJudge.metrics&&typeof finalJudge.metrics==='object'?finalJudge.metrics:{};
    html+=sectionHtml('Final Judge', `<div class='mini-list'>${[
      `<div class='mini-item'><div class='mini-title'>结论</div><div class='muted'>${esc(finalJudge.passed?'通过':'未通过')}</div></div>`,
      reasons.length?`<div class='mini-item'><div class='mini-title'>阻塞原因</div>${linesHtml(reasons)}</div>`:'',
      Object.keys(metrics).length?`<div class='mini-item'><div class='mini-title'>指标</div>${jsonHtml(metrics)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  const summary=payload&&payload.summary&&typeof payload.summary==='object'?payload.summary:null;
  if(summary){
    html+=sectionHtml('Actual Summary', `<div class='mini-list'>${[
      toArray(summary.actual_events).length?`<div class='mini-item'><div class='mini-title'>实际发生</div>${linesHtml(summary.actual_events)}</div>`:'',
      toArray(summary.reader_now_knows).length?`<div class='mini-item'><div class='mini-title'>读者现在知道</div>${linesHtml(summary.reader_now_knows)}</div>`:'',
      toArray(summary.reader_now_believes).length?`<div class='mini-item'><div class='mini-title'>读者现在相信</div>${linesHtml(summary.reader_now_believes)}</div>`:'',
      toArray(summary.seeded_clues).length?`<div class='mini-item'><div class='mini-title'>已埋线索</div>${linesHtml(summary.seeded_clues)}</div>`:'',
      toArray(summary.locked_truths).length?`<div class='mini-item'><div class='mini-title'>仍锁住的真相</div>${linesHtml(summary.locked_truths)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  html+="</div>";
  return html;
}
function renderErrorEvent(payload){
  return `<div class='agent-view'>${infoRow('错误', payload&&payload.error||'未知错误')}</div>`;
}
function clipDisplayText(text,maxChars){
  const raw=String(text||'');
  if(!raw)return '';
  if(raw.length<=maxChars)return raw;
  return `[内容较长，仅展示最近 ${maxChars} 字]\\n${raw.slice(-maxChars)}`;
}
function mergeStreamText(current,incoming){
  const prev=String(current||''),next=String(incoming||'');
  if(!next)return prev;
  if(!prev)return next;
  if(next.startsWith(prev))return next;
  if(prev.endsWith(next))return prev;
  return prev+next;
}
function summarizeStreamPrompt(prompt){
  const cleaned=String(prompt||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').trim();
  if(!cleaned)return '';
  return cleaned.length>160?`${cleaned.slice(0,160)}…`:cleaned;
}
function renderEmbeddedStreams(streamGroups){
  const groups=Array.isArray(streamGroups)?streamGroups.filter(Boolean):[];
  if(!groups.length)return '';
  return `<div class='stream-shell'>${groups.map((group,index)=>{
    const streamTitle=esc(group.agent||`模型调用 ${index+1}`);
    const streamStatus=group.done?'已完成':'流式输出中';
    const promptSummary=summarizeStreamPrompt(group.prompt||'');
    const streamText=clipDisplayText(group.displayText||group.reply||group.text||'',18000);
    return `<div class='stream-card ${group.done?'':'live'}'><div class='stream-meta'><div class='stream-title'>${streamTitle}</div><div class='stream-status'>${esc(streamStatus)}</div></div>${promptSummary?`<div class='stream-prompt'>${esc(promptSummary)}</div>`:''}${streamText?`<div class='stream-text'>${esc(streamText)}</div>`:`<div class='muted'>流式输出暂未返回内容</div>`}</div>`;
  }).join('')}</div>`;
}
function renderItemPayload(item){
  const streamHtml=renderEmbeddedStreams(item.streamGroups);
  let body='';
  if(item.kind==='output'&&item.outputType==='chapter_draft_task')body=renderChapterDraftTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_review_bundle')body=renderChapterReviewBundle(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_plan_task')body=renderChapterPatchPlanTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_rewrite_task')body=renderChapterPatchRewriteTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_judge_task')body=renderChapterPatchJudgeTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='director_decision')body=renderDirectorDecision(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='reference_cards')body=renderReferenceCards(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='tool_observation')body=renderToolObservation(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='actual_chapter_summary')body=renderActualChapterSummary(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_stage_log')body=renderChapterStageLog(item.rawPayload);
  else if(item.kind==='event'&&item.eventType==='stage')body=renderStageEvent(item.rawPayload);
  else if(item.kind==='event'&&item.eventType==='error')body=renderErrorEvent(item.rawPayload);
  else if(item.kind==='plain'&&item.text)body=`<div class='pre'>${esc(item.text||'')}</div>`;
  else if(item.streamOnly)body='';
  else body=jsonHtml(item.rawPayload);
  if(item.streamOnly)return streamHtml||"<div class='muted'>等待模型返回内容</div>";
  return `${streamHtml}${body}`;
}
function sortTimelineItems(items){
  return items.sort((a,b)=>{
    const ta=String(a?.sortTs||''),tb=String(b?.sortTs||'');
    if(ta===tb)return String(a?.key||'').localeCompare(String(b?.key||''));
    return ta.localeCompare(tb);
  });
}
function setRefreshPaused(paused,reason=''){refreshPaused=paused;refreshPauseReason=paused?reason:'';if(refreshPauseTimer){clearTimeout(refreshPauseTimer);refreshPauseTimer=null;}}
function pauseRefreshFor(ms,reason=''){setRefreshPaused(true,reason);refreshPauseTimer=setTimeout(()=>{if(!isMouseSelecting)setRefreshPaused(false,'');},ms);}
function isEditingElement(el){return !!(el&&(el.tagName==='TEXTAREA'||el.tagName==='INPUT'||el.isContentEditable));}
function hasUserSelection(){const sel=window.getSelection&&window.getSelection();return !!(sel&&String(sel).trim().length);}
document.addEventListener('mousedown',()=>{isMouseSelecting=true;setRefreshPaused(true,'selecting');});
document.addEventListener('mouseup',()=>{isMouseSelecting=false;if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isEditingElement(document.activeElement))setRefreshPaused(false,'');});
document.addEventListener('selectionchange',()=>{if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isMouseSelecting&&!isEditingElement(document.activeElement)&&refreshPauseReason==='selection')setRefreshPaused(false,'');});
document.addEventListener('focusin',event=>{if(isEditingElement(event.target))setRefreshPaused(true,'editing');});
document.addEventListener('focusout',event=>{if(isEditingElement(event.target)){setTimeout(()=>{if(!hasUserSelection()&&!isEditingElement(document.activeElement)&&!isMouseSelecting)setRefreshPaused(false,'');},0);}});
function collectStreamGroups(evts){
  const groups=[],byId={};let activeKey='',seq=0;
  function ensureGroup(callId,ts,agent){
    const key=callId||`legacy_${++seq}`;
    if(byId[key]){if(agent&&!byId[key].agent)byId[key].agent=agent;return byId[key];}
    const group={groupKey:key,prompt:'',text:'',reply:'',displayText:'',sortTs:ts||'',done:false,agent:agent||''};
    byId[key]=group;groups.push(group);return group;
  }
  evts.forEach(e=>{
    const payload=e.payload||{};
    const callId=String(payload.call_id||'').trim();
    if(e.event_type==='llm_prompt'){
      const group=ensureGroup(callId||`prompt_${e.id||++seq}`,e.ts,e.agent);
      group.prompt=String(payload.preview||'');
      group.sortTs=e.ts||group.sortTs;
      if(e.agent&&!group.agent)group.agent=e.agent;
      activeKey=group.groupKey;
      return;
    }
    if(e.event_type==='llm_stream'){
      const group=callId?ensureGroup(callId,e.ts,e.agent):(activeKey&&byId[activeKey]&&!byId[activeKey].done?byId[activeKey]:ensureGroup(`stream_${e.id||++seq}`,e.ts,e.agent));
      group.text=mergeStreamText(group.text,payload.preview||'');
      group.displayText=group.text||group.displayText;
      group.sortTs=e.ts||group.sortTs;
      if(e.agent&&!group.agent)group.agent=e.agent;
      activeKey=group.groupKey;
      return;
    }
    if(e.event_type==='llm_reply'){
      const group=callId?ensureGroup(callId,e.ts,e.agent):(activeKey?byId[activeKey]:null);
      if(group){
        group.reply=mergeStreamText(group.reply,payload.preview||'');
        if(!group.text&&group.reply)group.displayText=group.reply;
        group.done=true;
        group.sortTs=e.ts||group.sortTs;
        if(e.agent&&!group.agent)group.agent=e.agent;
        if(activeKey===group.groupKey)activeKey='';
      }
    }
  });
  return groups.filter(group=>group.displayText||group.reply||group.prompt).map(group=>({
    ...group,
    prompt:String(group.prompt||'').slice(0,800),
    displayText:clipDisplayText(group.displayText||group.reply||'',24000),
  }));
}
function attachStreamGroupsToItems(runId,items,streamGroups,fallbackTitle=''){
  const bound=items.map(item=>({...item,streamGroups:Array.isArray(item.streamGroups)?item.streamGroups.slice():[]}));
  let index=0;
  bound.forEach(item=>{
    while(index<streamGroups.length){
      const group=streamGroups[index];
      if(String(group.sortTs||'')<=String(item.sortTs||'')){
        item.streamGroups.push(group);
        index+=1;
        continue;
      }
      break;
    }
  });
  while(index<streamGroups.length){
    const group=streamGroups[index];
    bound.push({
      key:`${runId}:stream:${group.groupKey}`,
      title:esc(fallbackTitle?`${fallbackTitle} · 流式输出`:(group.agent||'模型流式输出')),
      kind:'plain',
      text:'',
      sortTs:group.sortTs||'',
      streamGroups:[group],
      streamOnly:true,
    });
    index+=1;
  }
  return sortTimelineItems(bound);
}
function findActiveRunItemKey(items){
  for(let i=items.length-1;i>=0;i-=1){
    const groups=Array.isArray(items[i]?.streamGroups)?items[i].streamGroups:[];
    if(groups.some(group=>!group.done))return String(items[i].key||'');
  }
  return '';
}
function syncActiveRunCard(runId,activeKey){
  const prevKey=String(runActiveItemKeys[runId]||'');
  if(prevKey&&prevKey!==activeKey)boxStates[prevKey]=false;
  if(activeKey&&prevKey!==activeKey)boxStates[activeKey]=true;
  if(activeKey)runActiveItemKeys[runId]=activeKey;
  else delete runActiveItemKeys[runId];
}
function outputTaskLabel(out){const t=String(out?.output_type||'');if(t==='outline_blueprint')return'步骤1 大纲+蓝图';if(t==='worldbuilding')return'步骤2 背景体系+世界观';if(t==='character_bible')return'步骤3 角色卡';if(t==='character_added')return'步骤3 增加角色';if(t==='event_timeline')return'步骤4 客观事件时间线';if(t==='character_milestones')return'步骤5 角色发展线';if(t==='twist_designs')return'步骤6 反转设计';if(t==='story_lines')return'步骤7 明线暗线发展线';if(t==='chapter_briefs')return'步骤8 章节摘要规划';if(t==='step_revision_draft'){const p=out?.payload||{};const stepKey=String(p?.step_key||'');const idx=p?.character_index;if(stepKey==='step_3'&&Number.isInteger(idx))return`步骤3 单角色指令修改（角色 ${Number(idx)+1}）`;if(stepKey==='step_5'&&Number.isInteger(idx))return`步骤5 单角色发展线指令调整（角色 ${Number(idx)+1}）`;if(stepKey)return`${stepKey.toUpperCase()} 结果修订`;return'步骤结果修订';}if(t==='blueprint_review')return'Critic Blueprint 评审';if(t==='text_updated')return'正文AI修改';if(t==='chapter_blocks')return'正文 content blocks';if(t==='chapter_final_text')return'正文最终稿';if(t==='actual_chapter_summary')return'正文 actual summary';if(t==='chapter_stage_log')return'正文 agent 闭环';return'';}
function inferTaskLabel(run,detail){
  if(run?.task_label)return String(run.task_label);
  const ctx=detail?.context||{};
  const action=String(ctx?.action||'');
  const stepKey=String(ctx?.step_key||'');
  const revisionMode=String(ctx?.revision_mode||'');
  const idx=ctx?.character_index;
  const stepName=(key)=>({step_1:'步骤1 大纲+蓝图',step_2:'步骤2 背景体系+世界观',step_3:'步骤3 角色卡',step_4:'步骤4 客观事件时间线',step_5:'步骤5 角色发展线',step_6:'步骤6 反转设计',step_7:'步骤7 明线暗线发展线',step_8:'步骤8 章节摘要规划'}[key]||key.toUpperCase());
  if(action==='generate_outline')return'步骤1 大纲+蓝图';
  if(action==='generate_worldbuilding')return'步骤2 背景体系+世界观';
  if(action==='generate_characters')return'步骤3 角色卡';
  if(action==='generate_event_timeline')return'步骤4 客观事件时间线';
  if(action==='generate_milestones')return'步骤5 角色发展线';
  if(action==='generate_twist_designs')return'步骤6 反转设计';
  if(action==='generate_story_lines')return'步骤7 明线暗线发展线';
  if(action==='generate_chapter_briefs')return'步骤8 章节摘要规划';
  if(action==='generate_chapter_briefs_batch')return'步骤8 续生成章节摘要';
  if(action==='review_blueprint')return'Critic Blueprint 评审';
  if(action==='add_character')return'步骤3 增加角色';
  if(action==='add_character_milestone')return'步骤5 增加角色发展线';
  if(action==='continue_formal_novel' || action==='write_chapter')return'正文生成';
  if(action==='revise_single_character')return Number.isInteger(idx)?`步骤3 单角色指令修改（角色 ${Number(idx)+1}）`:'步骤3 单角色指令修改';
  if(action==='revise_single_character_milestone')return Number.isInteger(idx)?`步骤5 单角色发展线指令调整（角色 ${Number(idx)+1}）`:'步骤5 单角色发展线指令调整';
  if(action==='revise_step_result')return `${stepName(stepKey)} ${revisionMode==='review'?'质检修改':'指令修改'}`;
  if(action==='ai_update_concept')return'小说信息 AI 修改';
  if(action==='ai_update_text')return'正文 AI 修改';
  const outs=Array.isArray(detail?.outputs)?detail.outputs:[];
  for(let i=outs.length-1;i>=0;i-=1){const label=outputTaskLabel(outs[i]);if(label)return label;}
  const msg=String(run?.pending_message||'');
  if(msg.includes('大纲'))return'步骤1 大纲+蓝图';
  if(msg.includes('世界观')||msg.includes('背景'))return'步骤2 背景体系+世界观';
  if(msg.includes('角色卡')||msg.includes('关系网'))return'步骤3 角色卡';
  if(msg.includes('事件时间线'))return'步骤4 客观事件时间线';
  if(msg.includes('角色发展线'))return'步骤5 角色发展线';
  if(msg.includes('反转'))return'步骤6 反转设计';
  if(msg.includes('故事线')||msg.includes('明线')||msg.includes('暗线'))return'步骤7 明线暗线发展线';
  if(msg.includes('章节规划')||msg.includes('章节摘要'))return'步骤8 章节摘要规划';
  if(msg.includes('写下一章'))return'正文生成';
  if(String(run?.run_id||'').startsWith('edit_'))return'编辑任务';
  return'';
}
async function renderRuns(pref){
  const scrollState=captureLeftScrollState();
  if(!runsCache.length){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";restoreLeftScrollState(scrollState);return;}
  const cache=pref||{};
  for(const r of runsCache){
    if((expandedRuns.has(r.run_id)||r.is_running)&&!cache[r.run_id])cache[r.run_id]=await api(`/api/run?mode=${mode}&run_id=${r.run_id}`);
  }
  let html='';
  runsCache.forEach(r=>{
    const ex=expandedRuns.has(r.run_id),d=cache[r.run_id],outs=((d&&d.outputs)||[]).filter(o=>o?.output_type!=='chapter_live_preview'),evts=(d&&d.events)||[];
    const taskLabel=inferTaskLabel(r,d);
    const streamGroups=collectStreamGroups(evts);
    const normalEvents=evts.filter(e=>!['llm_stream','llm_prompt','llm_reply'].includes(e.event_type));
    const timelineItems=[];
    const chapterTaskItems=d?collectChapterTaskOutputs(d):[];
    if(r.pending_message)timelineItems.push({key:`${r.run_id}:pending`,title:'任务状态',kind:'plain',text:r.pending_message,sortTs:''});
    chapterTaskItems.forEach(item=>timelineItems.push(item));
    outs.forEach(o=>timelineItems.push({key:`${r.run_id}:out:${o.id}`,title:`${esc(o.agent)} · ${esc(o.title)}`,kind:'output',outputType:o.output_type,rawPayload:o.payload,sortTs:o.created_at||''}));
    normalEvents.forEach(e=>timelineItems.push({key:`${r.run_id}:evt:${e.id}`,title:`${esc(e.agent||'System')} · ${esc(e.title||'')}`,kind:'event',eventType:e.event_type,rawPayload:e.payload,sortTs:e.ts||''}));
    sortTimelineItems(timelineItems);
    const items=attachStreamGroupsToItems(r.run_id,timelineItems,streamGroups,taskLabel||'当前任务');
    const activeKey=findActiveRunItemKey(items);
    syncActiveRunCard(r.run_id,activeKey);
    html+=`<div class='run'><div class='head' onclick="toggleRun('${r.run_id}')"><span class='tag'>${esc(stageText(r.stage))}</span>${taskLabel?`<span class='tag'>${esc(taskLabel)}</span>`:''}${r.is_running?"<span class='tag live'>运行中</span>":''}${r.cancel_requested?"<span class='tag stop'>停止中</span>":''}<span>${esc(r.run_id)}</span><span class='ts'>${esc(shortTs(r.updated_at))}</span></div>`;
    if(ex){
      html+="<div class='body'>";
      if(r.is_running)html+=`<div style='margin-bottom:8px'><button class='ghost' onclick="event.stopPropagation();stopRun('${r.run_id}')">停止并删除这次运行</button></div>`;
      if(!items.length)html+="<div class='payload'>暂无运行输出</div>";
      items.forEach((item)=>{const isActive=item.key===activeKey;const isOpen=(item.key in boxStates)?boxStates[item.key]:isActive;html+=boxHtml(item.key,item.title,renderItemPayload(item),isOpen,`task-box${isActive?' active':''}`);});
      html+='</div>';
    }
    html+='</div>';
  });
  evs.innerHTML=html;
  restoreLeftScrollState(scrollState);
}
function toggleRun(id){expandedRuns.has(id)?expandedRuns.delete(id):expandedRuns.add(id);renderRuns();}
async function stopCurrentRun(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);if(!a)return alert('当前没有运行中的任务。');await stopRun(a.run_id);}
async function stopRun(id){if(!confirm('确认删除此运行记录？'))return;await api('/api/runs/stop',{method:'POST',body:JSON.stringify({mode,run_id:id})});expandedRuns.delete(id);delete runActiveItemKeys[id];if(pendingRunId===id){pendingRunId='';pendingStepRevision=null;lastLivePreviewKey='';}runsCache=runsCache.filter(x=>x.run_id!==id);bookId?await refreshNovel():renderRuns();updateStopButton();}
function summarizeBlock(text){const cleaned=String(text||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').split(' ').filter(Boolean).join(' ');return cleaned||'（空白内容）';}
function isDetailOpen(key,defaultOpen=true){return key in detailStates?detailStates[key]:defaultOpen;}
function toggleDetailState(key,isOpen){
  detailStates[key]=isOpen;
  requestAnimationFrame(()=>{
    autoSizeTextareas('pnl-input');
    autoSizeTextareas('pnl-blueprint');
    autoSizeTextareas('pnl-text');
  });
}
function autoSizeTextareas(rootId){document.querySelectorAll(`#${rootId} textarea`).forEach(el=>{const resize=()=>{el.style.height='auto';el.style.height=`${el.scrollHeight}px`;el.style.overflow='hidden';};if(!el.dataset.autosizeBound){el.addEventListener('input',resize);el.dataset.autosizeBound='1';}resize();});}
function captureScrollState(){const activePanel=document.querySelector('.pnl.active');const tc=document.getElementById('tc');return{windowX:window.scrollX,windowY:window.scrollY,leftScrollTop:evs?evs.scrollTop:0,rightScrollTop:tc?tc.scrollTop:0,activePanelId:activePanel?activePanel.id:'',activePanelScrollTop:activePanel?activePanel.scrollTop:0};}
function captureLeftScrollState(){return{leftScrollTop:evs?evs.scrollTop:0};}
function restoreScrollState(state){if(!state)return;requestAnimationFrame(()=>{window.scrollTo(state.windowX||0,state.windowY||0);if(evs)evs.scrollTop=state.leftScrollTop||0;const tc=document.getElementById('tc');if(tc)tc.scrollTop=state.rightScrollTop||0;if(state.activePanelId){const panel=document.getElementById(state.activePanelId);if(panel)panel.scrollTop=state.activePanelScrollTop||0;}});}
function restoreLeftScrollState(state){if(!state)return;requestAnimationFrame(()=>{if(evs)evs.scrollTop=state.leftScrollTop||0;});}
function setAllInputBlocks(open){document.querySelectorAll('#pnl-input details.input-block').forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas('pnl-input');}
function setPanelSections(panelId,open){document.querySelectorAll(`#${panelId} details.section-card`).forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas(panelId);}
function snapshotPanelDetailStates(panelId){const root=document.getElementById(panelId);if(!root)return;root.querySelectorAll('details[data-detail-key]').forEach(el=>{const key=el.dataset.detailKey;if(key)detailStates[key]=!!el.open;});}
function normalizeMultiline(value){const cr=String.fromCharCode(13),lf=String.fromCharCode(10);return String(value??'').split(cr+lf).join(lf).split(cr).join(lf).trimEnd();}
function renderNovelTypeOptions(){const grouped={};for(const item of novelTypeOptions){const group=item.group||'其他';if(!grouped[group])grouped[group]=[];grouped[group].push(item);}newTypeSelect.innerHTML=Object.entries(grouped).map(([group,items])=>`<optgroup label="${esc(group)}">${items.map(item=>`<option value="${esc(item.value)}">${esc(item.label)}</option>`).join('')}</optgroup>`).join('');if(!newTypeSelect.value)newTypeSelect.value='auto';}
function currentNovelTypeOption(){const value=String(newTypeSelect.value||'auto');return novelTypeOptions.find(item=>item.value===value)||novelTypeOptions.find(item=>item.value==='auto')||null;}
function updateNovelTypeHint(){const option=currentNovelTypeOption();if(!option){newTypeHint.textContent='不选也可以，系统会按题材需求和额外风格要求自动判断。';newStyleInput.placeholder=DEFAULT_STYLE_PLACEHOLDER;return;}const base='不选也可以，系统会按题材需求和额外风格要求自动判断。';if(option.value==='auto'){newTypeHint.textContent=base;newStyleInput.placeholder=DEFAULT_STYLE_PLACEHOLDER;return;}newTypeHint.textContent=`将默认匹配到“${option.genre_label}”，风格层走“${option.direction_label}”。${option.description}`;if(!newStyleInput.value.trim()&&option.default_style_request){newStyleInput.placeholder=`例如：${option.default_style_request}`;}else{newStyleInput.placeholder=DEFAULT_STYLE_PLACEHOLDER;}}
async function ensureNovelTypeOptions(){if(novelTypeOptions.length)return novelTypeOptions;const r=await api('/api/novel-types');if(!ensureOk(r))return [];novelTypeOptions=Array.isArray(r.items)?r.items:[];if(!novelTypeOptions.length){novelTypeOptions=[{value:'auto',label:'自动判断 / 通用言情',group:'通用',genre_label:'通用言情',direction_label:'通用连载',default_style_request:'',description:'不指定频道，系统自动判断。'}];}renderNovelTypeOptions();updateNovelTypeHint();return novelTypeOptions;}
async function openNewNovelDialog(){newNovelModal.style.display='flex';await ensureNovelTypeOptions();newTitleInput.focus();}
function closeNewNovelDialog(){newNovelModal.style.display='none';}
async function startFormalFromDialog(){const title=newTitleInput.value.trim();const q=normalizeMultiline(newQueryInput.value);if(!q)return alert('请输入题材/需求。');const style=normalizeMultiline(newStyleInput.value);const novelType=String(newTypeSelect.value||'auto');const r=await api('/api/novels/create',{method:'POST',body:JSON.stringify({mode,title,query:q,style_request:style,novel_type:novelType})});if(!ensureOk(r))return;closeNewNovelDialog();bookId=r.book.id;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};currentBook=r.book;stagePill.textContent='未开始';await loadNovels();novelSel.value=bookId;await refreshNovel();updateStopButton();}
function setPendingRunState(runId,{stage,pendingMessage,taskLabel,clearLivePreview=false,clearActiveItem=false}={}){
  pendingRunId=runId||'';
  if(clearLivePreview)lastLivePreviewKey='';
  if(clearActiveItem&&pendingRunId)delete runActiveItemKeys[pendingRunId];
  if(!pendingRunId)return;
  expandedRuns.add(pendingRunId);
  boxStates={};
  runsCache=[{run_id:pendingRunId,is_running:true,stage:stage||'planning',updated_at:new Date().toISOString(),task_label:taskLabel||pendingMessage||'',pending_message:pendingMessage||taskLabel||''},...runsCache.filter(x=>x.run_id!==pendingRunId)];
}
async function startRunRequest(path,payload,{stage,pendingMessage,taskLabel,clearLivePreview=false,clearActiveItem=false}={}){
  const r=await api(path,{method:'POST',body:JSON.stringify(payload)});
  if(!ensureOk(r))return null;
  setPendingRunState(r.run_id||'',{stage,pendingMessage,taskLabel,clearLivePreview,clearActiveItem});
  await renderRuns();
  updateStopButton();
  return r;
}
async function startPlanningRun(path,message,taskLabel,payloadExtra={}){if(!bookId)return alert('请先选择一部小说。');return await startRunRequest(path,withLlmProvider({book_id:bookId,...(payloadExtra||{})}),{stage:'planning',pendingMessage:message,taskLabel});}
async function startConfiguredPlanningRun(configKey){const config=STEP_RUN_CONFIGS[configKey];if(!config)return alert('未找到对应步骤配置。');await startPlanningRun(config.path,config.pendingMessage,config.taskLabel,config.payload||{});}
async function continueFormal(){if(!bookId)return alert('请先选择一部小说。');await startRunRequest('/api/novels/continue',withLlmProvider({book_id:bookId}),{stage:'writing',pendingMessage:'正在写下一章，请稍候...',taskLabel:'正文生成',clearLivePreview:true,clearActiveItem:true});}
async function deleteNovel(){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除此小说？该操作不可撤销。'))return;await api('/api/novels/delete',{method:'POST',body:JSON.stringify({mode,book_id:bookId})});bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();lastLivePreviewKey='';runActiveItemKeys={};evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';await loadNovels();updateStopButton();}
async function testBlueprint(){const q=prompt('输入题材需求（测试大纲）：');if(!q)return;const r=await startRunRequest('/api/test/blueprint',{query:q},{stage:'planning',pendingMessage:'测试大纲运行中'});if(!r)return;expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);}
async function testWrite(){let r;if(bookId)r=await startRunRequest('/api/test/write',{book_id:bookId},{stage:'writing',pendingMessage:'测试写作运行中'});else{const q=prompt('输入题材需求（测试写作）：');if(!q)return;r=await startRunRequest('/api/test/write',{query:q},{stage:'writing',pendingMessage:'测试写作运行中'});}if(!r)return;expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);}
async function testCritique(){if(!bookId)return alert('请先选择一部小说。');await startRunRequest('/api/test/critique',{book_id:bookId},{stage:'critique',pendingMessage:'测试评价运行中'});}
async function testPatch(){if(!bookId)return alert('请先选择一部小说。');const blockId=prompt('请输入 block_id：');if(!blockId)return;const operation=prompt('操作类型 replace / append / prepend','replace')||'replace';const patchContent=prompt('补丁内容：');if(!patchContent)return;const reason=prompt('修改原因：','manual test patch')||'manual test patch';await startRunRequest('/api/test/patch',{book_id:bookId,block_id:blockId,operation,patch_content:patchContent,reason},{stage:'patching',pendingMessage:'测试补丁运行中'});}
async function aiReviseConcept(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你希望 AI 怎么修改概念：');if(!guidance)return;await startRunRequest('/api/novels/ai_update_concept',withLlmProvider({mode,book_id:bookId,scope,target_id:targetId,guidance}),{stage:'planning',pendingMessage:'AI 修改中'});}
async function aiReviseText(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt(scope==='chapter'?'描述你希望 AI 怎么修改这章：':'描述你希望 AI 怎么修改这段：');if(!guidance)return;await startRunRequest('/api/novels/ai_update_text',withLlmProvider({mode,book_id:bookId,scope,target_id:targetId,guidance}),{stage:'patching',pendingMessage:'AI 修改文本中'});}
async function applyBookMutationResult(result){if(!ensureOk(result))return false;currentBook=result.book;renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();return true;}
async function deleteChapter(chapterId,chapterTitle){if(!bookId)return alert('请先选择一部小说。');const label=String(chapterTitle||chapterId||'该章节');if(!confirm(`确认删除章节：${label}？`))return;const result=await api('/api/novels/delete_chapter',{method:'POST',body:JSON.stringify({mode,book_id:bookId,chapter_id:chapterId})});if(!await applyBookMutationResult(result))return;alert('章节已删除。');}

async function resolveCharacterCandidate(candidateId,action){
  if(!bookId)return alert('请先选择一部小说。');
  const result=await api('/api/novels/resolve_character_candidate',{method:'POST',body:JSON.stringify({mode,book_id:bookId,candidate_id:candidateId,action})});
  if(!await applyBookMutationResult(result))return;
  alert('角色已添加');
}

function renderInputPanel(book){
  const currentQuery=book?.metadata?.query||'';
  const userTopic=book?.metadata?.user_topic||'';
  const styleRequest=book?.metadata?.style_request||'';
  const assistantPersonaPrompt=book?.metadata?.assistant_persona_prompt||'';
  const totalWordTarget=book?.metadata?.total_word_target||'';
  const chapterCountTarget=book?.metadata?.chapter_count_target||'';
  const chapterWordTarget=book?.metadata?.chapter_word_target||'';
  const paceNotes=book?.metadata?.pace_notes||'';
  const block=(key,id,title,text,placeholder,help,defaultOpen)=>`<details class='input-block' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summarizeBlock(text))}</div></div><div class='summary-arrow'>展开 / 折叠</div></summary><div class='block-body'><textarea id='${id}' placeholder='${esc(placeholder)}'>${esc(text)}</textarea><div class='block-help'>${help}</div></div></details>`;
  const writingSummary=[
    totalWordTarget?`总字 ${totalWordTarget}`:'',
    chapterCountTarget?`章数 ${chapterCountTarget}`:'',
    chapterWordTarget?`每章 ${chapterWordTarget}`:'',
    paceNotes?`节奏 ${paceNotes}`:''
  ].filter(Boolean).join(' / ')||'暂无写作要求';
  const writingBlock=`<details class='input-block' data-detail-key='input-writing-requirements' ${isDetailOpen('input-writing-requirements',false)?'open':''} ontoggle="toggleDetailState('input-writing-requirements', this.open)"><summary><div class='summary-text'><div class='summary-title'>写作要求</div><div class='summary-desc'>${esc(writingSummary)}</div></div><div class='summary-arrow'>›</div></summary><div class='block-body'><div class='writing-req-grid'><div class='field'><label>总字数目标</label><input id='concept-total-word-target' value='${esc(totalWordTarget)}' placeholder='约80-100万字' /></div><div class='field'><label>章节数目标</label><input id='concept-chapter-count-target' value='${esc(chapterCountTarget)}' placeholder='约180-220章' /></div><div class='field'><label>章节字数</label><input id='concept-chapter-word-target' value='${esc(chapterWordTarget)}' placeholder='约2500-3500字' /></div></div><div class='writing-req-full'><label>节奏备注</label><textarea id='concept-pace-notes' placeholder='描述各阶段节奏安排'>${esc(paceNotes)}</textarea></div><div class='block-help'>写作要求会影响步骤 1-8 的生成结果</div></div></details>`;
  const heroSummary='在这里填写小说的基础信息，修改后记得点保存。';
  const html=`<div class='card'><div class='sec'>用户输入</div><div class='input-hero'><div class='input-hero-copy'><div class='input-hero-kicker'>小说基础设置</div><div class='input-hero-title-row'><h2 class='input-hero-title'>${esc(book?.title||'未命名小说')}</h2><span class='input-hero-badge'>写作控制台</span></div><div class='input-hero-desc'>${heroSummary}</div></div><div class='input-toolbar'><div class='actions'><button class='ghost' onclick='setAllInputBlocks(true)'>全部展开</button><button class='ghost' onclick='setAllInputBlocks(false)'>全部折叠</button><button onclick='saveConcept()'>保存所有修改</button></div></div></div><div class='title-field'><label>书名标题</label><input id='concept-title' value='${esc(book?.title||'')}' placeholder='输入小说书名' /></div><div class='input-blocks'>${block('input-query','concept-query','题材与需求',currentQuery,'支持 Markdown 详细描述题材','此内容影响步骤 1-8 的生成',true)}${block('input-topic','concept-user-topic','用户主题',userTopic,'可选填写用户关注的主题方向','仅在明确时填写',false)}${block('input-style','concept-style-request','风格要求',styleRequest,'留空则由系统判断风格','明确时填写，不填则自动决策',false)}${block('input-assistant-persona','concept-assistant-persona','小说助手人设',assistantPersonaPrompt,'例如：你是一名擅长古风权谋禁忌言情的长篇作者……','会动态插入“写正文”提示词。可留空。',false)}${writingBlock}</div></div>`;
  document.getElementById('pnl-input').innerHTML=html;
  autoSizeTextareas('pnl-input');
}
function renderBlueprint(book, blueprintReview){
  const premise=book?.premise||{};
  const blueprint=book?.metadata?.story_blueprint||{};
  const storyEngine=blueprint.story_engine||{};
  const sectionCard=(key,title,summary,body,defaultOpen=true)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  const toolbarSection=(key,title,summary,actions,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-toolbar' onclick='event.stopPropagation()'>${actions}</div></summary><div class='section-body'>${body}</div></details>`;
  const listHtml=(items, emptyText='暂无内容')=>{const arr=toArray(items);return arr.length?`<div class='mini-list'>${arr.map(item=>`<div class='mini-item'>${esc(typeof item==='string'?item:JSON.stringify(item,null,2))}</div>`).join('')}</div>`:`<div class='relationship-empty'>${emptyText}</div>`;};
  const detailRowsHtml=(title,items,emptyText)=>{const arr=toArray(items);if(!arr.length)return `<div class='field-block'><div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(title)}：</span><span class='field-val'>${esc(emptyText)}</span></div></div>`;return `<div class='field-block'><div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(title)}：</span><span class='field-val'>共 ${arr.length} 条</span></div>${arr.map((item,index)=>`<div class='field-row'><span class='field-dot'>${index+1}.</span><span class='field-val'>${esc(typeof item==='string'?item:JSON.stringify(item,null,2))}</span></div>`).join('')}</div>`;};
  const stepSection=(stepKey,title,summary,body,defaultOpen=false)=>{const badge=stepDraftDirty[stepKey]?`<span class='dirty-dot'>●未保存</span>`:'';const extra=stepKey==='step_5'?`<button class='ghost' onclick="addMilestoneLine()">增加角色</button>`:'';const acts=`${badge}${extra}<button class='ghost' onclick="clearStepDraft('${stepKey}')">清空</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存</button>`;return toolbarSection(stepKey,title,summary,acts,body,defaultOpen);};
  const subStepEditor=(stepKey,subKey,label)=>{const s=ensureStepObject(stepKey,stepPayloadFromBook(book,stepKey));return `<div class='step-editor'><div class='step-editor-body'><div class='step-editor-empty'>可以直接在这个模块里改内容，点右上角"保存"才会真正写回。</div>${renderStepEditorField(stepKey,[subKey],s[subKey]??[])}</div></div>`;};
  const step3DraftObj=stepDraftDirty['step_3']?(stepDraftObjects['step_3']||{}):null;
  const rawStep3Chars=Array.isArray(step3DraftObj?.characters)?step3DraftObj.characters:(book?.characters||[]);
  const displayCharacters=rawStep3Chars.filter(item=>item&&typeof item==='object');
  if(step3DraftObj&&Array.isArray(step3DraftObj.characters)&&displayCharacters.length!==step3DraftObj.characters.length){step3DraftObj.characters=displayCharacters;stepDraftObjects['step_3']=step3DraftObj;stepDrafts['step_3']=JSON.stringify(step3DraftObj,null,2);}
  const step3Dirty=!!stepDraftDirty['step_3'];
  const dirtyBadge=step3Dirty?`<span class='dirty-dot' title='有未保存的修改'>●未保存</span>`:'';
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说信息概览</div><div class='panel-title'>步骤 1-8 详情</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-blueprint',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-blueprint',false)">全部折叠</button></div></div>`;
  html+=stepSection('step_1','1 大纲+蓝图',premise.story_summary||premise.high_concept||'暂无概念信息',subStepEditor('step_1','premise','大纲主体')+subStepEditor('step_1','story_engine','叙事架构'),false);
  html+=stepSection('step_2','2 背景体系+世界观',storyEngine.engine_sentence||'暂无引擎句',subStepEditor('step_2','story_engine','世界观'));
  const fieldRows=(pairs)=>pairs.filter(([,v])=>v).map(([k,v])=>`<div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(k)}：</span><span class='field-val'>${esc(v)}</span></div>`).join('')||"<div class='field-row'>（暂无信息）</div>";
  const charField=(idx,key,label,val)=>`<div class='step-inline-field'><label>${esc(label)}</label><textarea class='step-inline-textarea' oninput="updateStepEditorValue('step_3','characters.${idx}.${key}','string',this.value)">${esc(val||'')}</textarea></div>`;
  const characterCards=displayCharacters.map((item,index)=>{const title=item.name||item.role||`角色 ${index+1}`;const summary=[item.role,item.personality,item.occupation].filter(Boolean).join(' · ')||'暂无信息';const editFields=[charField(index,'name','名称',item.name),charField(index,'role','角色定位',item.role),charField(index,'occupation','职业',item.occupation),charField(index,'appearance','外貌',item.appearance),charField(index,'personality','性格',item.personality),charField(index,'social_background','社会背景',item.social_background),charField(index,'education_background','教育背景',item.education_background),charField(index,'career','事业',item.career),charField(index,'initial_state','初始状态',item.initial_state),charField(index,'motivation','动机',item.motivation),charField(index,'behavior_pattern','行为模式',item.behavior_pattern),charField(index,'arc','成长弧',item.arc),charField(index,'relationships','关系',item.relationships)].join('');const axes=toArray(item.development_axes||[]);const body=`<div class='step-inline-root'>${editFields}</div>${axes.length?`<div style='margin-top:8px'>${listHtml(axes,'')}</div>`:''}<div style='display:flex;justify-content:flex-end;gap:8px;margin-top:12px'><button class='ghost' onclick='reviseSingleCharacterByInstruction(${index})'>指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存修改</button></div>`;return sectionCard(`step3-character-${index}`,title,summary,body,false);}).join('')||"<div class='relationship-empty'>暂无角色</div>";
  const charActions=`${dirtyBadge}<button class='ghost' onclick="clearStepDraft('step_3')">清空</button><button class='ghost' onclick="addCharacterByInstruction()">增加角色</button><button class='ghost' onclick="reviseStepDraft('step_3','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('step_3','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存</button>`;
  html+=toolbarSection('step3-characters','3 角色卡',`${displayCharacters.length} 个角色`,charActions,characterCards,false);
  html+=stepSection('step_4','4 客观事件时间线',`${(blueprint.event_timeline||[]).length} 条`,subStepEditor('step_4','event_timeline','事件时间线'));
  const step5State=ensureStepObject('step_5',stepPayloadFromBook(book,'step_5'));
  const milestoneItems=Array.isArray(step5State?.character_milestones)?step5State.character_milestones:[];
  const characterCardMap=new Map(displayCharacters.map(item=>[String(item?.name||'').trim(),item]));
  const milestoneCards=milestoneItems.map((item,index)=>{
    const name=String(item?.character_name||'').trim()||`角色 ${index+1}`;
    const card=characterCardMap.get(name)||null;
    const summary=card?[card.role,card.personality,card.occupation].filter(Boolean).join(' · ')||'已匹配角色卡':'未匹配到角色卡，请先确认角色名与角色卡一致';
    const detailKey=`step5-character-${index}`;
    const toolbar=`<button class='ghost' onclick='event.stopPropagation();saveStepDraft(\"step_5\")'>保存修改</button><button class='ghost' onclick='event.stopPropagation();reviseSingleMilestoneByInstruction(${index})'>指令调整</button>`;
    const body=`<div class='step-editor'><div class='step-editor-body'>${renderStepEditorField('step_5',['character_milestones',index],item)}</div></div>`;
    return `<details class='section-card' data-detail-key='${detailKey}' ${isDetailOpen(detailKey,true)?'open':''} ontoggle="toggleDetailState('${detailKey}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${esc(name)}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-toolbar' onclick='event.stopPropagation()'>${toolbar}</div></summary><div class='section-body'>${body}</div></details>`;
  }).join('')||"<div class='relationship-empty'>暂无角色发展线</div>";
  html+=stepSection('step_5','5 角色发展线',`${milestoneItems.length} 条发展线`,milestoneCards);
  html+=stepSection('step_6','6 反转设计',`${(blueprint.twist_designs||[]).length} 个反转`,subStepEditor('step_6','twist_designs','反转设计'));
  const step8State=ensureStepObject('step_8',stepPayloadFromBook(book,'step_8'));
  const step8Inline=`<div class='step-editor'><div class='step-editor-body'>${renderStepEditorField('step_8',['chapter_briefs'],step8State.chapter_briefs??[])}</div></div>`;
  const step7Summary=`${(blueprint.story_lines||[]).length} 条故事线`;
  const step8Summary=`${(blueprint.chapter_briefs||[]).length} 章摘要`;
  html+=stepSection('step_7','7 明线暗线发展线',step7Summary,subStepEditor('step_7','story_lines','明线暗线（含关键章节推进）'));
  html+=stepSection('step_8','8 章节摘要（点一次生成一章）',step8Summary,step8Inline);
  const actualSummaries=Array.isArray(book?.metadata?.actual_chapter_summaries)?book.metadata.actual_chapter_summaries:[];
  const latestCritic=book?.metadata?.latest_critic_report||null;
  html+=sectionCard('actual-summaries','已完成章节 actual summaries',`${actualSummaries.length} 章`,listHtml(actualSummaries.map(item=>`${item.chapter_id||''}：${(item.actual_events||[]).join('；')}`),'暂无已完成章节'),false);
  if(latestCritic){html+=sectionCard('latest-critics','最近一次章节 critic',latestCritic.summary||'暂无总结',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', latestCritic.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((latestCritic.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}：${item.evidence||item.recommendation||''}`),'暂无问题')}</div></div>`,false);}
  if(blueprintReview){html+=sectionCard('blueprint-review','Critic Blueprint',blueprintReview.summary||'暂无评审结论',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', blueprintReview.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((blueprintReview.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}`),'暂无问题')}</div></div>`,false);}
  document.getElementById('pnl-blueprint').innerHTML=html;
  autoSizeTextareas('pnl-blueprint');
}
function renderText(book,livePreview=null,runDetail=null){
  const volumes=book?.volumes||[];
  const chapters=[];
  const candidates=Array.isArray(book?.metadata?.new_character_candidates)?book.metadata.new_character_candidates:[];
  volumes.forEach(volume=>(volume.chapters||[]).forEach(chapter=>chapters.push({volume,chapter})));
  const recentPatchedBlockIds=latestPatchedBlockIds(runDetail);
  const draftPreview=latestChapterPreviewByMode(runDetail,'chapter_draft');
  const draftPreviewText=String(draftPreview?.payload?.final_text||'').trim();
  if(livePreview&&livePreview.chapter_id){
    const idx=chapters.findIndex(item=>String(item?.chapter?.id||'')===String(livePreview.chapter_id||''));
    const previewChapter={
      id:String(livePreview.chapter_id||''),
      title:String(livePreview.chapter_title||livePreview.chapter_id||'实时章节'),
      summary:'实时生成中',
      scenes:[],
      content_blocks:Array.isArray(livePreview.content_blocks)?livePreview.content_blocks:[],
      character_mindsets:Array.isArray(livePreview.character_mindsets)?livePreview.character_mindsets:[],
      final_text:String(livePreview.final_text||''),
      final_version:Number(livePreview.final_version||0),
      is_finalized:!!livePreview.is_finalized,
      preview_mode:String(livePreview.preview_mode||''),
      recent_patched_block_ids:recentPatchedBlockIds,
      draft_text:draftPreviewText,
    };
    const previewEntry={volume:{title:'运行中',id:'runtime'},chapter:previewChapter};
    if(idx>=0)chapters[idx]=previewEntry;
    else chapters.push(previewEntry);
  }
  const sectionCard=(key,title,summary,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  const renderLegacyScenes=(chapter)=>{
    return (chapter.scenes||[]).map((scene,sceneIndex)=>{
      const blocks=(scene.blocks||[]).map((block,blockIndex)=>`<div class='block' style='margin-top:8px'><div class='row'><strong>段落 ${blockIndex+1}</strong>${block.purpose?` <span class='muted'>${esc(block.purpose)}</span>`:''}${block.id?` <span class='muted'>${esc(block.id)}</span>`:''}</div><div>${esc(block.text||'')}</div></div>`).join('')||"<div class='relationship-empty'>暂无段落内容</div>";
      return `<div class='relationship-card'><div class='subsec'>场景 ${sceneIndex+1}${scene.title?` · ${esc(scene.title)}`:''}</div>${infoRow('场景概述', scene.summary||'')}${blocks}</div>`;
    }).join('')||"<div class='relationship-empty'>暂无场景</div>";
  };
  if(!chapters.length && !candidates.length){document.getElementById('pnl-text').innerHTML="<div class='empty'>暂无内容</div>";return;}
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说正文</div><div class='panel-title'>章节内容</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-text',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-text',false)">全部折叠</button></div></div>`;
  if(candidates.length){
    const cards=candidates.map((item,index)=>{
      const traits=Array.isArray(item?.provisional_traits)?item.provisional_traits.filter(Boolean):[];
      const links=Array.isArray(item?.links_to_existing_characters)?item.links_to_existing_characters.filter(link=>link&&typeof link==='object'):[];
      const linkLines=links.length?links.map(link=>`<div class='kv'><div class='k'>${esc(link.target||'未知角色')}</div><div>${esc(link.relation||'未知关系')}</div></div>`).join(''):"<div class='relationship-empty'>暂无关联角色</div>";
      return `<div class='relationship-card'><div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'><div><div class='subsec'>${esc(item?.name||`角色候选 ${index+1}`)}</div><div class='muted'>首登场：${esc(item?.first_appearance_chapter||'待定')}</div></div><div class='actions'><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','add')">确认添加</button></div></div>${infoRow('场景作用', item?.role_in_scene||'')}${infoRow('存在理由', item?.why_needed||'')}${traits.length?sectionHtml('特征', chipsHtml(traits)):''}${sectionHtml('与现有角色关联', linkLines)}</div>`;
    }).join('');
    html+=sectionCard('text-character-candidates','新角色候选',`共 ${candidates.length} 个候选角色`,`<div class='relationship-stack'>${cards}</div>`,true);
  }
  chapters.forEach(({volume,chapter},index)=>{
    const title=chapter.title||chapter.id||`第${index+1}章`;
    const summary=chapter.summary||'暂无摘要';
    const chapterToolbar=`<div style='display:flex;justify-content:flex-end;gap:8px;margin-bottom:8px'><button class='ghost' onclick="aiReviseText('chapter','${esc(chapter.id||'')}')">整章指令修改</button><button class='ghost' onclick="deleteChapter('${esc(chapter.id||'')}')">删除章节</button></div>`;
    const contentBlocks=Array.isArray(chapter?.content_blocks)?chapter.content_blocks:[];
    const characterMindsets=Array.isArray(chapter?.character_mindsets)?chapter.character_mindsets:[];
    const finalText=String(chapter?.final_text||'').trim();
    const isFinalized=!!chapter?.is_finalized;
    const previewMode=String(chapter?.preview_mode||'').trim();
    const draftText=String(chapter?.draft_text||'').trim();
    const patchHighlightIds=Array.isArray(chapter?.recent_patched_block_ids)?chapter.recent_patched_block_ids:[];
    const hasChapterPreview=!!finalText;
    const assembledPreviewText=mergeChapterBlocksText(contentBlocks,finalText);
    const previewModeLabel=previewMode==='content_blocks'?'内容块逐块追加中':previewMode==='chapter_rewrite'?'整章审校重写中':previewMode==='final_polish'?'整章精修中':previewMode==='final_text'?'整章覆写已收口':'';
    const mindsetBody=renderCharacterMindsetsBlock(characterMindsets);
    let proseBody='';
    if(hasChapterPreview||contentBlocks.length){
      const proseLabel=isFinalized?'当前小说正文':'当前修订中的正文';
      const liveSummary=isFinalized?'终稿已经收口，可直接阅读当前正文。':'这里会持续显示本轮正在修订的正文，命中的 block 修完后会直接体现在这里。';
      proseBody=`<div class='relationship-card'><div class='subsec'>${proseLabel}</div><div class='task-note'>${esc(liveSummary)}</div><div class='block live-draft-text'>${esc(assembledPreviewText||finalText)}</div>${previewModeLabel?`<div class='live-draft-meta'><span class='block-badge status'>${esc(previewModeLabel)}</span>${patchHighlightIds.length?`<span class='block-badge patched'>本轮更新 ${patchHighlightIds.length} 个 block</span>`:''}</div>`:''}</div>`;
      if(draftText&&draftText!==assembledPreviewText){
        proseBody+=`<div class='relationship-card'><div class='subsec'>整章首稿快照</div><div class='block live-draft-text'>${esc(draftText)}</div></div>`;
      }
      if(contentBlocks.length){
        proseBody+=`<div class='relationship-card'><div class='subsec'>当前 block 视图</div><div class='chapter-live-blocks'><div class='relationship-stack'>${renderBlockCards(contentBlocks,{label:'内容块',highlightIds:patchHighlightIds})}</div></div></div>`;
      }
    }else if(contentBlocks.length){
      proseBody=`<div class='relationship-card'><div class='subsec'>增量写作中</div><div class='muted'>每个 content block 提交后，这里都会继续往下追加。</div><div class='relationship-stack'>${renderBlockCards(contentBlocks,{label:'内容块'})}</div></div>`;
    }else{
      proseBody=`<div class='relationship-card'><div class='subsec'>正文展示</div><div class='relationship-stack'>${renderLegacyScenes(chapter)}</div></div>`;
    }
    const modeSummary=isFinalized&&finalText?'已终稿覆盖':(hasChapterPreview||contentBlocks.length)&&previewMode?'实时修订视图':contentBlocks.length?'按内容块逐步追加':'场景回放';
    const body=`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>基础信息</div>${infoRow('卷名', volume.title||volume.id||'')}${infoRow('章节标题', title)}${infoRow('章节概述', summary)}${infoRow('展示模式', modeSummary)}${previewModeLabel?infoRow('运行状态', previewModeLabel):''}</div>${chapterToolbar}${mindsetBody}${proseBody}</div>`;
    html+=sectionCard(`text-chapter-${chapter.id||index}`,title,summary,body,false);
  });
  document.getElementById('pnl-text').innerHTML=html;
}

function renderCritic(c){
  if(!c){document.getElementById('pnl-critic').innerHTML="<div class='empty'>暂无评价内容</div>";return;}
  const sectionCard=(key,title,summary,body,defaultOpen=true)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>评价结果</div><div class='panel-title'>评价详情</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-critic',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-critic',false)">全部折叠</button></div></div>`;
  html+=sectionCard('critic-summary','评价总结',c.summary||'暂无摘要',`${infoRow('摘要', c.summary||'')}${infoRow('问题数', (c.issues||[]).length)}`,true);
  (c.issues||[]).forEach((issue,index)=>{
    html+=sectionCard(`critic-issue-${index}`,`${issue.severity||'未知'} · ${issue.title||`Issue ${index+1}`}`,issue.evidence||issue.impact||'无详细描述',`<div class='issue'>${infoRow('位置', issue.location?.block_id||'')}${infoRow('证据', issue.evidence||'')}${infoRow('影响', issue.impact||'')}${infoRow('建议', issue.recommendation||'')}</div>`,false);
  });
  document.getElementById('pnl-critic').innerHTML=html;
}

function showTab(name){document.querySelectorAll('.tab').forEach((e,i)=>e.classList.toggle('active',['input','blueprint','text','critic'][i]===name));document.querySelectorAll('.pnl').forEach(e=>e.classList.remove('active'));document.getElementById('pnl-'+name).classList.add('active');}
const btnNew=document.getElementById('btnNew'),btnStep1=document.getElementById('btnStep1'),btnStep2=document.getElementById('btnStep2'),btnStep3=document.getElementById('btnStep3'),btnStep4=document.getElementById('btnStep4'),btnStep5=document.getElementById('btnStep5'),btnStep6=document.getElementById('btnStep6'),btnStep7=document.getElementById('btnStep7'),btnStep8=document.getElementById('btnStep8'),btnBlueprintReview=document.getElementById('btnBlueprintReview'),btnContinue=document.getElementById('btnContinue'),btnBlueprint=document.getElementById('btnBlueprint'),btnWrite=document.getElementById('btnWrite'),btnCritique=document.getElementById('btnCritique'),btnPatch=document.getElementById('btnPatch'),btnStop=document.getElementById('btnStop'),stagePill=document.getElementById('stage-pill'),bootPill=document.getElementById('boot-pill'),novelSel=document.getElementById('novelSel'),modeSel=document.getElementById('modeSel'),modelSel=document.getElementById('modelSel'),evs=document.getElementById('evs'),newNovelModal=document.getElementById('newNovelModal'),newTitleInput=document.getElementById('newTitleInput'),newQueryInput=document.getElementById('newQueryInput'),newTypeSelect=document.getElementById('newTypeSelect'),newTypeHint=document.getElementById('newTypeHint'),newStyleInput=document.getElementById('newStyleInput');
function showFrontendError(message){
  if(bootPill)bootPill.textContent=`前端失败：${String(message||'未知错误').slice(0,40)}`;
  if(evs){
    evs.innerHTML=`<div class='empty'>前端初始化失败：${esc(message||'未知错误')}</div>`;
  }
  console.error(message);
}
window.addEventListener('error',event=>{
  showFrontendError(event?.error?.message||event?.message||'脚本运行错误');
});
window.addEventListener('unhandledrejection',event=>{
  const reason=event?.reason;
  showFrontendError(reason?.message||String(reason||'未处理的异步错误'));
});
async function initApp(){
  try{
    if(bootPill)bootPill.textContent='前端初始化中';
    try{
      const savedMode=readStoredMode();
      mode=validMode(savedMode)?savedMode:'formal';
    }catch{mode='formal';}
    try{
      const savedProvider=String(localStorage.getItem(LLM_PROVIDER_STORAGE_KEY)||'').toLowerCase();
      llmProvider=validLlmProvider(savedProvider)?savedProvider:'deepseek';
    }catch{llmProvider='deepseek';}
    if(modeSel)modeSel.value=mode;
    if(modelSel)modelSel.value=llmProvider;
    toggleButtons();
    await ensureNovelTypeOptions();
    await loadNovels({autoSelectSingle:true});
    if(bootPill)bootPill.textContent=`前端已加载 ${Math.max((novelSel?.options?.length||1)-1,0)} 本`;
    updateStopButton();
    if(bookId)await refreshNovel();
    setInterval(async()=>{
      if(refreshPaused)return;
      // Avoid double re-render during active runs: polling both endpoints in one tick
      // causes the left run panel to redraw twice and appear as flicker.
      if(pendingRunId){
        await refreshPendingRun();
        return;
      }
      if(bookId)await refreshNovel();
    },1500);
  }catch(err){
    showFrontendError(err?.message||String(err));
  }
}
initApp();
</script></body></html>"""
