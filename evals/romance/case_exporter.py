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
        character_cards = [item.model_dump(mode="json") for item in book.characters]
        chapter_brief = self._find_chapter_brief(story_blueprint=story_blueprint, chapter_id=chapter_id)
        actual_summary = dict(writing_runs.get("actual_chapter_summary") or self._actual_summary_for(metadata, chapter_id))
        prior_summaries = self._prior_actual_summaries(metadata=metadata, chapter_id=chapter_id)
        stage_log = list(writing_runs.get("stage_log") or self._extract_stage_log(outputs))
        content_blocks = list(writing_runs.get("content_blocks") or self._extract_content_blocks(outputs, chapter_id=chapter_id))
        character_mind_states = self._character_mind_states(chapter=chapter, writing_runs=writing_runs, stage_log=stage_log)
        inferred_character_mind_states = False
        if not character_mind_states:
            character_mind_states = self._infer_character_mind_states(
                chapter_brief=chapter_brief,
                writer_context_debug=writer_context_debug,
                character_cards=character_cards,
            )
            inferred_character_mind_states = bool(character_mind_states)
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
        if inferred_character_mind_states:
            export_notes.append(
                CaseExportNote(
                    level="info",
                    field="inputs.character_mind_states",
                    message="Character mind states were inferred from persisted writer-context clues because the stored run did not preserve chapter mindsets.",
                )
            )

        quality_risk = self._quality_risk(final_judge=final_judge, latest_review=latest_review, review_iterations=review_iterations)
        metrics = HistoricalCaseMetrics(
            llm_calls=None,
            review_rounds=len(review_iterations),
            patch_rounds=len(patch_reports),
            used_full_rewrite=self._used_full_rewrite(stage_log=stage_log),
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
                character_cards=character_cards,
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
                "character_cards": character_cards,
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
    def _infer_character_mind_states(
        *,
        chapter_brief: dict[str, Any],
        writer_context_debug: dict[str, Any],
        character_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        focus_names = [
            str(item or "").strip()
            for item in list(chapter_brief.get("character_focus") or [])
            if str(item or "").strip()
        ]
        card_names = [
            str(item.get("name") or "").strip()
            for item in character_cards
            if str(item.get("name") or "").strip()
        ]
        ordered_names: list[str] = []
        for name in [*focus_names, *card_names]:
            if name and name not in ordered_names:
                ordered_names.append(name)
        candidate_names = ordered_names[:2]
        if not candidate_names:
            return []

        scene_text = str(writer_context_debug.get("scene_character_context_text") or "")
        relationship_text = str(writer_context_debug.get("relationship_state_text") or "")
        character_packet_text = str(writer_context_debug.get("step_3_character_packets_text") or "")
        chapter_payload_text = str(writer_context_debug.get("chapter_payload_text") or "")
        if not any(
            value.strip()
            for value in (scene_text, relationship_text, character_packet_text, chapter_payload_text)
        ):
            return []

        cards_by_name = {
            str(item.get("name") or "").strip(): dict(item)
            for item in character_cards
            if str(item.get("name") or "").strip()
        }
        inferred: list[dict[str, Any]] = []
        for name in candidate_names:
            peer_name = next((item for item in candidate_names if item != name), "")
            mindset = HistoricalCaseExporter._infer_single_character_mindset(
                name=name,
                peer_name=peer_name,
                all_names=ordered_names,
                chapter_brief=chapter_brief,
                writer_context_debug=writer_context_debug,
                character_card=cards_by_name.get(name, {}),
                relationship_text=relationship_text,
                scene_text=scene_text,
                character_packet_text=character_packet_text,
                chapter_payload_text=chapter_payload_text,
            )
            if mindset:
                inferred.append(mindset)
        return inferred

    @staticmethod
    def _infer_single_character_mindset(
        *,
        name: str,
        peer_name: str,
        all_names: list[str],
        chapter_brief: dict[str, Any],
        writer_context_debug: dict[str, Any],
        character_card: dict[str, Any],
        relationship_text: str,
        scene_text: str,
        character_packet_text: str,
        chapter_payload_text: str,
    ) -> dict[str, Any] | None:
        scene_segment = HistoricalCaseExporter._named_segment(scene_text, name=name, all_names=all_names)
        packet_segment = HistoricalCaseExporter._named_segment(character_packet_text, name=name, all_names=all_names)
        relationship_clause = HistoricalCaseExporter._relationship_clause(
            relationship_text,
            name=name,
            peer_name=peer_name,
        )
        motivation_text = str(character_card.get("motivation") or "")
        initial_state_text = str(character_card.get("initial_state") or "")
        if not any(
            value.strip()
            for value in (scene_segment, packet_segment, relationship_clause, motivation_text, initial_state_text)
        ):
            return None

        surface_emotion = (
            HistoricalCaseExporter._extract_last_marker_value(packet_segment, "外显")
            or HistoricalCaseExporter._extract_last_marker_value(packet_segment, "表层情绪")
            or HistoricalCaseExporter._extract_last_marker_value(packet_segment, "表面情绪")
            or HistoricalCaseExporter._last_clause(scene_segment)
            or HistoricalCaseExporter._first_clause(initial_state_text)
            or "情绪紧绷"
        )
        core_emotion = (
            HistoricalCaseExporter._extract_marker_value(packet_segment, "抱有")
            or HistoricalCaseExporter._extract_marker_value(relationship_clause, "抱有")
            or HistoricalCaseExporter._extract_marker_value(relationship_clause, "藏着")
            or HistoricalCaseExporter._extract_marker_value(motivation_text, "深层：")
            or HistoricalCaseExporter._extract_marker_value(motivation_text, "更深层：")
            or HistoricalCaseExporter._first_clause(relationship_clause)
            or HistoricalCaseExporter._first_clause(initial_state_text)
            or surface_emotion
        )
        primary_goal = (
            HistoricalCaseExporter._extract_marker_value(packet_segment, "核心动机是")
            or HistoricalCaseExporter._extract_marker_value(packet_segment, "核心目标是")
            or HistoricalCaseExporter._extract_marker_value(motivation_text, "明面：")
            or HistoricalCaseExporter._extract_marker_value(motivation_text, "表层：")
            or HistoricalCaseExporter._first_clause(motivation_text)
            or HistoricalCaseExporter._first_clause(str(chapter_brief.get("summary") or ""))
            or "稳住当前局面"
        )
        hidden_need = (
            HistoricalCaseExporter._extract_marker_value(motivation_text, "深层：")
            or HistoricalCaseExporter._extract_marker_value(motivation_text, "更深层：")
            or HistoricalCaseExporter._extract_marker_value(relationship_clause, "抱有")
            or HistoricalCaseExporter._first_clause(relationship_clause)
            or primary_goal
        )
        fear = (
            HistoricalCaseExporter._extract_fear_value(initial_state_text)
            or HistoricalCaseExporter._extract_fear_value(motivation_text)
            or HistoricalCaseExporter._generic_fear_hint(
                chapter_brief=chapter_brief,
                name=name,
                peer_name=peer_name,
            )
            or (
                f"怕在当前场面先失控，提前暴露对{peer_name}的真正立场"
                if peer_name
                else "怕在当前场面先失控，丢掉仅有的回旋空间"
            )
        )
        breaking_point_hint = (
            HistoricalCaseExporter._brief_hint_for_character(chapter_brief, name=name)
            or HistoricalCaseExporter._extract_marker_value(packet_segment, "细节动作包括")
            or (
                f"若{peer_name}继续在礼法边缘施压，{name}会出现更明显的情绪外泄"
                if peer_name
                else f"若场面继续升级，{name}会出现更明显的情绪外泄"
            )
        )
        known_but_unspoken = (
            HistoricalCaseExporter._extract_marker_value(motivation_text, "更深层：")
            or HistoricalCaseExporter._first_clause(relationship_clause)
            or hidden_need
        )
        misbelief = (
            HistoricalCaseExporter._explicit_misbelief_hint(packet_segment=packet_segment, relationship_clause=relationship_clause)
            or (
                f"{name}把{peer_name}当前的冷静先理解为敌意与算计"
                if peer_name
                else f"{name}把当前局势先理解为只能继续硬扛的死局"
            )
        )
        chapter_change_hint = (
            HistoricalCaseExporter._extract_change_hint(chapter_brief, name=name)
            or HistoricalCaseExporter._first_clause(str(chapter_brief.get("relationship_reprice") or ""))
            or HistoricalCaseExporter._first_clause(str(chapter_brief.get("emotional_turn") or ""))
            or "本章后人物对局势的判断会出现松动"
        )

        attitude_to_key_others: dict[str, str] = {}
        if peer_name:
            attitude_to_key_others[peer_name] = (
                HistoricalCaseExporter._first_clause(relationship_clause, limit=120)
                or f"对{peer_name}保持高度警惕，但情绪已经被对方牵动"
            )

        return {
            "character_id": name,
            "character_name": name,
            "surface_emotion": surface_emotion,
            "core_emotion": core_emotion,
            "primary_goal": primary_goal,
            "hidden_need": hidden_need,
            "fear": fear,
            "attitude_to_key_others": attitude_to_key_others,
            "self_control_level": HistoricalCaseExporter._infer_self_control_level(
                scene_segment,
                packet_segment,
                relationship_clause,
                initial_state_text,
            ),
            "breaking_point_hint": breaking_point_hint,
            "known_but_unspoken": known_but_unspoken,
            "misbelief": misbelief,
            "chapter_change_hint": chapter_change_hint,
        }

    @staticmethod
    def _named_segment(text: str, *, name: str, all_names: list[str]) -> str:
        raw = str(text or "").strip()
        if not raw or not name:
            return ""
        start = -1
        marker_length = 0
        for marker in (f"{name}：", f"{name}:"):
            position = raw.find(marker)
            if position >= 0 and (start < 0 or position < start):
                start = position
                marker_length = len(marker)
        if start < 0:
            return ""
        segment = raw[start + marker_length :]
        end = len(segment)
        for other_name in all_names:
            if not other_name or other_name == name:
                continue
            for marker in (f"{other_name}：", f"{other_name}:"):
                position = segment.find(marker)
                if position >= 0:
                    end = min(end, position)
        return segment[:end].strip("；; \n")

    @staticmethod
    def _relationship_clause(text: str, *, name: str, peer_name: str) -> str:
        raw = str(text or "").strip()
        if not raw or not name:
            return ""
        fragments: list[str] = []
        for delimiter in ("；", "。", "\n"):
            raw = raw.replace(delimiter, "；")
        for fragment in raw.split("；"):
            for chunk in str(fragment or "").split("，"):
                value = chunk.strip("，, \n")
                if value:
                    fragments.append(value)
        if peer_name:
            for chunk in fragments:
                if f"{name}对{peer_name}" in chunk:
                    return chunk
        candidates: list[str] = []
        for chunk in fragments:
            if not chunk or name not in chunk:
                continue
            if peer_name and peer_name in chunk:
                return chunk
            candidates.append(chunk)
        return candidates[0] if candidates else ""

    @staticmethod
    def _first_clause(text: str, *, limit: int = 80) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        cut = len(raw)
        for delimiter in ("；", "。", "！", "？", "\n", ";", ".", "!", "?", "，", ","):
            position = raw.find(delimiter)
            if 0 <= position < cut:
                cut = position
        return raw[:cut].strip()[:limit].strip()

    @staticmethod
    def _last_clause(text: str, *, limit: int = 80) -> str:
        raw = str(text or "").strip("；; \n")
        if not raw:
            return ""
        for delimiter in ("；", "。", "\n", ";", ".", "，", ","):
            if delimiter in raw:
                raw = raw.split(delimiter)[-1]
        return raw.strip()[:limit].strip()

    @staticmethod
    def _extract_marker_value(text: str, marker: str, *, limit: int = 120) -> str:
        raw = str(text or "").strip()
        if not raw or not marker:
            return ""
        position = raw.find(marker)
        if position < 0:
            return ""
        value = raw[position + len(marker) :].lstrip("：:，, ")
        end = len(value)
        for delimiter in ("；", "。", "！", "？", "\n", ";", ".", "!", "?", "，", ","):
            marker_position = value.find(delimiter)
            if marker_position >= 0:
                end = min(end, marker_position)
        return value[:end].strip()[:limit].strip()

    @staticmethod
    def _extract_last_marker_value(text: str, marker: str, *, limit: int = 120) -> str:
        raw = str(text or "").strip()
        if not raw or not marker:
            return ""
        position = raw.rfind(marker)
        if position < 0:
            return ""
        value = raw[position + len(marker) :].lstrip("：:，, ")
        end = len(value)
        for delimiter in ("；", "。", "！", "？", "\n", ";", ".", "!", "?", "，", ","):
            marker_position = value.find(delimiter)
            if marker_position >= 0:
                end = min(end, marker_position)
        return value[:end].strip()[:limit].strip()

    @staticmethod
    def _brief_hint_for_character(chapter_brief: dict[str, Any], *, name: str) -> str:
        for key in ("backstory_trigger", "human_pain_anchor", "ending_pull", "small_payoff"):
            value = str(chapter_brief.get(key) or "").strip()
            if value and name in value:
                return HistoricalCaseExporter._first_clause(value, limit=120)
        for item in list(chapter_brief.get("allowed_clues") or []):
            value = str(item or "").strip()
            if value and name in value:
                return HistoricalCaseExporter._first_clause(value, limit=120)
        return ""

    @staticmethod
    def _extract_fear_value(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if "最怕的不是" in raw and "而是" in raw:
            return HistoricalCaseExporter._extract_marker_value(raw, "而是")
        return (
            HistoricalCaseExporter._extract_marker_value(raw, "最怕的不是")
            or HistoricalCaseExporter._extract_marker_value(raw, "最怕")
            or HistoricalCaseExporter._extract_marker_value(raw, "害怕")
        )

    @staticmethod
    def _extract_reader_belief(*, chapter_payload_text: str, peer_name: str) -> str:
        raw = str(chapter_payload_text or "").strip()
        if not raw:
            return ""
        for label in ("Reader belief to preserve:", "reader belief to preserve:"):
            position = raw.find(label)
            if position < 0:
                continue
            value = raw[position + len(label) :].splitlines()[0].strip()
            if peer_name and peer_name not in value:
                return ""
            return HistoricalCaseExporter._first_clause(value, limit=120) or value[:120].strip()
        return ""

    @staticmethod
    def _explicit_misbelief_hint(*, packet_segment: str, relationship_clause: str) -> str:
        for text in (packet_segment, relationship_clause):
            raw = str(text or "").strip()
            if not raw:
                continue
            if "误以为" in raw:
                return HistoricalCaseExporter._extract_marker_value(raw, "误以为")
            if "误判" in raw:
                return HistoricalCaseExporter._extract_marker_value(raw, "误判")
        return ""

    @staticmethod
    def _generic_fear_hint(*, chapter_brief: dict[str, Any], name: str, peer_name: str) -> str:
        world_limit = HistoricalCaseExporter._first_clause(str(chapter_brief.get("world_limit") or ""), limit=120)
        if world_limit and peer_name:
            return f"怕在“{world_limit}”的场面里先失控，被{peer_name}抓住破绽"
        if world_limit:
            return f"怕在“{world_limit}”的场面里先失控，被外界抓住把柄"
        if peer_name:
            return f"怕在当前场面先失控，被{peer_name}看穿真正意图"
        return ""

    @staticmethod
    def _extract_change_hint(chapter_brief: dict[str, Any], *, name: str) -> str:
        for key in ("character_shift", "relationship_reprice", "emotional_turn"):
            value = str(chapter_brief.get(key) or "").strip()
            if not value:
                continue
            if name in value:
                return HistoricalCaseExporter._first_clause(value, limit=120)
            if key != "character_shift":
                return HistoricalCaseExporter._first_clause(value, limit=120)
        return ""

    @staticmethod
    def _infer_self_control_level(*texts: str) -> str:
        blob = " ".join(str(item or "") for item in texts)
        if any(keyword in blob for keyword in ("失控", "暴怒", "崩溃", "发疯")) and not any(
            keyword in blob for keyword in ("克制", "隐忍", "冷静", "端严", "镇定")
        ):
            return "low"
        if any(keyword in blob for keyword in ("克制", "隐忍", "冷静", "端严", "镇定", "体面", "只答", "仅通过动作")):
            return "high"
        if any(keyword in blob for keyword in ("紧绷", "压抑", "警惕", "怯懦", "礼貌镇定", "restrained", "restraint", "calm")):
            return "medium_high"
        if any(keyword in blob for keyword in ("hesitant", "shaken", "nervous")):
            return "medium_low"
        return "medium"

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
    def _used_full_rewrite(*, stage_log: list[dict[str, Any]]) -> bool:
        for entry in stage_log:
            if not isinstance(entry, dict):
                continue
            tool_calls = [str(item or "").strip() for item in list(entry.get("tool_calls") or [])]
            if "rewrite_by_plan" in tool_calls:
                return True
            if str(entry.get("tool_name") or "").strip() == "rewrite_by_plan":
                return True
            if entry.get("used_full_rewrite") is True:
                return True
            rewrite_strategy = str(entry.get("rewrite_strategy") or entry.get("rewrite_mode") or "").strip().lower()
            if rewrite_strategy in {"full_rewrite", "full"}:
                return True
        return False

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
