from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any

from novel_flow.agents.writing_chapter_agent import WritingChapterAgent
from novel_flow.config import Settings
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import ChapterExecutionResult
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.novel_context import NovelContextFormatter, NovelContextSelectorService
from novel_flow.services.tool_registry import ToolRegistry

from evals.romance.instrumentation import InstrumentedLLMClient, InstrumentedToolRegistry
from evals.romance.judges import (
    ActionCarriedRevealRuleAnalyzer,
    AntiSlopRuleAnalyzer,
    ExplanationDensityRuleAnalyzer,
    PronounLeadRuleAnalyzer,
    RedundancyRuleAnalyzer,
    RelationshipCostRealizationRuleAnalyzer,
    RomanceChapterJudge,
)
from evals.romance.loader import load_cases
from evals.romance.models import (
    RomanceCaseArtifacts,
    RomanceCaseDiff,
    RomanceCaseResult,
    RomanceCostMetrics,
    RomanceEvalCase,
    RomanceHardFailFlag,
    RomanceJudgeDiagnosis,
    RomanceMetricDetail,
    RomanceOptimizationTarget,
    RomanceRunDiff,
    RomanceRunSummary,
    ScoreDelta,
)
from evals.romance.report_paths import build_structured_run_dir, normalize_reports_root, write_text_with_aliases
from evals.romance.reporting import CORE_METRICS, write_diff_files, write_summary_files


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


PROMPT_MODULES = {
    "brief": "prompts/writer/step_8_chapter_briefs.txt",
    "mindset": "prompts/writer/build_character_mindset.txt",
    "planning": "prompts/writer/plan_content_blocks.txt",
    "writer": "prompts/writer/write_chapter_full.txt",
}

ISSUE_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "relationship_progression_score": {
        "label": "关系推进",
        "issue_type": "relationship_progression",
        "flag_type": "relationship_progression_break",
        "blocker_threshold": 4.5,
        "high_threshold": 6.4,
        "medium_threshold": 7.1,
        "blocker_severity": "blocker",
        "diagnosis_tokens": ("关系", "推进", "原地", "拉扯"),
        "target_modules": [PROMPT_MODULES["brief"], PROMPT_MODULES["writer"]],
        "patch_hint": "让 step 8 明确本章关系要发生什么变化，再要求正文用可见动作或选择把变化兑现出来。",
        "expected_metric_gains": [
            "relationship_progression_score",
            "romance_tension_score",
            "hook_score",
        ],
    },
    "continuity_score": {
        "label": "连贯性",
        "issue_type": "continuity",
        "flag_type": "continuity_break",
        "blocker_threshold": 4.5,
        "high_threshold": 6.5,
        "medium_threshold": 7.2,
        "blocker_severity": "blocker",
        "diagnosis_tokens": ("承接", "连贯", "突兀", "断裂", "前后"),
        "target_modules": [PROMPT_MODULES["planning"], PROMPT_MODULES["writer"]],
        "patch_hint": "优先修补前情承接、因果顺序和场景转折，不要用更华丽的 prose 掩盖断裂。",
        "expected_metric_gains": [
            "continuity_score",
            "mind_state_consistency_score",
            "relationship_progression_score",
        ],
    },
    "mind_state_consistency_score": {
        "label": "角色心智一致性",
        "issue_type": "mind_state_consistency",
        "flag_type": "mind_state_break",
        "blocker_threshold": 4.5,
        "high_threshold": 6.5,
        "medium_threshold": 7.2,
        "blocker_severity": "blocker",
        "diagnosis_tokens": ("心智", "人设", "失控", "克制", "突然"),
        "target_modules": [PROMPT_MODULES["mindset"], PROMPT_MODULES["writer"]],
        "patch_hint": "把 fear、hidden_need、misbelief 和 self_control_level 变成正文硬约束，禁止角色越级表态或突然失控。",
        "expected_metric_gains": [
            "mind_state_consistency_score",
            "continuity_score",
            "emotional_resonance_score",
        ],
    },
    "hook_score": {
        "label": "章节钩子",
        "issue_type": "hook",
        "flag_type": "hook_underpowered",
        "blocker_threshold": 3.8,
        "high_threshold": 6.2,
        "medium_threshold": 7.0,
        "blocker_severity": "high",
        "diagnosis_tokens": ("钩子", "开头", "结尾", "尾钩", "追读"),
        "target_modules": [PROMPT_MODULES["brief"], PROMPT_MODULES["planning"]],
        "patch_hint": "把开头异样感和结尾下一章驱动力提前写进 brief 与 block 责任，而不是等正文临场发挥。",
        "expected_metric_gains": [
            "hook_score",
            "relationship_progression_score",
            "romance_tension_score",
        ],
    },
    "redundancy_score": {
        "label": "重复铺陈",
        "issue_type": "redundancy",
        "flag_type": "redundancy_drag",
        "blocker_threshold": 3.8,
        "high_threshold": 6.0,
        "medium_threshold": 7.0,
        "blocker_severity": "high",
        "diagnosis_tokens": ("重复", "铺陈", "解释", "同一层"),
        "target_modules": [PROMPT_MODULES["planning"], PROMPT_MODULES["writer"]],
        "patch_hint": "减少同一情绪或判断的解释型复述，让每个 block 都新增信息、代价或关系变化。",
        "expected_metric_gains": [
            "redundancy_score",
            "emotional_resonance_score",
            "hook_score",
        ],
    },
}

ROMANCE_PULL_BLUEPRINT = {
    "label": "追读拉力",
    "issue_type": "romance_pull",
    "flag_type": "romance_pull_weak",
    "diagnosis_tokens": ("拉扯", "情绪", "电流", "共振", "追读"),
    "target_modules": [PROMPT_MODULES["planning"], PROMPT_MODULES["writer"]],
    "patch_hint": "增强 block 内的情绪代价、身体泄露和关系压差，不要只写解释性的心理总结。",
    "expected_metric_gains": [
        "romance_tension_score",
        "emotional_resonance_score",
        "character_attraction_score",
    ],
}

ROMANCE_MODE_MISS_BLUEPRINT = {
    "label": "言情模式错型",
    "issue_type": "romance_mode_miss",
    "flag_type": "romance_mode_miss",
    "target_modules": [
        PROMPT_MODULES["brief"],
        PROMPT_MODULES["planning"],
        PROMPT_MODULES["writer"],
    ],
    "patch_hint": (
        "先把 step 8 里的双人关系目标写实：谁在意谁、谁回避谁、"
        "哪一步关系变化必须落页。权谋、亲属、旧案压力只能做外层压力，不能替代 romance 主轴。"
    ),
    "expected_metric_gains": [
        "romance_tension_score",
        "relationship_progression_score",
        "character_attraction_score",
        "hook_score",
    ],
}

SUMMARY_PROSE_BLUEPRINT = {
    "label": "摘要式空文",
    "issue_type": "summary_prose_fail",
    "flag_type": "summary_prose_fail",
    "target_modules": [PROMPT_MODULES["planning"], PROMPT_MODULES["writer"]],
    "patch_hint": (
        "把标签和结论改写成可见场面：用动作、停顿、称呼变化、选择代价和"
        "现场反馈来兑现关系变化，不要只用“他很冷、她也很冷”式总结句代替正文。"
    ),
    "expected_metric_gains": [
        "romance_tension_score",
        "relationship_progression_score",
        "emotional_resonance_score",
        "hook_score",
        "redundancy_score",
    ],
}

SEVERITY_RANK = {"blocker": 3, "high": 2, "medium": 1}


class RomanceEvalHarness:
    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        settings: Settings | None = None,
        mode: str = "fast",
        case_dir: str | Path | None = None,
        reports_root: str | Path | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        base_llm = llm_client or build_llm_client(self.settings)
        self.llm_client = InstrumentedLLMClient(base_llm)
        self.mode = str(mode or "fast").strip().lower()
        self.case_dir = Path(case_dir or Path(__file__).resolve().parent / "cases")
        self.reports_root, self.runs_root = normalize_reports_root(reports_root)

    def run(
        self,
        *,
        label: str = "",
        case_ids: list[str] | None = None,
        compare_to: str | Path | None = None,
    ) -> tuple[RomanceRunSummary, RomanceRunDiff | None]:
        cases = load_cases(self.case_dir, case_ids=case_ids)
        run_label = _sanitize_label(label or f"{self.mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        provider_name = self.settings.llm_provider
        model_name = self._effective_model_name()
        run_paths = build_structured_run_dir(
            self.reports_root,
            task_slug="chapter_eval",
            label=run_label,
            case_ids=[case.case_id for case in cases],
            provider=provider_name,
            model=model_name,
        )
        run_dir = run_paths.run_dir

        results: list[RomanceCaseResult] = []
        run_errors: list[str] = []
        for case in cases:
            try:
                results.append(self._run_case(case=case, run_dir=run_dir))
            except Exception as exc:  # pragma: no cover - defensive outer guard
                run_errors.append(f"{case.case_id}: {exc}")

        verdict_counts, blocked_case_ids, optimization_target_counts = self._summarize_results(results)

        summary = RomanceRunSummary(
            label=run_label,
            mode=self.mode,
            provider=provider_name,
            model=model_name,
            run_dir=str(run_dir),
            case_ids=[case.case_id for case in cases],
            average_scores=self._average_scores(results),
            verdict_counts=verdict_counts,
            blocked_case_ids=blocked_case_ids,
            optimization_target_counts=optimization_target_counts,
            case_results=results,
            errors=run_errors,
        )
        json_path, md_path = write_summary_files(summary, run_dir)
        summary = summary.model_copy(
            update={
                "report_json": str(json_path),
                "report_markdown": str(md_path),
            }
        )
        write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("summary.json",))

        diff: RomanceRunDiff | None = None
        if compare_to:
            diff = compare_run_summaries(compare_to, summary)
            write_diff_files(diff, run_dir, baseline_label=diff.baseline_label)
            summary = summary.model_copy(update={"compared_to": str(compare_to)})
            write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("summary.json",))
        return summary, diff

    def assemble_existing_run(
        self,
        *,
        run_dir: str | Path,
        label: str = "",
        compare_to: str | Path | None = None,
    ) -> tuple[RomanceRunSummary, RomanceRunDiff | None]:
        run_path = Path(run_dir)
        if not run_path.exists():
            raise FileNotFoundError(f"Run directory does not exist: {run_path}")

        results: list[RomanceCaseResult] = []
        result_paths = sorted(run_path.glob("*/chapter_eval_case_result.json")) or sorted(run_path.glob("*/result.json"))
        for result_path in result_paths:
            results.append(RomanceCaseResult.model_validate_json(result_path.read_text(encoding="utf-8")))
        verdict_counts, blocked_case_ids, optimization_target_counts = self._summarize_results(results)
        summary = RomanceRunSummary(
            label=_sanitize_label(label or run_path.name),
            mode=self.mode,
            provider=self.settings.llm_provider,
            model=self._effective_model_name(),
            run_dir=str(run_path),
            case_ids=[result.case_id for result in results],
            average_scores=self._average_scores(results),
            verdict_counts=verdict_counts,
            blocked_case_ids=blocked_case_ids,
            optimization_target_counts=optimization_target_counts,
            case_results=results,
        )
        json_path, md_path = write_summary_files(summary, run_path)
        summary = summary.model_copy(
            update={
                "report_json": str(json_path),
                "report_markdown": str(md_path),
            }
        )
        write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("summary.json",))

        diff: RomanceRunDiff | None = None
        if compare_to:
            diff = compare_run_summaries(compare_to, summary)
            write_diff_files(diff, run_path, baseline_label=diff.baseline_label)
            summary = summary.model_copy(update={"compared_to": str(compare_to)})
            write_text_with_aliases(json_path, summary.model_dump_json(indent=2), alias_names=("summary.json",))
        return summary, diff

    def _run_case(self, *, case: RomanceEvalCase, run_dir: Path) -> RomanceCaseResult:
        case_dir = run_dir / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        case_input_path = case_dir / "chapter_eval_case_input.json"
        write_text_with_aliases(case_input_path, case.model_dump_json(indent=2), alias_names=("case_input.json",))

        generation_start = len(self.llm_client.records)
        started_at = time.perf_counter()
        self.llm_client.set_phase(f"generation:{case.case_id}")

        writer_context = self._build_writer_context(case)
        writer_context_json = _json_text(_writer_context_to_dict(writer_context))
        writer_context_path = case_dir / "chapter_eval_writer_context.json"
        write_text_with_aliases(writer_context_path, writer_context_json, alias_names=("writer_context.json",))

        registry = InstrumentedToolRegistry(
            ToolRegistry.build_default(
                llm_client=self.llm_client,
                prompt_library=PromptLibrary(),
            )
        )
        agent = WritingChapterAgent(
            llm_client=self.llm_client,
            prompt_library=PromptLibrary(),
            tool_registry=registry,
            mode=self.mode,
        )
        execution = agent.write_chapter(
            chapter_brief=case.chapter_brief,
            premise=case.premise,
            twist_designs=case.twist_designs,
            story_lines=case.story_lines,
            character_cards=case.character_cards,
            worldbuilding=case.worldbuilding,
            actual_chapter_summaries=case.actual_chapter_summaries,
            character_milestones=case.character_milestones,
            prior_character_mindsets=case.prior_character_mindsets,
            prebuilt_context=writer_context,
        )
        duration_seconds = time.perf_counter() - started_at
        generation_calls = len(self.llm_client.records) - generation_start

        execution_json = execution.model_dump_json(indent=2)
        execution_path = case_dir / "chapter_eval_execution.json"
        write_text_with_aliases(execution_path, execution_json, alias_names=("chapter_execution.json",))
        stage_log_path = case_dir / "chapter_eval_stage_log.json"
        write_text_with_aliases(stage_log_path, _json_text(execution.stage_log), alias_names=("stage_log.json",))
        final_text_path = case_dir / "chapter_text__final.txt"
        write_text_with_aliases(final_text_path, execution.chapter_text, alias_names=("final_text.txt",))

        judge_payload_path = case_dir / "chapter_eval_judge.json"
        judge_errors: list[str] = []
        judge_detail: dict[str, RomanceMetricDetail] = {}
        breakdowns: dict[str, RomanceMetricDetail] = {}
        diagnosis = RomanceJudgeDiagnosis()

        rule_redundancy = RedundancyRuleAnalyzer().analyze(
            chapter_text=execution.chapter_text,
            stage_log=execution.stage_log,
            review_reports=execution.review_reports,
        )
        rule_anti_slop = AntiSlopRuleAnalyzer().analyze(
            chapter_text=execution.chapter_text,
            review_reports=execution.review_reports,
        )
        rule_pronoun_lead = PronounLeadRuleAnalyzer().analyze(chapter_text=execution.chapter_text)
        rule_explanation_density = ExplanationDensityRuleAnalyzer().analyze(chapter_text=execution.chapter_text)
        rule_action_carried_reveal = ActionCarriedRevealRuleAnalyzer().analyze(chapter_text=execution.chapter_text)
        rule_relationship_cost = RelationshipCostRealizationRuleAnalyzer().analyze(chapter_text=execution.chapter_text)

        judge_start = len(self.llm_client.records)
        self.llm_client.set_phase(f"judge:{case.case_id}")
        try:
            judge = RomanceChapterJudge(self.llm_client).judge(
                case=case,
                writer_context_json=writer_context_json,
                chapter_execution_json=execution_json,
                chapter_text=execution.chapter_text,
            )
            write_text_with_aliases(judge_payload_path, judge.model_dump_json(indent=2), alias_names=("judge.json",))
            diagnosis = judge.diagnosis
            judge_detail = self._judge_metrics_to_core(
                judge=judge,
                rule_redundancy=rule_redundancy,
                rule_anti_slop=rule_anti_slop,
            )
            breakdowns = {
                "male_lead_attraction": judge.male_lead_attraction,
                "female_lead_attraction": judge.female_lead_attraction,
                "lead_pair_chemistry": judge.lead_pair_chemistry,
                "opening_hook_score": judge.opening_hook,
                "ending_hook_score": judge.ending_hook,
                "judge_genre_fit_score": judge.genre_fit,
                "judge_redundancy_score": judge.redundancy,
                "rule_redundancy_score": rule_redundancy,
                "rule_anti_slop_score": rule_anti_slop,
                "rule_pronoun_lead_score": rule_pronoun_lead,
                "rule_explanation_density_score": rule_explanation_density,
                "rule_action_carried_reveal_score": rule_action_carried_reveal,
                "rule_relationship_cost_realization_score": rule_relationship_cost,
            }
            if rule_redundancy.score < 7.0 and not any("重复" in item for item in diagnosis.weaknesses):
                diagnosis.weaknesses.append("中段存在重复铺陈信号")
                diagnosis.improvement_hints.append(rule_redundancy.improvement_hint)
            if rule_anti_slop.score < 7.0 and not any(token in item for item in diagnosis.weaknesses for token in ("直白", "心理", "解释")):
                diagnosis.weaknesses.append("存在直白心理解释信号")
                diagnosis.improvement_hints.append(rule_anti_slop.improvement_hint)
            if rule_pronoun_lead.score < 7.0 and not any("代词" in item for item in diagnosis.weaknesses):
                diagnosis.weaknesses.append("句首代词密度偏高，场面起句不足")
                diagnosis.improvement_hints.append(rule_pronoun_lead.improvement_hint)
            if rule_explanation_density.score < 7.0 and not any("解释句" in item for item in diagnosis.weaknesses):
                diagnosis.weaknesses.append("解释句密度偏高，动作后常被作者翻译")
                diagnosis.improvement_hints.append(rule_explanation_density.improvement_hint)
            if rule_action_carried_reveal.score < 7.0 and not any("动作" in item or "场面" in item for item in diagnosis.weaknesses):
                diagnosis.weaknesses.append("关键信息更多靠说明而非动作/场面露出")
                diagnosis.improvement_hints.append(rule_action_carried_reveal.improvement_hint)
            if rule_relationship_cost.score < 7.0 and not any("代价" in item for item in diagnosis.weaknesses):
                diagnosis.weaknesses.append("线索推进没有稳定兑现成关系或人身代价")
                diagnosis.improvement_hints.append(rule_relationship_cost.improvement_hint)
        except Exception as exc:
            judge_errors.append(f"romance_judge_failed: {exc}")
            write_text_with_aliases(
                judge_payload_path,
                _json_text(
                    {
                        "error": str(exc),
                        "rule_redundancy": rule_redundancy.model_dump(mode="json"),
                        "rule_anti_slop": rule_anti_slop.model_dump(mode="json"),
                        "rule_pronoun_lead": rule_pronoun_lead.model_dump(mode="json"),
                        "rule_explanation_density": rule_explanation_density.model_dump(mode="json"),
                        "rule_action_carried_reveal": rule_action_carried_reveal.model_dump(mode="json"),
                        "rule_relationship_cost_realization": rule_relationship_cost.model_dump(mode="json"),
                    }
                ),
                alias_names=("judge.json",),
            )
            judge_detail = self._fallback_core_metrics(
                rule_redundancy=rule_redundancy,
                rule_anti_slop=rule_anti_slop,
            )
            breakdowns = {
                "rule_redundancy_score": rule_redundancy,
                "rule_anti_slop_score": rule_anti_slop,
                "rule_pronoun_lead_score": rule_pronoun_lead,
                "rule_explanation_density_score": rule_explanation_density,
                "rule_action_carried_reveal_score": rule_action_carried_reveal,
                "rule_relationship_cost_realization_score": rule_relationship_cost,
            }
            diagnosis = RomanceJudgeDiagnosis(
                strengths=[],
                weaknesses=["LLM judge 未返回可用结果，本次使用降级分数。"],
                improvement_hints=["先修复 judge 输出，再重新跑评测以获取可靠趋势。"],
            )
        judge_calls = len(self.llm_client.records) - judge_start

        cost_metrics = self._build_cost_metrics(
            case_id=case.case_id,
            execution=execution,
            duration_seconds=duration_seconds,
            generation_calls=generation_calls,
            judge_calls=judge_calls,
            registry=registry,
        )
        verdict, hard_fail_flags, optimization_targets = self._derive_actionability(
            metrics=judge_detail,
            breakdowns=breakdowns,
            diagnosis=diagnosis,
            judge_errors=judge_errors,
        )
        result = RomanceCaseResult(
            case_id=case.case_id,
            title=case.title,
            description=case.description,
            tags=case.tags,
            verdict=verdict,
            scores={key: round(detail.score, 2) for key, detail in judge_detail.items()},
            metrics=judge_detail,
            breakdowns=breakdowns,
            diagnosis=diagnosis,
            hard_fail_flags=hard_fail_flags,
            optimization_targets=optimization_targets,
            cost_metrics=cost_metrics,
            artifacts=RomanceCaseArtifacts(
                case_dir=str(case_dir),
                case_input_json=str(case_input_path),
                writer_context_json=str(writer_context_path),
                chapter_execution_json=str(execution_path),
                stage_log_json=str(stage_log_path),
                final_text_txt=str(final_text_path),
                judge_json=str(judge_payload_path),
                result_json=str(case_dir / "result.json"),
            ),
            errors=judge_errors,
        )
        result_path = case_dir / "chapter_eval_case_result.json"
        write_text_with_aliases(result_path, result.model_dump_json(indent=2), alias_names=("result.json",))
        return result

    def _build_writer_context(self, case: RomanceEvalCase) -> Any:
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
        prompt_library = PromptLibrary()
        context = NovelContextFormatter.format_writer_context(
            selection,
            context_sanitizer=ContextSanitizationTask(
                llm_client=self.llm_client,
                prompt_library=prompt_library,
            ),
        )
        overrides = case.context_overrides
        writing_requirements_json = (
            _json_text(overrides.writing_requirements)
            if overrides.writing_requirements
            else "{}"
        )
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

    def _build_cost_metrics(
        self,
        *,
        case_id: str,
        execution: ChapterExecutionResult,
        duration_seconds: float,
        generation_calls: int,
        judge_calls: int,
        registry: InstrumentedToolRegistry,
    ) -> RomanceCostMetrics:
        tool_counts = registry.counts()
        patch_targets: set[str] = set()
        for entry in execution.stage_log:
            patch_plan = entry.get("patch_plan") if isinstance(entry, dict) else None
            for item in list((patch_plan or {}).get("patch_targets") or []):
                target_id = str(item.get("target_id") or "").strip()
                if target_id:
                    patch_targets.add(target_id)
        block_count = len(execution.content_blocks)
        patched_block_count = len(patch_targets)
        review_calls = sum(
            count
            for tool_name, count in tool_counts.items()
            if tool_name.startswith("review_") or tool_name == "judge_patched_chapter"
        )
        return RomanceCostMetrics(
            llm_calls=generation_calls,
            judge_llm_calls=judge_calls,
            review_calls=review_calls,
            patch_rounds=tool_counts.get("rewrite_blocks_by_plan", 0),
            used_full_rewrite=tool_counts.get("rewrite_by_plan", 0) > 0,
            duration_seconds=round(duration_seconds, 2),
            block_count=block_count,
            patched_block_count=patched_block_count,
            patched_block_ratio=round(patched_block_count / block_count, 2) if block_count else 0.0,
            generation_prompt_chars=self.llm_client.prompt_chars(f"generation:{case_id}"),
            judge_prompt_chars=self.llm_client.prompt_chars(f"judge:{case_id}"),
            tool_calls_by_name=tool_counts,
        )

    @staticmethod
    def _summarize_results(
        results: list[RomanceCaseResult],
    ) -> tuple[dict[str, int], list[str], dict[str, int]]:
        verdict_counts: Counter[str] = Counter()
        blocked_case_ids: list[str] = []
        optimization_target_counts: Counter[str] = Counter()
        for result in results:
            verdict_counts[result.verdict] += 1
            if result.verdict == "blocked":
                blocked_case_ids.append(result.case_id)
            for target in result.optimization_targets:
                optimization_target_counts[target.target_module] += 1
        ordered_target_counts = dict(
            sorted(
                optimization_target_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        return dict(verdict_counts), sorted(blocked_case_ids), ordered_target_counts

    @staticmethod
    def _severity_for_score(
        score: float,
        *,
        blocker_threshold: float,
        high_threshold: float,
        medium_threshold: float,
        blocker_severity: str,
    ) -> str | None:
        if score <= blocker_threshold:
            return blocker_severity
        if score <= high_threshold:
            return "high"
        if score <= medium_threshold:
            return "medium"
        return None

    @staticmethod
    def _diagnosis_blob(diagnosis: RomanceJudgeDiagnosis) -> str:
        return " ".join(
            [
                *diagnosis.strengths,
                *diagnosis.weaknesses,
                *diagnosis.improvement_hints,
            ]
        ).lower()

    @staticmethod
    def _issue_evidence(
        detail: RomanceMetricDetail,
        *,
        diagnosis: RomanceJudgeDiagnosis,
        diagnosis_tokens: tuple[str, ...],
    ) -> str:
        parts: list[str] = []
        primary = str(detail.evidence_summary or "").strip()
        if primary:
            parts.append(primary)
        for item in [*diagnosis.weaknesses, *diagnosis.improvement_hints]:
            text = str(item or "").strip()
            if text and any(token in text for token in diagnosis_tokens):
                parts.append(text)
        deduped: list[str] = []
        for part in parts:
            if part not in deduped:
                deduped.append(part)
        return "；".join(deduped[:2]) or "未捕捉到额外证据。"

    @staticmethod
    def _issue_confidence(
        *,
        score: float,
        severity: str,
        threshold: float,
        diagnosis_hit: bool,
        detail: RomanceMetricDetail,
    ) -> float:
        confidence = 0.58 + min(max(threshold - score, 0.0) * 0.08, 0.22)
        confidence += 0.12 if severity == "blocker" else 0.06 if severity == "high" else 0.0
        confidence += 0.08 if diagnosis_hit else 0.0
        confidence += 0.04 if detail.source in {"llm", "hybrid"} else 0.0
        return round(min(confidence, 0.95), 2)

    @staticmethod
    def _target_sort_key(target: RomanceOptimizationTarget) -> tuple[int, float, str, str]:
        return (
            -SEVERITY_RANK.get(target.severity, 0),
            -target.confidence,
            target.issue_type,
            target.target_module,
        )

    @staticmethod
    def _best_available_detail(
        metrics: dict[str, RomanceMetricDetail],
        primary_key: str,
        fallback_keys: tuple[str, ...] = (),
    ) -> RomanceMetricDetail | None:
        detail = metrics.get(primary_key)
        if detail is not None:
            return detail
        for key in fallback_keys:
            detail = metrics.get(key)
            if detail is not None:
                return detail
        return None

    @staticmethod
    def _upsert_target(
        target_map: dict[tuple[str, str], RomanceOptimizationTarget],
        target: RomanceOptimizationTarget,
    ) -> None:
        key = (target.target_module, target.issue_type)
        existing = target_map.get(key)
        if existing is None or RomanceEvalHarness._target_sort_key(target) < RomanceEvalHarness._target_sort_key(existing):
            target_map[key] = target

    @classmethod
    def _derive_actionability(
        cls,
        *,
        metrics: dict[str, RomanceMetricDetail],
        breakdowns: dict[str, RomanceMetricDetail],
        diagnosis: RomanceJudgeDiagnosis,
        judge_errors: list[str],
    ) -> tuple[str, list[RomanceHardFailFlag], list[RomanceOptimizationTarget]]:
        diagnosis_blob = cls._diagnosis_blob(diagnosis)
        hard_fail_flags: list[RomanceHardFailFlag] = []
        target_map: dict[tuple[str, str], RomanceOptimizationTarget] = {}

        for metric_name, blueprint in ISSUE_BLUEPRINTS.items():
            detail = metrics.get(metric_name)
            if detail is None:
                continue
            severity = cls._severity_for_score(
                detail.score,
                blocker_threshold=blueprint["blocker_threshold"],
                high_threshold=blueprint["high_threshold"],
                medium_threshold=blueprint["medium_threshold"],
                blocker_severity=blueprint["blocker_severity"],
            )
            if severity is None:
                continue
            diagnosis_hit = any(token in diagnosis_blob for token in blueprint["diagnosis_tokens"])
            evidence_summary = cls._issue_evidence(
                detail,
                diagnosis=diagnosis,
                diagnosis_tokens=blueprint["diagnosis_tokens"],
            )
            confidence = cls._issue_confidence(
                score=detail.score,
                severity=severity,
                threshold=blueprint["blocker_threshold"] if severity == "blocker" else blueprint["high_threshold"],
                diagnosis_hit=diagnosis_hit,
                detail=detail,
            )
            if severity in {"blocker", "high"}:
                hard_fail_flags.append(
                    RomanceHardFailFlag(
                        flag_type=blueprint["flag_type"],
                        severity=severity,
                        reason=(
                            f"{blueprint['label']}仅 {detail.score:.1f} 分，"
                            f"已经低于 {'阻断' if severity == 'blocker' else '高风险'}阈值。{detail.reason}"
                        ),
                        evidence_summary=evidence_summary,
                        related_metrics=[metric_name],
                        suggested_modules=list(blueprint["target_modules"]),
                        source="fallback" if detail.source == "fallback" else "heuristic",
                    )
                )
            for target_module in blueprint["target_modules"]:
                target = RomanceOptimizationTarget(
                    target_module=target_module,
                    issue_type=blueprint["issue_type"],
                    severity=severity,
                    confidence=confidence,
                    reason=f"{blueprint['label']}当前 {detail.score:.1f} 分。{detail.reason}",
                    evidence_summary=evidence_summary,
                    patch_hint=blueprint["patch_hint"],
                    related_metrics=[metric_name],
                    expected_metric_gains=list(blueprint["expected_metric_gains"]),
                )
                cls._upsert_target(target_map, target)

        tension_detail = metrics.get("romance_tension_score")
        progression_detail = metrics.get("relationship_progression_score")
        emotional_detail = metrics.get("emotional_resonance_score")
        hook_detail = metrics.get("hook_score")
        redundancy_detail = metrics.get("redundancy_score")
        chemistry_detail = cls._best_available_detail(breakdowns, "lead_pair_chemistry")

        if (
            tension_detail is not None
            and progression_detail is not None
            and emotional_detail is not None
            and chemistry_detail is not None
            and tension_detail.score <= 2.5
            and progression_detail.score <= 2.5
            and emotional_detail.score <= 3.2
            and chemistry_detail.score <= 2.5
        ):
            evidence_summary = "；".join(
                [
                    f"拉扯感：{tension_detail.evidence_summary}",
                    f"关系推进：{progression_detail.evidence_summary}",
                    f"双人化学反应：{chemistry_detail.evidence_summary}",
                ]
            )
            hard_fail_flags.append(
                RomanceHardFailFlag(
                    flag_type=ROMANCE_MODE_MISS_BLUEPRINT["flag_type"],
                    severity="blocker",
                    reason=(
                        "当前章节的主要压强不是言情双人关系，而是外层权力、旧案或亲属对峙，"
                        "已经偏离 romance eval 要求的主模式。"
                    ),
                    evidence_summary=evidence_summary,
                    related_metrics=[
                        "romance_tension_score",
                        "relationship_progression_score",
                        "emotional_resonance_score",
                        "character_attraction_score",
                    ],
                    suggested_modules=list(ROMANCE_MODE_MISS_BLUEPRINT["target_modules"]),
                )
            )
            for target_module in ROMANCE_MODE_MISS_BLUEPRINT["target_modules"]:
                cls._upsert_target(
                    target_map,
                    RomanceOptimizationTarget(
                        target_module=target_module,
                        issue_type=ROMANCE_MODE_MISS_BLUEPRINT["issue_type"],
                        severity="blocker",
                        confidence=0.93,
                        reason=(
                            f"拉扯感 {tension_detail.score:.1f} / 关系推进 {progression_detail.score:.1f} / "
                            f"双人化学反应 {chemistry_detail.score:.1f}，说明章节压根没立住言情主轴。"
                        ),
                        evidence_summary=evidence_summary,
                        patch_hint=ROMANCE_MODE_MISS_BLUEPRINT["patch_hint"],
                        related_metrics=[
                            "romance_tension_score",
                            "relationship_progression_score",
                            "emotional_resonance_score",
                            "character_attraction_score",
                        ],
                        expected_metric_gains=list(ROMANCE_MODE_MISS_BLUEPRINT["expected_metric_gains"]),
                    ),
                )

        if (
            tension_detail is not None
            and progression_detail is not None
            and emotional_detail is not None
            and hook_detail is not None
            and redundancy_detail is not None
            and tension_detail.score <= 1.5
            and progression_detail.score <= 1.5
            and emotional_detail.score <= 1.5
            and hook_detail.score <= 2.5
            and redundancy_detail.score <= 2.5
        ):
            evidence_summary = "；".join(
                [
                    f"拉扯感：{tension_detail.evidence_summary}",
                    f"关系推进：{progression_detail.evidence_summary}",
                    f"钩子：{hook_detail.evidence_summary}",
                    f"重复铺陈：{redundancy_detail.evidence_summary}",
                ]
            )
            hard_fail_flags.append(
                RomanceHardFailFlag(
                    flag_type=SUMMARY_PROSE_BLUEPRINT["flag_type"],
                    severity="blocker",
                    reason=(
                        "这章更像把剧情提纲或情绪标签复述了一遍，缺少能落在页上的场面执行，"
                        "属于摘要式空文。"
                    ),
                    evidence_summary=evidence_summary,
                    related_metrics=[
                        "romance_tension_score",
                        "relationship_progression_score",
                        "emotional_resonance_score",
                        "hook_score",
                        "redundancy_score",
                    ],
                    suggested_modules=list(SUMMARY_PROSE_BLUEPRINT["target_modules"]),
                )
            )
            for target_module in SUMMARY_PROSE_BLUEPRINT["target_modules"]:
                cls._upsert_target(
                    target_map,
                    RomanceOptimizationTarget(
                        target_module=target_module,
                        issue_type=SUMMARY_PROSE_BLUEPRINT["issue_type"],
                        severity="blocker",
                        confidence=0.95,
                        reason=(
                            f"拉扯感 {tension_detail.score:.1f} / 关系推进 {progression_detail.score:.1f} / "
                            f"情绪余波 {emotional_detail.score:.1f} / 钩子 {hook_detail.score:.1f}，"
                            "说明文本停留在摘要层，没有把场面真正写出来。"
                        ),
                        evidence_summary=evidence_summary,
                        patch_hint=SUMMARY_PROSE_BLUEPRINT["patch_hint"],
                        related_metrics=[
                            "romance_tension_score",
                            "relationship_progression_score",
                            "emotional_resonance_score",
                            "hook_score",
                            "redundancy_score",
                        ],
                        expected_metric_gains=list(SUMMARY_PROSE_BLUEPRINT["expected_metric_gains"]),
                    ),
                )

        if tension_detail is not None and emotional_detail is not None:
            romance_pull_score = round(mean([tension_detail.score, emotional_detail.score]), 2)
            if romance_pull_score <= 6.2 and min(tension_detail.score, emotional_detail.score) <= 5.8:
                combined_detail = cls._best_available_detail(
                    metrics,
                    "romance_tension_score",
                    ("emotional_resonance_score",),
                )
                assert combined_detail is not None
                diagnosis_hit = any(token in diagnosis_blob for token in ROMANCE_PULL_BLUEPRINT["diagnosis_tokens"])
                severity = "high" if romance_pull_score <= 5.0 else "medium"
                evidence_summary = "；".join(
                    [
                        f"拉扯感：{tension_detail.evidence_summary}",
                        f"情绪余波：{emotional_detail.evidence_summary}",
                    ]
                )
                confidence = cls._issue_confidence(
                    score=romance_pull_score,
                    severity=severity,
                    threshold=5.0 if severity == "high" else 6.2,
                    diagnosis_hit=diagnosis_hit,
                    detail=combined_detail,
                )
                if severity == "high":
                    hard_fail_flags.append(
                        RomanceHardFailFlag(
                            flag_type=ROMANCE_PULL_BLUEPRINT["flag_type"],
                            severity="high",
                            reason=(
                                f"追读拉力均值仅 {romance_pull_score:.1f} 分，"
                                "说明正文的情绪拉力和关系电流还没真正立起来。"
                            ),
                            evidence_summary=evidence_summary,
                            related_metrics=[
                                "romance_tension_score",
                                "emotional_resonance_score",
                            ],
                            suggested_modules=list(ROMANCE_PULL_BLUEPRINT["target_modules"]),
                        )
                    )
                for target_module in ROMANCE_PULL_BLUEPRINT["target_modules"]:
                    key = (target_module, ROMANCE_PULL_BLUEPRINT["issue_type"])
                    target = RomanceOptimizationTarget(
                        target_module=target_module,
                        issue_type=ROMANCE_PULL_BLUEPRINT["issue_type"],
                        severity=severity,
                        confidence=confidence,
                        reason=(
                            f"拉扯感 {tension_detail.score:.1f} / 情绪余波 {emotional_detail.score:.1f}，"
                            "章节追读拉力仍然偏弱。"
                        ),
                        evidence_summary=evidence_summary,
                        patch_hint=ROMANCE_PULL_BLUEPRINT["patch_hint"],
                        related_metrics=[
                            "romance_tension_score",
                            "emotional_resonance_score",
                        ],
                        expected_metric_gains=list(ROMANCE_PULL_BLUEPRINT["expected_metric_gains"]),
                    )
                    cls._upsert_target(target_map, target)

        if judge_errors:
            for target_module in (
                "evals/romance/judges/llm_judge.py",
                "evals/romance/prompts/romance_chapter_judge.txt",
            ):
                key = (target_module, "judge_reliability")
                target_map[key] = RomanceOptimizationTarget(
                    target_module=target_module,
                    issue_type="judge_reliability",
                    severity="high",
                    confidence=0.92,
                    reason="本 case 的 romance judge 未返回可用结构，当前评测结果只适合作为降级参考。",
                    evidence_summary="；".join(judge_errors[:2]),
                    patch_hint="先修复 judge schema / prompt / JSON 稳定性，再根据完整评测结果指导 Codex 改正文链路。",
                    related_metrics=[],
                    expected_metric_gains=[],
                )

        verdict = "pass"
        if judge_errors or any(flag.severity == "blocker" for flag in hard_fail_flags):
            verdict = "blocked"
        elif hard_fail_flags or any(detail.score < 7.0 for detail in metrics.values()):
            verdict = "needs_work"

        hard_fail_flags = sorted(
            hard_fail_flags,
            key=lambda item: (-SEVERITY_RANK.get(item.severity, 0), item.flag_type),
        )
        optimization_targets = sorted(target_map.values(), key=cls._target_sort_key)[:8]
        return verdict, hard_fail_flags, optimization_targets

    @staticmethod
    def _hybrid_redundancy_score(
        *,
        judge_score: float,
        rule_score: float,
        anti_slop_score: float,
    ) -> float:
        supportive_rule_score = min(rule_score, anti_slop_score, judge_score)
        return round((judge_score * 0.8) + (supportive_rule_score * 0.2), 2)

    @staticmethod
    def _judge_metrics_to_core(
        *,
        judge: Any,
        rule_redundancy: RomanceMetricDetail,
        rule_anti_slop: RomanceMetricDetail,
    ) -> dict[str, RomanceMetricDetail]:
        attraction_score = round(
            (judge.male_lead_attraction.score * 0.3)
            + (judge.female_lead_attraction.score * 0.3)
            + (judge.lead_pair_chemistry.score * 0.4),
            2,
        )
        hook_score = round((judge.opening_hook.score + judge.ending_hook.score) / 2, 2)
        hybrid_redundancy_score = RomanceEvalHarness._hybrid_redundancy_score(
            judge_score=judge.redundancy.score,
            rule_score=rule_redundancy.score,
            anti_slop_score=rule_anti_slop.score,
        )
        return {
            "romance_tension_score": judge.romance_tension.model_copy(update={"source": "llm"}),
            "relationship_progression_score": judge.relationship_progression.model_copy(update={"source": "llm"}),
            "emotional_resonance_score": judge.emotional_resonance.model_copy(update={"source": "llm"}),
            "character_attraction_score": RomanceMetricDetail(
                score=attraction_score,
                reason="由男主吸引力、女主吸引力和双人化学反应加权合成。",
                evidence_summary=(
                    f"男主：{judge.male_lead_attraction.evidence_summary}；"
                    f"女主：{judge.female_lead_attraction.evidence_summary}；"
                    f"双人：{judge.lead_pair_chemistry.evidence_summary}"
                ),
                improvement_hint=judge.lead_pair_chemistry.improvement_hint,
                source="hybrid",
            ),
            "hook_score": RomanceMetricDetail(
                score=hook_score,
                reason="由开篇钩子与结尾钩子均值合成。",
                evidence_summary=(
                    f"开头：{judge.opening_hook.evidence_summary}；"
                    f"结尾：{judge.ending_hook.evidence_summary}"
                ),
                improvement_hint=judge.ending_hook.improvement_hint,
                source="hybrid",
            ),
            "continuity_score": judge.continuity.model_copy(update={"source": "llm"}),
            "redundancy_score": RomanceMetricDetail(
                score=hybrid_redundancy_score,
                reason="以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。",
                evidence_summary=(
                    f"Judge：{judge.redundancy.evidence_summary}；"
                    f"Rule：{rule_redundancy.evidence_summary}；"
                    f"Anti-slop：{rule_anti_slop.evidence_summary}"
                ),
                improvement_hint=rule_anti_slop.improvement_hint if rule_anti_slop.score < rule_redundancy.score else judge.redundancy.improvement_hint,
                source="hybrid",
            ),
            "mind_state_consistency_score": judge.mind_state_consistency.model_copy(update={"source": "llm"}),
            "genre_fit_score": judge.genre_fit.model_copy(update={"source": "llm"}),
        }

    @staticmethod
    def _fallback_core_metrics(
        *,
        rule_redundancy: RomanceMetricDetail,
        rule_anti_slop: RomanceMetricDetail,
    ) -> dict[str, RomanceMetricDetail]:
        fallback = lambda hint: RomanceMetricDetail(  # noqa: E731
            score=5.0,
            reason="LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。",
            evidence_summary="未获取到可靠的 judge 证据摘要。",
            improvement_hint=hint,
            source="fallback",
        )
        fallback_redundancy = min(rule_redundancy.score, rule_anti_slop.score)
        return {
            "romance_tension_score": fallback("先修复 judge，再观察拉扯感评分。"),
            "relationship_progression_score": fallback("先修复 judge，再观察关系推进评分。"),
            "emotional_resonance_score": fallback("先修复 judge，再观察情绪共鸣评分。"),
            "character_attraction_score": fallback("先修复 judge，再观察角色吸引力评分。"),
            "hook_score": fallback("先修复 judge，再观察章节钩子评分。"),
            "continuity_score": fallback("先修复 judge，再观察连贯性评分。"),
            "redundancy_score": RomanceMetricDetail(
                score=fallback_redundancy,
                reason="LLM judge 失败，本项退化为规则型重复/anti-slop 检测。",
                evidence_summary=(
                    f"规则重复：{rule_redundancy.evidence_summary}；"
                    f"Anti-slop：{rule_anti_slop.evidence_summary}"
                ),
                improvement_hint=rule_anti_slop.improvement_hint if rule_anti_slop.score < rule_redundancy.score else rule_redundancy.improvement_hint,
                source="rule",
            ),
            "mind_state_consistency_score": fallback("先修复 judge，再观察角色心智一致性评分。"),
            "genre_fit_score": fallback("先修复 judge，再观察类型适配评分。"),
        }

    @staticmethod
    def _average_scores(results: list[RomanceCaseResult]) -> dict[str, float]:
        averages: dict[str, float] = {}
        for metric in CORE_METRICS:
            values = [result.scores.get(metric) for result in results if metric in result.scores]
            averages[metric] = round(mean(values), 2) if values else 0.0
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


def _resolve_summary(summary_or_path: RomanceRunSummary | str | Path) -> tuple[RomanceRunSummary, Path]:
    if isinstance(summary_or_path, RomanceRunSummary):
        return summary_or_path, Path(summary_or_path.report_json or summary_or_path.run_dir)
    path = Path(summary_or_path)
    if path.is_dir():
        path = path / "summary.json"
    summary = RomanceRunSummary.model_validate_json(path.read_text(encoding="utf-8"))
    return summary, path


def _blocked_case_ids(summary: RomanceRunSummary) -> set[str]:
    if summary.blocked_case_ids:
        return set(summary.blocked_case_ids)
    return {item.case_id for item in summary.case_results if item.verdict == "blocked"}


def compare_run_summaries(
    baseline: RomanceRunSummary | str | Path,
    candidate: RomanceRunSummary | str | Path,
) -> RomanceRunDiff:
    baseline_summary, baseline_path = _resolve_summary(baseline)
    candidate_summary, candidate_path = _resolve_summary(candidate)

    baseline_cases = {item.case_id: item for item in baseline_summary.case_results}
    candidate_cases = {item.case_id: item for item in candidate_summary.case_results}
    case_diffs: list[RomanceCaseDiff] = []
    improved_metrics_counter: Counter[str] = Counter()
    declined_metrics_counter: Counter[str] = Counter()
    baseline_blocked_ids = _blocked_case_ids(baseline_summary)
    candidate_blocked_ids = _blocked_case_ids(candidate_summary)

    for case_id in sorted(set(baseline_cases) & set(candidate_cases)):
        base_case = baseline_cases[case_id]
        cand_case = candidate_cases[case_id]
        score_deltas: dict[str, ScoreDelta] = {}
        improved_metrics: list[str] = []
        declined_metrics: list[str] = []
        for metric in CORE_METRICS:
            base_value = float(base_case.scores.get(metric, 0.0))
            cand_value = float(cand_case.scores.get(metric, 0.0))
            delta = round(cand_value - base_value, 2)
            score_deltas[metric] = ScoreDelta(
                baseline=base_value,
                candidate=cand_value,
                delta=delta,
            )
            if delta >= 0.3:
                improved_metrics.append(metric)
                improved_metrics_counter[metric] += 1
            elif delta <= -0.3:
                declined_metrics.append(metric)
                declined_metrics_counter[metric] += 1

        base_blockers = {
            item.flag_type
            for item in base_case.hard_fail_flags
            if item.severity == "blocker"
        }
        candidate_blockers = {
            item.flag_type
            for item in cand_case.hard_fail_flags
            if item.severity == "blocker"
        }
        cost_deltas = {
            "llm_calls": round(cand_case.cost_metrics.llm_calls - base_case.cost_metrics.llm_calls, 2),
            "patch_rounds": round(cand_case.cost_metrics.patch_rounds - base_case.cost_metrics.patch_rounds, 2),
            "duration_seconds": round(
                cand_case.cost_metrics.duration_seconds - base_case.cost_metrics.duration_seconds,
                2,
            ),
        }
        case_diffs.append(
            RomanceCaseDiff(
                case_id=case_id,
                title=cand_case.title,
                baseline_verdict=base_case.verdict,
                candidate_verdict=cand_case.verdict,
                score_deltas=score_deltas,
                improved_metrics=improved_metrics,
                declined_metrics=declined_metrics,
                new_blockers=sorted(candidate_blockers - base_blockers),
                resolved_blockers=sorted(base_blockers - candidate_blockers),
                cost_deltas=cost_deltas,
            )
        )

    average_score_deltas: dict[str, ScoreDelta] = {}
    for metric in CORE_METRICS:
        base_value = float(baseline_summary.average_scores.get(metric, 0.0))
        cand_value = float(candidate_summary.average_scores.get(metric, 0.0))
        average_score_deltas[metric] = ScoreDelta(
            baseline=base_value,
            candidate=cand_value,
            delta=round(cand_value - base_value, 2),
        )

    return RomanceRunDiff(
        baseline_label=baseline_summary.label,
        candidate_label=candidate_summary.label,
        average_score_deltas=average_score_deltas,
        case_diffs=case_diffs,
        improved_metrics=sorted(improved_metrics_counter),
        declined_metrics=sorted(declined_metrics_counter),
        blocked_case_delta=len(candidate_blocked_ids) - len(baseline_blocked_ids),
        new_blocker_case_ids=sorted(candidate_blocked_ids - baseline_blocked_ids),
        resolved_blocker_case_ids=sorted(baseline_blocked_ids - candidate_blocked_ids),
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
    )
