from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"

TEXT_EXTS = {".txt", ".md", ".yaml", ".yml"}
MOJIBAKE_TOKENS = [
    "?", "?", "?", "?", "?", "?", "?", "?", "?", "?", "?"
]
QUESTION_RE = re.compile(r"\?{4,}")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in PROMPTS.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_EXTS:
            files.append(path)
    return sorted(files)


def inspect(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"not valid UTF-8: {exc}"]

    for token in MOJIBAKE_TOKENS:
        if token in text:
            issues.append(f"contains suspicious mojibake token: {token}")
            break

    for i, line in enumerate(text.splitlines(), start=1):
        if QUESTION_RE.search(line):
            # allow placeholder braces/questions in English JSON docs, but repeated ? in prompt prose is suspicious
            issues.append(f"line {i}: contains repeated question marks")
            break

    return issues


def main() -> int:
    bad = []
    for path in iter_files():
        issues = inspect(path)
        if issues:
            bad.append((path, issues))

    if not bad:
        print("prompt encoding check passed")
        return 0

    print("prompt encoding check failed")
    for path, issues in bad:
        rel = path.relative_to(ROOT)
        print(f"- {rel}")
        for issue in issues:
            print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
