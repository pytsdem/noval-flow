from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from evals.romance.step_plan_evals import StepPlanEvalRunner


class StepPlanEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_step_plan_evals_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_scores_active_step_fixtures(self) -> None:
        summary = StepPlanEvalRunner(reports_root=self.root / "reports").run(
            cases_dir="evals/romance/cases",
            label="active_step_plan",
        )

        self.assertEqual(len(summary.case_reports), 3)
        self.assertGreaterEqual(summary.average_score, 6.5)
        self.assertTrue((self.root / "reports" / "active_step_plan" / "step_plan_eval_summary.json").exists())
        self.assertTrue((self.root / "reports" / "active_step_plan" / "report.md").exists())
        for case_report in summary.case_reports:
            self.assertEqual(len(case_report.step_reports), 8)
            self.assertIn(case_report.verdict, {"pass", "warn"})

    def test_blocks_thin_fixture(self) -> None:
        cases_dir = self.root / "cases"
        case_dir = cases_dir / "thin_case"
        case_dir.mkdir(parents=True)
        (case_dir / "steps.json").write_text(
            json.dumps(
                {
                    "case_id": "thin_case",
                    "step_1": {"premise": {"title": "薄", "high_concept": "", "genre": "romance", "target_style": "", "emotional_hook": "", "central_conflict": ""}},
                    "step_2": {"story_engine": {"world_rules": []}},
                    "step_3": {"characters": []},
                    "step_4": {"event_timeline": []},
                    "step_5": {"milestone_grid": []},
                    "step_6": {"twist_designs": []},
                    "step_7": {"story_lines": []},
                    "step_8": {"chapter_briefs": []},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary = StepPlanEvalRunner(reports_root=self.root / "reports").run(
            cases_dir=cases_dir,
            label="thin_step_plan",
        )

        self.assertEqual(summary.verdict_counts["blocked"], 1)
        self.assertEqual(summary.case_reports[0].verdict, "blocked")


if __name__ == "__main__":
    unittest.main()
