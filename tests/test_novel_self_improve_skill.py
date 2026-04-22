from __future__ import annotations

import json
import unittest
from pathlib import Path


class NovelSelfImproveSkillTests(unittest.TestCase):
    def test_skill_wrapper_files_exist(self) -> None:
        skill_dir = Path("skills/novel_self_improve")
        expected = [
            skill_dir / "SKILL.md",
            skill_dir / "manifest.json",
            skill_dir / "export_cases.ps1",
            skill_dir / "analyze_failures.py",
        ]
        for path in expected:
            self.assertTrue(path.exists(), msg=f"Missing skill artifact: {path}")
        manifest = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["skill_id"], "novel_self_improve")
        self.assertNotIn("python -m tools.run_novel_self_improve", manifest.get("tools", []))


if __name__ == "__main__":
    unittest.main()
