from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_REPORTS_ROOT = Path(__file__).resolve().parent / "reports"


def sanitize_path_segment(value: str, *, fallback: str) -> str:
    keep = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or "").strip()]
    text = "".join(keep).strip("_.")
    return text or fallback


def case_bucket(case_ids: Iterable[str]) -> str:
    normalized = [str(case_id).strip() for case_id in case_ids if str(case_id).strip()]
    if not normalized:
        return "multi_case__unknown"
    if len(normalized) == 1:
        return sanitize_path_segment(normalized[0], fallback="case")
    return f"multi_case__{len(normalized)}cases"


def normalize_reports_root(reports_root: str | Path | None = None) -> tuple[Path, Path]:
    base = Path(reports_root or DEFAULT_REPORTS_ROOT)
    if base.name == "runs":
        reports_base = base.parent
        runs_root = base
    elif base.name == "reports":
        reports_base = base
        runs_root = base / "runs"
    else:
        reports_base = base
        runs_root = base
    reports_base.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)
    return reports_base, runs_root


def _coerce_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StructuredRunPaths:
    reports_root: Path
    runs_root: Path
    run_dir: Path
    date_key: str
    task_slug: str
    provider_slug: str
    model_slug: str
    case_bucket: str
    run_label: str


def build_structured_run_dir(
    reports_root: str | Path | None = None,
    *,
    task_slug: str,
    label: str,
    case_ids: Iterable[str] = (),
    provider: str = "analysis",
    model: str = "manual",
    generated_at: datetime | str | None = None,
) -> StructuredRunPaths:
    reports_base, runs_root = normalize_reports_root(reports_root)
    run_at = _coerce_datetime(generated_at)
    date_key = run_at.strftime("%Y%m%d")
    task_key = sanitize_path_segment(task_slug, fallback="eval")
    provider_key = sanitize_path_segment(provider, fallback="analysis")
    model_key = sanitize_path_segment(model, fallback="manual")
    case_key = case_bucket(case_ids)
    label_key = sanitize_path_segment(label, fallback=f"{task_key}_{run_at.strftime('%Y%m%d_%H%M%S')}")
    run_dir = runs_root / date_key / task_key / f"{provider_key}__{model_key}" / case_key / label_key
    run_dir.mkdir(parents=True, exist_ok=True)
    return StructuredRunPaths(
        reports_root=reports_base,
        runs_root=runs_root,
        run_dir=run_dir,
        date_key=date_key,
        task_slug=task_key,
        provider_slug=provider_key,
        model_slug=model_key,
        case_bucket=case_key,
        run_label=label_key,
    )


def write_text_with_aliases(primary_path: Path, text: str, *, alias_names: Iterable[str] = ()) -> Path:
    primary_path.parent.mkdir(parents=True, exist_ok=True)
    primary_path.write_text(text, encoding="utf-8")
    for alias_name in alias_names:
        alias_path = primary_path.parent / str(alias_name)
        if alias_path == primary_path:
            continue
        alias_path.write_text(text, encoding="utf-8")
    return primary_path
