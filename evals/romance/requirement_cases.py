from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evals.romance.models import RomanceEvalCase
from novel_flow.models.schemas import BookDocument, StoryPremise, Volume
from novel_flow.storage.sqlite_store import SQLiteStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_user_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").rstrip()


class RequirementCaseUserInput(BaseModel):
    title: str
    query: str
    style_request: str = ""
    user_topic: str = ""
    assistant_persona_prompt: str = ""


class RequirementCaseBinding(BaseModel):
    book_id: str
    mode: Literal["test", "formal"] = "test"
    db_path: str = "data/novel_flow_test.db"
    entry_stage: Literal["step"] = "step"
    checkpoint_chapters: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    is_self_improve_test_case: bool = True


class SelfImproveRequirementCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_type: Literal["self_improve_requirement_case"] = "self_improve_requirement_case"
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    user_input: RequirementCaseUserInput
    self_improve_binding: RequirementCaseBinding
    eval_fixture: RomanceEvalCase | None = None

    def to_seed_book(self, *, case_path: str = "") -> BookDocument:
        now = _utc_now()
        clean_query = _clean_user_text(self.user_input.query)
        clean_style = _clean_user_text(self.user_input.style_request)
        clean_title = _clean_user_text(self.user_input.title).strip()
        clean_topic = _clean_user_text(self.user_input.user_topic)
        clean_persona = _clean_user_text(self.user_input.assistant_persona_prompt)
        title_hint = clean_title or (clean_query.strip().splitlines()[0][:24] or self.title or self.case_id).strip()
        binding_payload = self.self_improve_binding.model_dump(mode="json")
        metadata: dict[str, Any] = {
            "query": clean_query,
            "original_query": clean_query,
            "user_topic": clean_topic,
            "style_request": clean_style,
            "assistant_persona_prompt": clean_persona,
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
            "self_improve_test_case": True,
            "self_improve_case_id": self.case_id,
            "self_improve_case_title": self.title,
            "self_improve_case_description": self.description,
            "self_improve_case_tags": list(self.tags),
            "self_improve_binding": binding_payload,
            "self_improve_case_path": case_path,
            "self_improve_seed_source": "requirement_case",
            "self_improve_seeded_at": now.isoformat(),
        }
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
        return BookDocument(
            id=self.self_improve_binding.book_id,
            title=title_hint,
            premise=premise,
            characters=[],
            volumes=[Volume(id="vol_001", title="Volume 1", summary="", chapters=[])],
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )


def _iter_case_paths(case_dir: Path) -> list[Path]:
    return sorted(path for path in case_dir.glob("*.json") if path.name != "export_summary.json")


def load_requirement_case(case_path: Path) -> SelfImproveRequirementCase:
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    return SelfImproveRequirementCase.model_validate(payload)


def load_requirement_cases(case_dir: Path, *, case_ids: list[str] | None = None) -> list[SelfImproveRequirementCase]:
    selected = set(case_ids or [])
    cases: list[SelfImproveRequirementCase] = []
    found_selected: set[str] = set()
    for case_path in _iter_case_paths(case_dir):
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "user_input" not in payload or "self_improve_binding" not in payload:
            continue
        case = SelfImproveRequirementCase.model_validate(payload)
        if selected and case.case_id not in selected:
            continue
        cases.append(case)
        found_selected.add(case.case_id)
    if selected:
        missing = sorted(selected - found_selected)
        if missing:
            raise FileNotFoundError(f"Missing self-improve requirement cases: {', '.join(missing)}")
    return cases


def seed_requirement_cases(
    *,
    db_path: str | Path,
    case_dir: str | Path,
    case_ids: list[str] | None = None,
    reset_existing: bool = True,
) -> list[dict[str, Any]]:
    store = SQLiteStore(Path(db_path))
    root = Path.cwd()
    selected = set(case_ids or [])
    seeded: list[dict[str, Any]] = []
    for case_path in _iter_case_paths(Path(case_dir)):
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "user_input" not in payload or "self_improve_binding" not in payload:
            continue
        case = SelfImproveRequirementCase.model_validate(payload)
        if selected and case.case_id not in selected:
            continue
        if reset_existing and store.load_book(case.self_improve_binding.book_id):
            store.delete_book(case.self_improve_binding.book_id)
        relative_path = case_path.resolve().relative_to(root.resolve()) if case_path.resolve().is_relative_to(root.resolve()) else case_path.resolve()
        book = case.to_seed_book(case_path=str(relative_path).replace("\\", "/"))
        store.save_book(book)
        seeded.append(
            {
                "case_id": case.case_id,
                "case_path": str(relative_path).replace("\\", "/"),
                "book_id": case.self_improve_binding.book_id,
                "mode": case.self_improve_binding.mode,
                "title": case.title,
                "novel_title": book.title,
            }
        )
    return seeded
