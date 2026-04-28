from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field

from evals.romance.step_fixture_loader import iter_step_fixture_paths, load_step_fixture
from novel_flow.models.schemas import ChapterBrief


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StepPlanMetric(BaseModel):
    score: float = Field(ge=0.0, le=10.0)
    reason: str = ""


class StepPlanStepReport(BaseModel):
    step_id: str
    title: str
    metrics: dict[str, StepPlanMetric] = Field(default_factory=dict)
    step_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class StepPlanCaseReport(BaseModel):
    case_id: str
    source: str = ""
    verdict: Literal["pass", "warn", "blocked"] = "warn"
    average_step_score: float = 0.0
    step_reports: list[StepPlanStepReport] = Field(default_factory=list)
    warning_steps: list[str] = Field(default_factory=list)
    blocking_steps: list[str] = Field(default_factory=list)


class StepPlanEvalSummary(BaseModel):
    label: str
    generated_at: datetime = Field(default_factory=_utc_now)
    source_case_dir: str = ""
    case_ids: list[str] = Field(default_factory=list)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    average_score: float = 0.0
    case_reports: list[StepPlanCaseReport] = Field(default_factory=list)
    report_json: str = ""
    report_markdown: str = ""


STRONG_TOKENS = (
    "灭口",
    "赐婚",
    "同生契",
    "秘境",
    "直播",
    "倒计时",
    "黑稿",
    "背叛",
    "误读",
    "危机",
    "代价",
    "旧案",
    "规则",
)
RELATION_TOKENS = ("婚", "救", "恨", "爱", "旧情", "暧昧", "误读", "同盟", "保护", "心动", "前任")
COST_TOKENS = ("代价", "惩罚", "限制", "不能", "必须", "风险", "追责", "反噬", "灭口")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    return str(value).strip()


def _clamp(score: float) -> float:
    return max(0.0, min(10.0, round(score, 2)))


def _metric(score: float, reason: str) -> StepPlanMetric:
    return StepPlanMetric(score=_clamp(score), reason=reason[:220])


def _hits(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token in text)


def _count_score(count: int, *, target: int, base: float = 4.0, each: float = 1.0) -> float:
    return base + min(float(target), float(count)) * each


def _field_count(items: list[dict[str, Any]], fields: list[str]) -> int:
    return sum(1 for item in items if isinstance(item, dict) and all(_text(item.get(field)) for field in fields))


def _evaluate_step1(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_1") or {}
    premise = step.get("premise") or {}
    engine = step.get("story_engine") or {}
    hook_text = _text([premise.get("high_concept"), premise.get("core_hook"), premise.get("emotional_hook"), premise.get("selling_points")])
    conflict_text = _text([premise.get("central_conflict"), premise.get("escalation_path"), engine.get("story_trigger"), engine.get("structural_inertia")])
    fit_text = _text([premise.get("genre"), premise.get("target_style"), engine.get("default_track"), engine.get("narrative_mode")])
    novelty_text = _text([hook_text, engine.get("world_rules"), engine.get("objective_conditions")])
    metrics = {
        "hook_clarity": _metric(4.5 + min(3.0, len(hook_text) / 60) + _hits(hook_text, STRONG_TOKENS) * 0.6, hook_text),
        "conflict_engine": _metric(4.0 + min(3.0, len(conflict_text) / 80) + _hits(conflict_text, COST_TOKENS) * 0.5, conflict_text),
        "genre_tone_fit": _metric(5.0 + min(3.0, len(fit_text) / 70) + (1.0 if premise.get("target_style") else 0.0), fit_text),
        "novelty_pressure": _metric(4.5 + _hits(novelty_text, STRONG_TOKENS) * 0.5 + min(2.0, len(engine.get("world_rules") or []) * 0.3), novelty_text),
    }
    return _step_report("step_1", "premise", metrics)


def _evaluate_step2(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_2") or payload.get("step_1") or {}
    engine = step.get("story_engine") or {}
    detail = engine.get("worldbuilding_detail") or step.get("worldbuilding_detail") or {}
    rules = engine.get("world_rules") or []
    pressure_text = _text([engine.get("power_structure"), detail.get("institutions"), detail.get("resource_limits"), detail.get("punishment_rules")])
    romance_text = _text([detail.get("romance_pressure"), engine.get("rebound_mechanism"), engine.get("default_track")])
    metrics = {
        "rule_functionality": _metric(_count_score(len(rules), target=6, each=0.7) + min(1.0, len(detail) * 0.15), f"world_rules={len(rules)}, detail_sections={len(detail)}"),
        "pressure_system": _metric(4.0 + min(3.0, len(pressure_text) / 120) + _hits(pressure_text, COST_TOKENS) * 0.35, pressure_text),
        "romance_support": _metric(4.5 + min(2.5, _hits(romance_text, RELATION_TOKENS) * 0.6) + (1.0 if detail.get("romance_pressure") else 0.0), romance_text),
        "anti_infodump": _metric(8.0 if 4 <= len(rules) <= 10 and 3 <= len(detail) <= 7 else 6.0, f"rules={len(rules)} detail_sections={len(detail)}"),
    }
    return _step_report("step_2", "story_engine", metrics)


def _evaluate_step3(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_3") or {}
    characters = [item for item in step.get("characters") or [] if isinstance(item, dict)]
    network = [item for item in step.get("relationship_network") or [] if isinstance(item, dict)]
    developed = [item for item in characters if len(item.get("development_axes") or []) >= 2 and _text(item.get("motivation"))]
    behavior = [item for item in characters if _text(item.get("behavior_pattern")) and _text(item.get("initial_state"))]
    relation_text = _text([network, [item.get("relationships") for item in characters]])
    metrics = {
        "drive_depth": _metric(3.5 + min(4.0, len(developed) * 1.0), f"developed_characters={len(developed)}"),
        "relationship_tension": _metric(4.0 + min(3.0, len(network) * 0.8) + min(2.0, _hits(relation_text, RELATION_TOKENS) * 0.35), relation_text),
        "behavior_writability": _metric(3.5 + min(4.5, len(behavior) * 1.0), f"behavior_ready_characters={len(behavior)}"),
        "cast_function": _metric(4.0 + min(4.0, len(characters) * 0.8), f"characters={len(characters)}"),
    }
    return _step_report("step_3", "characters", metrics)


def _evaluate_step4(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_4") or {}
    events = [item for item in step.get("event_timeline") or [] if isinstance(item, dict)]
    causal = _field_count(events, ["event_id"]) + _field_count(events, ["trigger", "consequence"])
    function_ready = sum(1 for item in events if _text(item.get("function")) or _text(item.get("consequence")))
    event_text = _text(events)
    metrics = {
        "causal_chain": _metric(4.0 + min(4.0, causal * 0.6), f"events={len(events)}, causal_fields={causal}"),
        "escalation": _metric(4.0 + min(3.0, len(events) * 0.6) + _hits(event_text, STRONG_TOKENS) * 0.25, event_text),
        "relationship_impact": _metric(4.0 + min(3.5, _hits(event_text, RELATION_TOKENS) * 0.45) + min(1.0, function_ready * 0.2), event_text),
        "hook_density": _metric(4.0 + min(4.0, _hits(event_text, STRONG_TOKENS) * 0.45), event_text),
    }
    return _step_report("step_4", "event_timeline", metrics)


def _evaluate_step5(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_5") or {}
    milestones = [item for item in step.get("milestone_grid") or step.get("character_milestones") or [] if isinstance(item, dict)]
    milestone_text = _text(milestones)
    no_jump = sum(1 for item in milestones if _text(item.get("must_not_jump_to")))
    state_ready = sum(1 for item in milestones if _text(item.get("range")) and _text(item.get("relationship")))
    metrics = {
        "arc_progression": _metric(4.0 + min(4.0, len(milestones) * 0.9), f"milestones={len(milestones)}"),
        "no_early_closure": _metric(4.0 + min(4.0, no_jump * 1.0), f"must_not_jump_to={no_jump}"),
        "state_trackability": _metric(4.0 + min(4.0, state_ready * 1.0), f"state_ready={state_ready}"),
        "cost_alignment": _metric(4.0 + min(4.0, _hits(milestone_text, COST_TOKENS + RELATION_TOKENS) * 0.35), milestone_text),
    }
    return _step_report("step_5", "character_milestones", metrics)


def _evaluate_step6(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_6") or {}
    twists = [item for item in step.get("twist_designs") or [] if isinstance(item, dict)]
    clue_ready = sum(1 for item in twists if item.get("allowed_clues") and _text(item.get("payoff_effect")))
    belief_ready = _field_count(twists, ["false_belief", "truth", "reader_alignment"])
    relationship_text = _text([item.get("payoff_effect") for item in twists])
    forced_guard = sum(1 for item in twists if item.get("forbidden_reveals") and _text(item.get("seed_from")) and _text(item.get("reveal_at")))
    metrics = {
        "seed_payoff": _metric(4.0 + min(4.0, clue_ready * 1.4), f"clue_ready_twists={clue_ready}"),
        "misbelief_quality": _metric(4.0 + min(4.0, belief_ready * 1.4), f"belief_ready_twists={belief_ready}"),
        "relationship_reprice": _metric(4.0 + min(4.0, _hits(relationship_text, RELATION_TOKENS) * 0.6), relationship_text),
        "no_forced_twist": _metric(4.0 + min(4.0, forced_guard * 1.4), f"guarded_twists={forced_guard}"),
    }
    return _step_report("step_6", "twists", metrics)


def _evaluate_step7(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_7") or {}
    lines = [item for item in step.get("story_lines") or [] if isinstance(item, dict)]
    types = {item.get("line_type") for item in lines if item.get("line_type")}
    carried = sum(1 for item in lines if item.get("carried_twists"))
    continuity = _field_count(lines, ["start_state", "midpoint_shift", "end_state"])
    reader = _field_count(lines, ["core_question", "reader_hook_mode"])
    metrics = {
        "line_separation": _metric(4.0 + min(4.0, len(types) * 1.2), f"line_types={len(types)}, lines={len(lines)}"),
        "interlock": _metric(4.0 + min(3.0, carried * 1.0) + (1.0 if step.get("line_interlock") else 0.0), f"carried_twists={carried}, has_line_interlock={bool(step.get('line_interlock'))}"),
        "continuity_drive": _metric(4.0 + min(4.0, continuity * 1.3), f"continuity_ready_lines={continuity}"),
        "reader_question": _metric(4.0 + min(4.0, reader * 1.3), f"reader_ready_lines={reader}"),
    }
    return _step_report("step_7", "story_lines", metrics)


def _evaluate_step8(payload: dict[str, Any]) -> StepPlanStepReport:
    step = payload.get("step_8") or {}
    briefs = [ChapterBrief.model_validate(item) for item in step.get("chapter_briefs") or [] if isinstance(item, dict)]
    selected = briefs[:3]
    opening_text = _text([item.opening_hook for item in selected])
    ending_text = _text([item.ending_pull for item in selected])
    chain_ready = sum(1 for item in selected if _text(item.incoming_hook))
    function_ready = sum(1 for item in selected if _text(item.core_scene) and _text(item.relationship_reprice) and _text(item.small_payoff))
    retention_context = _text([step.get("generation_context"), step.get("retention_design")])
    metrics = {
        "opening_hook": _metric(4.0 + min(4.0, _hits(opening_text, STRONG_TOKENS) * 0.6) + min(1.0, len(opening_text) / 160), opening_text),
        "ending_pull": _metric(4.0 + min(4.0, _hits(ending_text, STRONG_TOKENS) * 0.6) + min(1.0, len(ending_text) / 160), ending_text),
        "chapter_chain": _metric(4.0 + min(4.0, chain_ready * 1.3), f"incoming_hooks={chain_ready}, briefs={len(selected)}"),
        "first3_retention": _metric(4.0 + min(3.0, function_ready * 1.0) + min(1.5, len(retention_context) / 160), f"function_ready={function_ready}; {retention_context}"),
    }
    return _step_report("step_8", "chapter_briefs", metrics)


def _step_report(step_id: str, title: str, metrics: dict[str, StepPlanMetric]) -> StepPlanStepReport:
    step_score = round(mean(metric.score for metric in metrics.values()), 2) if metrics else 0.0
    warnings = [key for key, metric in metrics.items() if metric.score < 6.5]
    return StepPlanStepReport(step_id=step_id, title=title, metrics=metrics, step_score=step_score, warnings=warnings)


STEP_EVALUATORS = [
    _evaluate_step1,
    _evaluate_step2,
    _evaluate_step3,
    _evaluate_step4,
    _evaluate_step5,
    _evaluate_step6,
    _evaluate_step7,
    _evaluate_step8,
]


class StepPlanEvalRunner:
    def __init__(self, *, reports_root: str | Path = "evals/romance/reports") -> None:
        self.reports_root = Path(reports_root)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        cases_dir: str | Path = "evals/romance/cases",
        label: str = "",
        case_ids: list[str] | None = None,
    ) -> StepPlanEvalSummary:
        selected = set(case_ids or [])
        paths = [
            path
            for path in iter_step_fixture_paths(cases_dir)
            if not selected or path.parent.name in selected
        ]
        if selected:
            found = {path.parent.name for path in paths}
            missing = sorted(selected - found)
            if missing:
                raise FileNotFoundError(f"Missing step fixtures: {', '.join(missing)}")

        reports = [self._evaluate_case(path) for path in paths]
        run_label = str(label or "step_plan_eval").strip()
        run_dir = self.reports_root / run_label
        run_dir.mkdir(parents=True, exist_ok=True)

        verdict_counter = Counter(report.verdict for report in reports)
        average_score = round(mean(report.average_step_score for report in reports), 2) if reports else 0.0
        summary = StepPlanEvalSummary(
            label=run_label,
            source_case_dir=str(Path(cases_dir)),
            case_ids=[item.case_id for item in reports],
            verdict_counts={key: verdict_counter.get(key, 0) for key in ("pass", "warn", "blocked")},
            average_score=average_score,
            case_reports=reports,
        )
        json_path = run_dir / "step_plan_eval_summary.json"
        md_path = run_dir / "report.md"
        summary = summary.model_copy(update={"report_json": str(json_path), "report_markdown": str(md_path)})
        json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        md_path.write_text(render_step_plan_eval_markdown(summary), encoding="utf-8")
        return summary

    @staticmethod
    def _evaluate_case(path: Path) -> StepPlanCaseReport:
        payload = load_step_fixture(path)
        step_reports = [evaluator(payload) for evaluator in STEP_EVALUATORS]
        average_score = round(mean(item.step_score for item in step_reports), 2) if step_reports else 0.0
        blocking_steps = [item.step_id for item in step_reports if item.step_score < 5.8]
        warning_steps = [item.step_id for item in step_reports if item.step_id not in blocking_steps and item.step_score < 6.8]
        verdict: Literal["pass", "warn", "blocked"] = "blocked"
        if not blocking_steps and average_score >= 7.4 and not warning_steps:
            verdict = "pass"
        elif not blocking_steps and average_score >= 6.5:
            verdict = "warn"
        return StepPlanCaseReport(
            case_id=str(payload.get("case_id") or path.parent.name),
            source=str(path),
            verdict=verdict,
            average_step_score=average_score,
            step_reports=step_reports,
            warning_steps=warning_steps,
            blocking_steps=blocking_steps,
        )


def render_step_plan_eval_markdown(summary: StepPlanEvalSummary) -> str:
    lines = [
        f"# Step Plan Eval: {summary.label}",
        "",
        f"- source_case_dir: `{summary.source_case_dir}`",
        f"- cases: `{len(summary.case_reports)}`",
        f"- average_score: `{summary.average_score:.2f}`",
        f"- verdict_counts: pass={summary.verdict_counts.get('pass', 0)}, warn={summary.verdict_counts.get('warn', 0)}, blocked={summary.verdict_counts.get('blocked', 0)}",
    ]
    for report in summary.case_reports:
        lines.extend(
            [
                "",
                f"## {report.case_id}",
                "",
                f"- source: `{report.source}`",
                f"- verdict: `{report.verdict}`",
                f"- average_step_score: `{report.average_step_score:.2f}`",
                f"- warning_steps: {', '.join(report.warning_steps) or 'None'}",
                f"- blocking_steps: {', '.join(report.blocking_steps) or 'None'}",
                "",
                "| step | score | warnings |",
                "| --- | ---: | --- |",
            ]
        )
        for step in report.step_reports:
            lines.append(f"| {step.step_id} {step.title} | {step.step_score:.2f} | {', '.join(step.warnings) or 'None'} |")
    return "\n".join(lines).strip() + "\n"
