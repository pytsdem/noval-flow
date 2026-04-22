from __future__ import annotations

import shutil
import unittest
from uuid import uuid4
from pathlib import Path

from evals.romance.history_models import (
    HistoricalCaseInputs,
    HistoricalCaseIntermediates,
    HistoricalCaseMetadata,
    HistoricalCaseMetrics,
    HistoricalCaseOutputs,
    HistoricalEvalCase,
)
from evals.romance.step_evals import StepEvalRunner


class StepEvalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_step_evals_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_runner_blocks_cases_with_weak_upstream_artifacts(self) -> None:
        case_dir = self.root / "cases"
        case_dir.mkdir()
        weak_case = HistoricalEvalCase(
            case_id="case_weak",
            metadata=HistoricalCaseMetadata(
                chapter_id="ch_001",
                chapter_title="Weak Upstream",
                tags=["opening_hook"],
            ),
            inputs=HistoricalCaseInputs(
                chapter_brief={
                    "title": "Weak Upstream",
                    "summary": "The setup is vague.",
                    "opening_hook": "",
                    "ending_pull": "",
                    "relationship_reprice": "",
                },
                chapter_payload="",
                relationship_state={"text": ""},
                character_mind_states=[],
                writing_pack={
                    "step_6_twists_text": "",
                    "step_7_story_lines_text": "",
                    "relevant_world_rules_text": "",
                },
            ),
            intermediates=HistoricalCaseIntermediates(
                block_plan={"stage": "plan_content_blocks", "block_count": 1, "blocks": []},
            ),
            outputs=HistoricalCaseOutputs(
                final_text="A flat scene with weak setup.",
                final_summary="The upstream steps are not ready.",
                final_status="failed_partial",
            ),
            metrics=HistoricalCaseMetrics(),
        )
        (case_dir / "case_weak.json").write_text(weak_case.model_dump_json(indent=2), encoding="utf-8")

        summary = StepEvalRunner(reports_root=self.root / "reports").run(case_dir=case_dir, label="step_gate")

        self.assertTrue((self.root / "reports" / "step_gate" / "step_eval_summary.json").exists())
        self.assertEqual(summary.gate_counts["blocked"], 1)
        report = summary.case_reports[0]
        self.assertEqual(report.gate_decision.verdict, "blocked")
        self.assertFalse(report.gate_decision.accept_for_chapter_generation)
        self.assertIn("writing_pack_quality_score", report.gate_decision.blocking_steps)

    def test_runner_marks_strong_upstream_artifacts_as_pass(self) -> None:
        case_dir = self.root / "strong_cases"
        case_dir.mkdir()
        strong_case = HistoricalEvalCase(
            case_id="case_strong",
            metadata=HistoricalCaseMetadata(
                chapter_id="ch_002",
                chapter_title="Strong Upstream",
                tags=["high_tension_romance"],
            ),
            inputs=HistoricalCaseInputs(
                chapter_brief={
                    "title": "Strong Upstream",
                    "summary": "He tests her under pressure.",
                    "opening_hook": "The order falls.",
                    "ending_pull": "The witness dies.",
                    "relationship_reprice": "She stops feeling purely hostile.",
                    "human_pain_anchor": "He kneels before the whole court.",
                },
                chapter_payload="payload",
                relationship_state={"text": "Their hostility is now entangled with dependence."},
                character_mind_states=[
                    {"character_name": "A", "fear": "losing control", "hidden_need": "to be believed"}
                ],
                writing_pack={
                    "step_6_twists_text": "twist packet",
                    "step_7_story_lines_text": "story line packet",
                    "relevant_world_rules_text": "court rules",
                    "chapter_payload_text": "payload",
                },
            ),
            intermediates=HistoricalCaseIntermediates(
                block_plan={
                    "stage": "plan_content_blocks",
                    "block_count": 3,
                    "blocks": [
                        {"block_id": "b1"},
                        {"block_id": "b2"},
                        {"block_id": "b3"},
                    ],
                },
            ),
            outputs=HistoricalCaseOutputs(
                final_text="A pressured and coherent scene.",
                final_summary="The upstream steps are chapter-ready.",
                final_status="success",
            ),
            metrics=HistoricalCaseMetrics(),
        )
        (case_dir / "case_strong.json").write_text(strong_case.model_dump_json(indent=2), encoding="utf-8")

        summary = StepEvalRunner(reports_root=self.root / "reports").run(case_dir=case_dir, label="step_gate_strong")

        self.assertEqual(summary.gate_counts["pass"], 1)
        report = summary.case_reports[0]
        self.assertEqual(report.gate_decision.verdict, "pass")
        self.assertTrue(report.gate_decision.accept_for_chapter_generation)
        self.assertEqual(report.gate_decision.blocking_steps, [])


if __name__ == "__main__":
    unittest.main()
