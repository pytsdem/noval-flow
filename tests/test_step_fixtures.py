from __future__ import annotations

import unittest
import shutil
from pathlib import Path
from uuid import uuid4

from evals.romance.step_plan_evals import StepPlanEvalRunner
from evals.romance.step_fixture_loader import iter_step_fixture_paths, step_fixture_path, validate_step_fixture


class StepFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_step_fixtures_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_active_step_fixtures_validate_and_score_step_plan(self) -> None:
        case_ids = [
            "romance_case_01_court_return",
            "romance_case_02_xianxia_rival_trial",
            "romance_case_03_urban_reunion_comedy",
        ]
        self.assertEqual(
            [path.parent.name for path in iter_step_fixture_paths()],
            case_ids,
        )
        for case_id in case_ids:
            path = step_fixture_path(case_id)
            counts = validate_step_fixture(path)
            self.assertGreaterEqual(counts["world_rules"], 6)
            self.assertGreaterEqual(counts["worldbuilding_detail_sections"], 5)
            self.assertGreaterEqual(counts["characters"], 4)
            self.assertGreaterEqual(counts["developed_characters"], 4)
            self.assertGreaterEqual(counts["character_deep_cards"], 4)
            self.assertGreaterEqual(counts["twist_designs"], 2)
            self.assertGreaterEqual(counts["story_lines"], 2)
            self.assertGreaterEqual(counts["chapter_briefs"], 3)

        summary = StepPlanEvalRunner(reports_root=self.root / "reports").run(
            cases_dir="evals/romance/cases",
            label="fixture_step_plan_eval",
        )
        self.assertEqual(summary.case_ids, case_ids)
        self.assertGreaterEqual(summary.average_score, 6.5)
        self.assertEqual(sum(summary.verdict_counts.values()), 3)


if __name__ == "__main__":
    unittest.main()
