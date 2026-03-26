from __future__ import annotations

from pathlib import Path


class PromptLibrary:
    """Loads prompt templates from the repository-level prompts directory."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[3] / "prompts"

    def load(self, relative_path: str) -> str:
        template_path = self.base_dir / relative_path
        return template_path.read_text(encoding="utf-8").strip()

    def render(self, relative_path: str, **kwargs: object) -> str:
        template = self.load(relative_path)
        return template.format(**kwargs)
