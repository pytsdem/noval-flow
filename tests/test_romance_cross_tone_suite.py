from __future__ import annotations

import unittest
from pathlib import Path

from evals.romance.loader import load_cases, load_suite_case_ids


class RomanceCrossToneSuiteTests(unittest.TestCase):
    def test_suite_loads_high_concept_cross_tone_cases(self) -> None:
        suite_path = Path("evals/romance/suites/romance_cross_tone_smoke.yml")
        case_ids = load_suite_case_ids(suite_path)
        cases = load_cases(Path("evals/romance/cases"), case_ids=case_ids)

        self.assertEqual(
            case_ids,
            [
                "romance_case_01_court_return",
                "romance_case_02_xianxia_rival_trial",
                "romance_case_03_urban_reunion_comedy",
            ],
        )
        self.assertEqual(len(cases), 3)
        by_id = {case.case_id: case for case in cases}
        self.assertEqual(by_id["romance_case_02_xianxia_rival_trial"].genre_profile, "xianxia_fantasy_romance")
        self.assertEqual(by_id["romance_case_02_xianxia_rival_trial"].tone_profile, "light_adventure_banter")
        self.assertIn("心声", by_id["romance_case_02_xianxia_rival_trial"].premise.high_concept)
        self.assertEqual(by_id["romance_case_03_urban_reunion_comedy"].genre_profile, "urban_modern_romance")
        self.assertEqual(by_id["romance_case_03_urban_reunion_comedy"].tone_profile, "light_witty_reunion")
        self.assertIn("直播", by_id["romance_case_03_urban_reunion_comedy"].premise.high_concept)


if __name__ == "__main__":
    unittest.main()
