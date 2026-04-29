from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evals.romance.long_arc_step8_eval import LongArcStep8EvalRunner, LongArcStep8Evaluator
from evals.romance.step_fixture_loader import load_step_fixture


class LongArcStep8EvalTests(unittest.TestCase):
    def test_evaluates_existing_step8_fixture(self) -> None:
        payload = load_step_fixture("evals/romance/cases/romance_case_01_court_return/steps.json")

        report = LongArcStep8Evaluator().evaluate_case(
            case_id="romance_case_01_court_return",
            source="fixture",
            payload=payload,
        )

        self.assertEqual(report.case_id, "romance_case_01_court_return")
        self.assertGreaterEqual(report.chapter_count, 3)
        self.assertIn("chapter_chain_causality", report.metrics)
        self.assertIn("escalation_curve", report.metrics)
        self.assertIn("reader_retention_curve", report.metrics)

    def test_runner_writes_summary_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = LongArcStep8EvalRunner(reports_root=tmp).run(
                cases_dir="evals/romance/cases",
                label="unit_long_arc",
                case_ids=["romance_case_01_court_return"],
            )

            self.assertEqual(summary.label, "unit_long_arc")
            self.assertEqual(summary.case_ids, ["romance_case_01_court_return"])
            self.assertTrue(Path(summary.report_json).exists())
            self.assertTrue(Path(summary.report_markdown).exists())
            self.assertTrue((Path(summary.report_json).parent / "long_arc_step8_eval_summary.json").exists())
            self.assertFalse(summary.generated)


if __name__ == "__main__":
    unittest.main()
