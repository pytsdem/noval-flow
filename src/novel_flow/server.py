from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.agents.critic import CriticAgent
from novel_flow.agents.master import MasterAgent
from novel_flow.agents.memory import MemoryAgent
from novel_flow.agents.research import ResearchAgent
from novel_flow.agents.writer import WriterAgent
from novel_flow.config import Settings
from novel_flow.events import EventBus, PipelineEvent, RunCancelledError, check_cancelled
from novel_flow.llm.base import LLMClient
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import BookBlueprint, BookDocument, CharacterCard, ChapterPlan, NewCharacterCandidate, PatchInstruction, PatchOperation, StoryPremise, Volume, WorkflowStage, WorkflowState
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.crawler import MockTrendCrawler
from novel_flow.services.patcher import PatchExecutor
from novel_flow.services.reference_library import ReferenceLibrary

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
    def __init__(self, stores: AppStores) -> None:
        self.stores = stores
        self._run_handles: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

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
        for row in store.list_recent_events(run_id, limit=500):
            item = dict(row)
            item["payload"] = self._parse_json(item["payload_json"])
            events.append(item)
        return {
            "run_id": run_id,
            "stage": state.stage.value if state else None,
            "current_book_id": state.current_book_id if state else None,
            "updated_at": state.updated_at.isoformat() if state else None,
            "is_running": bool(handle and handle.is_running),
            "cancel_requested": bool(handle and handle.cancel_event.is_set()),
            "outputs": outputs,
            "events": events,
        }

    def delete_novel(self, mode: str, book_id: str) -> None:
        self._store(mode).delete_book(book_id)

    @staticmethod
    def _clean_user_text(value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n").rstrip()

    def create_novel_shell(self, mode: str, *, query: str, style_request: str = "", title: str = "") -> dict[str, Any]:
        store = self._store(mode)
        now = datetime.now(timezone.utc)
        clean_query = self._clean_user_text(query)
        clean_style = self._clean_user_text(style_request)
        clean_title = self._clean_user_text(title).strip()
        title_hint = clean_title or (clean_query.strip().splitlines()[0][:24] or "Untitled Novel").strip()
        premise = StoryPremise(
            title=title_hint,
            high_concept="TBD",
            story_summary="",
            genre="TBD",
            target_style=clean_style or "TBD",
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
                "style": clean_style,
                "target_words": 100000,
                "total_word_target": "10万字左右",
                "chapter_count_target": "40章左右",
                "chapter_word_target": "2500-3500字",
                "pace_notes": "",
                "planning_phase": "created",
                "volume_titles": ["Volume 1"],
                "chapter_plans": [],
                "character_milestones": [],
                "new_character_candidates": [],
                "scene_only_characters": [],
                "story_blueprint": {},
                "blueprint_review": None,
                "next_chapter_index": 0,
                "completed_chapter_ids": [],
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
        chapter_plans: list[dict[str, Any]] | None,
        query: str | None = None,
        user_topic: str | None = None,
        style_request: str | None = None,
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
            book.metadata["style"] = cleaned_style
            if premise is None:
                book.premise.target_style = cleaned_style or "TBD"
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
        if chapter_plans is not None:
            plans = [ChapterPlan.model_validate(item) for item in chapter_plans]
            book.metadata["chapter_plans"] = [plan.model_dump(mode="json") for plan in plans]
            next_index = int(book.metadata.get("next_chapter_index", 0))
            book.metadata["next_chapter_index"] = min(next_index, len(plans))
            completed = set(book.metadata.get("completed_chapter_ids", []))
            book.metadata["completed_chapter_ids"] = [plan.chapter_id for plan in plans if plan.chapter_id in completed]
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
            story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
            relationships = list(story_blueprint.get("relationship_network", []) or [])
            for link in target.links_to_existing_characters:
                relationships.append(
                    {
                        "line_name": f"{target.name}-{link.target}关系线",
                        "subject": target.name,
                        "target": link.target,
                        "surface_relation": link.relation,
                        "true_relation": link.relation,
                        "relation_stage_summary": "",
                        "core_emotion": [],
                        "psychological_basis": "",
                        "key_tensions": [],
                        "desire_vs_fear": {},
                        "power_dynamic": {},
                        "relationship_debt": "",
                        "turning_points": [],
                        "story_function": [],
                        "contrast_targets": [],
                        "payoff": "",
                    }
                )
            story_blueprint["relationship_network"] = relationships
            book.metadata["story_blueprint"] = story_blueprint
        elif action == "scene_only":
            scene_only = list(book.metadata.get("scene_only_characters", []) or [])
            scene_only.append(target.model_dump(mode="json"))
            book.metadata["scene_only_characters"] = scene_only
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

    @staticmethod
    def _planning_context_payload(book: BookDocument) -> dict[str, Any]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        return {
            "book_title": book.title,
            "original_requirement": str(book.metadata.get("original_query") or ""),
            "current_requirement": str(book.metadata.get("query") or ""),
            "user_topic": str(book.metadata.get("user_topic") or ""),
            "style_request": str(book.metadata.get("style_request") or ""),
            "writing_requirements": {
                "total_word_target": str(book.metadata.get("total_word_target") or ""),
                "chapter_count_target": str(book.metadata.get("chapter_count_target") or ""),
                "chapter_word_target": str(book.metadata.get("chapter_word_target") or ""),
                "pace_notes": str(book.metadata.get("pace_notes") or ""),
            },
            "premise": book.premise.model_dump(mode="json"),
            "step_outputs": {
                "step_1_outline_blueprint": {
                    "theme_statement": book.premise.theme_statement,
                    "story_summary": book.premise.story_summary,
                    "high_concept": book.premise.high_concept,
                    "selling_points": book.premise.selling_points,
                    "escalation_path": book.premise.escalation_path,
                    "story_engine": story_blueprint.get("story_engine", {}),
                },
                "step_2_worldbuilding": {
                    "story_engine": story_blueprint.get("story_engine", {}),
                },
                "step_3_characters_relationships": {
                    "characters": [item.model_dump(mode="json") for item in book.characters],
                    "relationship_network": story_blueprint.get("relationship_network", []),
                },
                "step_4_event_timeline": {
                    "event_timeline": story_blueprint.get("event_timeline", []),
                },
                "step_5_character_milestones": {
                    "character_milestones": book.metadata.get("character_milestones", []),
                },
                "step_6_twist_designs": {
                    "twist_designs": story_blueprint.get("twist_designs", []),
                },
                "step_7_story_lines": {
                    "story_lines": story_blueprint.get("story_lines", []),
                    "chapter_briefs": story_blueprint.get("chapter_briefs", []),
                },
                "step_8_chapter_plans": {
                    "chapter_plans": book.metadata.get("chapter_plans", []),
                },
            },
        }

    @classmethod
    def _planning_context_json(cls, book: BookDocument) -> str:
        return json.dumps(cls._planning_context_payload(book), ensure_ascii=False, indent=2)

    @staticmethod
    def _step_title(step_key: str) -> str:
        titles = {
            "step_1": "1 大纲+蓝图",
            "step_2": "2 背景系+世界观",
            "step_3": "3 角色卡+关系网",
            "step_4": "4 客观事件时间线",
            "step_5": "5 角色发展线",
            "step_6": "6 反转设计",
            "step_7": "7 故事线+章节标题",
            "step_8": "8 章节规划+大纲",
        }
        if step_key not in titles:
            raise ValueError(f"Unsupported step key: {step_key}")
        return titles[step_key]

    @staticmethod
    def _step_payload_from_book(book: BookDocument, step_key: str) -> dict[str, Any]:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if step_key == "step_1":
            return {
                "premise": book.premise.model_dump(mode="json"),
                "story_engine": story_blueprint.get("story_engine", {}),
            }
        if step_key == "step_2":
            return {"story_engine": story_blueprint.get("story_engine", {})}
        if step_key == "step_3":
            return {
                "characters": [item.model_dump(mode="json") for item in book.characters],
                "relationship_network": story_blueprint.get("relationship_network", []),
            }
        if step_key == "step_4":
            return {"event_timeline": story_blueprint.get("event_timeline", [])}
        if step_key == "step_5":
            return {"character_milestones": book.metadata.get("character_milestones", [])}
        if step_key == "step_6":
            return {"twist_designs": story_blueprint.get("twist_designs", [])}
        if step_key == "step_7":
            return {
                "story_lines": story_blueprint.get("story_lines", []),
                "chapter_briefs": story_blueprint.get("chapter_briefs", []),
            }
        if step_key == "step_8":
            return {"chapter_plans": book.metadata.get("chapter_plans", [])}
        raise ValueError(f"Unsupported step key: {step_key}")

    @staticmethod
    def _normalize_step_payload(step_key: str, payload: Any) -> dict[str, Any]:
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
        if step_key == "step_2":
            return {"story_engine": BlueprintAgent._normalize_story_engine(payload.get("story_engine", {}))}
        if step_key == "step_3":
            characters_raw = payload.get("characters", [])
            if not isinstance(characters_raw, list):
                raise ValueError("step_3.characters 必须是 JSON 数组。")
            sanitized_raw = [item for item in characters_raw if isinstance(item, dict)]
            if characters_raw and not sanitized_raw:
                raise ValueError("step_3.characters 中没有可用的角色对象。")
            characters = [CharacterCard.model_validate(item) for item in sanitized_raw]
            return {
                "characters": [item.model_dump(mode="json") for item in characters],
                "relationship_network": BlueprintAgent._normalize_relationship_network(payload.get("relationship_network", [])),
            }
        if step_key == "step_4":
            return {"event_timeline": BlueprintAgent._normalize_event_timeline(payload.get("event_timeline", []))}
        if step_key == "step_5":
            return {"character_milestones": BlueprintAgent._normalize_character_milestones(payload.get("character_milestones", []))}
        if step_key == "step_6":
            return {"twist_designs": BlueprintAgent._normalize_twist_designs(payload.get("twist_designs", []))}
        if step_key == "step_7":
            return {
                "story_lines": BlueprintAgent._normalize_story_lines(payload.get("story_lines", [])),
                "chapter_briefs": BlueprintAgent._normalize_chapter_briefs(payload.get("chapter_briefs", [])),
            }
        if step_key == "step_8":
            plans_raw = payload.get("chapter_plans", [])
            if not isinstance(plans_raw, list):
                raise ValueError("step_8.chapter_plans 必须是 JSON 数组。")
            plans = [
                ChapterPlan.model_validate(BlueprintAgent._normalize_chapter_plan_payload(dict(item))).model_dump(mode="json")
                for item in plans_raw
                if isinstance(item, dict)
            ]
            return {"chapter_plans": plans}
        raise ValueError(f"Unsupported step key: {step_key}")

    @staticmethod
    def _apply_step_payload(book: BookDocument, step_key: str, payload: dict[str, Any]) -> None:
        story_blueprint = dict(book.metadata.get("story_blueprint", {}) or {})
        if step_key == "step_1":
            premise = StoryPremise.model_validate(payload["premise"])
            book.premise = premise
            book.title = premise.title or book.title
            story_blueprint["story_engine"] = payload.get("story_engine", {})
        elif step_key == "step_2":
            story_blueprint["story_engine"] = payload.get("story_engine", {})
        elif step_key == "step_3":
            book.characters = [CharacterCard.model_validate(item) for item in payload.get("characters", [])]
            story_blueprint["relationship_network"] = payload.get("relationship_network", [])
        elif step_key == "step_4":
            story_blueprint["event_timeline"] = payload.get("event_timeline", [])
        elif step_key == "step_5":
            book.metadata["character_milestones"] = payload.get("character_milestones", [])
        elif step_key == "step_6":
            story_blueprint["twist_designs"] = payload.get("twist_designs", [])
        elif step_key == "step_7":
            story_blueprint["story_lines"] = payload.get("story_lines", [])
            story_blueprint["chapter_briefs"] = payload.get("chapter_briefs", [])
        elif step_key == "step_8":
            plans = [ChapterPlan.model_validate(item) for item in payload.get("chapter_plans", [])]
            book.metadata["chapter_plans"] = [item.model_dump(mode="json") for item in plans]
            next_index = int(book.metadata.get("next_chapter_index", 0))
            book.metadata["next_chapter_index"] = min(next_index, len(plans))
            completed = set(book.metadata.get("completed_chapter_ids", []))
            book.metadata["completed_chapter_ids"] = [plan.chapter_id for plan in plans if plan.chapter_id in completed]
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
        self._apply_step_payload(book, step_key, normalized)
        book.updated_at = datetime.now(timezone.utc)
        store.save_book(book)
        return {
            "book": book.model_dump(mode="json"),
            "step_payload": self._step_payload_from_book(book, step_key),
        }

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

    def stop_run(self, mode: str, run_id: str) -> None:
        handle = self._handle(run_id)
        if handle and handle.mode == mode and handle.is_running:
            handle.cancel_event.set()
        self._store(mode).delete_run(run_id)

    def ai_update_concept(self, mode: str, *, book_id: str, scope: str, target_id: str | None, guidance: str) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "ai_update_concept", "scope": scope, "target_id": target_id or ""})
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

    def ai_update_text(self, mode: str, *, book_id: str, scope: str, target_id: str, guidance: str) -> str:
        run_id = f"edit_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            writer = self._build_writer()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PATCHING, current_book_id=book.id, context={"action": "ai_update_text", "scope": scope, "target_id": target_id})
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

    def start_formal_novel(self, query: str, style_request: str = "") -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            master = self._build_master(store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                master.start_new_outline(query=query, run_id=run_id, mode="formal", style_request=style_request)

        return self._launch_run("formal", run_id, task)

    def generate_formal_outline(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_outline"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, style_request, "outline", "blueprint"], tags=["story structure", "plot"])
                payload = blueprint_agent.build_story_spine(
                    query,
                    style_request=style_request,
                    planning_context_json=self._planning_context_json(book),
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

    def generate_formal_worldbuilding(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or book.premise.target_style or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_worldbuilding"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "worldbuilding", "power structure"], tags=["worldbuilding", "plot"])
                payload = blueprint_agent.build_worldbuilding_step(research_query=query, style_request=style_request, book=book, planning_context_json=self._planning_context_json(book), reference_pack=reference_pack)
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "worldbuilding", "Step 2 worldbuilding", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_characters(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            volume_titles = [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [getattr(volume, "title", "Volume 1") for volume in book.volumes] or ["Volume 1"]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_characters"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "character bible", "relationship network"], tags=["character", "relationship", "story structure"])
                payload = blueprint_agent.build_character_bible_step(
                    query,
                    book.premise,
                    volume_titles,
                    story_blueprint=dict(book.metadata.get("story_blueprint", {})),
                    planning_context_json=self._planning_context_json(book),
                    reference_pack=reference_pack,
                )
                book.characters = [CharacterCard.model_validate(item) for item in payload.get("characters", [])]
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "character_bible", "Step 3 character bible + relationship network", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_chapter_plans(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            if not book.characters:
                raise ValueError("请先生成人物与关系网，再生成章节规划。")
            query = self._planning_query(book)
            volume_titles = [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [getattr(volume, "title", "Volume 1") for volume in book.volumes] or ["Volume 1"]
            character_milestones = list(book.metadata.get("character_milestones", []))
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_chapter_plans"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "chapter roadmap", "chapter planning"], tags=["chapter roadmap", "story structure", "plot"])
                chapter_plans = blueprint_agent.build_chapter_roadmap(
                    query,
                    book.premise,
                    book.characters,
                    volume_titles,
                    story_blueprint=dict(book.metadata.get("story_blueprint", {})),
                    character_milestones=character_milestones,
                    planning_context_json=self._planning_context_json(book),
                    reference_pack=reference_pack,
                )
                book.metadata["chapter_plans"] = [plan.model_dump(mode="json") for plan in chapter_plans]
                book.metadata["next_chapter_index"] = min(int(book.metadata.get("next_chapter_index", 0)), len(chapter_plans))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "chapter_roadmap", "Step 8 chapter roadmap", {"chapter_plans": [plan.model_dump(mode="json") for plan in chapter_plans]})
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_milestones(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            chapter_plans = [ChapterPlan.model_validate(item) for item in book.metadata.get("chapter_plans", [])]
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_milestones"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "character milestones", "character arcs"], tags=["character", "story structure"])
                milestones = blueprint_agent.build_character_milestones(
                    research_query=query,
                    premise=book.premise,
                    characters=book.characters,
                    story_blueprint=dict(book.metadata.get("story_blueprint", {})),
                    chapter_plans=chapter_plans,
                    planning_context_json=self._planning_context_json(book),
                    reference_pack=reference_pack,
                )
                book.metadata["character_milestones"] = milestones
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "character_milestones", "Step 5 character milestones", {"character_milestones": milestones})
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_event_timeline(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or book.premise.target_style or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_event_timeline"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "event timeline", "cause and effect"], tags=["plot", "story structure"])
                payload = blueprint_agent.build_event_timeline_step(research_query=query, style_request=style_request, book=book, planning_context_json=self._planning_context_json(book), reference_pack=reference_pack)
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "event_timeline", "Step 4 event timeline", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_twist_designs(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or book.premise.target_style or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_twist_designs"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "twist designs", "emotional reversals"], tags=["plot", "twist", "story structure"])
                payload = blueprint_agent.build_twist_designs_step(research_query=query, style_request=style_request, book=book, planning_context_json=self._planning_context_json(book), reference_pack=reference_pack)
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "twist_designs", "Step 6 twist designs", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def generate_formal_story_lines(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            blueprint_agent = self._build_blueprint_agent()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            query = self._planning_query(book)
            style_request = str(book.metadata.get("style_request") or book.premise.target_style or "")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.PLANNING, current_book_id=book.id, context={"action": "generate_story_lines"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[query, "story lines", "chapter titles"], tags=["plot", "chapter roadmap", "story structure"])
                payload = blueprint_agent.build_story_lines_step(research_query=query, style_request=style_request, book=book, planning_context_json=self._planning_context_json(book), reference_pack=reference_pack)
                book.metadata["story_blueprint"] = self._merge_story_blueprint(dict(book.metadata.get("story_blueprint", {})), payload.get("story_blueprint", {}))
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "BlueprintAgent", "story_lines", "Step 7 story lines", payload)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def review_formal_blueprint(self, *, book_id: str) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            critic = self._build_critic()
            memory = MemoryAgent(store=store)
            book = memory.load_book(book_id)
            if book is None:
                raise ValueError(f"Book not found: {book_id}")
            state = WorkflowState(run_id=run_id, stage=WorkflowStage.CRITIQUE, current_book_id=book.id, context={"action": "review_blueprint"})
            memory.save_state(state, mode="formal")
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                reference_pack = self._reference_pack_for_book(memory, run_id=run_id, book=book, stage="planning", focus=[book.title, "blueprint review", "consistency"], tags=["plot", "story structure", "character"])
                volume_titles = [str(item) for item in book.metadata.get("volume_titles", []) if str(item).strip()] or [getattr(volume, "title", "Volume 1") for volume in book.volumes]
                chapter_plans = [ChapterPlan.model_validate(item) for item in book.metadata.get("chapter_plans", [])]
                blueprint = BookBlueprint(
                    blueprint_id=f"blueprint_{book.id}",
                    premise=book.premise,
                    characters=book.characters,
                    volume_titles=volume_titles or ["Volume 1"],
                    chapter_plans=chapter_plans,
                )
                review = critic.review_blueprint(blueprint, reference_pack=reference_pack)
                book.metadata["blueprint_review"] = review
                book.updated_at = datetime.now(timezone.utc)
                memory.save_book(book)
                self._save_output(memory, run_id, "CriticAgent", "blueprint_review", "Blueprint review", review)
                state.stage = WorkflowStage.COMPLETE
                state.updated_at = datetime.now(timezone.utc)
                memory.save_state(state, mode="formal")

        return self._launch_run("formal", run_id, task)

    def continue_formal_novel(self, *, book_id: str | None = None, title: str | None = None) -> str:
        run_id = f"run_{uuid4().hex[:10]}"

        def task(store: SQLiteStore, handle: RunHandle) -> None:
            master = self._build_master(store)
            with EventBus(run_id=run_id, store=store, cancel_event=handle.cancel_event):
                master.continue_novel(book_id=book_id, title=title, run_id=run_id, mode="formal")

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
                updated_book, chapter = writer.write_next_chapter(book)
                check_cancelled()
                memory.save_book(updated_book)
                self._save_output(memory, run_id, "WriterAgent", "chapter_written", f"Chapter written: {chapter.title}", chapter.model_dump(mode="json"))
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

    def _build_llm(self) -> LLMClient:
        return build_llm_client(self.stores.settings)

    def _build_writer(self) -> WriterAgent:
        return WriterAgent(llm_client=self._build_llm(), patch_executor=PatchExecutor())

    def _build_blueprint_agent(self) -> BlueprintAgent:
        return BlueprintAgent(llm_client=self._build_llm())

    def _build_critic(self) -> CriticAgent:
        return CriticAgent(llm_client=self._build_llm())

    def _build_master(self, store: SQLiteStore) -> MasterAgent:
        llm_client = self._build_llm()
        return MasterAgent(
            memory_agent=MemoryAgent(store=store),
            research_agent=ResearchAgent(crawler=MockTrendCrawler()),
            blueprint_agent=BlueprintAgent(llm_client=llm_client),
            writer_agent=WriterAgent(llm_client=llm_client, patch_executor=PatchExecutor()),
            critic_agent=CriticAgent(llm_client=llm_client),
        )

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
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = NovelApp._merge_story_blueprint(dict(merged.get(key, {})), value)
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
                        ),
                    }
                )
                return
            if parsed.path == "/api/novels/generate_outline":
                self._json({"ok": True, "run_id": self.app.generate_formal_outline(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_worldbuilding":
                self._json({"ok": True, "run_id": self.app.generate_formal_worldbuilding(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_characters":
                self._json({"ok": True, "run_id": self.app.generate_formal_characters(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_milestones":
                self._json({"ok": True, "run_id": self.app.generate_formal_milestones(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_event_timeline":
                self._json({"ok": True, "run_id": self.app.generate_formal_event_timeline(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_twist_designs":
                self._json({"ok": True, "run_id": self.app.generate_formal_twist_designs(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_story_lines":
                self._json({"ok": True, "run_id": self.app.generate_formal_story_lines(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/generate_chapter_plans":
                self._json({"ok": True, "run_id": self.app.generate_formal_chapter_plans(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/review_blueprint":
                self._json({"ok": True, "run_id": self.app.review_formal_blueprint(book_id=str(payload.get("book_id", "")))})
                return
            if parsed.path == "/api/novels/continue":
                self._json({"ok": True, "run_id": self.app.continue_formal_novel(book_id=payload.get("book_id"), title=payload.get("title"))})
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
                    chapter_plans=payload.get("chapter_plans"),
                    query=payload.get("query"),
                    user_topic=payload.get("user_topic"),
                    style_request=payload.get("style_request"),
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
.title{font-size:12px;color:#eef2ff;margin-bottom:0}
.payload{font-size:11px;color:#93a0bf;white-space:pre-wrap;word-break:break-word;line-height:1.7}
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
.block{background:#0f131c;border-left:2px solid #4e628f;border-radius:8px;padding:12px;margin:8px 0;white-space:pre-wrap;line-height:1.85}
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
<div id='hdr'><div class='hdr-row'><div class='hdr-brand'><h1>Novel Flow</h1><span id='boot-pill' class='tag'>前端待初始化</span></div><div class='hdr-selects'><select id='modeSel' onchange='changeMode()'><option value='formal'>正式模式</option><option value='test'>测试模式</option></select><select id='novelSel' onchange='selectNovel(this.value)'><option value=''>选择小说</option></select><span id='stage-pill'>未开始</span></div><div class='hdr-primary'><button id='btnNew' onclick='openNewNovelDialog()'>新建小说</button><button id='btnContinue' onclick='continueFormal()'>写下一章</button><button id='btnStop' class='ghost' onclick='stopCurrentRun()' style='display:none'>停止运行</button><button class='danger' onclick='deleteNovel()'>删除小说</button><button id='btnBlueprint' onclick='testBlueprint()' style='display:none'>测试大纲</button><button id='btnWrite' onclick='testWrite()' style='display:none'>测试写正文</button><button id='btnCritique' onclick='testCritique()' style='display:none'>测试评价</button><button id='btnPatch' onclick='testPatch()' style='display:none'>测试修改</button></div></div><div class='hdr-row hdr-steps'><button id='btnStep1' class='step-btn' onclick='generateOutline()'>1 大纲+蓝图</button><button id='btnStep2' class='step-btn' onclick='generateWorldbuilding()'>2 背景系+世界观</button><button id='btnStep3' class='step-btn' onclick='generateCharacters()'>3 角色卡+关系网</button><button id='btnStep4' class='step-btn' onclick='generateEventTimeline()'>4 客观事件时间线</button><button id='btnStep5' class='step-btn' onclick='generateMilestones()'>5 角色发展线</button><button id='btnStep6' class='step-btn' onclick='generateTwistDesigns()'>6 反转设计</button><button id='btnStep7' class='step-btn' onclick='generateStoryLines()'>7 故事线+章节标题</button><button id='btnStep8' class='step-btn' onclick='generateChapterPlans()'>8 章节规划+大纲</button><button id='btnBlueprintReview' class='step-btn' onclick='reviewBlueprint()'>Critic Blueprint</button></div></div>
<div id='newNovelModal' class='modal'><div class='modal-card'><div class='modal-head'><div class='modal-title'>新建小说</div><div class='modal-desc'>这里先保存小说标题、原始题材需求和可选风格，不会自动继续到大纲生成。创建后请手动点击“1 大纲+蓝图”。</div></div><div class='modal-body'><div class='modal-section'><div class='modal-section-title'>基础信息</div><div class='field-grid'><div class='field full'><label>小说标题</label><input id='newTitleInput' placeholder='例如：她非良母' /><div class='field-help'>这里是书名，后续会显示在左上角小说切换列表里，也可以在用户输入页继续修改。</div></div><div class='field full'><label>题材/需求</label><textarea id='newQueryInput' placeholder='例如：都市情感反转，女主发现丈夫隐藏身份后反击'></textarea><div class='field-help'>写清题材、主角处境、核心冲突，或者你最想看到的关键局面。</div></div><div class='field full'><label>风格要求（可留空）</label><textarea id='newStyleInput' placeholder='例如：古言权谋、轻喜剧、短篇悬疑、第三人称群像；留空则由系统自行判断'></textarea><div class='field-help'>这里只在你明确填写时生效，不再默认固定文风或人称。</div></div></div></div><div class='modal-section'><div class='modal-section-title'>扩展配置</div><div class='config-placeholder'>后续可以在这里增加目标体量、章节数、叙事视角、禁用元素、参考卡片范围等配置。当前版本先使用系统默认决策。</div></div></div><div class='modal-actions'><button class='ghost' onclick='closeNewNovelDialog()'>取消</button><button onclick='startFormalFromDialog()'>保存需求</button></div></div></div>
<div id='main'><div id='left'><div id='subhdr'>左侧显示当前小说的历史运行记录，当前运行默认展开</div><div id='evs'><div class='empty'>选择小说或发起一次运行后查看过程</div></div></div><div id='right'><div id='tabs'><div class='tab active' onclick="showTab('input')">用户输入</div><div class='tab' onclick="showTab('blueprint')">小说信息</div><div class='tab' onclick="showTab('text')">小说正文</div><div class='tab' onclick="showTab('critic')">评价结果</div></div><div id='tc'><div id='pnl-input' class='pnl active'><div class='empty'>等待加载用户输入</div></div><div id='pnl-blueprint' class='pnl'><div class='empty'>等待加载小说信息</div></div><div id='pnl-text' class='pnl'><div class='empty'>等待加载小说正文</div></div><div id='pnl-critic' class='pnl'><div class='empty'>等待加载评价结果</div></div></div></div></div>
<script>
let mode='formal',bookId='',pendingRunId='',runsCache=[],expandedRuns=new Set(),boxStates={},detailStates={},currentBook=null,pendingStepRevision=null;
let refreshPaused=false,refreshPauseReason='',refreshPauseTimer=null,isMouseSelecting=false;
const STAGES={research:'调研中',planning:'大纲中',writing:'写作中',critique:'评价中',patching:'修改中',complete:'已完成'};
const stageText=v=>STAGES[v]||v||'未开始',esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),shortTs=v=>v?String(v).replace('T',' ').slice(0,19):'';
async function api(path,opt){const r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json'}},opt||{}));return await r.json();}
function ensureOk(r){if(r&&r.ok===false){alert(r.error||'请求失败');return false;}return true;}
let stepDrafts={},stepDraftDirty={},stepReviewNotes={},stepDraftBookId='';
let stepDraftObjects={};
function deepClone(value){return JSON.parse(JSON.stringify(value??{}));}
function resetStepDraftCache(targetBookId=''){stepDraftBookId=targetBookId;stepDrafts={};stepDraftDirty={};stepReviewNotes={};stepDraftObjects={};}
function stepPayloadFromBook(book,stepKey){const storyBlueprint=book?.metadata?.story_blueprint||{};if(stepKey==='step_1')return{premise:book?.premise||{},story_engine:storyBlueprint.story_engine||{}};if(stepKey==='step_2')return{story_engine:storyBlueprint.story_engine||{}};if(stepKey==='step_3')return{characters:book?.characters||[],relationship_network:Array.isArray(storyBlueprint.relationship_network)?storyBlueprint.relationship_network:[]};if(stepKey==='step_4')return{event_timeline:Array.isArray(storyBlueprint.event_timeline)?storyBlueprint.event_timeline:[]};if(stepKey==='step_5')return{character_milestones:Array.isArray(book?.metadata?.character_milestones)?book.metadata.character_milestones:[]};if(stepKey==='step_6')return{twist_designs:Array.isArray(storyBlueprint.twist_designs)?storyBlueprint.twist_designs:[]};if(stepKey==='step_7')return{story_lines:Array.isArray(storyBlueprint.story_lines)?storyBlueprint.story_lines:[],chapter_briefs:Array.isArray(storyBlueprint.chapter_briefs)?storyBlueprint.chapter_briefs:[]};if(stepKey==='step_8')return{chapter_plans:Array.isArray(book?.metadata?.chapter_plans)?book.metadata.chapter_plans:[]};return{};}
function ensureStepDraft(stepKey,payloadObj){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const serialized=JSON.stringify(payloadObj??{},null,2);if(!(stepKey in stepDrafts)||!stepDraftDirty[stepKey]){stepDrafts[stepKey]=serialized;stepDraftObjects[stepKey]=deepClone(payloadObj??{});}return stepDrafts[stepKey];}
function ensureStepObject(stepKey,payloadObj){ensureStepDraft(stepKey,payloadObj);if(!(stepKey in stepDraftObjects))stepDraftObjects[stepKey]=deepClone(payloadObj??{});return stepDraftObjects[stepKey];}
function updateStepDraft(stepKey,value){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=value;stepDraftDirty[stepKey]=true;try{stepDraftObjects[stepKey]=JSON.parse(value);}catch{}}
function markStepDraftSaved(stepKey,payloadObj,notes){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=JSON.stringify(payloadObj??{},null,2);stepDraftObjects[stepKey]=deepClone(payloadObj??{});stepDraftDirty[stepKey]=false;stepReviewNotes[stepKey]=Array.isArray(notes)?notes:[];}
function applyStepRevisionDraft(result){if(!result||!result.step_key)return;const stepKey=result.step_key;const revisedText=result.draft_json||JSON.stringify(result.step_payload||{},null,2);stepDrafts[stepKey]=revisedText;try{stepDraftObjects[stepKey]=JSON.parse(revisedText);}catch{stepDraftObjects[stepKey]=deepClone(result.step_payload||{});}stepDraftDirty[stepKey]=true;stepReviewNotes[stepKey]=Array.isArray(result.review_notes)?result.review_notes:[];if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function latestOutputByType(runData,outputType){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){if(outs[i]?.output_type===outputType)return outs[i].payload||null;}return null;}
function stepFieldLabel(key){const labels={premise:'大纲主体',story_engine:'写作架构',characters:'角色卡',relationship_network:'关系网',event_timeline:'客观事件时间线',character_milestones:'角色发展线',twist_designs:'反转设计',story_lines:'故事线',chapter_briefs:'章节标题与摘要',chapter_plans:'章节规划',title:'标题',high_concept:'高概念',theme_statement:'立意',story_summary:'故事简介',genre:'题材',target_style:'风格',emotional_hook:'情绪钩子',central_conflict:'核心冲突',core_hook:'核心看点',escalation_path:'升级路径',twist_blueprint:'反转蓝图',ending_payoff:'结尾兑现',selling_points:'卖点',engine_sentence:'故事驱动句',narrative_mode:'叙事结构',viewpoint_strategy:'视角策略',reveal_strategy:'信息揭示策略',hook_strategy:'前三章留人策略',default_track:'默认轨道',world_rules:'世界规则',power_structure:'权力结构',world_map:'世界地图',structural_inertia:'结构惯性',rebound_mechanism:'反弹机制',story_trigger:'故事启动条件',objective_conditions:'客观条件与机会结构',name:'名称',line_type:'线类型',start_state:'起点状态',midpoint_shift:'中段变化',end_state:'终点状态',core_question:'核心问题',chapter_id:'章节编号',active_lines:'挂线',summary:'摘要',turn:'转折',cliffhanger:'悬念',chapter_type:'章型',core_question_left:'留给读者的问题',small_payoff:'小兑现',reader_hook:'读者钩子',new_information:'新信息',relationship_shift:'关系变化',ending_pull:'结尾牵引',objective:'本章任务',tension:'张力',phase:'阶段',story_function:'剧情功能',key_turn:'关键转折',payoff:'兑现',next_route_hint:'下一步提示',target_words:'目标字数',scene_density:'场景密度',scene_beats:'场景节拍',planned_scene_count:'场景数量',scene_id:'场景编号',conflict:'冲突',info_reveal:'信息释放',emotional_shift:'情绪变化',appearance:'外貌'};return labels[key]||String(key).replaceAll('_',' ');}
function parseStepPath(pathText){return String(pathText||'').split('.').filter(Boolean).map(part=>/^[0-9]+$/.test(part)?Number(part):part);}
function setStepValueByPath(root,path,value){if(!path.length)return value;let cursor=root;for(let i=0;i<path.length-1;i+=1){const key=path[i],nextKey=path[i+1];if(Array.isArray(cursor)&&typeof key==='number'){while(cursor.length<=key)cursor.push(typeof nextKey==='number'?[]:{});if(cursor[key]===null||cursor[key]===undefined)cursor[key]=typeof nextKey==='number'?[]:{};cursor=cursor[key];continue;}if(cursor[key]===undefined||cursor[key]===null){cursor[key]=typeof nextKey==='number'?[]:{};}cursor=cursor[key];}const finalKey=path[path.length-1];if(Array.isArray(cursor)&&typeof finalKey==='number'){while(cursor.length<finalKey)cursor.push({});while(cursor.length<=finalKey)cursor.push('');cursor[finalKey]=value;return root;}cursor[finalKey]=value;return root;}
function updateStepEditorValue(stepKey,pathText,kind,rawValue){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const state=ensureStepObject(stepKey,{});const path=parseStepPath(pathText);let value=rawValue;if(kind==='string_array'){value=normalizeMultiline(rawValue).split('\\n').map(item=>item.trim()).filter(Boolean);}else if(kind==='number'){const trimmed=String(rawValue??'').trim();value=trimmed===''?'':Number(trimmed);}else if(kind==='boolean'){value=!!rawValue;}setStepValueByPath(state,path,value);stepDrafts[stepKey]=JSON.stringify(state,null,2);stepDraftDirty[stepKey]=true;}
function renderStepEditorField(stepKey,path,value){const pathText=path.join('.');if(Array.isArray(value)){if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;const primitiveArray=value.every(item=>item===null||['string','number','boolean'].includes(typeof item));if(primitiveArray){return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string_array', this.value)">${esc(value.map(item=>String(item??'')).join('\\n'))}</textarea>`;}return `<div class='step-inline-stack'>${value.map((item,index)=>`<details class='step-inline-card'><summary class='step-inline-card-title'>${esc(stepFieldLabel(String(path[path.length-1]||'item')))} ${index+1}</summary>${renderStepEditorField(stepKey,[...path,index],item)}</details>`).join('')}</div>`;}if(value&&typeof value==='object'){const entries=Object.entries(value);if(!entries.length)return `<div class='step-inline-empty'>当前为空。</div>`;return `<div class='step-inline-root'>${entries.map(([key,val])=>`<div class='step-inline-field'><label>${esc(stepFieldLabel(key))}</label>${renderStepEditorField(stepKey,[...path,key],val)}</div>`).join('')}</div>`;}if(typeof value==='number'){return `<input class='step-inline-input' type='number' value='${esc(value)}' oninput="updateStepEditorValue('${stepKey}','${pathText}','number', this.value)" />`;}if(typeof value==='boolean'){return `<label class='row'><input type='checkbox' ${value?'checked':''} onchange="updateStepEditorValue('${stepKey}','${pathText}','boolean', this.checked)" /> ${value?'是':'否'}</label>`;}return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string', this.value)">${esc(value??'')}</textarea>`;}
function renderStepEditor(stepKey,stepTitle,payloadObj){const notes=Array.isArray(stepReviewNotes[stepKey])?stepReviewNotes[stepKey]:[];const state=ensureStepObject(stepKey,payloadObj);return `<div class='step-editor'><div class='step-editor-toolbar'><div class='step-editor-title'>${esc(stepTitle)} 直接编辑</div><div class='step-editor-actions'><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button></div></div><div class='step-editor-body'>${notes.length?`<ul class='step-editor-notes'>${notes.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:`<div class='step-editor-empty'>可以直接在这个模块里改内容；按 Enter 会换行，点右上角“保存修改”才会真正写回。</div>`}${renderStepEditorField(stepKey,[],state)}<div class='step-editor-hint'>这里是当前步骤的结构化编辑区。质检修改和指令修改会先生成建议稿并回填到这里，确认后再保存。</div></div></div>`;}
function getStepPayloadText(stepKey,payloadObj){const state=ensureStepObject(stepKey,payloadObj);return JSON.stringify(state??{},null,2);}
async function saveStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));const result=await api('/api/novels/save_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text})});if(!ensureOk(result))return;currentBook=result.book;markStepDraftSaved(stepKey,result.step_payload||stepPayloadFromBook(result.book,stepKey),stepReviewNotes[stepKey]||[]);renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();alert('当前步骤修改已保存。');}
async function reviseStepDraft(stepKey,revisionMode){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));let guidance='';if(revisionMode==='instruction'){guidance=prompt('描述你希望这一步结果怎么改：');if(!guidance)return;}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text,revision_mode:revisionMode,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:stepKey,revision_mode:revisionMode,payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:revisionMode==='review'?'步骤质检修改已启动。':'步骤指令修改已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function regenerateRelationshipNetwork(index){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));let guidance;if(index!=null){const item=(currentBook?.blueprint?.relationship_network||[])[index];const label=item?`${item.line_name||''}（${item.subject||''}→${item.target||''}）`:`第 ${index+1} 条`;guidance=`保留当前角色卡 characters 不变，只重新生成 relationship_network 中的第 ${index+1} 条关系：${label}。保留其他条目不动，仅对该条目重新创作，输出完整 relationship_network 数组。不要改动 characters。`;}else{guidance='保留当前角色卡 characters 不变，只重新生成 relationship_network。基于现有角色卡、步骤一和步骤二结果，输出完整详细关系卡，不要改动 characters。';}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:index!=null?`关系网第 ${index+1} 条重新生成任务已启动。`:'关系网重新生成任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseRelationshipNetworkByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望关系网怎么改：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const guidance=`保留当前角色卡 characters 不变，只调整 relationship_network。必须基于现有角色卡展开，不要改动 characters。\n用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'关系网按指令调整任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addCharacterByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述新角色需求（身份、作用、和谁形成关系）：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const guidance=`仅在 characters 中新增 1 个角色，不要删除或重写现有角色；relationship_network 保持不变。新增角色要与现有核心角色形成明确关系，并能推动后续剧情。\n用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'新增角色任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleCharacterByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const r=await api('/api/novels/revise_single_character',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;applyStepRevisionDraft(r);alert('该角色的建议稿已生成，请点“保存修改”后生效。');}
function toggleButtons(){const t=mode==='test';btnNew.style.display=t?'none':'inline-block';btnStep1.style.display=t?'none':'inline-block';btnStep2.style.display=t?'none':'inline-block';btnStep3.style.display=t?'none':'inline-block';btnStep4.style.display=t?'none':'inline-block';btnStep5.style.display=t?'none':'inline-block';btnStep6.style.display=t?'none':'inline-block';btnStep7.style.display=t?'none':'inline-block';btnStep8.style.display=t?'none':'inline-block';btnBlueprintReview.style.display=t?'none':'inline-block';btnContinue.style.display=t?'none':'inline-block';btnBlueprint.style.display=t?'inline-block':'none';btnWrite.style.display=t?'inline-block':'none';btnCritique.style.display=t?'inline-block':'none';btnPatch.style.display=t?'inline-block':'none';}
function updateStopButton(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);btnStop.style.display=a?'inline-block':'none';}
async function loadNovels(){const novels=await api('/api/novels?mode='+mode);novelSel.innerHTML="<option value=''>选择小说</option>";novels.forEach(n=>{const o=document.createElement('option');o.value=n.book_id;o.textContent=n.title||n.book_id;novelSel.appendChild(o);});if(bookId)novelSel.value=bookId;}
async function loadRuns(){if(!bookId){runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];return renderRuns();}runsCache=await api(`/api/runs?mode=${mode}&book_id=${bookId}`);const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();}
function renderEmptyRightPanels(){document.getElementById('pnl-input').innerHTML="<div class='empty'>等待加载用户输入</div>";document.getElementById('pnl-blueprint').innerHTML="<div class='empty'>等待加载小说信息</div>";document.getElementById('pnl-text').innerHTML="<div class='empty'>等待加载小说正文</div>";document.getElementById('pnl-critic').innerHTML="<div class='empty'>等待加载评价结果</div>";showTab('input');}
async function changeMode(){mode=modeSel.value;bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();boxStates={};resetStepDraftCache('');evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';toggleButtons();updateStopButton();await loadNovels();}
async function selectNovel(id){bookId=id;currentBook=null;pendingRunId='';pendingStepRevision=null;expandedRuns=new Set();boxStates={};resetStepDraftCache(id||'');if(!bookId){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';updateStopButton();return;}await refreshNovel();}
async function refreshNovel(){if(!bookId)return;const d=await api(`/api/novel?mode=${mode}&book_id=${bookId}`);if(!d.book)return;if(stepDraftBookId!==d.book.id)resetStepDraftCache(d.book.id);const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);const scrollState=captureScrollState();currentBook=d.book;if(!editingInRight){renderInputPanel(d.book);renderBlueprint(d.book,d.blueprint_review);renderText(d.book);renderCritic(d.critic);}stagePill.textContent=stageText(d.latest_stage);runsCache=d.runs||[];const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();await loadNovels();restoreScrollState(scrollState);}
async function refreshPendingRun(){if(!pendingRunId)return;const trackedRunId=pendingRunId;const d=await api(`/api/run?mode=${mode}&run_id=${trackedRunId}`);stagePill.textContent=stageText(d.stage||'writing');const running=d.is_running!==false;if(running){runsCache=[{run_id:trackedRunId,is_running:true,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),pending_message:'运行中，等待模型返回更多内容。'},...runsCache.filter(x=>x.run_id!==trackedRunId)];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();return;}let revisionPayload=latestOutputByType(d,'step_revision_draft');const completedRevision=pendingStepRevision&&pendingStepRevision.run_id===trackedRunId?pendingStepRevision:null;pendingRunId='';pendingStepRevision=null;if(!revisionPayload&&completedRevision&&completedRevision.step_key&&completedRevision.payload_text){const fallback=await api('/api/novels/revise_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:completedRevision.step_key,payload_text:completedRevision.payload_text,revision_mode:completedRevision.revision_mode||'instruction',guidance:completedRevision.guidance||''})});if(ensureOk(fallback)){revisionPayload=fallback;}}if(revisionPayload)applyStepRevisionDraft(revisionPayload);if(d.current_book_id){bookId=d.current_book_id;novelSel.value=bookId;await refreshNovel();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}return;}runsCache=[{run_id:trackedRunId,is_running:false,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),pending_message:'运行已结束，查看下方最新事件。'}];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}}
function boxHtml(key,title,payloadHtml,isOpen){return `<details class='box' ${isOpen?'open':''} ontoggle="toggleBox('${key}', this.open)"><summary><span class='title'>${title}</span></summary><div class='payload'>${payloadHtml}</div></details>`}
function toggleBox(key,isOpen){boxStates[key]=isOpen;}
const toArray=v=>Array.isArray(v)?v.filter(Boolean):[];
const jsonHtml=v=>`<div class='pre json'>${esc(JSON.stringify(v??{},null,2))}</div>`;
const chipsHtml=v=>{const items=toArray(v);return items.length?`<div class='chips'>${items.map(item=>`<span class='chip'>${esc(item)}</span>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
const linesHtml=v=>{const items=toArray(v);return items.length?`<div class='mini-list'>${items.map(item=>`<div class='mini-item'>${esc(item)}</div>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
function infoRow(label,value){if(value===undefined||value===null||value==='')return '';return `<div class='kv'><div class='k'>${esc(label)}</div><div>${esc(value)}</div></div>`}
function sectionHtml(label,body){return `<div class='subsec'>${esc(label)}</div>${body}`}
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
function renderStageEvent(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('原因', payload&&payload.reason||'');
  html+="</div>";
  return html;
}
function renderErrorEvent(payload){
  return `<div class='agent-view'>${infoRow('错误', payload&&payload.error||'未知错误')}</div>`;
}
function renderItemPayload(item){
  if(item.kind==='output'&&item.outputType==='director_decision')return renderDirectorDecision(item.rawPayload);
  if(item.kind==='output'&&item.outputType==='reference_cards')return renderReferenceCards(item.rawPayload);
  if(item.kind==='output'&&item.outputType==='tool_observation')return renderToolObservation(item.rawPayload);
  if(item.kind==='event'&&item.eventType==='stage')return renderStageEvent(item.rawPayload);
  if(item.kind==='event'&&item.eventType==='error')return renderErrorEvent(item.rawPayload);
  if(item.kind==='plain')return `<div class='pre'>${esc(item.text||'')}</div>`;
  return jsonHtml(item.rawPayload);
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
function buildStreamItems(runId,evts){const groups=[],byId={};let active=null,seq=0;function ensureGroup(callId,ts,agent){const key=callId||`legacy_${++seq}`;if(byId[key]){if(agent&&!byId[key].agent)byId[key].agent=agent;return byId[key];}const group={key,text:'',reply:'',sortTs:ts||'',done:false,agent:agent||''};byId[key]=group;groups.push(group);return group;}evts.forEach(e=>{const payload=e.payload||{},callId=payload.call_id||'';if(e.event_type==='llm_prompt'){active=ensureGroup(callId||`prompt_${e.id||++seq}`,e.ts,e.agent);active.prompt=payload.preview||'';}else if(e.event_type==='llm_stream'){const group=callId?ensureGroup(callId,e.ts,e.agent):(active&&!active.done?active:ensureGroup(`stream_${e.id||++seq}`,e.ts,e.agent));group.text+=payload.preview||'';group.sortTs=e.ts||group.sortTs;if(e.agent&&!group.agent)group.agent=e.agent;}else if(e.event_type==='llm_reply'){const group=callId?ensureGroup(callId,e.ts,e.agent):active;if(group){group.reply=payload.preview||'';group.done=true;group.sortTs=e.ts||group.sortTs;if(e.agent&&!group.agent)group.agent=e.agent;}}});return groups.filter(group=>group.text||group.reply).map((group,index)=>({key:`${runId}:stream:${group.key}`,title:`${group.agent||'LLM'} · 流式输出 #${index+1}`,kind:'plain',text:group.text||group.reply||'',sortTs:group.sortTs||''}));}
async function renderRuns(pref){const scrollState=captureLeftScrollState();if(!runsCache.length){evs.innerHTML="<div class='empty'>??????</div>";restoreLeftScrollState(scrollState);return;}const cache=pref||{};for(const r of runsCache){if(expandedRuns.has(r.run_id)&&!cache[r.run_id])cache[r.run_id]=await api(`/api/run?mode=${mode}&run_id=${r.run_id}`);}let html='';runsCache.forEach(r=>{const ex=expandedRuns.has(r.run_id),d=cache[r.run_id],outs=(d&&d.outputs)||[],evts=(d&&d.events)||[];const streamItems=buildStreamItems(r.run_id,evts);const normalEvents=evts.filter(e=>!['llm_stream','llm_prompt','llm_reply'].includes(e.event_type));const items=[];if(r.pending_message)items.push({key:`${r.run_id}:pending`,title:'???',kind:'plain',text:r.pending_message,sortTs:r.updated_at||''});streamItems.forEach(item=>items.push(item));outs.forEach(o=>items.push({key:`${r.run_id}:out:${o.id}`,title:`${esc(o.agent)} ? ${esc(o.title)}`,kind:'output',outputType:o.output_type,rawPayload:o.payload,sortTs:o.created_at||''}));normalEvents.forEach(e=>items.push({key:`${r.run_id}:evt:${e.id}`,title:`${esc(e.agent||'System')} ? ${esc(e.title||'')}`,kind:'event',eventType:e.event_type,rawPayload:e.payload,sortTs:e.ts||''}));items.sort((a,b)=>String(a.sortTs).localeCompare(String(b.sortTs)));html+=`<div class='run'><div class='head' onclick="toggleRun('${r.run_id}')"><span class='tag'>${esc(stageText(r.stage))}</span>${r.is_running?"<span class='tag live'>???</span>":''}${r.cancel_requested?"<span class='tag stop'>???</span>":''}<span>${esc(r.run_id)}</span><span class='ts'>${esc(shortTs(r.updated_at))}</span></div>`;if(ex){html+="<div class='body'>";if(r.is_running)html+=`<div style='margin-bottom:8px'><button class='ghost' onclick="event.stopPropagation();stopRun('${r.run_id}')">?????</button></div>`;if(!items.length)html+="<div class='payload'>??????</div>";items.forEach((item,index)=>{const isLatest=index===items.length-1;const isOpen=(item.key in boxStates)?boxStates[item.key]:isLatest;html+=boxHtml(item.key,item.title,renderItemPayload(item),isOpen);});html+='</div>';}html+='</div>';});evs.innerHTML=html;restoreLeftScrollState(scrollState);}
function toggleRun(id){expandedRuns.has(id)?expandedRuns.delete(id):expandedRuns.add(id);renderRuns();}
async function stopCurrentRun(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);if(!a)return alert('当前没有运行中的任务。');await stopRun(a.run_id);}
async function stopRun(id){if(!confirm('确认删除此运行记录？'))return;await api('/api/runs/stop',{method:'POST',body:JSON.stringify({mode,run_id:id})});expandedRuns.delete(id);if(pendingRunId===id){pendingRunId='';pendingStepRevision=null;}runsCache=runsCache.filter(x=>x.run_id!==id);bookId?await refreshNovel():renderRuns();updateStopButton();}
function summarizeBlock(text){const cleaned=String(text||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').split(' ').filter(Boolean).join(' ');return cleaned||'（空白内容）';}
function isDetailOpen(key,defaultOpen=true){return key in detailStates?detailStates[key]:defaultOpen;}
function toggleDetailState(key,isOpen){detailStates[key]=isOpen;}
function autoSizeTextareas(rootId){document.querySelectorAll(`#${rootId} textarea`).forEach(el=>{const resize=()=>{el.style.height='auto';el.style.height=`${el.scrollHeight}px`;el.style.overflow='hidden';};if(!el.dataset.autosizeBound){el.addEventListener('input',resize);el.dataset.autosizeBound='1';}resize();});}
function captureScrollState(){const activePanel=document.querySelector('.pnl.active');const tc=document.getElementById('tc');return{windowX:window.scrollX,windowY:window.scrollY,leftScrollTop:evs?evs.scrollTop:0,rightScrollTop:tc?tc.scrollTop:0,activePanelId:activePanel?activePanel.id:'',activePanelScrollTop:activePanel?activePanel.scrollTop:0};}
function captureLeftScrollState(){return{leftScrollTop:evs?evs.scrollTop:0};}
function restoreScrollState(state){if(!state)return;requestAnimationFrame(()=>{window.scrollTo(state.windowX||0,state.windowY||0);if(evs)evs.scrollTop=state.leftScrollTop||0;const tc=document.getElementById('tc');if(tc)tc.scrollTop=state.rightScrollTop||0;if(state.activePanelId){const panel=document.getElementById(state.activePanelId);if(panel)panel.scrollTop=state.activePanelScrollTop||0;}});}
function restoreLeftScrollState(state){if(!state)return;requestAnimationFrame(()=>{if(evs)evs.scrollTop=state.leftScrollTop||0;});}
function setAllInputBlocks(open){document.querySelectorAll('#pnl-input details.input-block').forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas('pnl-input');}
function setPanelSections(panelId,open){document.querySelectorAll(`#${panelId} details.section-card`).forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas(panelId);}
function normalizeMultiline(value){const cr=String.fromCharCode(13),lf=String.fromCharCode(10);return String(value??'').split(cr+lf).join(lf).split(cr).join(lf).trimEnd();}
function openNewNovelDialog(){newNovelModal.style.display='flex';newTitleInput.focus();}
function closeNewNovelDialog(){newNovelModal.style.display='none';}
async function startFormalFromDialog(){const title=newTitleInput.value.trim();const q=normalizeMultiline(newQueryInput.value);if(!q)return alert('请输入题材/需求。');const style=normalizeMultiline(newStyleInput.value);const r=await api('/api/novels/create',{method:'POST',body:JSON.stringify({mode,title,query:q,style_request:style})});if(!ensureOk(r))return;closeNewNovelDialog();bookId=r.book.id;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();currentBook=r.book;stagePill.textContent='未开始';await loadNovels();novelSel.value=bookId;await refreshNovel();updateStopButton();}
async function startPlanningRun(path,message){if(!bookId)return alert('请先选择一部小说。');const r=await api(path,{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:message},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function generateOutline(){await startPlanningRun('/api/novels/generate_outline','大纲+蓝图生成中');}
async function generateWorldbuilding(){await startPlanningRun('/api/novels/generate_worldbuilding','世界观+背景体系生成中');}
async function generateCharacters(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_characters',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'角色卡+关系网生成中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function generateMilestones(){await startPlanningRun('/api/novels/generate_milestones','角色发展线生成中');}
async function generateEventTimeline(){await startPlanningRun('/api/novels/generate_event_timeline','事件时间线生成中');}
async function generateTwistDesigns(){await startPlanningRun('/api/novels/generate_twist_designs','反转设计生成中');}
async function generateStoryLines(){await startPlanningRun('/api/novels/generate_story_lines','故事线+章节标题生成中');}
async function generateChapterPlans(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_chapter_plans',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'章节规划+大纲生成中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviewBlueprint(){await startPlanningRun('/api/novels/review_blueprint','Blueprint Critic 评审中');}
async function continueFormal(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/continue',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'正在写下一章，请稍候...'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function deleteNovel(){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除此小说？该操作不可撤销。'))return;await api('/api/novels/delete',{method:'POST',body:JSON.stringify({mode,book_id:bookId})});bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();evs.innerHTML="<div class='empty'>????????????????</div>";renderEmptyRightPanels();stagePill.textContent='未开始';await loadNovels();updateStopButton();}
async function testBlueprint(){const q=prompt('输入题材需求（测试大纲）：');if(!q)return;const r=await api('/api/test/blueprint',{method:'POST',body:JSON.stringify({query:q})});pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'测试大纲运行中'}]:[];await renderRuns();updateStopButton();}
async function testWrite(){let r;if(bookId)r=await api('/api/test/write',{method:'POST',body:JSON.stringify({book_id:bookId})});else{const q=prompt('输入题材需求（测试写作）：');if(!q)return;r=await api('/api/test/write',{method:'POST',body:JSON.stringify({query:q})});}pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'测试写作运行中'}]:[];await renderRuns();updateStopButton();}
async function testCritique(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/test/critique',{method:'POST',body:JSON.stringify({book_id:bookId})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'critique',updated_at:new Date().toISOString(),pending_message:'测试评价运行中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function testPatch(){if(!bookId)return alert('请先选择一部小说。');const blockId=prompt('请输入 block_id：');if(!blockId)return;const operation=prompt('操作类型 replace / append / prepend','replace')||'replace';const patchContent=prompt('补丁内容：');if(!patchContent)return;const reason=prompt('修改原因：','manual test patch')||'manual test patch';const r=await api('/api/test/patch',{method:'POST',body:JSON.stringify({book_id:bookId,block_id:blockId,operation,patch_content:patchContent,reason})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'测试补丁运行中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseConcept(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你希望 AI 怎么修改概念：');if(!guidance)return;const r=await api('/api/novels/ai_update_concept',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'AI 修改中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseText(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt(scope==='chapter'?'描述你希望 AI 怎么修改这章：':'描述你希望 AI 怎么修改这段：');if(!guidance)return;const r=await api('/api/novels/ai_update_text',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'AI 修改文本中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}

async function resolveCharacterCandidate(candidateId,action){
  if(!bookId)return alert('请先选择一部小说。');
  const result=await api('/api/novels/resolve_character_candidate',{method:'POST',body:JSON.stringify({mode,book_id:bookId,candidate_id:candidateId,action})});
  if(!ensureOk(result))return;
  currentBook=result.book;
  renderInputPanel(currentBook);
  renderBlueprint(currentBook);
  renderText(currentBook);
  await loadNovels();
  alert(action==='add'?'角色已添加':'已设为仅本场景');
}

function renderInputPanel(book){
  const currentQuery=book?.metadata?.query||'';
  const userTopic=book?.metadata?.user_topic||'';
  const styleRequest=book?.metadata?.style_request||'';
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
  const html=`<div class='card'><div class='sec'>用户输入</div><div class='input-hero'><div class='input-hero-copy'><div class='input-hero-kicker'>小说基础设置</div><div class='input-hero-title-row'><h2 class='input-hero-title'>${esc(book?.title||'未命名小说')}</h2><span class='input-hero-badge'>写作控制台</span></div><div class='input-hero-desc'>${heroSummary}</div></div><div class='input-toolbar'><div class='actions'><button class='ghost' onclick='setAllInputBlocks(true)'>全部展开</button><button class='ghost' onclick='setAllInputBlocks(false)'>全部折叠</button><button onclick='saveConcept()'>保存所有修改</button></div></div></div><div class='title-field'><label>书名标题</label><input id='concept-title' value='${esc(book?.title||'')}' placeholder='输入小说书名' /></div><div class='input-blocks'>${block('input-query','concept-query','题材与需求',currentQuery,'支持 Markdown 详细描述题材','此内容影响步骤 1-8 的生成',true)}${block('input-topic','concept-user-topic','用户主题',userTopic,'可选填写用户关注的主题方向','仅在明确时填写',false)}${block('input-style','concept-style-request','风格要求',styleRequest,'留空则由系统判断风格','明确时填写，不填则自动决策',false)}${writingBlock}</div></div>`;
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
  const stepSection=(stepKey,title,summary,body,defaultOpen=false)=>{const badge=stepDraftDirty[stepKey]?`<span class='dirty-dot'>●未保存</span>`:'';const acts=`${badge}<button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存</button>`;return toolbarSection(stepKey,title,summary,acts,body,defaultOpen);};
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
  const charActions=`${dirtyBadge}<button class='ghost' onclick="addCharacterByInstruction()">增加角色</button><button class='ghost' onclick="reviseStepDraft('step_3','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('step_3','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存</button>`;
  html+=toolbarSection('step3-characters','3 角色卡',`${displayCharacters.length} 个角色`,charActions,characterCards,false);
  html+=stepSection('step_4','4 客观事件时间线',`${(blueprint.event_timeline||[]).length} 条`,subStepEditor('step_4','event_timeline','事件时间线'));
  html+=stepSection('step_5','5 角色发展线',`${(book?.metadata?.character_milestones||[]).length} 条发展线`,subStepEditor('step_5','character_milestones','角色发展线'));
  html+=stepSection('step_6','6 反转设计',`${(blueprint.twist_designs||[]).length} 个反转`,subStepEditor('step_6','twist_designs','反转设计'));
  html+=stepSection('step_7','7 故事线+章节标题',`${(blueprint.story_lines||[]).length} 条故事线 / ${(blueprint.chapter_briefs||[]).length} 章`,subStepEditor('step_7','story_lines','故事线')+subStepEditor('step_7','chapter_briefs','章节标题'));
  html+=stepSection('step_8','8 章节规划+大纲',`${(book?.metadata?.chapter_plans||[]).length} 章`,subStepEditor('step_8','chapter_plans','章节规划'));
  if(blueprintReview){html+=sectionCard('blueprint-review','Critic Blueprint',blueprintReview.summary||'暂无评审结论',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', blueprintReview.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((blueprintReview.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}`),'暂无问题')}</div></div>`,false);}
  document.getElementById('pnl-blueprint').innerHTML=html;
  autoSizeTextareas('pnl-blueprint');
}
function renderText(book){
  const volumes=book?.volumes||[];
  const chapters=[];
  const candidates=Array.isArray(book?.metadata?.new_character_candidates)?book.metadata.new_character_candidates:[];
  volumes.forEach(volume=>(volume.chapters||[]).forEach(chapter=>chapters.push({volume,chapter})));
  const sectionCard=(key,title,summary,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  if(!chapters.length && !candidates.length){document.getElementById('pnl-text').innerHTML="<div class='empty'>暂无内容</div>";return;}
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说正文</div><div class='panel-title'>章节内容</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-text',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-text',false)">全部折叠</button></div></div>`;
  if(candidates.length){
    const cards=candidates.map((item,index)=>{
      const traits=Array.isArray(item?.provisional_traits)?item.provisional_traits.filter(Boolean):[];
      const links=Array.isArray(item?.links_to_existing_characters)?item.links_to_existing_characters.filter(link=>link&&typeof link==='object'):[];
      const linkLines=links.length?links.map(link=>`<div class='kv'><div class='k'>${esc(link.target||'未知角色')}</div><div>${esc(link.relation||'未知关系')}</div></div>`).join(''):"<div class='relationship-empty'>暂无关联角色</div>";
      return `<div class='relationship-card'><div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'><div><div class='subsec'>${esc(item?.name||`角色候选 ${index+1}`)}</div><div class='muted'>首登场：${esc(item?.first_appearance_chapter||'待定')}</div></div><div class='actions'><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','add')">确认添加</button><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','scene_only')">仅本场景</button></div></div>${infoRow('场景作用', item?.role_in_scene||'')}${infoRow('存在理由', item?.why_needed||'')}${traits.length?sectionHtml('特征', chipsHtml(traits)):''}${sectionHtml('与现有角色关联', linkLines)}</div>`;
    }).join('');
    html+=sectionCard('text-character-candidates','新角色候选',`共 ${candidates.length} 个候选角色`,`<div class='relationship-stack'>${cards}</div>`,true);
  }
  chapters.forEach(({volume,chapter},index)=>{
    const title=chapter.title||chapter.id||`第${index+1}章`;
    const summary=chapter.summary||'暂无摘要';
    const scenes=(chapter.scenes||[]).map((scene,sceneIndex)=>{
      const blocks=(scene.blocks||[]).map((block,blockIndex)=>`<div class='block' style='margin-top:8px'><div class='row'><strong>块 ${blockIndex+1}</strong>${block.purpose?` <span class='muted'>${esc(block.purpose)}</span>`:''}</div><div>${esc(block.text||'')}</div></div>`).join('')||"<div class='relationship-empty'>暂无段落内容</div>";
      return `<div class='relationship-card'><div class='subsec'>场景 ${sceneIndex+1}${scene.title?` · ${esc(scene.title)}`:''}</div>${infoRow('场景概述', scene.summary||'')}${blocks}</div>`;
    }).join('')||"<div class='relationship-empty'>暂无场景</div>";
    const body=`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>基础信息</div>${infoRow('卷名', volume.title||volume.id||'')}${infoRow('章节标题', title)}${infoRow('章节概述', summary)}</div><div class='relationship-card'><div class='subsec'>场景</div><div class='relationship-stack'>${scenes}</div></div></div>`;
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
const btnNew=document.getElementById('btnNew'),btnStep1=document.getElementById('btnStep1'),btnStep2=document.getElementById('btnStep2'),btnStep3=document.getElementById('btnStep3'),btnStep4=document.getElementById('btnStep4'),btnStep5=document.getElementById('btnStep5'),btnStep6=document.getElementById('btnStep6'),btnStep7=document.getElementById('btnStep7'),btnStep8=document.getElementById('btnStep8'),btnBlueprintReview=document.getElementById('btnBlueprintReview'),btnContinue=document.getElementById('btnContinue'),btnBlueprint=document.getElementById('btnBlueprint'),btnWrite=document.getElementById('btnWrite'),btnCritique=document.getElementById('btnCritique'),btnPatch=document.getElementById('btnPatch'),btnStop=document.getElementById('btnStop'),stagePill=document.getElementById('stage-pill'),bootPill=document.getElementById('boot-pill'),novelSel=document.getElementById('novelSel'),modeSel=document.getElementById('modeSel'),evs=document.getElementById('evs'),newNovelModal=document.getElementById('newNovelModal'),newTitleInput=document.getElementById('newTitleInput'),newQueryInput=document.getElementById('newQueryInput'),newStyleInput=document.getElementById('newStyleInput');
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
    toggleButtons();
    await loadNovels();
    if(bootPill)bootPill.textContent=`前端已加载 ${Math.max((novelSel?.options?.length||1)-1,0)} 本`;
    updateStopButton();
    setInterval(async()=>{
      if(refreshPaused)return;
      if(bookId)await refreshNovel();
      if(pendingRunId)await refreshPendingRun();
    },1500);
  }catch(err){
    showFrontendError(err?.message||String(err));
  }
}
initApp();
</script></body></html>"""

