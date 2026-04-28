from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_flow.models.schemas import CharacterCard, ChapterBrief, StoryPremise, StoryLine, TwistDesign

DEFAULT_CASES_DIR = Path("evals/romance/cases")


def load_step_fixture(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def step_fixture_path(case_id: str, cases_dir: str | Path = DEFAULT_CASES_DIR) -> Path:
    return Path(cases_dir) / case_id / "steps.json"


def iter_step_fixture_paths(cases_dir: str | Path = DEFAULT_CASES_DIR) -> list[Path]:
    root = Path(cases_dir)
    return sorted(path for path in root.glob("*/steps.json") if not path.parts[-2].startswith("_"))


def validate_step_fixture(path: str | Path) -> dict[str, Any]:
    payload = load_step_fixture(path)
    step1 = dict(payload.get("step_1") or {})
    step3 = dict(payload.get("step_3") or {})
    step6 = dict(payload.get("step_6") or {})
    step7 = dict(payload.get("step_7") or {})
    step8 = dict(payload.get("step_8") or {})
    story_engine = dict(step1.get("story_engine") or {})
    world_rules = list(story_engine.get("world_rules") or [])
    worldbuilding_detail = dict(story_engine.get("worldbuilding_detail") or step1.get("worldbuilding_detail") or {})
    StoryPremise.model_validate(step1.get("premise") or {})
    characters = [CharacterCard.model_validate(item) for item in step3.get("characters") or []]
    developed_characters = [
        item
        for item in step3.get("characters") or []
        if isinstance(item, dict) and len(item.get("development_axes") or []) >= 2
    ]
    twists = [TwistDesign.model_validate(item) for item in step6.get("twist_designs") or []]
    lines = [StoryLine.model_validate(item) for item in step7.get("story_lines") or []]
    briefs = [ChapterBrief.model_validate(item) for item in step8.get("chapter_briefs") or []]
    return {
        "case_id": payload.get("case_id", ""),
        "world_rules": len(world_rules),
        "worldbuilding_detail_sections": len(worldbuilding_detail),
        "characters": len(characters),
        "developed_characters": len(developed_characters),
        "character_deep_cards": len(step3.get("character_deep_cards") or []),
        "twist_designs": len(twists),
        "story_lines": len(lines),
        "chapter_briefs": len(briefs),
    }
