from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field

from evals.romance.step_fixture_loader import iter_step_fixture_paths, load_step_fixture
from novel_flow.agents.blueprint import BlueprintAgent
from novel_flow.config import Settings
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import ChapterBrief


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value).strip()


def _clamp(score: float) -> float:
    return max(0.0, min(10.0, round(score, 2)))


def _metric(score: float, reason: str) -> "LongArcMetric":
    return LongArcMetric(score=_clamp(score), reason=reason[:260])


def _chapter_no(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _safe_mean(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def _hits(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token and token in text)


def _tokenize_chineseish(text: str) -> set[str]:
    pieces = re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z0-9_]{2,}", text)
    return {item for item in pieces if len(item.strip()) >= 2}


HIGH_PRESSURE_TOKENS = (
    "灭口",
    "赐婚",
    "倒计时",
    "同生契",
    "秘境",
    "发布会",
    "旧案",
    "反噬",
    "背叛",
    "暴露",
    "追杀",
    "危机",
    "审问",
    "失控",
    "代价",
    "真相",
    "陷阱",
    "阴谋",
    "密令",
    "婚约",
    "旧伤",
    "钩子",
)
RELATION_TOKENS = ("关系", "误读", "旧情", "暧昧", "婚约", "同盟", "保护", "试探", "边界", "心动", "回避", "重估")
ADVANCE_TOKENS = ("推进", "发现", "逼出", "改变", "选择", "交换", "暴露", "转向", "代价", "线索", "重估", "承接")
CLOSURE_TOKENS = ("和解", "表白", "说清", "彻底明白", "真相大白", "消除误会")


class LongArcMetric(BaseModel):
    score: float = Field(ge=0.0, le=10.0)
    reason: str = ""


class LongArcCaseReport(BaseModel):
    case_id: str
    source: str = ""
    generated_step8_path: str = ""
    chapter_count: int = 0
    verdict: Literal["pass", "warn", "blocked"] = "warn"
    average_score: float = 0.0
    metrics: dict[str, LongArcMetric] = Field(default_factory=dict)
    warning_metrics: list[str] = Field(default_factory=list)
    blocking_metrics: list[str] = Field(default_factory=list)


class LongArcEvalSummary(BaseModel):
    label: str
    generated_at: datetime = Field(default_factory=_utc_now)
    source_case_dir: str = ""
    generated: bool = False
    target_chapters: int = 0
    batch_size: int = 0
    case_ids: list[str] = Field(default_factory=list)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    average_score: float = 0.0
    case_reports: list[LongArcCaseReport] = Field(default_factory=list)
    report_json: str = ""
    report_markdown: str = ""


class LongArcStep8Evaluator:
    def evaluate_case(
        self,
        *,
        case_id: str,
        source: str,
        payload: dict[str, Any],
        generated_step8_path: str = "",
    ) -> LongArcCaseReport:
        step8 = payload.get("step_8") or {}
        briefs = [
            ChapterBrief.model_validate(item)
            for item in step8.get("chapter_briefs") or []
            if isinstance(item, dict)
        ]
        briefs.sort(key=lambda item: _chapter_no(item.chapter_id))
        metrics = self._metrics(payload, briefs)
        average_score = _safe_mean([item.score for item in metrics.values()])
        blocking_metrics = [key for key, value in metrics.items() if value.score < 5.8]
        warning_metrics = [key for key, value in metrics.items() if key not in blocking_metrics and value.score < 6.8]
        verdict: Literal["pass", "warn", "blocked"] = "blocked"
        if not blocking_metrics and average_score >= 7.5 and not warning_metrics:
            verdict = "pass"
        elif not blocking_metrics and average_score >= 6.6:
            verdict = "warn"
        return LongArcCaseReport(
            case_id=case_id,
            source=source,
            generated_step8_path=generated_step8_path,
            chapter_count=len(briefs),
            verdict=verdict,
            average_score=average_score,
            metrics=metrics,
            warning_metrics=warning_metrics,
            blocking_metrics=blocking_metrics,
        )

    def _metrics(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> dict[str, LongArcMetric]:
        return {
            "story_spine_alignment": self._story_spine_alignment(payload, briefs),
            "genre_tone_consistency": self._genre_tone_consistency(payload, briefs),
            "chapter_chain_causality": self._chapter_chain_causality(briefs),
            "escalation_curve": self._escalation_curve(briefs),
            "character_arc_alignment": self._character_arc_alignment(payload, briefs),
            "twist_seed_payoff": self._twist_seed_payoff(payload, briefs),
            "line_interlock": self._line_interlock(payload, briefs),
            "reader_retention_curve": self._reader_retention_curve(briefs),
            "information_budget_control": self._information_budget_control(briefs),
            "repetition_plateau": self._repetition_plateau(briefs),
        }

    def _story_spine_alignment(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> LongArcMetric:
        premise = (payload.get("step_1") or {}).get("premise") or {}
        spine_text = _text([premise.get("high_concept"), premise.get("core_hook"), premise.get("central_conflict"), premise.get("selling_points")])
        spine_tokens = _tokenize_chineseish(spine_text)
        brief_texts = [_text([item.summary, item.core_scene, item.chapter_object, item.ending_pull]) for item in briefs]
        aligned = sum(1 for text in brief_texts if bool(_tokenize_chineseish(text) & spine_tokens) or _hits(text, HIGH_PRESSURE_TOKENS) >= 1)
        functional = sum(1 for item in briefs if item.active_lines and item.core_scene and item.ending_pull)
        score = 4.0 + min(3.0, aligned / max(len(briefs), 1) * 3.0) + min(3.0, functional / max(len(briefs), 1) * 3.0)
        return _metric(score, f"aligned_chapters={aligned}/{len(briefs)}, functional_briefs={functional}/{len(briefs)}")

    def _genre_tone_consistency(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> LongArcMetric:
        style_text = _text([(payload.get("step_1") or {}).get("premise", {}).get("target_style"), payload.get("user_input", {}).get("style_request")])
        all_text = _text([item.model_dump(mode="json") for item in briefs])
        relation_hits = _hits(all_text, RELATION_TOKENS)
        pressure_hits = _hits(all_text, HIGH_PRESSURE_TOKENS)
        style_bonus = 1.0 if style_text else 0.0
        romance_presence = min(3.0, relation_hits * 0.35)
        pressure_presence = min(2.0, pressure_hits * 0.18)
        score = 4.5 + style_bonus + romance_presence + pressure_presence
        return _metric(score, f"style={style_text}; relation_hits={relation_hits}, pressure_hits={pressure_hits}")

    def _chapter_chain_causality(self, briefs: list[ChapterBrief]) -> LongArcMetric:
        if not briefs:
            return _metric(0.0, "no chapter briefs")
        chained = 0
        lexical = 0
        for prev, current in zip(briefs, briefs[1:]):
            if _text(current.incoming_hook):
                chained += 1
            overlap = _tokenize_chineseish(prev.ending_pull) & _tokenize_chineseish(current.incoming_hook)
            if overlap or _hits(_text([prev.ending_pull, current.incoming_hook]), HIGH_PRESSURE_TOKENS) >= 1:
                lexical += 1
        denominator = max(len(briefs) - 1, 1)
        score = 3.5 + chained / denominator * 4.0 + lexical / denominator * 2.5
        return _metric(score, f"incoming_hooks={chained}/{denominator}, ending_to_incoming_overlap={lexical}/{denominator}")

    def _escalation_curve(self, briefs: list[ChapterBrief]) -> LongArcMetric:
        if not briefs:
            return _metric(0.0, "no chapter briefs")
        intensities = [
            _hits(_text([item.opening_hook, item.core_scene, item.ending_pull, item.human_pain_anchor]), HIGH_PRESSURE_TOKENS)
            + min(2, len(item.active_twists or []))
            for item in briefs
        ]
        early = _safe_mean([float(v) for v in intensities[: max(1, len(intensities) // 3)]])
        late = _safe_mean([float(v) for v in intensities[-max(1, len(intensities) // 3) :]])
        unique_scenes = len({str(item.scene_engine) for item in briefs if item.scene_engine})
        turns = sum(1 for item in briefs if _hits(_text([item.character_shift, item.relationship_reprice, item.emotional_turn]), ADVANCE_TOKENS + RELATION_TOKENS) >= 1)
        growth = 1.5 if late >= early else 0.0
        score = 4.0 + growth + min(2.0, unique_scenes * 0.4) + min(2.5, turns / max(len(briefs), 1) * 2.5)
        return _metric(score, f"early_intensity={early}, late_intensity={late}, scene_engines={unique_scenes}, turn_chapters={turns}/{len(briefs)}")

    def _character_arc_alignment(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> LongArcMetric:
        names = {
            str(item.get("name", "")).strip()
            for item in (payload.get("step_3") or {}).get("characters") or []
            if isinstance(item, dict)
        }
        focused = sum(1 for item in briefs if any(name in names for name in item.character_focus))
        arc_ready = sum(1 for item in briefs if item.character_shift and item.relationship_reprice and item.emotional_turn)
        premature = sum(1 for item in briefs if _hits(_text([item.summary, item.relationship_reprice, item.emotional_turn]), CLOSURE_TOKENS) >= 1)
        score = 4.0 + min(2.5, focused / max(len(briefs), 1) * 2.5) + min(3.0, arc_ready / max(len(briefs), 1) * 3.0) - min(2.0, premature * 0.4)
        return _metric(score, f"known_focus={focused}/{len(briefs)}, arc_ready={arc_ready}/{len(briefs)}, premature_closure={premature}")

    def _twist_seed_payoff(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> LongArcMetric:
        twist_ids = {
            str(item.get("twist_id", "")).strip()
            for item in (payload.get("step_6") or {}).get("twist_designs") or []
            if isinstance(item, dict)
        }
        active = [twist for item in briefs for twist in item.active_twists if twist in twist_ids]
        clue_chapters = sum(1 for item in briefs if item.allowed_clues or item.clue_reveal_mechanism)
        forbidden_ready = sum(1 for item in briefs if item.forbidden)
        spread = len(set(active))
        score = 4.0 + min(2.0, spread * 0.8) + min(2.5, clue_chapters / max(len(briefs), 1) * 2.5) + min(1.5, forbidden_ready / max(len(briefs), 1) * 1.5)
        return _metric(score, f"active_twists={Counter(active)}, clue_chapters={clue_chapters}/{len(briefs)}, guarded={forbidden_ready}/{len(briefs)}")

    def _line_interlock(self, payload: dict[str, Any], briefs: list[ChapterBrief]) -> LongArcMetric:
        line_ids = {
            str(item.get("line_id", "")).strip()
            for item in (payload.get("step_7") or {}).get("story_lines") or []
            if isinstance(item, dict)
        }
        active = [line for item in briefs for line in item.active_lines if line in line_ids]
        multi_line = sum(1 for item in briefs if len([line for line in item.active_lines if line in line_ids]) >= 2)
        spread = len(set(active))
        dominant_ratio = max(Counter(active).values(), default=0) / max(len(active), 1)
        score = 4.0 + min(2.0, spread * 0.7) + min(2.5, multi_line / max(len(briefs), 1) * 2.5) + (1.0 if dominant_ratio <= 0.75 else 0.0)
        return _metric(score, f"line_spread={spread}/{len(line_ids)}, multi_line_chapters={multi_line}/{len(briefs)}, dominant_ratio={dominant_ratio:.2f}")

    def _reader_retention_curve(self, briefs: list[ChapterBrief]) -> LongArcMetric:
        if not briefs:
            return _metric(0.0, "no chapter briefs")
        checkpoints = [3, 10, 20, len(briefs)]
        available = [min(point, len(briefs)) for point in checkpoints if min(point, len(briefs)) > 0]
        strong_windows = 0
        reasons: list[str] = []
        for point in sorted(set(available)):
            window = briefs[max(0, point - 3) : point]
            strong = sum(1 for item in window if item.ending_pull and (_hits(item.ending_pull, HIGH_PRESSURE_TOKENS + RELATION_TOKENS) >= 1 or "？" in item.ending_pull or "?" in item.ending_pull))
            if strong >= min(2, len(window)):
                strong_windows += 1
            reasons.append(f"ch{point}:strong_endings={strong}/{len(window)}")
        score = 4.0 + strong_windows / max(len(set(available)), 1) * 5.0
        return _metric(score, "; ".join(reasons))

    def _information_budget_control(self, briefs: list[ChapterBrief]) -> LongArcMetric:
        if not briefs:
            return _metric(0.0, "no chapter briefs")
        overloaded = 0
        controlled = 0
        for item in briefs:
            text = _text(item.info_budget)
            budget_text = re.sub(r"target\s*=\s*\d+\s*[-~—]\s*\d+", "", text, flags=re.IGNORECASE)
            budget_text = re.sub(r"\d+\s*[-~—]\s*\d+\s*(?:字|chars|characters|words)?", "", budget_text, flags=re.IGNORECASE)
            numbers = [int(value) for value in re.findall(r"\d+", budget_text)]
            total = sum(numbers) if numbers else 0
            if len(item.allowed_info) <= 4 and len(item.allowed_clues) <= 3 and total <= 7:
                controlled += 1
            if len(item.allowed_info) > 4 or len(item.allowed_clues) > 3 or total > 9:
                overloaded += 1
        score = 4.0 + controlled / len(briefs) * 5.0 - min(2.0, overloaded * 0.35)
        return _metric(score, f"controlled={controlled}/{len(briefs)}, overloaded={overloaded}")

    def _repetition_plateau(self, briefs: list[ChapterBrief]) -> LongArcMetric:
        if not briefs:
            return _metric(0.0, "no chapter briefs")
        repeated_pairs = 0
        repeated_scene_engine = 0
        for prev, current in zip(briefs, briefs[1:]):
            prev_tokens = _tokenize_chineseish(_text([prev.core_scene, prev.chapter_object, prev.ending_pull]))
            current_tokens = _tokenize_chineseish(_text([current.core_scene, current.chapter_object, current.ending_pull]))
            overlap_ratio = len(prev_tokens & current_tokens) / max(len(current_tokens), 1)
            if overlap_ratio > 0.45:
                repeated_pairs += 1
            if prev.scene_engine == current.scene_engine:
                repeated_scene_engine += 1
        denominator = max(len(briefs) - 1, 1)
        score = 9.0 - repeated_pairs / denominator * 4.0 - repeated_scene_engine / denominator * 2.0
        return _metric(score, f"repeated_pairs={repeated_pairs}/{denominator}, repeated_scene_engine={repeated_scene_engine}/{denominator}")


class LongArcStep8EvalRunner:
    def __init__(self, *, reports_root: str | Path = "evals/romance/reports") -> None:
        self.reports_root = Path(reports_root)
        self.reports_root.mkdir(parents=True, exist_ok=True)
        self.evaluator = LongArcStep8Evaluator()

    def run(
        self,
        *,
        cases_dir: str | Path = "evals/romance/cases",
        label: str = "",
        case_ids: list[str] | None = None,
        generate: bool = False,
        target_chapters: int = 30,
        batch_size: int = 2,
        llm_provider: str | None = None,
    ) -> LongArcEvalSummary:
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

        run_label = self._sanitize_label(label or ("long_arc_step8_generated" if generate else "long_arc_step8_static"))
        run_dir = self.reports_root / run_label
        run_dir.mkdir(parents=True, exist_ok=True)
        reports = [
            self._evaluate_path(
                path,
                run_dir=run_dir,
                generate=generate,
                target_chapters=target_chapters,
                batch_size=batch_size,
                llm_provider=llm_provider,
            )
            for path in paths
        ]
        verdict_counter = Counter(report.verdict for report in reports)
        summary = LongArcEvalSummary(
            label=run_label,
            source_case_dir=str(Path(cases_dir)),
            generated=generate,
            target_chapters=target_chapters if generate else 0,
            batch_size=batch_size if generate else 0,
            case_ids=[item.case_id for item in reports],
            verdict_counts={key: verdict_counter.get(key, 0) for key in ("pass", "warn", "blocked")},
            average_score=_safe_mean([item.average_score for item in reports]),
            case_reports=reports,
        )
        json_path = run_dir / "long_arc_step8_summary.json"
        md_path = run_dir / "report.md"
        summary = summary.model_copy(update={"report_json": str(json_path), "report_markdown": str(md_path)})
        json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        md_path.write_text(render_long_arc_markdown(summary), encoding="utf-8")
        return summary

    def _evaluate_path(
        self,
        path: Path,
        *,
        run_dir: Path,
        generate: bool,
        target_chapters: int,
        batch_size: int,
        llm_provider: str | None,
    ) -> LongArcCaseReport:
        payload = load_step_fixture(path)
        case_id = str(payload.get("case_id") or path.parent.name)
        generated_path = ""
        if generate:
            payload = self._generate_step8(payload, target_chapters=target_chapters, batch_size=batch_size, llm_provider=llm_provider)
            case_dir = run_dir / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            generated_path = str(case_dir / "generated_steps.json")
            Path(generated_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.evaluator.evaluate_case(
            case_id=case_id,
            source=str(path),
            payload=payload,
            generated_step8_path=generated_path,
        )

    def _generate_step8(
        self,
        payload: dict[str, Any],
        *,
        target_chapters: int,
        batch_size: int,
        llm_provider: str | None,
    ) -> dict[str, Any]:
        settings = Settings.from_env()
        if llm_provider:
            settings = settings.model_copy(update={"llm_provider": llm_provider})
        agent = BlueprintAgent(build_llm_client(settings))
        previous: list[dict[str, Any]] = []
        target = max(int(target_chapters or 1), 1)
        size = max(int(batch_size or 1), 1)
        for start in range(0, target, size):
            end = min(start + size, target)
            batch = {
                "start_index": start,
                "end_index": end - 1,
                "batch_size": end - start,
                "total_chapters": target,
                "chapter_ids": [f"ch_{index + 1:03d}" for index in range(start, end)],
            }
            result = agent.build_chapter_briefs_step(
                research_query=_text(payload.get("user_input") or payload.get("step_1")),
                volume_titles=_volume_titles(payload),
                batch=batch,
                story_spine=_story_spine(payload),
                worldbuilding=_worldbuilding(payload),
                character_bible={"characters": list((payload.get("step_3") or {}).get("characters") or [])},
                event_timeline=list((payload.get("step_4") or {}).get("event_timeline") or []),
                character_milestones=list((payload.get("step_5") or {}).get("milestone_grid") or (payload.get("step_5") or {}).get("character_milestones") or []),
                twist_designs=list((payload.get("step_6") or {}).get("twist_designs") or []),
                story_lines=list((payload.get("step_7") or {}).get("story_lines") or []),
                previous_chapter_briefs=previous,
                target_chapter_count=target,
                reference_pack="长线 step8 连续生成评测：请优先保证章节链、升级曲线、角色发展和反转埋线。",
            )
            previous.extend([item for item in result.get("chapter_briefs") or [] if isinstance(item, dict)])
        updated = dict(payload)
        updated["step_8"] = {"chapter_briefs": previous}
        return updated

    @staticmethod
    def _sanitize_label(label: str) -> str:
        keep = [ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(label or "").strip()]
        return "".join(keep).strip("_") or datetime.now().strftime("%Y%m%d_%H%M%S")


def _volume_titles(payload: dict[str, Any]) -> list[str]:
    for key in ("volume_titles", "volume_titles_json"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return [str(item) for item in value]
    return ["第一卷"]


def _story_spine(payload: dict[str, Any]) -> dict[str, Any]:
    step1 = payload.get("step_1") or {}
    return {
        "premise": step1.get("premise") or {},
        "story_engine": step1.get("story_engine") or {},
        "planning_objective": step1.get("planning_objective") or {},
    }


def _worldbuilding(payload: dict[str, Any]) -> dict[str, Any]:
    step2 = payload.get("step_2") or {}
    if step2:
        return step2
    return {"story_engine": (payload.get("step_1") or {}).get("story_engine") or {}}


def render_long_arc_markdown(summary: LongArcEvalSummary) -> str:
    lines = [
        f"# Long Arc Step8 Eval: {summary.label}",
        "",
        f"- source_case_dir: `{summary.source_case_dir}`",
        f"- cases: `{len(summary.case_reports)}`",
        f"- generated: `{summary.generated}`",
        f"- target_chapters: `{summary.target_chapters}`",
        f"- batch_size: `{summary.batch_size}`",
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
                f"- generated_step8_path: `{report.generated_step8_path or 'None'}`",
                f"- chapter_count: `{report.chapter_count}`",
                f"- verdict: `{report.verdict}`",
                f"- average_score: `{report.average_score:.2f}`",
                f"- warning_metrics: {', '.join(report.warning_metrics) or 'None'}",
                f"- blocking_metrics: {', '.join(report.blocking_metrics) or 'None'}",
                "",
                "| metric | score | reason |",
                "| --- | ---: | --- |",
            ]
        )
        for name, metric in report.metrics.items():
            lines.append(f"| {name} | {metric.score:.2f} | {metric.reason.replace('|', '/')} |")
    return "\n".join(lines).strip() + "\n"
