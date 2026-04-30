from __future__ import annotations

import unittest

from evals.romance.judges.rule_metrics import (
    ActionCarriedRevealRuleAnalyzer,
    AntiSlopRuleAnalyzer,
    ExplanationDensityRuleAnalyzer,
    PronounLeadRuleAnalyzer,
    RelationshipCostRealizationRuleAnalyzer,
)
from novel_flow.services.prose_lint import analyze_prose_surface


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


class PronounLeadRuleAnalyzerTests(unittest.TestCase):
    def test_analyze_penalizes_heavy_pronoun_led_sentences(self) -> None:
        detail = PronounLeadRuleAnalyzer().analyze(
            chapter_text=(
                "她捏紧袖口。她没有抬头。她只看着案上的灯。"
                "他站在门边。她又把指节压白。"
            )
        )

        self.assertLess(detail.score, 7.0)
        self.assertIn("句首代词占比", detail.evidence_summary)

    def test_analyze_rewards_varied_sentence_openings(self) -> None:
        detail = PronounLeadRuleAnalyzer().analyze(
            chapter_text=(
                "灯油在盏里轻轻一爆，火苗偏向窗缝。"
                "袖口里的冷意先窜上来，她这才把手缩回去。"
                "门外有人咳了一声，半句问安卡在廊下。"
            )
        )

        self.assertGreaterEqual(detail.score, 8.0)
        self.assertIn("未检测到明显", detail.evidence_summary)


class ExplanationDensityRuleAnalyzerTests(unittest.TestCase):
    def test_analyze_penalizes_explanation_heavy_text(self) -> None:
        detail = ExplanationDensityRuleAnalyzer().analyze(
            chapter_text=(
                "她知道自己不能退。"
                "这让她更明白，今晚若开口，便再也回不去。"
                "他也意识到，她不是在装镇定。"
            )
        )

        self.assertLess(detail.score, 7.0)
        self.assertIn("解释句占比", detail.evidence_summary)

    def test_analyze_rewards_action_carried_revelation(self) -> None:
        detail = ExplanationDensityRuleAnalyzer().analyze(
            chapter_text=(
                "她把茶盏往前推了半寸，盏底在案上刮出一声轻响。"
                "他没接，只把袖中的婚书按平，指节却慢了一拍。"
            )
        )

        self.assertGreaterEqual(detail.score, 8.0)
        self.assertIn("未检测到明显解释句密度问题", detail.evidence_summary)


class ActionCarriedRevealRuleAnalyzerTests(unittest.TestCase):
    def test_rewards_action_and_object_led_scene(self) -> None:
        detail = ActionCarriedRevealRuleAnalyzer().analyze(
            chapter_text=(
                "雪光压在窗纸上，她把婚书往案角推了半寸。"
                "他没接，只看着那道被指节按出来的折痕。"
            )
        )

        self.assertGreaterEqual(detail.score, 7.0)
        self.assertIn("body_or_object_hits", detail.evidence_summary)


class RelationshipCostRealizationRuleAnalyzerTests(unittest.TestCase):
    def test_penalizes_procedure_without_human_cost(self) -> None:
        detail = RelationshipCostRealizationRuleAnalyzer().analyze(
            chapter_text=(
                "他先去核对案卷编号，又查司礼监挂号，再比对印鉴。"
                "流程走得很快，线索也更清楚了。"
            )
        )

        self.assertLess(detail.score, 7.0)
        self.assertIn("procedure_hits", detail.evidence_summary)


class ProseSurfaceSignalTests(unittest.TestCase):
    def test_surface_sentence_split_and_explanation_detection_are_not_character_level(self) -> None:
        surface = analyze_prose_surface(
            "她知道自己不能退。雪从檐角滑下来。"
            "他意识到她没说出口的话，比这场风还冷。"
        )

        self.assertEqual(surface.evidence["sentence_count"], 3)
        self.assertEqual(len(surface.evidence["explanation_sentences"]), 2)
        self.assertGreater(surface.explanation_ratio, 0.5)


if __name__ == "__main__":
    unittest.main()
