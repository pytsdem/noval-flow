from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from novel_flow.storage.sqlite_store import SQLiteStore

from evals.romance.history_models import (
    CaseExportNote,
    CaseExportSummary,
    HistoricalCaseInputs,
    HistoricalCaseIntermediates,
    HistoricalCaseMetadata,
    HistoricalCaseMetrics,
    HistoricalCaseOutputs,
    HistoricalEvalCase,
)


def _json_loads(payload: Any) -> Any:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _normalize_tag(tag: str) -> str:
    return str(tag or "").strip().lower().replace(" ", "_").replace("-", "_")


def _issue_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("issues", []) if isinstance(report, dict) else []
    return [item for item in raw if isinstance(item, dict)]


def _severity_weight(severity: str) -> float:
    mapping = {
        "critical": 2.5,
        "high": 2.0,
        "medium": 1.0,
        "low": 0.5,
    }
    return mapping.get(str(severity or "").strip().lower(), 0.5)


def _truncate_text(text: str, limit: int = 240) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


def _git_revision(cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return ""
    return completed.stdout.strip()


@dataclass
class _ExportCandidate:
    case: HistoricalEvalCase
    timestamp: str
    quality_risk: float
    cost_score: float
    tags: set[str]


class HistoricalCaseExporter:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.store = SQLiteStore(self.db_path)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.pipeline_version = _git_revision(self.repo_root)

    def export(
        self,
        *,
        output_dir: str | Path,
        limit: int = 20,
        sample_mode: str = "latest",
        book_id: str | None = None,
        chapter_id: str | None = None,
        run_id: str | None = None,
        tags: list[str] | None = None,
    ) -> CaseExportSummary:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        normalized_mode = str(sample_mode or "latest").strip().lower()
        requested_tags = {_normalize_tag(item) for item in (tags or []) if str(item).strip()}

        notes: list[str] = []
        candidates: list[_ExportCandidate] = []
        run_rows = self.store.list_runs(limit=max(int(limit) * 8, 50), book_id=book_id)
        if run_id:
            run_rows = [row for row in run_rows if str(row.get("run_id") or "") == run_id]

        for row in run_rows:
            try:
                candidate = self._build_candidate(row=row, chapter_filter=chapter_id)
            except Exception as exc:
                notes.append(f"Skipped run {row.get('run_id')}: {exc}")
                continue
            if candidate is None:
                continue
            if requested_tags and not (candidate.tags & requested_tags):
                continue
            candidates.append(candidate)

        if normalized_mode == "latest":
            ordered = sorted(candidates, key=lambda item: item.timestamp, reverse=True)
        elif normalized_mode == "low_score":
            ordered = sorted(
                candidates,
                key=lambda item: (item.quality_risk, item.timestamp),
                reverse=True,
            )
            notes.append("low_score sampling uses stored workflow risk as a proxy because romance eval scores are not persisted in the production database.")
        elif normalized_mode == "high_cost":
            ordered = sorted(
                candidates,
                key=lambda item: (item.cost_score, item.timestamp),
                reverse=True,
            )
        elif normalized_mode in {"tagged", "tag", "tags"}:
            ordered = sorted(candidates, key=lambda item: item.timestamp, reverse=True)
        else:
            raise ValueError(f"Unsupported sample mode: {sample_mode}")

        selected = ordered[: max(int(limit), 0)]
        exported_case_ids: list[str] = []
        for item in selected:
            case_path = output_path / f"{item.case.case_id}.json"
            case_path.write_text(item.case.model_dump_json(indent=2), encoding="utf-8")
            exported_case_ids.append(item.case.case_id)

        summary = CaseExportSummary(
            output_dir=str(output_path),
            source_db=str(self.db_path),
            sample_mode=normalized_mode,
            limit=int(limit),
            exported_case_ids=exported_case_ids,
            notes=notes,
        )
        (output_path / "export_summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        return summary

    def _build_candidate(
        self,
        *,
        row: dict[str, Any],
        chapter_filter: str | None,
    ) -> _ExportCandidate | None:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            return None
        book_id = str(row.get("current_book_id") or "").strip()
        if not book_id:
            return None
        book = self.store.load_book(book_id)
        if book is None:
            return None

        raw_outputs = self.store.list_run_outputs(run_id)
        outputs = [self._decode_run_output(item) for item in raw_outputs]
        chapter_map = self._chapter_map(book)
        chapter_id = chapter_filter or self._resolve_chapter_id(outputs=outputs, book=book)
        if not chapter_id:
            return None
        chapter = chapter_map.get(chapter_id)
        if chapter is None:
            return None

        metadata = dict(book.metadata or {})
        writer_context_debug = dict((metadata.get("writer_context_debug") or {}).get(chapter_id, {}) or {})
        writing_runs = dict((metadata.get("writing_chapter_runs") or {}).get(chapter_id, {}) or {})
        story_blueprint = dict(metadata.get("story_blueprint") or {})
        chapter_brief = self._find_chapter_brief(story_blueprint=story_blueprint, chapter_id=chapter_id)
        actual_summary = dict(writing_runs.get("actual_chapter_summary") or self._actual_summary_for(metadata, chapter_id))
        prior_summaries = self._prior_actual_summaries(metadata=metadata, chapter_id=chapter_id)
        stage_log = list(writing_runs.get("stage_log") or self._extract_stage_log(outputs))
        content_blocks = list(writing_runs.get("content_blocks") or self._extract_content_blocks(outputs, chapter_id=chapter_id))
        character_mind_states = self._character_mind_states(chapter=chapter, writing_runs=writing_runs, stage_log=stage_log)
        review_iterations = self._review_iterations(stage_log=stage_log, fallback_reports=writing_runs.get("review_reports"))
        patch_reports = [item for item in stage_log if str(item.get("stage") or "").startswith("rewrite_iteration_")]
        latest_review = review_iterations[-1]["review_reports"] if review_iterations else dict(writing_runs.get("review_reports") or {})
        final_judge = dict(writing_runs.get("final_judge") or self._latest_final_judge(review_iterations))
        final_text = self._resolve_final_text(outputs=outputs, writing_runs=writing_runs, chapter=chapter)
        final_status = self._final_status(final_judge=final_judge, stage_log=stage_log)
        tags = self._infer_tags(chapter_brief=chapter_brief, actual_summary=actual_summary, final_text=final_text)

        export_notes: list[CaseExportNote] = []
        missing = []
        if not writer_context_debug:
            missing.append("inputs.sanitized_writer_context")
        if not content_blocks:
            missing.append("intermediates.content_blocks")
        if not chapter_brief:
            missing.append("inputs.chapter_brief")
        if final_text == "":
            missing.append("outputs.final_text")
        if row.get("mode") not in {"fast", "deep"}:
            export_notes.append(
                CaseExportNote(
                    level="info",
                    field="metadata.mode",
                    message=f"Stored workflow mode {row.get('mode')!r} does not map to writer fast/deep; exported as other.",
                )
            )
        if not self.pipeline_version:
            export_notes.append(
                CaseExportNote(
                    level="info",
                    field="metadata.pipeline_version",
                    message="Git revision could not be resolved; pipeline_version is empty.",
                )
            )
        for field_name in missing:
            export_notes.append(
                CaseExportNote(
                    level="warning",
                    field=field_name,
                    message="Field was not persisted in the current run and was exported with an empty compatible value.",
                )
            )

        quality_risk = self._quality_risk(final_judge=final_judge, latest_review=latest_review, review_iterations=review_iterations)
        metrics = HistoricalCaseMetrics(
            llm_calls=None,
            review_rounds=len(review_iterations),
            patch_rounds=len(patch_reports),
            used_full_rewrite=bool(patch_reports),
            latency_ms=None,
            token_usage={},
            tool_calls_by_name=self._tool_calls_by_name(review_iterations),
            failing_tools=self._failing_tools(latest_review),
            quality_risk=round(quality_risk, 2),
        )
        cost_score = (
            (metrics.patch_rounds * 4.0)
            + (metrics.review_rounds * 1.5)
            + (3.0 if metrics.used_full_rewrite else 0.0)
            + (1.0 if metrics.failing_tools else 0.0)
        )

        goals = self._goals(chapter_brief=chapter_brief)
        context_overrides = {
            "assistant_persona_prompt": str(writer_context_debug.get("assistant_persona_prompt") or ""),
            "writing_requirements": self._safe_json_dict(writer_context_debug.get("writing_requirements_json")),
            "reference_pack": str(writer_context_debug.get("reference_pack") or ""),
            "previous_chapter_full_text": str(writer_context_debug.get("previous_chapter_full_text") or ""),
            "completed_chapter_summary_bundle": str(writer_context_debug.get("completed_chapter_memory_text") or ""),
            "chapter_payload_text": str(writer_context_debug.get("chapter_payload_text") or ""),
            "timeline_anchor_facts_text": str(writer_context_debug.get("timeline_anchor_facts_text") or ""),
            "relevant_world_rules_text": str(writer_context_debug.get("relevant_world_rules_text") or ""),
            "scene_character_context_text": str(writer_context_debug.get("scene_character_context_text") or ""),
            "relationship_state_text": str(writer_context_debug.get("relationship_state_text") or ""),
        }

        case = HistoricalEvalCase(
            case_id=f"{chapter_id}_{run_id}",
            metadata=HistoricalCaseMetadata(
                book_id=book.id,
                chapter_id=chapter_id,
                run_id=run_id,
                timestamp=str(row.get("updated_at") or ""),
                pipeline_version=self.pipeline_version,
                mode=str(row.get("mode") if row.get("mode") in {"fast", "deep"} else "other"),
                source="db",
                tags=sorted(tags),
                chapter_title=chapter.title,
                sample_mode="",
                source_label=f"book:{book.id}",
            ),
            inputs=HistoricalCaseInputs(
                chapter_brief=chapter_brief,
                chapter_payload=str(writer_context_debug.get("chapter_payload_text") or ""),
                relationship_state={
                    "text": str(writer_context_debug.get("relationship_state_text") or ""),
                    "summary": list(actual_summary.get("relationship_state") or []),
                },
                character_mind_states=character_mind_states,
                scene_character_context={
                    "text": str(writer_context_debug.get("scene_character_context_text") or ""),
                    "character_focus": list(chapter_brief.get("character_focus") or []),
                },
                recent_actual_summaries=prior_summaries,
                writing_pack={
                    "selection_summary_text": str(writer_context_debug.get("selection_summary_text") or ""),
                    "completed_chapter_memory_text": str(writer_context_debug.get("completed_chapter_memory_text") or ""),
                    "step_1_story_foundation_text": str(writer_context_debug.get("step_1_story_foundation_text") or ""),
                    "step_2_worldbuilding_text": str(writer_context_debug.get("step_2_worldbuilding_text") or ""),
                    "step_3_character_packets_text": str(writer_context_debug.get("step_3_character_packets_text") or ""),
                    "step_4_event_timeline_text": str(writer_context_debug.get("step_4_event_timeline_text") or ""),
                    "step_5_character_milestones_text": str(writer_context_debug.get("step_5_character_milestones_text") or ""),
                    "step_6_twists_text": str(writer_context_debug.get("step_6_twists_text") or ""),
                    "step_7_story_lines_text": str(writer_context_debug.get("step_7_story_lines_text") or ""),
                    "step_8_chapter_brief_text": str(writer_context_debug.get("step_8_chapter_brief_text") or ""),
                    "timeline_anchor_facts_text": str(writer_context_debug.get("timeline_anchor_facts_text") or ""),
                    "relevant_world_rules_text": str(writer_context_debug.get("relevant_world_rules_text") or ""),
                    "style_card_text": str(writer_context_debug.get("style_card_text") or ""),
                    "reference_pack": str(writer_context_debug.get("reference_pack") or ""),
                    "writing_requirements": self._safe_json_dict(writer_context_debug.get("writing_requirements_json")),
                },
                sanitized_writer_context=writer_context_debug,
                premise=book.premise.model_dump(mode="json"),
                twist_designs=list(story_blueprint.get("twist_designs") or []),
                story_lines=list(story_blueprint.get("story_lines") or []),
                character_cards=[item.model_dump(mode="json") for item in book.characters],
                worldbuilding=dict(story_blueprint or {}),
                character_milestones=list(metadata.get("character_milestones") or []),
                goals=goals,
                context_overrides=context_overrides,
            ),
            intermediates=HistoricalCaseIntermediates(
                block_plan=self._block_plan(stage_log=stage_log, content_blocks=content_blocks),
                review_reports=review_iterations,
                patch_plan=self._patch_plan(review_iterations=review_iterations),
                patch_reports=patch_reports,
                actual_summary=actual_summary,
                chapter_summary={
                    "title": chapter.title,
                    "summary": chapter.summary,
                },
                stage_log=stage_log,
                content_blocks=content_blocks,
                final_judge=final_judge,
            ),
            outputs=HistoricalCaseOutputs(
                final_text=final_text,
                final_summary=_truncate_text(chapter.summary or " ".join(actual_summary.get("actual_events") or []), 400),
                final_status=final_status,
                final_version=int(writing_runs.get("final_version") or getattr(chapter, "final_version", 0) or 0),
            ),
            metrics=metrics,
            export_notes=export_notes,
            replay_case={
                "case_id": f"{chapter_id}_{run_id}",
                "title": chapter.title,
                "description": chapter.summary,
                "tags": sorted(tags),
                "premise": book.premise.model_dump(mode="json"),
                "chapter_brief": chapter_brief,
                "twist_designs": list(story_blueprint.get("twist_designs") or []),
                "story_lines": list(story_blueprint.get("story_lines") or []),
                "character_cards": [item.model_dump(mode="json") for item in book.characters],
                "worldbuilding": dict(story_blueprint or {}),
                "character_milestones": list(metadata.get("character_milestones") or []),
                "actual_chapter_summaries": prior_summaries,
                "prior_character_mindsets": character_mind_states,
                "goals": goals,
                "context_overrides": context_overrides,
            },
        )
        return _ExportCandidate(
            case=case,
            timestamp=str(row.get("updated_at") or ""),
            quality_risk=quality_risk,
            cost_score=cost_score,
            tags=tags,
        )

    @staticmethod
    def _decode_run_output(row: dict[str, Any]) -> dict[str, Any]:
        payload = _json_loads(row.get("payload_json", "{}"))
        return {
            "id": row.get("id"),
            "run_id": row.get("run_id"),
            "agent": row.get("agent"),
            "output_type": row.get("output_type"),
            "title": row.get("title"),
            "created_at": row.get("created_at"),
            "payload": payload,
        }

    @staticmethod
    def _chapter_map(book: Any) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for volume in list(getattr(book, "volumes", []) or []):
            for chapter in list(getattr(volume, "chapters", []) or []):
                mapping[str(chapter.id)] = chapter
        return mapping

    @staticmethod
    def _resolve_chapter_id(*, outputs: list[dict[str, Any]], book: Any) -> str:
        for output_type in ("chapter_final_text", "actual_chapter_summary", "chapter_written", "chapter_stage_log"):
            for item in reversed(outputs):
                if item["output_type"] != output_type:
                    continue
                payload = dict(item.get("payload") or {})
                chapter_id = str(payload.get("chapter_id") or payload.get("id") or "").strip()
                if chapter_id:
                    return chapter_id
        volumes = list(getattr(book, "volumes", []) or [])
        if not volumes or not volumes[0].chapters:
            return ""
        return str(volumes[0].chapters[-1].id)

    @staticmethod
    def _find_chapter_brief(*, story_blueprint: dict[str, Any], chapter_id: str) -> dict[str, Any]:
        for item in list(story_blueprint.get("chapter_briefs") or []):
            if str(item.get("chapter_id") or "") == chapter_id:
                return dict(item)
        return {}

    @staticmethod
    def _actual_summary_for(metadata: dict[str, Any], chapter_id: str) -> dict[str, Any]:
        for item in list(metadata.get("actual_chapter_summaries") or []):
            if str(item.get("chapter_id") or "") == chapter_id:
                return dict(item)
        return {}

    @staticmethod
    def _prior_actual_summaries(metadata: dict[str, Any], chapter_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in list(metadata.get("actual_chapter_summaries") or []):
            if str(item.get("chapter_id") or "") == chapter_id:
                break
            results.append(dict(item))
        return results

    @staticmethod
    def _extract_stage_log(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in reversed(outputs):
            if item["output_type"] == "chapter_stage_log":
                return list(item.get("payload", {}).get("stage_log") or [])
        return []

    @staticmethod
    def _extract_content_blocks(outputs: list[dict[str, Any]], *, chapter_id: str) -> list[dict[str, Any]]:
        for item in reversed(outputs):
            if item["output_type"] == "chapter_blocks":
                payload = dict(item.get("payload") or {})
                if chapter_id and str(payload.get("chapter_id") or "") != chapter_id:
                    continue
                return list(payload.get("blocks") or [])
        return []

    @staticmethod
    def _character_mind_states(*, chapter: Any, writing_runs: dict[str, Any], stage_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if list(writing_runs.get("character_mindsets") or []):
            return list(writing_runs.get("character_mindsets") or [])
        if list(getattr(chapter, "character_mindsets", []) or []):
            return [item.model_dump(mode="json") for item in list(getattr(chapter, "character_mindsets", []) or [])]
        for item in stage_log:
            if str(item.get("stage") or "") == "build_character_mindsets":
                return list(item.get("character_mindsets") or [])
        return []

    @staticmethod
    def _review_iterations(stage_log: list[dict[str, Any]], fallback_reports: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entry in stage_log:
            stage_name = str(entry.get("stage") or "")
            if not stage_name.startswith("review_iteration_"):
                continue
            items.append(
                {
                    "stage": stage_name,
                    "tool_calls": list(entry.get("tool_calls") or []),
                    "review_reports": dict(entry.get("review_reports") or {}),
                    "final_judge": dict(entry.get("final_judge") or {}),
                    "chapter_revision_plan": dict(entry.get("chapter_revision_plan") or {}),
                    "dynamic_instruction": dict(entry.get("dynamic_instruction") or {}),
                }
            )
        if items:
            return items
        if isinstance(fallback_reports, dict) and fallback_reports:
            return [
                {
                    "stage": "review_iteration_1",
                    "tool_calls": sorted(fallback_reports),
                    "review_reports": dict(fallback_reports),
                    "final_judge": {},
                    "chapter_revision_plan": {},
                    "dynamic_instruction": {},
                }
            ]
        return []

    @staticmethod
    def _latest_final_judge(review_iterations: list[dict[str, Any]]) -> dict[str, Any]:
        for item in reversed(review_iterations):
            judge = dict(item.get("final_judge") or {})
            if judge:
                return judge
        return {}

    @staticmethod
    def _resolve_final_text(*, outputs: list[dict[str, Any]], writing_runs: dict[str, Any], chapter: Any) -> str:
        value = str(writing_runs.get("final_text") or "").strip()
        if value:
            return value
        for output_type in ("chapter_final_text", "chapter_written"):
            for item in reversed(outputs):
                if item["output_type"] != output_type:
                    continue
                payload = dict(item.get("payload") or {})
                text = str(payload.get("final_text") or "").strip()
                if text:
                    return text
        return str(getattr(chapter, "final_text", "") or "")

    @staticmethod
    def _final_status(*, final_judge: dict[str, Any], stage_log: list[dict[str, Any]]) -> str:
        if not final_judge:
            return "unknown"
        if final_judge.get("passed") is False:
            return "failed_partial"
        if bool(final_judge.get("passed")):
            return "patched" if any(str(item.get("stage") or "").startswith("rewrite_iteration_") for item in stage_log) else "success"
        return "unknown"

    @staticmethod
    def _safe_json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"raw": value}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        return {}

    @staticmethod
    def _goals(*, chapter_brief: dict[str, Any]) -> dict[str, Any]:
        return {
            "chapter_goal": str(chapter_brief.get("summary") or ""),
            "emotional_goal": str(chapter_brief.get("reader_emotion") or ""),
            "relationship_goal": str(chapter_brief.get("relationship_reprice") or ""),
            "hook_goal": str(chapter_brief.get("opening_hook") or chapter_brief.get("ending_pull") or ""),
            "continuation_drive": str(chapter_brief.get("ending_pull") or ""),
        }

    @staticmethod
    def _block_plan(*, stage_log: list[dict[str, Any]], content_blocks: list[dict[str, Any]]) -> dict[str, Any]:
        for item in stage_log:
            if str(item.get("stage") or "") == "plan_content_blocks":
                return {
                    "stage": "plan_content_blocks",
                    "block_count": int(item.get("block_count") or 0),
                    "blocks": list(item.get("blocks") or []),
                    "skill_ids": list(item.get("skill_ids") or []),
                }
        return {
            "stage": "committed_blocks_only",
            "block_count": len(content_blocks),
            "blocks": content_blocks,
            "skill_ids": [],
        }

    @staticmethod
    def _patch_plan(review_iterations: list[dict[str, Any]]) -> dict[str, Any]:
        plans = []
        for item in review_iterations:
            plan = dict(item.get("chapter_revision_plan") or {})
            dynamic_instruction = dict(item.get("dynamic_instruction") or {})
            if plan or dynamic_instruction:
                plans.append(
                    {
                        "stage": item.get("stage"),
                        "chapter_revision_plan": plan,
                        "dynamic_instruction": dynamic_instruction,
                    }
                )
        if not plans:
            return {}
        return {"iterations": plans, "latest": plans[-1]}

    @staticmethod
    def _failing_tools(review_reports: dict[str, Any]) -> list[str]:
        failing: list[str] = []
        for tool_name, payload in review_reports.items():
            if not isinstance(payload, dict):
                continue
            passed = payload.get("passed")
            rewrite_needed = payload.get("rewrite_needed")
            if passed is False or rewrite_needed is True:
                failing.append(str(tool_name))
        return sorted(set(failing))

    def _quality_risk(
        self,
        *,
        final_judge: dict[str, Any],
        latest_review: dict[str, Any],
        review_iterations: list[dict[str, Any]],
    ) -> float:
        score = 0.0
        score += len(list(final_judge.get("blocking_reasons") or [])) * 1.5
        score += len(self._failing_tools(latest_review)) * 1.2
        for report in latest_review.values():
            if not isinstance(report, dict):
                continue
            for issue in _issue_items(report):
                score += _severity_weight(issue.get("severity"))
        if review_iterations:
            score += max(0, len(review_iterations) - 1) * 1.0
        return score

    @staticmethod
    def _tool_calls_by_name(review_iterations: list[dict[str, Any]]) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for item in review_iterations:
            for tool_name in list(item.get("tool_calls") or []):
                counter[str(tool_name)] += 1
        return dict(sorted(counter.items()))

    def _infer_tags(
        self,
        *,
        chapter_brief: dict[str, Any],
        actual_summary: dict[str, Any],
        final_text: str,
    ) -> set[str]:
        tags: set[str] = set()
        chapter_type = _normalize_tag(str(chapter_brief.get("chapter_type") or ""))
        if chapter_type:
            tags.add(chapter_type)
        scene_engine = _normalize_tag(str(chapter_brief.get("scene_engine") or ""))
        if scene_engine:
            tags.add(scene_engine)
        if str(chapter_brief.get("opening_hook") or "").strip():
            tags.add("opening_hook")
        if str(chapter_brief.get("ending_pull") or "").strip():
            tags.add("ending_hook")
        if str(chapter_brief.get("relationship_reprice") or "").strip() or str(chapter_brief.get("romance_seed") or "").strip():
            tags.add("relationship_progression")
        text_blob = " ".join(
            [
                str(chapter_brief.get("summary") or ""),
                str(chapter_brief.get("reader_emotion") or ""),
                str(chapter_brief.get("ending_pull") or ""),
                " ".join(str(item) for item in list(actual_summary.get("relationship_state") or [])),
                _truncate_text(final_text, 500),
            ]
        ).lower()
        if any(token in text_blob for token in ("pressure", "court", "对峙", "压迫", "恨", "张力", "敌意")):
            tags.add("high_tension_romance")
        if any(token in text_blob for token in ("暧昧", "试探", "attraction", "chemistry", "靠近")):
            tags.add("relationship_progression")
        if any(token in text_blob for token in ("dead", "尸", "爆点", "翻案", "witness", "证人")):
            tags.add("ending_bomb")
        return tags
