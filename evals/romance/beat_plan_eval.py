from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from statistics import mean
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from evals.romance.instrumentation import InstrumentedLLMClient
from evals.romance.loader import load_cases
from evals.romance.models import RomanceEvalCase, RomanceMetricDetail
from evals.romance.report_paths import build_structured_run_dir, normalize_reports_root, write_text_with_aliases
from novel_flow.config import Settings
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import ChapterBeat
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.chapter_tool_payloads import ChapterToolPayloadBuilder
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.novel_context import NovelContextFormatter, NovelContextSelectorService
from novel_flow.tools.plan_content_blocks import PlanContentBlocksTool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_label(label: str) -> str:
    keep = [ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(label or "").strip()]
    return "".join(keep).strip("_") or datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _writer_context_to_dict(context: Any) -> dict[str, Any]:
    if is_dataclass(context):
        payload = asdict(context)
    elif hasattr(context, "__dict__"):
        payload = dict(context.__dict__)
    else:
        return {"value": str(context)}
    serializable: dict[str, Any] = {}
    for key, value in payload.items():
        if hasattr(value, "model_dump"):
            serializable[key] = value.model_dump(mode="json")
        elif isinstance(value, list):
            serializable[key] = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        else:
            serializable[key] = value
    return serializable


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        parts = [_text(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        parts = [_text(item) for item in value.values()]
        return " ".join(part for part in parts if part)
    return str(value).strip()


def _tokenize_chineseish(text: str) -> set[str]:
    pieces = re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z0-9_]{2,}", str(text or ""))
    return {piece.lower() for piece in pieces if len(piece.strip()) >= 2}


def _jaccard(left: str, right: str) -> float:
    left_tokens = _tokenize_chineseish(left)
    right_tokens = _tokenize_chineseish(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)


def _metric(score: float, reason: str, evidence_summary: str, improvement_hint: str) -> RomanceMetricDetail:
    return RomanceMetricDetail(
        score=max(0.0, min(10.0, round(score, 2))),
        reason=reason,
        evidence_summary=evidence_summary,
        improvement_hint=improvement_hint,
        source="rule",
    )


class BeatPlanCostMetrics(BaseModel):
    llm_calls: int = 0
    context_llm_calls: int = 0
    planning_llm_calls: int = 0
    duration_seconds: float = 0.0
    context_prompt_chars: int = 0
    planning_prompt_chars: int = 0


class BeatPlanArtifacts(BaseModel):
    case_dir: str = ""
    case_input_json: str = ""
    writer_context_json: str = ""
    beat_plan_json: str = ""
    result_json: str = ""


class BeatOverlapDetail(BaseModel):
    left_block_id: str
    right_block_id: str
    overall_overlap: float = Field(ge=0.0, le=1.0)
    new_value_overlap: float = Field(ge=0.0, le=1.0)
    relationship_overlap: float = Field(ge=0.0, le=1.0)
    clue_overlap: float = Field(ge=0.0, le=1.0)
    end_state_overlap: float = Field(ge=0.0, le=1.0)
    note: str = ""


class BeatPlanCaseReport(BaseModel):
    case_id: str
    title: str
    tags: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "warn", "blocked"] = "warn"
    beat_count: int = 0
    target_beat_count: int = 0
    average_score: float = 0.0
    metrics: dict[str, RomanceMetricDetail] = Field(default_factory=dict)
    overlap_alerts: list[BeatOverlapDetail] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cost_metrics: BeatPlanCostMetrics = Field(default_factory=BeatPlanCostMetrics)
    artifacts: BeatPlanArtifacts = Field(default_factory=BeatPlanArtifacts)
    errors: list[str] = Field(default_factory=list)


class BeatPlanEvalSummary(BaseModel):
    label: str
    generated_at: datetime = Field(default_factory=_utc_now)
    provider: str = ""
    model: str = ""
    run_dir: str = ""
    case_ids: list[str] = Field(default_factory=list)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    average_score: float = 0.0
    average_scores: dict[str, float] = Field(default_factory=dict)
    case_reports: list[BeatPlanCaseReport] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    report_json: str = ""
    report_markdown: str = ""


class BeatPlanEvalRunner:
    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        settings: Settings | None = None,
        reports_root: str | Path | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        base_llm = llm_client or build_llm_client(self.settings)
        self.llm_client = InstrumentedLLMClient(base_llm)
        self.prompt_library = PromptLibrary()
        self.reports_root, self.runs_root = normalize_reports_root(reports_root)

    def run(
        self,
        *,
        cases_dir: str | Path = "evals/romance/cases",
        label: str = "",
        case_ids: list[str] | None = None,
        sanitize_context: bool = True,
    ) -> BeatPlanEvalSummary:
        cases = load_cases(Path(cases_dir), case_ids=case_ids)
        run_label = _sanitize_label(label or f"beat_plan_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        provider_name = self.settings.llm_provider
        model_name = self._effective_model_name()
        run_paths = build_structured_run_dir(
            self.reports_root,
            task_slug="beat_plan_eval",
            label=run_label,
            case_ids=[case.case_id for case in cases],
            provider=provider_name,
            model=model_name,
        )
        run_dir = run_paths.run_dir

        reports = [
            self._run_case(case=case, run_dir=run_dir, sanitize_context=sanitize_context)
            for case in cases
        ]
        verdict_counts = dict(Counter(report.verdict for report in reports))
        average_scores = self._average_scores(reports)
        average_score = round(mean(report.average_score for report in reports), 2) if reports else 0.0
        summary = BeatPlanEvalSummary(
            label=run_label,
            provider=provider_name,
            model=model_name,
            run_dir=str(run_dir),
            case_ids=[case.case_id for case in cases],
            verdict_counts={key: verdict_counts.get(key, 0) for key in ("pass", "warn", "blocked")},
            average_score=average_score,
            average_scores=average_scores,
            case_reports=reports,
            notes=[
                "This eval generates a real chapter beat plan through plan_content_blocks, then stops before prose drafting.",
                "Scores are rule-based so planner overlap and weak contract coverage can be caught before full chapter generation cost.",
            ],
        )
        json_path = run_dir / "beat_plan_eval_summary.json"
        md_path = run_dir / "beat_plan_eval_report.md"
        summary = summary.model_copy(update={"report_json": str(json_path), "report_markdown": str(md_path)})
        write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("summary.json",))
        write_text_with_aliases(md_path, render_beat_plan_eval_markdown(summary), alias_names=("report.md",))
        return summary

    def _run_case(self, *, case: RomanceEvalCase, run_dir: Path, sanitize_context: bool) -> BeatPlanCaseReport:
        case_dir = run_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        case_input_path = case_dir / "beat_plan_eval_case_input.json"
        write_text_with_aliases(case_input_path, case.model_dump_json(indent=2), alias_names=("case_input.json",))

        started_at = time.perf_counter()
        start_records = len(self.llm_client.records)

        self.llm_client.set_phase(f"context:{case.case_id}")
        writer_context = self._build_writer_context(case, sanitize_context=sanitize_context)
        context_calls = len(self.llm_client.records) - start_records
        writer_context_path = case_dir / "beat_plan_eval_writer_context.json"
        write_text_with_aliases(
            writer_context_path,
            _json_text(_writer_context_to_dict(writer_context)),
            alias_names=("writer_context.json",),
        )

        planning_start = len(self.llm_client.records)
        self.llm_client.set_phase(f"planning:{case.case_id}")
        payload = ChapterToolPayloadBuilder.build_plan_content_blocks_payload(
            chapter_brief=case.chapter_brief,
            context=writer_context,
        )
        tool = PlanContentBlocksTool(llm_client=self.llm_client, prompt_library=self.prompt_library)
        errors: list[str] = []
        try:
            raw_plan = tool.run(payload)
            beats = [ChapterBeat.model_validate(item) for item in raw_plan.get("blocks", [])]
        except Exception as exc:
            raw_plan = {"blocks": []}
            beats = []
            errors.append(f"beat_plan_generation_failed: {exc}")
        planning_calls = len(self.llm_client.records) - planning_start
        duration_seconds = time.perf_counter() - started_at

        beat_plan_path = case_dir / "beat_plan__generated.json"
        write_text_with_aliases(beat_plan_path, _json_text(raw_plan), alias_names=("beat_plan.json",))

        target_beat_count = PlanContentBlocksTool._target_block_count(
            case.chapter_brief.pace_contract,
            fallback_count=len(beats) or 4,
        )
        metrics, overlap_alerts = self._evaluate_plan(case=case, beats=beats, target_beat_count=target_beat_count)
        average_score = round(mean(metric.score for metric in metrics.values()), 2) if metrics else 0.0
        warnings, verdict = self._verdict(
            metrics=metrics,
            overlap_alerts=overlap_alerts,
            beat_count=len(beats),
            average_score=average_score,
        )
        if errors:
            verdict = "blocked"
            warnings = list(warnings) + ["Beat plan generation failed before scoring could complete."]
            average_score = 0.0

        report = BeatPlanCaseReport(
            case_id=case.case_id,
            title=case.title,
            tags=case.tags,
            verdict=verdict,
            beat_count=len(beats),
            target_beat_count=target_beat_count,
            average_score=average_score,
            metrics=metrics,
            overlap_alerts=overlap_alerts,
            warnings=warnings,
            cost_metrics=BeatPlanCostMetrics(
                llm_calls=len(self.llm_client.records) - start_records,
                context_llm_calls=context_calls,
                planning_llm_calls=planning_calls,
                duration_seconds=round(duration_seconds, 2),
                context_prompt_chars=self.llm_client.prompt_chars(f"context:{case.case_id}"),
                planning_prompt_chars=self.llm_client.prompt_chars(f"planning:{case.case_id}"),
            ),
            artifacts=BeatPlanArtifacts(
                case_dir=str(case_dir),
                case_input_json=str(case_input_path),
                writer_context_json=str(writer_context_path),
                beat_plan_json=str(beat_plan_path),
                result_json=str(case_dir / "beat_plan_eval_case_result.json"),
            ),
            errors=errors,
        )
        result_path = case_dir / "beat_plan_eval_case_result.json"
        write_text_with_aliases(result_path, report.model_dump_json(indent=2), alias_names=("result.json",))
        return report

    def _build_writer_context(self, case: RomanceEvalCase, *, sanitize_context: bool) -> Any:
        snapshot = NovelContextSelectorService.create_snapshot(
            chapter_brief=case.chapter_brief,
            premise=case.premise,
            twist_designs=case.twist_designs,
            story_lines=case.story_lines,
            worldbuilding=case.worldbuilding,
            character_cards=case.character_cards,
            character_milestones=case.character_milestones,
            actual_summaries=case.actual_chapter_summaries,
            current_chapter_id=case.chapter_brief.chapter_id,
        )
        selection = NovelContextSelectorService.select(snapshot=snapshot, strategy="writer_context")
        sanitizer = None
        if sanitize_context:
            sanitizer = ContextSanitizationTask(
                llm_client=self.llm_client,
                prompt_library=self.prompt_library,
            )
        context = NovelContextFormatter.format_writer_context(selection, context_sanitizer=sanitizer)
        overrides = case.context_overrides
        writing_requirements_json = _json_text(overrides.writing_requirements) if overrides.writing_requirements else "{}"
        completed_bundle = overrides.completed_chapter_summary_bundle or context.completed_chapter_memory_text
        update_map = {
            "assistant_persona_prompt": overrides.assistant_persona_prompt,
            "writing_requirements_json": writing_requirements_json,
            "reference_pack": overrides.reference_pack,
            "previous_chapter_full_text": overrides.previous_chapter_full_text,
            "completed_chapter_summary_bundle": completed_bundle,
        }
        for field_name in (
            "chapter_payload_text",
            "timeline_anchor_facts_text",
            "relevant_world_rules_text",
            "scene_character_context_text",
            "relationship_state_text",
        ):
            value = getattr(overrides, field_name)
            if str(value or "").strip():
                update_map[field_name] = value
        return replace(context, **update_map)

    def _evaluate_plan(
        self,
        *,
        case: RomanceEvalCase,
        beats: list[ChapterBeat],
        target_beat_count: int,
    ) -> tuple[dict[str, RomanceMetricDetail], list[BeatOverlapDetail]]:
        overlap_alerts = self._overlap_alerts(beats)
        metrics = {
            "beat_count_fit": self._beat_count_fit(case, beats, target_beat_count=target_beat_count),
            "beat_uniqueness_score": self._beat_uniqueness_score(beats, overlap_alerts),
            "adjacent_separation_score": self._adjacent_separation_score(beats, overlap_alerts),
            "must_not_repeat_quality": self._must_not_repeat_quality(case, beats),
            "contract_coverage_score": self._contract_coverage_score(case, beats),
            "progression_clarity_score": self._progression_clarity_score(case, beats),
            "dramatic_pressure_flow_score": self._dramatic_pressure_flow_score(beats),
        }
        return metrics, overlap_alerts

    def _beat_count_fit(
        self,
        case: RomanceEvalCase,
        beats: list[ChapterBeat],
        *,
        target_beat_count: int,
    ) -> RomanceMetricDetail:
        scene_engine = str(case.chapter_brief.scene_engine or "").strip()
        preferred_ranges = {
            "opening_pressure": (4, 5),
            "court_pressure": (4, 5),
            "relationship_collision": (4, 5),
            "disruptor_arrival": (4, 5),
            "investigation_pressure": (4, 6),
            "clue_reversal": (4, 6),
            "private_to_public_interruption": (4, 6),
            "aftermath_choice": (3, 5),
        }
        lower, upper = preferred_ranges.get(scene_engine, (max(3, target_beat_count - 1), target_beat_count + 1))
        gap = abs(len(beats) - target_beat_count)
        in_range = lower <= len(beats) <= upper
        score = 9.2 if len(beats) == target_beat_count else 8.3 if in_range else max(4.5, 8.0 - gap * 1.4)
        return _metric(
            score,
            "Beat count fits best when it stays near the pace contract target and the scene-engine range.",
            (
                f"scene_engine={scene_engine or 'unknown'}; beats={len(beats)}; "
                f"pace_contract_target={target_beat_count}; preferred_range={lower}-{upper}"
            ),
            "If the chapter is a single-pressure scene, push it back toward 4-5 beats before tuning prose.",
        )

    def _beat_uniqueness_score(
        self,
        beats: list[ChapterBeat],
        overlap_alerts: list[BeatOverlapDetail],
    ) -> RomanceMetricDetail:
        duplicate_new_value = 0
        seen_new_values: set[str] = set()
        for beat in beats:
            normalized = re.sub(r"\s+", " ", _text(beat.new_value)).lower()
            if normalized and normalized in seen_new_values:
                duplicate_new_value += 1
            if normalized:
                seen_new_values.add(normalized)
        flagged = len(overlap_alerts)
        score = max(0.0, 9.4 - duplicate_new_value * 1.8 - flagged * 0.9)
        evidence = "No duplicate-value alerts."
        if overlap_alerts:
            worst = max(overlap_alerts, key=lambda item: item.overall_overlap)
            evidence = (
                f"{worst.left_block_id} vs {worst.right_block_id} overlap={worst.overall_overlap:.2f}; "
                f"duplicate_new_value={duplicate_new_value}"
            )
        return _metric(
            score,
            "Each beat should add a non-redundant value turn instead of rephrasing the same dramatic job.",
            evidence,
            "If two beats can be summarized by the same sentence, merge them or rewrite the later beat into a new consequence.",
        )

    def _adjacent_separation_score(
        self,
        beats: list[ChapterBeat],
        overlap_alerts: list[BeatOverlapDetail],
    ) -> RomanceMetricDetail:
        adjacent_alerts = [
            item
            for item in overlap_alerts
            if abs(self._block_index(item.left_block_id) - self._block_index(item.right_block_id)) == 1
        ]
        mild_overlap = 0
        for left, right in zip(beats, beats[1:]):
            combined_overlap = _jaccard(self._combined_signature(left), self._combined_signature(right))
            if combined_overlap >= 0.35:
                mild_overlap += 1
        score = max(0.0, 9.3 - len(adjacent_alerts) * 2.4 - max(0, mild_overlap - len(adjacent_alerts)) * 0.6)
        evidence = "Adjacent beats stay distinct."
        if adjacent_alerts:
            sample = adjacent_alerts[0]
            evidence = (
                f"adjacent overlap alert: {sample.left_block_id} -> {sample.right_block_id}; "
                f"new_value={sample.new_value_overlap:.2f}, relationship={sample.relationship_overlap:.2f}, "
                f"clue={sample.clue_overlap:.2f}"
            )
        return _metric(
            score,
            "Adjacent beats should hand off consequence, not restate the same job with different wording.",
            evidence,
            "Check adjacent beats first. If new_value, relationship_delta, clue_delta, and end_state are all close, the later beat is probably redundant.",
        )

    def _must_not_repeat_quality(self, case: RomanceEvalCase, beats: list[ChapterBeat]) -> RomanceMetricDetail:
        total_items = sum(len(beat.must_not_repeat or []) for beat in beats)
        beats_with_guards = len([beat for beat in beats if beat.must_not_repeat])
        contract_seeded = 0
        for beat in beats:
            beat_items = [_text(item) for item in beat.must_not_repeat or [] if _text(item)]
            if any(
                _text(contract_item)
                and any(
                    _tokenize_chineseish(contract_item) & _tokenize_chineseish(beat_item)
                    for beat_item in beat_items
                )
                for contract_item in case.chapter_brief.must_not_repeat
            ):
                contract_seeded += 1
        unique_items = {
            re.sub(r"\s+", " ", _text(item)).lower()
            for beat in beats
            for item in beat.must_not_repeat or []
            if _text(item)
        }
        score = 3.8
        score += min(2.0, beats_with_guards / max(len(beats), 1) * 2.0)
        score += min(2.0, contract_seeded / max(len(beats), 1) * 2.0)
        score += min(2.2, len(unique_items) / max(total_items, 1) * 2.2)
        return _metric(
            score,
            "Per-beat anti-repeat guards work best when they are present, specific, and clearly inherit chapter-level repeat bans.",
            (
                f"beats_with_guards={beats_with_guards}/{len(beats)}; "
                f"contract_seeded={contract_seeded}/{len(beats)}; unique_guards={len(unique_items)}/{max(total_items, 1)}"
            ),
            "Do not stop at 'do not repeat the last beat'. Name exactly what the previous beat already finished.",
        )

    def _contract_coverage_score(self, case: RomanceEvalCase, beats: list[ChapterBeat]) -> RomanceMetricDetail:
        contract = case.chapter_brief.contract_view()
        checks = {
            "chapter_mission": self._any_overlap(
                beats,
                _text([contract["chapter_mission"], case.chapter_brief.core_scene]),
                fields=("purpose", "scene_goal", "new_value"),
            )
            or any(_text(beat.purpose) and _text(beat.scene_goal) for beat in beats[:2]),
            "plot_carrier": self._any_overlap(beats, contract["plot_carrier"], fields=("scene_goal", "must_reveal", "purpose"))
            or any(_text(beat.must_reveal) for beat in beats[1:3]),
            "relationship_delta": self._any_overlap(beats, contract["relationship_delta"], fields=("relationship_delta", "new_value"))
            or any(_text(beat.relationship_delta) for beat in beats),
            "cost_of_progress": self._any_overlap(beats, contract["cost_of_progress"], fields=("cost_shift", "end_state", "reader_feeling_target"))
            or any(_text(beat.cost_shift) for beat in beats),
            "must_payoff": self._any_overlap(beats[-2:] or beats, contract["must_payoff"], fields=("end_state", "must_reveal", "micro_hook"))
            or any(_text(beat.end_state) for beat in beats[-2:] or beats),
            "final_hook": self._any_overlap(beats[-1:] or beats, contract["final_hook"], fields=("micro_hook", "end_state", "new_value"))
            or any(_text(beat.micro_hook) for beat in beats[-1:] or beats),
        }
        covered = sum(1 for hit in checks.values() if hit)
        score = 4.0 + covered / len(checks) * 6.0
        missing = [key for key, hit in checks.items() if not hit]
        return _metric(
            score,
            "A strong beat plan visibly cashes the chapter contract instead of inventing a parallel mini-outline.",
            f"covered={covered}/{len(checks)}; missing={', '.join(missing) or 'none'}",
            "If Step8 names cost, payoff, and hook, the last half of the beat plan should show exactly where they land.",
        )

    def _progression_clarity_score(self, case: RomanceEvalCase, beats: list[ChapterBeat]) -> RomanceMetricDetail:
        first_anchor = self._any_overlap(beats[:1], case.chapter_brief.opening_hook, fields=("scene_goal", "must_reveal", "new_value"))
        last_anchor = self._any_overlap(beats[-1:], case.chapter_brief.final_hook, fields=("micro_hook", "end_state", "new_value"))
        turn_types = [str(beat.turn_type or "").strip() for beat in beats if str(beat.turn_type or "").strip()]
        unique_turn_types = len(set(turn_types))
        repeated_adjacent_turns = sum(1 for left, right in zip(turn_types, turn_types[1:]) if left == right and left)
        score = 4.2
        score += 1.8 if first_anchor else 0.2
        score += 2.2 if last_anchor else 0.3
        score += min(2.0, unique_turn_types / max(len(beats), 1) * 2.0)
        score -= min(1.5, repeated_adjacent_turns * 0.6)
        return _metric(
            score,
            "A clear plan opens sharply, changes in the middle, and cuts forward at the end.",
            (
                f"opening_anchor={first_anchor}; final_hook_anchor={last_anchor}; "
                f"unique_turn_types={unique_turn_types}/{len(beats)}; repeated_adjacent_turns={repeated_adjacent_turns}"
            ),
            "Let beat one open pressure, let the last beat cut to the next chapter, and keep middle beats from repeating the same turn type.",
        )

    def _dramatic_pressure_flow_score(self, beats: list[ChapterBeat]) -> RomanceMetricDetail:
        action_ready = sum(1 for beat in beats if beat.must_land_in_action)
        reaction_ready = sum(1 for beat in beats if beat.human_reaction_target)
        cost_ready = sum(1 for beat in beats if _text(beat.cost_shift))
        hook_ready = sum(1 for beat in beats if _text(beat.micro_hook))
        score = 4.0
        score += min(1.8, action_ready / max(len(beats), 1) * 1.8)
        score += min(1.8, reaction_ready / max(len(beats), 1) * 1.8)
        score += min(1.8, cost_ready / max(len(beats), 1) * 1.8)
        score += min(1.8, hook_ready / max(len(beats), 1) * 1.8)
        return _metric(
            score,
            "Dramatic pressure rises when beats carry action, human reaction, cost, and hook instead of summary-only movement.",
            (
                f"action_ready={action_ready}/{len(beats)}; reaction_ready={reaction_ready}/{len(beats)}; "
                f"cost_ready={cost_ready}/{len(beats)}; hook_ready={hook_ready}/{len(beats)}"
            ),
            "If a beat advances the chapter only through explanation, add action landing, human reaction, or explicit cost before touching prose.",
        )

    def _overlap_alerts(self, beats: list[ChapterBeat]) -> list[BeatOverlapDetail]:
        alerts: list[BeatOverlapDetail] = []
        for idx, left in enumerate(beats):
            for right in beats[idx + 1 :]:
                new_value_overlap = _jaccard(left.new_value, right.new_value)
                relationship_overlap = _jaccard(left.relationship_delta, right.relationship_delta)
                clue_overlap = _jaccard(left.clue_delta, right.clue_delta)
                end_state_overlap = _jaccard(left.end_state, right.end_state)
                overall = (
                    new_value_overlap * 0.4
                    + relationship_overlap * 0.25
                    + clue_overlap * 0.15
                    + end_state_overlap * 0.2
                )
                if overall < 0.42 and max(new_value_overlap, relationship_overlap, clue_overlap, end_state_overlap) < 0.72:
                    continue
                alerts.append(
                    BeatOverlapDetail(
                        left_block_id=left.block_id,
                        right_block_id=right.block_id,
                        overall_overlap=round(overall, 3),
                        new_value_overlap=round(new_value_overlap, 3),
                        relationship_overlap=round(relationship_overlap, 3),
                        clue_overlap=round(clue_overlap, 3),
                        end_state_overlap=round(end_state_overlap, 3),
                        note="These beats look close enough that one may be rephrasing the other's dramatic job.",
                    )
                )
        alerts.sort(key=lambda item: (-item.overall_overlap, item.left_block_id, item.right_block_id))
        return alerts[:8]

    def _verdict(
        self,
        *,
        metrics: dict[str, RomanceMetricDetail],
        overlap_alerts: list[BeatOverlapDetail],
        beat_count: int,
        average_score: float,
    ) -> tuple[list[str], Literal["pass", "warn", "blocked"]]:
        blockers: list[str] = []
        warnings: list[str] = []
        if beat_count < 3:
            blockers.append("Beat count is too low to support meaningful chapter progression.")
        for key in ("beat_uniqueness_score", "adjacent_separation_score", "contract_coverage_score", "progression_clarity_score"):
            detail = metrics.get(key)
            if detail is not None and detail.score < 5.8:
                blockers.append(f"{key} is blocking-level weak ({detail.score:.2f}).")
        if average_score < 6.4:
            blockers.append(f"Average beat-plan score is too low ({average_score:.2f}).")
        if blockers:
            return blockers, "blocked"

        if overlap_alerts:
            sample = overlap_alerts[0]
            warnings.append(
                f"Top overlap alert: {sample.left_block_id} vs {sample.right_block_id} overall={sample.overall_overlap:.2f}."
            )
        for key, detail in metrics.items():
            if detail.score < 6.8:
                warnings.append(f"{key} still needs work ({detail.score:.2f}).")
        if average_score < 7.4:
            warnings.append(f"Average beat-plan score is only {average_score:.2f}.")
        if warnings:
            return warnings, "warn"
        return warnings, "pass"

    @staticmethod
    def _combined_signature(beat: ChapterBeat) -> str:
        return _text(
            [
                beat.purpose,
                beat.scene_goal,
                beat.new_value,
                beat.relationship_delta,
                beat.clue_delta,
                beat.end_state,
                beat.micro_hook,
            ]
        )

    @staticmethod
    def _block_index(block_id: str) -> int:
        match = re.search(r"\.b(\d+)$", str(block_id or ""))
        return int(match.group(1)) if match else -1

    @staticmethod
    def _any_overlap(beats: list[ChapterBeat], target: str, *, fields: tuple[str, ...]) -> bool:
        target_text = _text(target)
        if not target_text:
            return False
        for beat in beats:
            for field in fields:
                value = _text(getattr(beat, field, ""))
                if not value:
                    continue
                if _jaccard(target_text, value) >= 0.18 or target_text in value or value in target_text:
                    return True
        return False

    @staticmethod
    def _average_scores(reports: list[BeatPlanCaseReport]) -> dict[str, float]:
        metric_names = sorted({name for report in reports for name in report.metrics.keys()})
        averages: dict[str, float] = {}
        for name in metric_names:
            values = [report.metrics[name].score for report in reports if name in report.metrics]
            averages[name] = round(mean(values), 2) if values else 0.0
        return averages

    def _effective_model_name(self) -> str:
        provider = self.settings.llm_provider.strip().lower()
        if provider == "deepseek":
            return self.settings.deepseek_model or ""
        if provider == "openai":
            return self.settings.openai_model or ""
        if provider == "doubao":
            return self.settings.doubao_model or ""
        if provider == "codex":
            return self.settings.codex_model or ""
        return ""


def render_beat_plan_eval_markdown(summary: BeatPlanEvalSummary) -> str:
    lines = [
        f"# Beat Plan Eval: {summary.label}",
        "",
        f"- provider: `{summary.provider}`",
        f"- model: `{summary.model}`",
        f"- generated_at: `{summary.generated_at.isoformat()}`",
        f"- cases: `{len(summary.case_reports)}`",
        f"- average_score: `{summary.average_score:.2f}`",
        (
            f"- verdict_counts: pass={summary.verdict_counts.get('pass', 0)}, "
            f"warn={summary.verdict_counts.get('warn', 0)}, blocked={summary.verdict_counts.get('blocked', 0)}"
        ),
        "",
        "## Average Scores",
        "",
        "| metric | score |",
        "| --- | ---: |",
    ]
    for name, score in sorted(summary.average_scores.items()):
        lines.append(f"| {name} | {score:.2f} |")

    for report in summary.case_reports:
        lines.extend(
            [
                "",
                f"## {report.case_id}",
                "",
                f"- title: `{report.title}`",
                f"- verdict: `{report.verdict}`",
                f"- beat_count: `{report.beat_count}` (target `{report.target_beat_count}`)",
                f"- average_score: `{report.average_score:.2f}`",
                (
                    f"- llm_calls: `{report.cost_metrics.llm_calls}` "
                    f"(context={report.cost_metrics.context_llm_calls}, planning={report.cost_metrics.planning_llm_calls})"
                ),
                f"- planning_prompt_chars: `{report.cost_metrics.planning_prompt_chars}`",
                f"- warnings: {'; '.join(report.warnings) or 'None'}",
                "",
                "| metric | score | reason |",
                "| --- | ---: | --- |",
            ]
        )
        for name, metric in sorted(report.metrics.items()):
            lines.append(f"| {name} | {metric.score:.2f} | {metric.reason} |")
        if report.overlap_alerts:
            lines.extend(["", "### Overlap Alerts", ""])
            for item in report.overlap_alerts[:4]:
                lines.append(
                    f"- `{item.left_block_id}` vs `{item.right_block_id}`: overall={item.overall_overlap:.2f}, "
                    f"new_value={item.new_value_overlap:.2f}, relationship={item.relationship_overlap:.2f}, "
                    f"clue={item.clue_overlap:.2f}, end_state={item.end_state_overlap:.2f}"
                )
        if report.errors:
            lines.append("")
            lines.append(f"- errors: {'; '.join(report.errors)}")
    return "\n".join(lines).strip() + "\n"
