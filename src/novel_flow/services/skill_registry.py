from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    tools: list[str]
    triggers: list[str]
    success_condition: dict[str, Any]
    max_iterations: int
    instruction_text: str
    path: Path


class SkillRegistry:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[3] / "skills"
        self._cache: dict[str, SkillDefinition] | None = None

    def load_all(self) -> dict[str, SkillDefinition]:
        if self._cache is not None:
            return self._cache
        skills: dict[str, SkillDefinition] = {}
        if not self.base_dir.exists():
            self._cache = skills
            return skills
        for skill_dir in sorted(path for path in self.base_dir.iterdir() if path.is_dir()):
            manifest_path = skill_dir / "manifest.json"
            instruction_path = skill_dir / "SKILL.md"
            if not manifest_path.exists() or not instruction_path.exists():
                continue
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            skill_id = str(payload.get("skill_id") or skill_dir.name).strip()
            if not skill_id:
                continue
            skills[skill_id] = SkillDefinition(
                skill_id=skill_id,
                tools=[str(item).strip() for item in payload.get("tools", []) if str(item).strip()],
                triggers=[str(item).strip() for item in payload.get("triggers", []) if str(item).strip()],
                success_condition=dict(payload.get("success_condition", {}) or {}),
                max_iterations=max(1, int(payload.get("max_iterations", 1))),
                instruction_text=instruction_path.read_text(encoding="utf-8").strip(),
                path=skill_dir,
            )
        self._cache = skills
        return skills

    def get(self, skill_id: str) -> SkillDefinition:
        skills = self.load_all()
        if skill_id not in skills:
            raise KeyError(f"Skill not found: {skill_id}")
        return skills[skill_id]
