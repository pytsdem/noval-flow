from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path("evals/romance/reports")
RUNS_ROOT = ROOT / "runs"
TEMPLATES_ROOT = ROOT / "templates"
LIVE_ROOT = ROOT / "self_improve_live"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".yml", ".yaml"}
SKIP_DIRS = {"self_improve_live", "runs", "templates", "__pycache__"}


@dataclass
class ReportEntry:
    old_dir: str
    new_dir: str
    label: str
    generated_at: str
    date_key: str
    provider: str
    model: str
    case_bucket: str
    case_ids: list[str]
    kind: str


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> dict:
    return json.loads(_read_text(path))


def _slug(value: str, *, fallback: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^0-9a-zA-Z._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or fallback


def _date_key(iso_value: str, *, fallback_path: Path) -> str:
    if iso_value:
        try:
            return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).strftime("%Y%m%d")
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_path.stat().st_mtime).strftime("%Y%m%d")


def _case_bucket(case_ids: Iterable[str]) -> str:
    normalized = [str(case_id).strip() for case_id in case_ids if str(case_id).strip()]
    if not normalized:
        return "multi_case__unknown"
    if len(normalized) == 1:
        return normalized[0]
    return f"multi_case__{len(normalized)}cases"


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _resolve_entry(path: Path) -> ReportEntry:
    if path.name == "sample_iteration":
        return ReportEntry(
            old_dir=str(path.as_posix()),
            new_dir=str((TEMPLATES_ROOT / "sample_iteration").as_posix()),
            label="sample_iteration",
            generated_at="",
            date_key="template",
            provider="template",
            model="sample",
            case_bucket="template",
            case_ids=[],
            kind="template",
        )

    summary_path = path / "summary.json"
    long_arc_summary_path = path / "long_arc_step8_summary.json"
    kind = "run"
    provider = "manual"
    model = "manual"
    label = path.name
    generated_at = ""
    case_ids: list[str] = []

    if summary_path.exists():
        data = _read_json(summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        provider = str(data.get("provider") or "manual")
        model = str(data.get("model") or "manual")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
    elif long_arc_summary_path.exists():
        data = _read_json(long_arc_summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
        if data.get("generated"):
            provider = "analysis"
            model = "step8-generated"
            kind = "analysis"
        else:
            provider = "analysis"
            model = "step8-static"
            kind = "analysis"
    else:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        kind = "misc"

    date_key = _date_key(generated_at, fallback_path=path)
    case_bucket = _case_bucket(case_ids)
    provider_slug = _slug(provider, fallback="manual")
    model_slug = _slug(model, fallback="manual")
    label_slug = _slug(label, fallback=_slug(path.name, fallback="report"))

    if kind == "template":
        target = TEMPLATES_ROOT / "sample_iteration"
    else:
        target = RUNS_ROOT / date_key / f"{provider_slug}__{model_slug}" / case_bucket / label_slug

    return ReportEntry(
        old_dir=str(path.as_posix()),
        new_dir=str(target.as_posix()),
        label=label,
        generated_at=generated_at,
        date_key=date_key,
        provider=provider_slug,
        model=model_slug,
        case_bucket=case_bucket,
        case_ids=case_ids,
        kind=kind,
    )


def _move_reports(*, dry_run: bool) -> list[ReportEntry]:
    entries: list[ReportEntry] = []
    for path in sorted(ROOT.iterdir()):
        if not path.is_dir() or path.name in SKIP_DIRS:
            continue
        entry = _resolve_entry(path)
        target = Path(entry.new_dir)
        if target == path:
            continue
        entries.append(entry)
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Target already exists: {target}")
        shutil.move(str(path), str(target))
    return entries


def _move_live_summary_snapshots(*, dry_run: bool) -> tuple[dict[str, str], int]:
    replacements: dict[str, str] = {}
    moved_count = 0
    for summary_path in sorted(LIVE_ROOT.glob("*_summary.json")):
        data = _read_json(summary_path)
        cases = data.get("cases", [])
        if not isinstance(cases, list) or not cases:
            continue
        moved_count += 1

        label = str(data.get("label") or summary_path.stem.replace("_summary", "")).strip()
        label_slug = _slug(label, fallback=_slug(summary_path.stem, fallback="summary"))
        date_key = _date_key(str(data.get("generated_at") or data.get("date") or ""), fallback_path=summary_path)
        case_ids = [str(item.get("case") or "").strip() for item in cases if isinstance(item, dict)]
        case_bucket = _case_bucket(case_ids)

        providers = _unique_preserve_order(
            _slug(str(item.get("provider") or item.get("provider_note") or ""), fallback="manual")
            for item in cases
            if isinstance(item, dict)
        )
        models = _unique_preserve_order(
            _slug(str(item.get("model") or ""), fallback="manual")
            for item in cases
            if isinstance(item, dict)
        )

        if len(providers) <= 1:
            provider_slug = providers[0] if providers else "manual"
            if len(models) <= 1:
                model_slug = models[0] if models else "manual"
            else:
                model_slug = _slug("-plus-".join(models), fallback="mixed-models")
        else:
            provider_slug = "mixed"
            model_slug = _slug("-plus-".join(providers), fallback="mixed-providers")

        target_dir = RUNS_ROOT / date_key / f"{provider_slug}__{model_slug}" / case_bucket / label_slug
        target_json = target_dir / "summary.json"
        target_md = target_dir / "summary.md"
        companion_md = summary_path.with_suffix(".md")

        replacements[str(summary_path.as_posix())] = str(target_json.as_posix())
        replacements[str(summary_path.as_posix()).replace("/", "\\")] = str(target_json.as_posix()).replace("/", "\\")
        if companion_md.exists():
            replacements[str(companion_md.as_posix())] = str(target_md.as_posix())
            replacements[str(companion_md.as_posix()).replace("/", "\\")] = str(target_md.as_posix()).replace("/", "\\")

        if dry_run:
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        if target_json.exists():
            raise FileExistsError(f"Target already exists: {target_json}")
        shutil.move(str(summary_path), str(target_json))
        if companion_md.exists():
            if target_md.exists():
                raise FileExistsError(f"Target already exists: {target_md}")
            shutil.move(str(companion_md), str(target_md))

    return replacements, moved_count


def _replace_all(text: str, replacements: dict[str, str]) -> str:
    updated = text
    for old_value, new_value in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        updated = updated.replace(old_value, new_value)
    return updated


def _rewrite_paths(entries: list[ReportEntry], *, dry_run: bool, extra_replacements: dict[str, str] | None = None) -> None:
    replacements: dict[str, str] = {}
    for entry in entries:
        replacements[entry.old_dir] = entry.new_dir
        replacements[entry.old_dir.replace("/", "\\")] = entry.new_dir.replace("/", "\\")
    if extra_replacements:
        replacements.update(extra_replacements)

    if not replacements:
        return

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        original = _read_text(path)
        updated = _replace_all(original, replacements)
        if updated == original:
            continue
        if dry_run:
            continue
        path.write_text(updated, encoding="utf-8")


def _write_catalog(entries: list[ReportEntry], *, dry_run: bool) -> None:
    run_dirs = sorted(
        [path for path in RUNS_ROOT.rglob("*") if path.is_dir() and any(child.is_file() for child in path.iterdir())],
        key=lambda path: str(path.as_posix()),
    )

    rows = sorted(entries, key=lambda item: (item.date_key, item.provider, item.model, item.case_bucket, item.label))
    catalog_path = ROOT / "catalog.json"
    index_path = ROOT / "index.md"

    catalog_payload = {
        "schema": "romance-report-catalog-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "runs_root": str(RUNS_ROOT.as_posix()),
        "entries": [asdict(entry) for entry in rows],
    }

    index_lines = [
        "# Romance Reports Index",
        "",
        "## Layout",
        "",
        "- `self_improve_live/`: live iteration report and ledger",
        "- `runs/YYYYMMDD/provider__model/case_bucket/label/`: archived eval artifacts",
        "- `templates/sample_iteration/`: report template/reference example",
        "",
        "## Moved Entries",
        "",
    ]
    if rows:
        for entry in rows:
            index_lines.append(
                f"- `{entry.date_key}` | `{entry.provider}__{entry.model}` | `{entry.case_bucket}` | "
                f"`{entry.label}` -> `{entry.new_dir}`"
            )
    else:
        index_lines.append("- No directory moves were needed.")

    index_lines.extend(["", "## Current Run Directories", ""])
    if run_dirs:
        for path in run_dirs:
            index_lines.append(f"- `{path.as_posix()}`")
    else:
        index_lines.append("- No archived run directories found.")

    if dry_run:
        return
    catalog_path.write_text(json.dumps(catalog_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize romance report artifacts into a structured archive.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would move without modifying files.")
    args = parser.parse_args()

    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)

    entries = _move_reports(dry_run=args.dry_run)
    live_summary_replacements, live_summary_move_count = _move_live_summary_snapshots(dry_run=args.dry_run)
    _rewrite_paths(entries, dry_run=args.dry_run, extra_replacements=live_summary_replacements)
    _write_catalog(entries, dry_run=args.dry_run)

    payload = {
        "moved_count": len(entries),
        "live_summary_move_count": live_summary_move_count,
        "dry_run": args.dry_run,
        "entries": [asdict(entry) for entry in entries],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
