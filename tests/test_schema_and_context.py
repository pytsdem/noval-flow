from __future__ import annotations

import unittest

from pydantic import ValidationError

from novel_flow.models.schemas import (
    ActualChapterSummary,
    ChapterBrief,
    CharacterCard,
    StoryLine,
    TwistDesign,
)
from novel_flow.server import NovelApp
from novel_flow.services.chapter_context import ChapterContextAssembler
from novel_flow.services.character_context import CharacterContextBuilder


class SchemaAndContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.twist = TwistDesign(
            twist_id="twist_01",
            title="Hidden motive",
            false_belief="Readers think she betrayed him.",
            truth="She framed him to save him.",
            reader_alignment="Readers side with him before reveal.",
            seed_from="ch_001",
            reveal_at="ch_018",
            allowed_clues=["pause", "avoid object"],
            forbidden_reveals=["do not say she saved him", "do not explain hidden motive"],
            pov_lock="No true inner thought before reveal.",
            related_characters=["Heroine"],
            payoff_effect="Relationship gets re-priced after reveal.",
        )
        self.line = StoryLine(
            line_id="line_case",
            name="Old case",
            line_type="mystery",
            visibility="visible",
            core_question="How to approach the old case indirectly",
            reader_hook_mode="pressure from rules",
            start_state="He cannot challenge the verdict directly.",
            midpoint_shift="A clue re-prices the relationship.",
            end_state="The truth is re-evaluated.",
            carried_twists=["twist_01"],
            line_rules=["Only indirect routes early."],
        )
        self.chapter_brief = ChapterBrief(
            chapter_id="ch_001",
            title="Return",
            chapter_type="opening",
            active_lines=["line_case"],
            active_twists=["twist_01"],
            summary="Hero wants revenge but must move indirectly.",
            incoming_hook="",
            opening_hook="A public imperial order lands at once.",
            chapter_object="Transfer register",
            reader_emotion="Readers side with him, hate her, and doubt her pause.",
            reader_belief="Readers believe she betrayed him.",
            allowed_info=["He lost everything in the old case."],
            allowed_clues=["She pauses at the old case term."],
            forbidden=["Do not explain her true motive."],
            world_limit="He cannot openly overturn the imperial verdict.",
            character_focus=["Hero", "Heroine"],
            character_shift="He turns from raw hatred to restrained action.",
            relationship_reprice="She shifts from traitor to suspiciously controlled figure.",
            emotional_turn="Victory pressure becomes imperial pressure and cold hatred.",
            backstory_trigger="",
            scene_engine="opening_pressure",
            small_payoff="He finds a legal indirect route.",
            ending_pull="The first witness is already dead.",
            info_budget="new clues=1",
        )

    def test_strict_models_reject_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            TwistDesign.model_validate({**self.twist.model_dump(mode="json"), "extra_field": "x"})

    def test_step_normalization_rejects_legacy_payloads(self) -> None:
        with self.assertRaises(ValueError):
            NovelApp._normalize_step_payload("step_7", {"story_lines": [], "chapter_briefs": []})
        with self.assertRaises(ValueError):
            NovelApp._normalize_step_payload("step_8", {"chapter_plans": []})

    def test_merge_story_blueprint_discards_relationship_network(self) -> None:
        merged = NovelApp._merge_story_blueprint(
            {"story_engine": {"engine_sentence": "old"}},
            {
                "relationship_network": [{"line_name": "legacy"}],
                "story_engine": {"world_rules": "rules"},
            },
        )
        self.assertNotIn("relationship_network", merged)
        self.assertEqual(merged["story_engine"]["engine_sentence"], "old")
        self.assertEqual(merged["story_engine"]["world_rules"], "rules")

    def test_server_no_longer_exposes_legacy_chapter_plan_generators(self) -> None:
        self.assertFalse(hasattr(NovelApp, "generate_formal_chapter_plans"))
        self.assertFalse(hasattr(NovelApp, "generate_formal_chapter_plans_batch"))

    def test_chapter_payload_masks_unrevealed_truth(self) -> None:
        context = ChapterContextAssembler.build(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding={"story_engine": {"world_rules": ["Imperial verdict cannot be challenged publicly."]}},
            character_cards=[],
            actual_summaries=[],
            current_chapter_id="ch_001",
        )
        self.assertIn("Readers believe she betrayed him.", context.chapter_payload_text)
        self.assertNotIn("She framed him to save him.", context.chapter_payload_text)
        self.assertIn("do not say she saved him", context.chapter_payload_text)

    def test_character_context_masks_hidden_motive(self) -> None:
        card = CharacterCard(
            name="Heroine",
            role="court witness",
            occupation="noblewoman",
            personality="calm and restrained",
            initial_state="She does not explain the past.",
            motivation="protect him from death",
            behavior_pattern="answers indirectly",
            arc="later she will reconcile",
        )
        text = CharacterContextBuilder.build(
            character_cards=[card],
            chapter_brief=self.chapter_brief,
            current_chapter_id="ch_001",
            active_twists=[self.twist],
            forbidden=self.chapter_brief.forbidden,
            scene_card=self._scene_card(),
            completed_chapter_memory_text="none",
        )
        self.assertIn("禁止写", text)
        self.assertNotIn("protect him from death", text)
        self.assertNotIn("reconcile", text)

    def test_completed_memory_comes_from_actual_summaries(self) -> None:
        summary = ActualChapterSummary(
            chapter_id="ch_001",
            actual_events=["He returns to court."],
            reader_now_knows=["The verdict is imperial."],
            reader_now_believes=["She betrayed him."],
            open_questions=["Why did she testify?"],
            character_states=["He must restrain himself."],
            relationship_state=["They meet again as enemies."],
            seeded_clues=["She pauses."],
            locked_truths=["Her true motive remains hidden."],
        )
        context = ChapterContextAssembler.build(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding={},
            character_cards=[],
            actual_summaries=[summary],
            current_chapter_id="ch_002",
        )
        self.assertIn("He returns to court.", context.completed_chapter_memory_text)

    @staticmethod
    def _scene_card():
        from novel_flow.models.schemas import SceneCard

        return SceneCard(
            scene_id="sc_001",
            purpose="Set up pressure",
            pov="Hero limited",
            location="court",
            visible_goal="observe reactions",
            obstacle="cannot challenge publicly",
            must_show=["restraint"],
            must_not_show=["truth"],
            reader_proxy="guard",
            proxy_function="asks why he cannot act directly",
            exit_state="He chooses indirect investigation",
        )


if __name__ == "__main__":
    unittest.main()
