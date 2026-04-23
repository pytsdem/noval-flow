from __future__ import annotations

import shutil
import unittest
from uuid import uuid4
from pathlib import Path

from evals.romance.comparison import compare_paths
from evals.romance.history_models import (
    HistoricalCaseMetrics,
    StepEvalAggregateFindings,
    StepEvalCaseReport,
    StepEvalSummary,
    StepGateDecision,
    WorkflowDiagnosticDetail,
)
from evals.romance.models import (
    RomanceCaseArtifacts,
    RomanceCaseResult,
    RomanceCostMetrics,
    RomanceHardFailFlag,
    RomanceMetricDetail,
    RomanceRunSummary,
)


def _detail(score: float) -> RomanceMetricDetail:
    return RomanceMetricDetail(
        score=score,
        reason="test",
        evidence_summary="test",
        improvement_hint="test",
        source="hybrid",
    )


def _case_result(
    case_id: str,
    *,
    delta: float = 0.0,
    continuity_delta: float = 0.0,
    llm_calls: int = 5,
    verdict: str = "needs_work",
    hard_fail_flags: list[RomanceHardFailFlag] | None = None,
) -> RomanceCaseResult:
    scores = {
        "romance_tension_score": 7.0 + delta,
        "relationship_progression_score": 6.8 + delta,
        "emotional_resonance_score": 7.1 + delta,
        "character_attraction_score": 7.2 + delta,
        "hook_score": 6.9 + delta,
        "continuity_score": 7.4 + continuity_delta,
        "redundancy_score": 7.5,
        "mind_state_consistency_score": 7.3,
    }
    return RomanceCaseResult(
        case_id=case_id,
        title="Case",
        verdict=verdict,
        scores=scores,
        metrics={key: _detail(value) for key, value in scores.items()},
        hard_fail_flags=hard_fail_flags or [],
        cost_metrics=RomanceCostMetrics(llm_calls=llm_calls, duration_seconds=10.0 + delta, patch_rounds=1),
        artifacts=RomanceCaseArtifacts(),
    )


class CaseComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_case_comparison_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_comparison_reports_accept_improving_candidate(self) -> None:
        baseline = RomanceRunSummary(
            label="baseline",
            mode="fast",
            case_results=[_case_result("case_001", delta=0.0, continuity_delta=0.0, llm_calls=5)],
            average_scores={
                "romance_tension_score": 7.0,
                "relationship_progression_score": 6.8,
                "emotional_resonance_score": 7.1,
                "character_attraction_score": 7.2,
                "hook_score": 6.9,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        candidate = RomanceRunSummary(
            label="candidate",
            mode="fast",
            case_results=[_case_result("case_001", delta=0.5, continuity_delta=0.0, llm_calls=6)],
            average_scores={
                "romance_tension_score": 7.5,
                "relationship_progression_score": 7.3,
                "emotional_resonance_score": 7.6,
                "character_attraction_score": 7.7,
                "hook_score": 7.4,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        baseline_path = self.root / "baseline.json"
        candidate_path = self.root / "candidate.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

        payload = compare_paths(baseline_path, candidate_path)
        self.assertEqual(payload["comparison_type"], "romance_eval")
        self.assertTrue(payload["decision"]["accept_change"])
        self.assertGreater(payload["decision"]["core_metric_delta"], 0)
        self.assertIn("romance_tension_score", payload["average_score_deltas"])
        self.assertEqual(payload["pairwise_preference"]["overall_preferred_side"], "candidate")
        self.assertEqual(payload["decision"]["pairwise_preferred_side"], "candidate")

    def test_comparison_rejects_guard_regression(self) -> None:
        baseline = RomanceRunSummary(
            label="baseline",
            mode="fast",
            case_results=[_case_result("case_001", delta=0.0, continuity_delta=0.0, llm_calls=5)],
            average_scores={
                "romance_tension_score": 7.0,
                "relationship_progression_score": 6.8,
                "emotional_resonance_score": 7.1,
                "character_attraction_score": 7.2,
                "hook_score": 6.9,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        candidate = RomanceRunSummary(
            label="candidate",
            mode="fast",
            case_results=[_case_result("case_001", delta=0.4, continuity_delta=-0.5, llm_calls=6)],
            average_scores={
                "romance_tension_score": 7.4,
                "relationship_progression_score": 7.2,
                "emotional_resonance_score": 7.5,
                "character_attraction_score": 7.6,
                "hook_score": 7.3,
                "continuity_score": 6.9,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        baseline_path = self.root / "baseline_guard.json"
        candidate_path = self.root / "candidate_guard.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

        payload = compare_paths(baseline_path, candidate_path)
        self.assertFalse(payload["decision"]["accept_change"])
        self.assertIn("Continuity regressed beyond the safety threshold.", payload["decision"]["reasons"])

    def test_comparison_rejects_pairwise_baseline_majority_even_when_average_core_improves(self) -> None:
        baseline_case_results = [
            _case_result("case_001", delta=0.0, continuity_delta=0.0, llm_calls=5),
            _case_result("case_002", delta=0.0, continuity_delta=0.0, llm_calls=5),
            _case_result("case_003", delta=0.0, continuity_delta=0.0, llm_calls=5),
        ]
        candidate_case_results = [
            _case_result("case_001", delta=1.0, continuity_delta=0.0, llm_calls=5),
            _case_result("case_002", delta=-0.25, continuity_delta=0.0, llm_calls=5),
            _case_result("case_003", delta=-0.25, continuity_delta=0.0, llm_calls=5),
        ]
        baseline = RomanceRunSummary(
            label="baseline_pairwise",
            mode="fast",
            case_results=baseline_case_results,
            average_scores={
                "romance_tension_score": 7.0,
                "relationship_progression_score": 6.8,
                "emotional_resonance_score": 7.1,
                "character_attraction_score": 7.2,
                "hook_score": 6.9,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        candidate = RomanceRunSummary(
            label="candidate_pairwise",
            mode="fast",
            case_results=candidate_case_results,
            average_scores={
                "romance_tension_score": 7.17,
                "relationship_progression_score": 6.97,
                "emotional_resonance_score": 7.27,
                "character_attraction_score": 7.37,
                "hook_score": 7.07,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
        )
        baseline_path = self.root / "baseline_pairwise.json"
        candidate_path = self.root / "candidate_pairwise.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

        payload = compare_paths(baseline_path, candidate_path)
        self.assertGreater(payload["decision"]["core_metric_delta"], 0)
        self.assertEqual(payload["pairwise_preference"]["candidate_case_wins"], 1)
        self.assertEqual(payload["pairwise_preference"]["baseline_case_wins"], 2)
        self.assertEqual(payload["pairwise_preference"]["overall_preferred_side"], "baseline")
        self.assertFalse(payload["decision"]["accept_change"])
        self.assertIn("Pairwise case preference favored the baseline.", payload["decision"]["reasons"])

    def test_comparison_rejects_new_blocker_case(self) -> None:
        blocker = RomanceHardFailFlag(
            flag_type="mind_state_break",
            severity="blocker",
            reason="mind state broke",
            evidence_summary="evidence",
            related_metrics=["mind_state_consistency_score"],
            suggested_modules=["prompts/writer/build_character_mindset.txt"],
        )
        baseline = RomanceRunSummary(
            label="baseline",
            mode="fast",
            case_results=[_case_result("case_001", delta=0.0, verdict="pass")],
            average_scores={
                "romance_tension_score": 7.0,
                "relationship_progression_score": 6.8,
                "emotional_resonance_score": 7.1,
                "character_attraction_score": 7.2,
                "hook_score": 6.9,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
            verdict_counts={"pass": 1},
        )
        candidate = RomanceRunSummary(
            label="candidate",
            mode="fast",
            case_results=[
                _case_result(
                    "case_001",
                    delta=0.4,
                    verdict="blocked",
                    hard_fail_flags=[blocker],
                )
            ],
            average_scores={
                "romance_tension_score": 7.4,
                "relationship_progression_score": 7.2,
                "emotional_resonance_score": 7.5,
                "character_attraction_score": 7.6,
                "hook_score": 7.3,
                "continuity_score": 7.4,
                "redundancy_score": 7.5,
                "mind_state_consistency_score": 7.3,
            },
            verdict_counts={"blocked": 1},
            blocked_case_ids=["case_001"],
        )
        baseline_path = self.root / "baseline_blocker.json"
        candidate_path = self.root / "candidate_blocker.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

        payload = compare_paths(baseline_path, candidate_path)
        self.assertFalse(payload["decision"]["accept_change"])
        self.assertEqual(payload["decision"]["blocked_case_delta"], 1)
        self.assertIn("Candidate introduced new blocker cases.", payload["decision"]["reasons"])

    def test_step_eval_comparison_accepts_fewer_blocked_cases(self) -> None:
        baseline = StepEvalSummary(
            label="baseline_step",
            case_reports=[
                StepEvalCaseReport(
                    case_id="case_001",
                    title="Case",
                    step_diagnostics={
                        "brief_quality_score": WorkflowDiagnosticDetail(score=6.5, reason="test", evidence=[], improvement_hint=""),
                        "relationship_state_quality_score": WorkflowDiagnosticDetail(score=6.0, reason="test", evidence=[], improvement_hint=""),
                        "mind_state_quality_score": WorkflowDiagnosticDetail(score=6.1, reason="test", evidence=[], improvement_hint=""),
                        "writing_pack_quality_score": WorkflowDiagnosticDetail(score=6.1, reason="test", evidence=[], improvement_hint=""),
                        "block_plan_quality_score": WorkflowDiagnosticDetail(score=6.2, reason="test", evidence=[], improvement_hint=""),
                    },
                    gate_decision=StepGateDecision(
                        verdict="blocked",
                        accept_for_chapter_generation=False,
                        blocking_steps=["writing_pack_quality_score", "block_plan_quality_score"],
                        average_step_score=6.18,
                    ),
                    cost_metrics=HistoricalCaseMetrics(),
                )
            ],
            aggregate_findings=StepEvalAggregateFindings(blocked_case_ids=["case_001"]),
            gate_counts={"pass": 0, "warn": 0, "blocked": 1},
        )
        candidate = StepEvalSummary(
            label="candidate_step",
            case_reports=[
                StepEvalCaseReport(
                    case_id="case_001",
                    title="Case",
                    step_diagnostics={
                        "brief_quality_score": WorkflowDiagnosticDetail(score=7.2, reason="test", evidence=[], improvement_hint=""),
                        "relationship_state_quality_score": WorkflowDiagnosticDetail(score=6.8, reason="test", evidence=[], improvement_hint=""),
                        "mind_state_quality_score": WorkflowDiagnosticDetail(score=6.9, reason="test", evidence=[], improvement_hint=""),
                        "writing_pack_quality_score": WorkflowDiagnosticDetail(score=7.2, reason="test", evidence=[], improvement_hint=""),
                        "block_plan_quality_score": WorkflowDiagnosticDetail(score=7.3, reason="test", evidence=[], improvement_hint=""),
                    },
                    gate_decision=StepGateDecision(
                        verdict="pass",
                        accept_for_chapter_generation=True,
                        average_step_score=7.08,
                    ),
                    cost_metrics=HistoricalCaseMetrics(),
                )
            ],
            aggregate_findings=StepEvalAggregateFindings(accepted_case_ids=["case_001"]),
            gate_counts={"pass": 1, "warn": 0, "blocked": 0},
        )
        baseline_path = self.root / "baseline_step.json"
        candidate_path = self.root / "candidate_step.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")
        candidate_path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")

        payload = compare_paths(baseline_path, candidate_path)
        self.assertEqual(payload["comparison_type"], "step_eval")
        self.assertTrue(payload["decision"]["accept_change"])
        self.assertEqual(payload["decision"]["blocked_case_delta"], -1)
        self.assertGreater(payload["decision"]["core_metric_delta"], 0)


if __name__ == "__main__":
    unittest.main()
