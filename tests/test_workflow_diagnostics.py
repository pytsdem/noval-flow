from __future__ import annotations

import shutil
import unittest
from uuid import uuid4
from pathlib import Path

from evals.romance.history_models import (
    AggregateFindings,
    HistoricalCaseInputs,
    HistoricalCaseIntermediates,
    HistoricalCaseMetadata,
    HistoricalCaseMetrics,
    HistoricalCaseOutputs,
    HistoricalEvalCase,
    WorkflowDiagnosticDetail,
    WorkflowDiagnosticsCaseReport,
)
from evals.romance.models import RomanceMetricDetail
from evals.romance.workflow_diagnostics import WorkflowDiagnosticsRunner


def _detail(score: float) -> RomanceMetricDetail:
    return RomanceMetricDetail(
        score=score,
        reason="test",
        evidence_summary="test",
        improvement_hint="test",
        source="hybrid",
    )


class WorkflowDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_workflow_diagnostics_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_runner_produces_case_and_aggregate_reports(self) -> None:
        case_dir = self.root / "cases"
        case_dir.mkdir()
        case = HistoricalEvalCase(
            case_id="case_001",
            metadata=HistoricalCaseMetadata(
                book_id="book_001",
                chapter_id="ch_001",
                run_id="run_001",
                chapter_title="Cold Return",
                tags=["opening_hook", "high_tension_romance"],
            ),
            inputs=HistoricalCaseInputs(
                chapter_brief={
                    "title": "Cold Return",
                    "summary": "He returns to test her in public.",
                    "opening_hook": "The order lands before he can breathe.",
                    "ending_pull": "The witness is dead.",
                    "relationship_reprice": "She stops feeling purely villainous.",
                    "human_pain_anchor": "He bows before the whole court.",
                },
                chapter_payload="chapter payload",
                relationship_state={"text": ""},
                character_mind_states=[],
                writing_pack={
                    "step_6_twists_text": "twist packet",
                    "step_7_story_lines_text": "",
                    "relevant_world_rules_text": "",
                },
            ),
            intermediates=HistoricalCaseIntermediates(
                block_plan={"stage": "plan_content_blocks", "block_count": 1, "blocks": [{"block_id": "ch_001.sc_001.b001"}]},
                review_reports=[
                    {
                        "stage": "review_iteration_1",
                        "review_reports": {
                            "review_continuity": {
                                "passed": False,
                                "level": "high",
                                "issues": [
                                    {
                                        "category": "continuity",
                                        "severity": "high",
                                        "evidence": "The threat repeats twice.",
                                        "reason": "The ending loses pull.",
                                        "fix": "Keep one ending threat.",
                                    }
                                ],
                                "rewrite_guidance": "Keep one ending threat.",
                            }
                        },
                        "final_judge": {"passed": False, "blocking_reasons": ["Continuity still weak."]},
                    }
                ],
                final_judge={"passed": False, "blocking_reasons": ["Continuity still weak."]},
                stage_log=[{"stage": "rewrite_iteration_1"}],
            ),
            outputs=HistoricalCaseOutputs(
                final_text=(
                    "她知道自己不能露怯，这让她更明白眼前的人更危险。"
                    "她又知道自己不能退，这让她更清楚谢临川不会轻易放手。"
                    "他意识到她没有一句真话，也觉得自己更难抽身。"
                ),
                final_summary="He returns under pressure.",
                final_status="failed_partial",
            ),
            metrics=HistoricalCaseMetrics(
                review_rounds=1,
                patch_rounds=1,
                used_full_rewrite=True,
                quality_risk=5.0,
            ),
        )
        (case_dir / "case_001.json").write_text(case.model_dump_json(indent=2), encoding="utf-8")

        reports_root = self.root / "reports"
        summary = WorkflowDiagnosticsRunner(reports_root=reports_root).run(case_dir=case_dir, label="diag_run")

        self.assertEqual(summary.case_ids, ["case_001"])
        self.assertTrue((reports_root / "diag_run" / "diagnostics_summary.json").exists())
        self.assertTrue((reports_root / "diag_run" / "report.md").exists())
        report = summary.case_reports[0]
        self.assertIn("state_modeling_layer", report.workflow_layer_diagnostics)
        self.assertIn("mind_state_quality_score", report.step_diagnostics)
        self.assertIn("continuity_score", report.final_text_scores)
        self.assertIn("anti_slop_score", report.diagnostic_signals)
        self.assertLess(report.diagnostic_signals["anti_slop_score"].score, 7.0)
        self.assertIn("state_modeling_layer", summary.aggregate_findings.most_common_root_layers)
        self.assertEqual(summary.aggregate_findings.slop_hotspot_cases, ["case_001"])

    def test_aggregate_analysis_counts_shared_failure_modes(self) -> None:
        report_a = WorkflowDiagnosticsCaseReport(
            case_id="a",
            title="A",
            tags=["opening_hook"],
            final_text_scores={
                "relationship_progression_score": _detail(5.0),
                "continuity_score": _detail(6.0),
                "redundancy_score": _detail(8.5),
            },
            workflow_layer_diagnostics={
                "input_definition_layer": WorkflowDiagnosticDetail(score=7.2, reason="ok", evidence=[], improvement_hint=""),
                "state_modeling_layer": WorkflowDiagnosticDetail(score=5.2, reason="low", evidence=[], improvement_hint=""),
                "writing_pack_layer": WorkflowDiagnosticDetail(score=7.0, reason="ok", evidence=[], improvement_hint=""),
                "chapter_planning_layer": WorkflowDiagnosticDetail(score=7.1, reason="ok", evidence=[], improvement_hint=""),
                "draft_execution_layer": WorkflowDiagnosticDetail(score=6.8, reason="mid", evidence=[], improvement_hint=""),
                "revision_layer": WorkflowDiagnosticDetail(score=6.5, reason="mid", evidence=[], improvement_hint=""),
            },
            step_diagnostics={
                "brief_quality_score": WorkflowDiagnosticDetail(score=7.1, reason="ok", evidence=[], improvement_hint=""),
                "relationship_state_quality_score": WorkflowDiagnosticDetail(score=5.0, reason="low", evidence=[], improvement_hint=""),
                "mind_state_quality_score": WorkflowDiagnosticDetail(score=5.8, reason="mid", evidence=[], improvement_hint=""),
                "writing_pack_quality_score": WorkflowDiagnosticDetail(score=7.0, reason="ok", evidence=[], improvement_hint=""),
                "block_plan_quality_score": WorkflowDiagnosticDetail(score=7.0, reason="ok", evidence=[], improvement_hint=""),
                "writer_execution_quality_score": WorkflowDiagnosticDetail(score=6.5, reason="mid", evidence=[], improvement_hint=""),
                "patch_effectiveness_score": WorkflowDiagnosticDetail(score=6.2, reason="mid", evidence=[], improvement_hint=""),
            },
            diagnostic_signals={
                "anti_slop_score": _detail(8.1),
            },
            cost_metrics=HistoricalCaseMetrics(used_full_rewrite=True),
        )
        report_b = WorkflowDiagnosticsCaseReport(
            case_id="b",
            title="B",
            tags=["opening_hook", "high_tension_romance"],
            final_text_scores={
                "relationship_progression_score": _detail(5.5),
                "continuity_score": _detail(7.2),
                "redundancy_score": _detail(6.2),
            },
            workflow_layer_diagnostics={
                "input_definition_layer": WorkflowDiagnosticDetail(score=7.3, reason="ok", evidence=[], improvement_hint=""),
                "state_modeling_layer": WorkflowDiagnosticDetail(score=5.4, reason="low", evidence=[], improvement_hint=""),
                "writing_pack_layer": WorkflowDiagnosticDetail(score=6.9, reason="mid", evidence=[], improvement_hint=""),
                "chapter_planning_layer": WorkflowDiagnosticDetail(score=7.2, reason="ok", evidence=[], improvement_hint=""),
                "draft_execution_layer": WorkflowDiagnosticDetail(score=6.7, reason="mid", evidence=[], improvement_hint=""),
                "revision_layer": WorkflowDiagnosticDetail(score=6.1, reason="mid", evidence=[], improvement_hint=""),
            },
            step_diagnostics={
                "brief_quality_score": WorkflowDiagnosticDetail(score=7.0, reason="ok", evidence=[], improvement_hint=""),
                "relationship_state_quality_score": WorkflowDiagnosticDetail(score=5.2, reason="low", evidence=[], improvement_hint=""),
                "mind_state_quality_score": WorkflowDiagnosticDetail(score=5.5, reason="low", evidence=[], improvement_hint=""),
                "writing_pack_quality_score": WorkflowDiagnosticDetail(score=6.9, reason="mid", evidence=[], improvement_hint=""),
                "block_plan_quality_score": WorkflowDiagnosticDetail(score=7.1, reason="ok", evidence=[], improvement_hint=""),
                "writer_execution_quality_score": WorkflowDiagnosticDetail(score=6.6, reason="mid", evidence=[], improvement_hint=""),
                "patch_effectiveness_score": WorkflowDiagnosticDetail(score=6.1, reason="mid", evidence=[], improvement_hint=""),
            },
            diagnostic_signals={
                "anti_slop_score": _detail(5.9),
            },
            cost_metrics=HistoricalCaseMetrics(used_full_rewrite=False),
        )

        aggregate = WorkflowDiagnosticsRunner._aggregate([report_a, report_b])
        self.assertIsInstance(aggregate, AggregateFindings)
        self.assertEqual(aggregate.most_common_low_scores[0], "relationship_progression_score")
        self.assertEqual(aggregate.most_common_root_layers[0], "state_modeling_layer")
        self.assertEqual(aggregate.most_common_root_steps[0], "relationship_state_quality_score")
        self.assertEqual(aggregate.frequent_full_rewrite_cases, ["a"])
        self.assertEqual(aggregate.redundancy_hotspot_cases, ["b"])
        self.assertEqual(aggregate.slop_hotspot_cases, ["b"])


if __name__ == "__main__":
    unittest.main()
