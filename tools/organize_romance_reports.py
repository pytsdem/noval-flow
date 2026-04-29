from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from evals.romance.report_paths import sanitize_path_segment


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
    task: str
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
    text = sanitize_path_segment(value.strip().lower(), fallback=fallback)
    text = re.sub(r"_{2,}", "_", text).strip("_.")
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


def _add_replacement_variants(replacements: dict[str, str], old_value: str, new_value: str) -> None:
    pairs = [
        (old_value, new_value),
        (old_value.replace("/", "\\"), new_value.replace("/", "\\")),
    ]
    for old_variant, new_variant in pairs:
        replacements[old_variant] = new_variant
        replacements[old_variant.replace("\\", "\\\\")] = new_variant.replace("\\", "\\\\")


def _infer_case_ids_from_children(path: Path) -> list[str]:
    case_ids: list[str] = []
    for child in sorted(path.iterdir()):
        if not child.is_dir():
            continue
        has_case_input = (child / "case_input.json").exists() or (child / "chapter_eval_case_input.json").exists()
        has_result = (child / "result.json").exists() or (child / "chapter_eval_case_result.json").exists()
        has_context = (child / "writer_context.json").exists() or (child / "chapter_eval_writer_context.json").exists()
        if has_case_input or has_result or has_context:
            case_ids.append(child.name)
    return case_ids


def _fallback_provider_model_from_path(path: Path) -> tuple[str, str]:
    for candidate in path.parents:
        name = candidate.name
        if "__" not in name:
            continue
        if candidate.parent.parent != RUNS_ROOT:
            continue
        provider, model = name.split("__", 1)
        return provider, model
    return "manual", "manual"


def _resolve_entry(path: Path) -> ReportEntry:
    if path.name == "sample_iteration":
        return ReportEntry(
            old_dir=str(path.as_posix()),
            new_dir=str((TEMPLATES_ROOT / "sample_iteration").as_posix()),
            label="sample_iteration",
            task="template",
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
    step_plan_summary_path = path / "step_plan_eval_summary.json"
    diagnostics_summary_path = path / "diagnostics_summary.json"
    step_gate_summary_path = path / "step_eval_summary.json"
    kind = "run"
    task = "misc_eval"
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
        if "mode" in data and "case_results" in data:
            task = "chapter_eval"
        elif "average_score" in data and "case_reports" in data:
            task = "beat_plan_eval"
        elif isinstance(data.get("cases"), list):
            task = "chapter_eval_rollup"
            generated_at = str(data.get("generated_at") or data.get("date") or "")
            case_ids = [
                str(item.get("case") or "").strip()
                for item in data.get("cases", [])
                if isinstance(item, dict) and str(item.get("case") or "").strip()
            ]
    elif long_arc_summary_path.exists():
        data = _read_json(long_arc_summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
        task = "long_arc_step8_eval"
        if data.get("generated"):
            provider = "analysis"
            model = "step8-generated"
            kind = "analysis"
        else:
            provider = "analysis"
            model = "step8-static"
            kind = "analysis"
    elif step_plan_summary_path.exists():
        data = _read_json(step_plan_summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
        task = "step_plan_static_eval"
        provider = "analysis"
        model = "fixture"
    elif diagnostics_summary_path.exists():
        data = _read_json(diagnostics_summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
        task = "workflow_diagnostics"
        provider = "analysis"
        model = "diagnostics"
    elif step_gate_summary_path.exists():
        data = _read_json(step_gate_summary_path)
        label = str(data.get("label") or path.name)
        generated_at = str(data.get("generated_at") or "")
        case_ids = [str(case_id) for case_id in data.get("case_ids", []) if str(case_id).strip()]
        task = "historical_step_gate_eval"
        provider = "analysis"
        model = "gate"
    else:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        kind = "misc"
        case_ids = _infer_case_ids_from_children(path)
        if case_ids:
            if "prose" in path.name.lower():
                task = "chapter_eval_partial"
            elif "beat" in path.name.lower():
                task = "beat_plan_eval"
            elif "step8" in path.name.lower():
                task = "step8_partial"

    if not case_ids:
        case_ids = _infer_case_ids_from_children(path)

    if provider == "manual" and model == "manual":
        provider, model = _fallback_provider_model_from_path(path)

    date_key = _date_key(generated_at, fallback_path=path)
    case_bucket = _case_bucket(case_ids)
    task_slug = _slug(task, fallback="misc_eval")
    provider_slug = _slug(provider, fallback="manual")
    model_slug = _slug(model, fallback="manual")
    label_slug = _slug(label, fallback=_slug(path.name, fallback="report"))

    if kind == "template":
        target = TEMPLATES_ROOT / "sample_iteration"
    else:
        target = RUNS_ROOT / date_key / task_slug / f"{provider_slug}__{model_slug}" / case_bucket / label_slug

    return ReportEntry(
        old_dir=str(path.as_posix()),
        new_dir=str(target.as_posix()),
        label=label,
        task=task_slug,
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


def _legacy_path_replacements(entry: ReportEntry) -> dict[str, str]:
    replacements: dict[str, str] = {}
    old_dir = entry.old_dir
    new_dir = entry.new_dir
    _add_replacement_variants(replacements, old_dir, new_dir)
    legacy_root = ROOT / Path(new_dir).name
    legacy_root_text = str(legacy_root.as_posix())
    _add_replacement_variants(replacements, legacy_root_text, new_dir)
    return replacements


def _load_catalog_replacements() -> dict[str, str]:
    catalog_path = ROOT / "catalog.json"
    if not catalog_path.exists():
        return {}
    try:
        payload = json.loads(_read_text(catalog_path))
    except json.JSONDecodeError:
        return {}
    replacements: dict[str, str] = {}
    for item in payload.get("entries", []):
        if not isinstance(item, dict):
            continue
        old_dir = str(item.get("old_dir") or "").strip()
        new_dir = str(item.get("new_dir") or "").strip()
        if not old_dir or not new_dir:
            continue
        _add_replacement_variants(replacements, old_dir, new_dir)
        legacy_root = ROOT / Path(new_dir).name
        _add_replacement_variants(replacements, str(legacy_root.as_posix()), new_dir)
    return replacements


def _move_legacy_run_directories(*, dry_run: bool) -> tuple[list[ReportEntry], dict[str, str]]:
    entries: list[ReportEntry] = []
    replacements: dict[str, str] = {}
    for date_dir in sorted(RUNS_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        for provider_dir in sorted(date_dir.iterdir()):
            if not provider_dir.is_dir() or "__" not in provider_dir.name:
                continue
            for case_bucket_dir in sorted(provider_dir.iterdir()):
                if not case_bucket_dir.is_dir():
                    continue
                for run_dir in sorted(case_bucket_dir.iterdir()):
                    if not run_dir.is_dir():
                        continue
                    entry = _resolve_entry(run_dir)
                    target = Path(entry.new_dir)
                    if target == run_dir:
                        continue
                    entries.append(entry)
                    replacements.update(_legacy_path_replacements(entry))
                    if dry_run:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise FileExistsError(f"Target already exists: {target}")
                    shutil.move(str(run_dir), str(target))
    return entries, replacements


def _prune_empty_directories(root: Path, *, dry_run: bool) -> int:
    removed = 0
    for path in sorted([item for item in root.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
        if path in {root, RUNS_ROOT, ROOT, LIVE_ROOT, TEMPLATES_ROOT}:
            continue
        try:
            next(path.iterdir())
            continue
        except StopIteration:
            pass
        if dry_run:
            removed += 1
            continue
        path.rmdir()
        removed += 1
    return removed


def _copy_alias(src: Path, dst: Path, *, dry_run: bool) -> int:
    if not src.exists():
        return 0
    if dry_run:
        return 0 if dst.exists() else 1
    if dst.exists():
        return 0
    dst.write_bytes(src.read_bytes())
    return 1


def _iter_structured_run_dirs() -> Iterable[tuple[str, Path]]:
    for date_dir in sorted(RUNS_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        for task_dir in sorted(date_dir.iterdir()):
            if not task_dir.is_dir() or "__" in task_dir.name:
                continue
            for provider_dir in sorted(task_dir.iterdir()):
                if not provider_dir.is_dir():
                    continue
                for case_bucket_dir in sorted(provider_dir.iterdir()):
                    if not case_bucket_dir.is_dir():
                        continue
                    for run_dir in sorted(case_bucket_dir.iterdir()):
                        if run_dir.is_dir():
                            yield task_dir.name, run_dir


def _backfill_task_filenames(*, dry_run: bool) -> int:
    created = 0
    for task_name, run_dir in _iter_structured_run_dirs():
        if task_name == "chapter_eval":
            created += _copy_alias(run_dir / "summary.json", run_dir / "chapter_eval_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "chapter_eval_report.md", dry_run=dry_run)
            for diff_path in run_dir.glob("diff_vs_*"):
                if diff_path.name.startswith("chapter_eval_"):
                    continue
                created += _copy_alias(diff_path, run_dir / f"chapter_eval_{diff_path.name}", dry_run=dry_run)
            for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
                created += _copy_alias(case_dir / "case_input.json", case_dir / "chapter_eval_case_input.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "writer_context.json", case_dir / "chapter_eval_writer_context.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "chapter_execution.json", case_dir / "chapter_eval_execution.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "stage_log.json", case_dir / "chapter_eval_stage_log.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "final_text.txt", case_dir / "chapter_text__final.txt", dry_run=dry_run)
                created += _copy_alias(case_dir / "judge.json", case_dir / "chapter_eval_judge.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "result.json", case_dir / "chapter_eval_case_result.json", dry_run=dry_run)
        elif task_name == "beat_plan_eval":
            created += _copy_alias(run_dir / "summary.json", run_dir / "beat_plan_eval_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "beat_plan_eval_report.md", dry_run=dry_run)
            for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
                created += _copy_alias(case_dir / "case_input.json", case_dir / "beat_plan_eval_case_input.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "writer_context.json", case_dir / "beat_plan_eval_writer_context.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "beat_plan.json", case_dir / "beat_plan__generated.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "result.json", case_dir / "beat_plan_eval_case_result.json", dry_run=dry_run)
        elif task_name == "step_plan_static_eval":
            created += _copy_alias(run_dir / "step_plan_eval_summary.json", run_dir / "step_plan_static_eval_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "step_plan_static_eval_report.md", dry_run=dry_run)
        elif task_name == "long_arc_step8_eval":
            created += _copy_alias(run_dir / "long_arc_step8_summary.json", run_dir / "long_arc_step8_eval_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "long_arc_step8_eval_report.md", dry_run=dry_run)
            for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
                created += _copy_alias(case_dir / "generated_steps.json", case_dir / "step8_generated_steps.json", dry_run=dry_run)
        elif task_name == "historical_step_gate_eval":
            created += _copy_alias(run_dir / "step_eval_summary.json", run_dir / "historical_step_gate_eval_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "historical_step_gate_eval_report.md", dry_run=dry_run)
        elif task_name == "workflow_diagnostics":
            created += _copy_alias(run_dir / "diagnostics_summary.json", run_dir / "workflow_diagnostics_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "report.md", run_dir / "workflow_diagnostics_report.md", dry_run=dry_run)
        elif task_name == "chapter_eval_partial":
            for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
                created += _copy_alias(case_dir / "case_input.json", case_dir / "chapter_eval_case_input.json", dry_run=dry_run)
                created += _copy_alias(case_dir / "writer_context.json", case_dir / "chapter_eval_writer_context.json", dry_run=dry_run)
        elif task_name == "chapter_eval_rollup":
            created += _copy_alias(run_dir / "summary.json", run_dir / "chapter_eval_rollup_summary.json", dry_run=dry_run)
            created += _copy_alias(run_dir / "summary.md", run_dir / "chapter_eval_rollup_report.md", dry_run=dry_run)
    return created


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
        _add_replacement_variants(replacements, entry.old_dir, entry.new_dir)
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
        "- `runs/YYYYMMDD/task/provider__model/case_bucket/label/`: archived eval artifacts",
        "- `templates/sample_iteration/`: report template/reference example",
        "",
        "## Moved Entries",
        "",
    ]
    if rows:
        for entry in rows:
            index_lines.append(
                f"- `{entry.date_key}` | `{entry.task}` | `{entry.provider}__{entry.model}` | `{entry.case_bucket}` | "
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
    legacy_run_entries, legacy_run_replacements = _move_legacy_run_directories(dry_run=args.dry_run)
    entries.extend(legacy_run_entries)
    live_summary_replacements, live_summary_move_count = _move_live_summary_snapshots(dry_run=args.dry_run)
    extra_replacements = {}
    extra_replacements.update(_load_catalog_replacements())
    extra_replacements.update(legacy_run_replacements)
    extra_replacements.update(live_summary_replacements)
    _rewrite_paths(entries, dry_run=args.dry_run, extra_replacements=extra_replacements)
    pruned_empty_dirs = _prune_empty_directories(RUNS_ROOT, dry_run=args.dry_run)
    created_alias_files = _backfill_task_filenames(dry_run=args.dry_run)
    _write_catalog(entries, dry_run=args.dry_run)

    payload = {
        "moved_count": len(entries),
        "live_summary_move_count": live_summary_move_count,
        "pruned_empty_dirs": pruned_empty_dirs,
        "created_alias_files": created_alias_files,
        "dry_run": args.dry_run,
        "entries": [asdict(entry) for entry in entries],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
