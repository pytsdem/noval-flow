from __future__ import annotations

import unittest

from evals.romance.judges.rule_metrics import AntiSlopRuleAnalyzer


class AntiSlopRuleAnalyzerTests(unittest.TestCase):
    def test_analyze_penalizes_direct_thought_and_explanation(self) -> None:
        detail = AntiSlopRuleAnalyzer().analyze(
            chapter_text=(
                "她知道自己不能露怯，这让她更明白他不会轻易放手。"
                "他意识到她在撒谎，也觉得自己更难抽身。"
            ),
            review_reports={
                "review_prose_quality": {
                    "issues": [
                        {
                            "category": "direct_thought",
                            "reason": "心理解释过直白",
                        }
                    ]
                }
            },
        )

        self.assertLess(detail.score, 7.0)
        self.assertIn("直白心理", detail.evidence_summary)
        self.assertIn("解释性总结", detail.evidence_summary)

    def test_analyze_returns_high_score_for_action_and_subtext_heavy_text(self) -> None:
        detail = AntiSlopRuleAnalyzer().analyze(
            chapter_text=(
                "她把茶盏往他手边推了半寸，却没抬眼。"
                "他接住那点退让，只把袖口拢紧，像是什么都没听见。"
            ),
            review_reports={},
        )

        self.assertGreaterEqual(detail.score, 8.0)
        self.assertIn("未检测到明显直白心理标签", detail.evidence_summary)


if __name__ == "__main__":
    unittest.main()
