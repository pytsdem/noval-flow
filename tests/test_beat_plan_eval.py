from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from evals.romance.beat_plan_eval import BeatPlanEvalRunner
from tests.test_romance_eval_harness import SequenceLLM, _case_payload, _sanitized_context_json


def _beat(
    *,
    index: int,
    purpose: str,
    scene_goal: str,
    new_value: str,
    relationship_delta: str,
    clue_delta: str,
    end_state: str,
    micro_hook: str,
    turn_type: str,
    must_not_repeat: list[str] | None = None,
) -> dict[str, object]:
    return {
        "block_id": f"ch_002.sc_001.b{index:03d}",
        "chapter_id": "ch_002",
        "block_index": index,
        "purpose": purpose,
        "characters": ["Hero", "Heroine"],
        "active_lines": ["line_case"],
        "active_twists": ["twist_01"],
        "scene_goal": scene_goal,
        "must_reveal": [scene_goal],
        "must_hide": ["Do not reveal her true motive."],
        "new_value": new_value,
        "must_not_repeat": must_not_repeat or ["Do not restate the previous beat's relationship judgment."],
        "relationship_delta": relationship_delta,
        "clue_delta": clue_delta,
        "must_land_in_action": ["Land the beat through action and consequence."],
        "emotional_tone": "Pressure with unresolved attraction.",
        "end_state": end_state,
        "human_reaction_target": ["Show one bodily or social reaction."],
        "cost_shift": "Progress costs public exposure.",
        "reader_feeling_target": "Readers should feel the pressure getting tighter.",
        "paragraph_budget": "2-4 paragraphs",
        "target_chars": 420,
        "paragraph_shape": ["main action", "reaction", "cost"],
        "micro_hook": micro_hook,
        "turn_type": turn_type,
        "character_anchor_line": None,
        "style_risk_guard": ["Do not turn the beat into summary prose."],
        "character_reentry_mode": None,
        "clue_reveal_mechanism": None,
        "text": "",
        "status": "draft",
        "version": 1,
    }


def _planned_beats_json(*, overlap: bool) -> str:
    blocks = [
        _beat(
            index=1,
            purpose="Open with public pressure.",
            scene_goal="The order lands before he can recover.",
            new_value="The chapter starts with public pressure, not private recollection.",
            relationship_delta="They move from distant hostility into immediate public collision.",
            clue_delta="No fresh clue yet; the pressure is what changes.",
            end_state="He must answer before he can regain his footing.",
            micro_hook="He has to answer under witness eyes.",
            turn_type="pressure_rise",
            must_not_repeat=["Do not retell the return-to-capital background."],
        ),
        _beat(
            index=2,
            purpose="Push the chapter object into negotiation.",
            scene_goal="The transfer register becomes actionable through live pressure.",
            new_value=(
                "The register becomes actionable through a humiliating procedural opening."
                if not overlap
                else "The chapter starts with public pressure, not private recollection."
            ),
            relationship_delta=(
                "Hostility turns into procedural testing because he needs her cooperation."
                if not overlap
                else "They move from distant hostility into immediate public collision."
            ),
            clue_delta=(
                "The chapter object enters the scene without revealing the deeper truth."
                if not overlap
                else "No fresh clue yet; the pressure is what changes."
            ),
            end_state=(
                "He wins one narrow path, but it costs him more public exposure."
                if not overlap
                else "He must answer before he can regain his footing."
            ),
            micro_hook="The same order that humiliates him is now his only path forward.",
            turn_type="clue_shift",
            must_not_repeat=["Do not replay the opening public-pressure beat."],
        ),
        _beat(
            index=3,
            purpose="Turn her controlled reaction into a clue.",
            scene_goal="Her over-controlled response becomes meaningful on page.",
            new_value="Her reaction stops feeling empty and starts feeling suspicious.",
            relationship_delta="His anger now carries doubt because her restraint feels too precise.",
            clue_delta="A pause around the old-case term becomes a usable clue.",
            end_state="He reads her reaction as evidence instead of pure insult.",
            micro_hook="Her pause says more than the order did.",
            turn_type="emotional_slip",
            must_not_repeat=["Do not restate the procedural opening from the prior beat."],
        ),
        _beat(
            index=4,
            purpose="Cut to the chapter-end hook.",
            scene_goal="Turn the investigation opening into a sharper next-step threat.",
            new_value="The chapter ends with a harder investigation cut than the one it opened with.",
            relationship_delta="They are now bound by a clue that makes separation harder.",
            clue_delta="The first witness is already dead before the next move can begin.",
            end_state="The path opens and then immediately narrows into a worse problem.",
            micro_hook="The first witness is already dead.",
            turn_type="withheld_answer",
            must_not_repeat=["Do not summarize the previous beats before cutting to the hook."],
        ),
    ]
    return json.dumps({"blocks": blocks}, ensure_ascii=False)


class BeatPlanEvalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_beat_plan_eval_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write_case(self, case_id: str) -> Path:
        case_dir = self.root / "cases"
        case_dir.mkdir(exist_ok=True)
        payload = _case_payload(case_id)
        payload["chapter_brief"]["info_budget"] = "target=4200-4800"
        payload["context_overrides"]["writing_requirements"]["target_words"] = "4200-4800"
        path = case_dir / f"{case_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return case_dir

    def test_runner_generates_real_beat_plan_and_reports_metrics(self) -> None:
        case_dir = self._write_case("case_plan_clean")
        llm = SequenceLLM([
            _sanitized_context_json(),
            _planned_beats_json(overlap=False),
        ])

        summary = BeatPlanEvalRunner(llm_client=llm, reports_root=self.root / "reports").run(
            cases_dir=case_dir,
            label="beat_plan_clean",
        )

        run_dir = Path(summary.run_dir)
        self.assertTrue((run_dir / "beat_plan_eval_summary.json").exists())
        self.assertTrue((run_dir / "beat_plan_eval_report.md").exists())
        self.assertTrue((run_dir / "summary.json").exists())
        self.assertEqual(summary.case_ids, ["case_plan_clean"])
        report = summary.case_reports[0]
        self.assertEqual(report.cost_metrics.context_llm_calls, 1)
        self.assertEqual(report.cost_metrics.planning_llm_calls, 1)
        self.assertEqual(report.beat_count, 4)
        self.assertEqual(report.target_beat_count, 4)
        self.assertIn("contract_coverage_score", report.metrics)
        self.assertEqual(report.overlap_alerts, [])
        self.assertGreater(report.metrics["contract_coverage_score"].score, 7.5)
        self.assertGreater(report.metrics["adjacent_separation_score"].score, 7.0)

    def test_runner_flags_overlapping_beats(self) -> None:
        case_dir = self._write_case("case_plan_overlap")
        llm = SequenceLLM([
            _sanitized_context_json(),
            _planned_beats_json(overlap=True),
        ])

        summary = BeatPlanEvalRunner(llm_client=llm, reports_root=self.root / "reports").run(
            cases_dir=case_dir,
            label="beat_plan_overlap",
        )

        report = summary.case_reports[0]
        self.assertNotEqual(report.verdict, "pass")
        self.assertTrue(report.overlap_alerts)
        self.assertLess(report.metrics["beat_uniqueness_score"].score, 7.0)
        self.assertLess(report.metrics["adjacent_separation_score"].score, 7.0)


if __name__ == "__main__":
    unittest.main()
