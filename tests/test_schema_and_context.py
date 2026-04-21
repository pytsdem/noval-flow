from __future__ import annotations

import unittest

from pydantic import ValidationError

from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    ActualChapterSummary,
    ChapterBrief,
    CharacterCard,
    StoryLine,
    StoryPremise,
    TwistDesign,
)
from novel_flow.server import NovelApp
from novel_flow.services.chapter_context import ChapterContextAssembler
from novel_flow.services.character_context import CharacterContextBuilder
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.context_coverage import WriterContextCoverageValidator


class SequenceLLM(LLMClient):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[list[LLMMessage]] = []

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        self.calls.append(messages)
        if not self.outputs:
            raise AssertionError("No more fake outputs available")
        return self.outputs.pop(0)


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
        self.premise = StoryPremise(
            title="Return",
            high_concept="A disgraced heir returns with frontier merit.",
            theme_statement="Power and old debts reshape love.",
            story_summary="He returns to the capital to reopen an old wound through indirect means. She framed him to save him.",
            genre="historical romance",
            target_style="restrained pressure",
            emotional_hook="Old hatred under court pressure.",
            central_conflict="He wants revenge but cannot attack directly.",
            core_hook="Return to court",
            escalation_path=["Public return", "Indirect probing"],
            twist_blueprint=["Reader misreads the heroine early."],
            ending_payoff="Their relationship is re-priced.",
            selling_points=["Court pressure", "Emotional misreading"],
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
            premise=self.premise,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding={"story_engine": {"world_rules": ["Imperial verdict cannot be challenged publicly."]}},
            character_cards=[],
            character_milestones=[],
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
        self.assertIn("Hidden truth lock", text)
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
            premise=self.premise,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding={},
            character_cards=[],
            character_milestones=[],
            actual_summaries=[summary],
            current_chapter_id="ch_002",
        )
        self.assertIn("He returns to court.", context.completed_chapter_memory_text)

    def test_timeline_anchor_facts_are_pulled_into_writer_context(self) -> None:
        worldbuilding = {
            "event_timeline": [
                {
                    "event_id": "EVT_0016",
                    "title": "Hero is forced out of the capital",
                    "time_label": "景和七年冬—景和八年春（Hero 18—19岁）",
                    "description": "He is removed from succession and forced to leave the capital for the frontier.",
                    "trigger": "The court wants to cut him off from the center.",
                    "consequence": "He loses his place in the capital and enters frontier service.",
                    "affected_characters": ["Hero", "Heroine"],
                },
                {
                    "event_id": "EVT_0000",
                    "title": "Hero returns to the capital with frontier merit",
                    "time_label": "景和十二年春（Hero 23岁）",
                    "description": "He returns to the capital and publicly meets the heroine again. She framed him to save him.",
                    "trigger": "Five years of verifiable frontier service and military merit bring him back into court view.",
                    "consequence": "The old case regains public pressure and both characters are pushed back into conflict.",
                    "affected_characters": ["Hero", "Heroine"],
                },
            ]
        }
        raw_context = ChapterContextAssembler.build(
            chapter_brief=self.chapter_brief,
            premise=self.premise,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding=worldbuilding,
            character_cards=[
                CharacterCard(
                    name="Hero",
                    role="returned heir",
                    occupation="general",
                    personality="cold restraint",
                    behavior_pattern="acts after watching",
                    initial_state="He returns under pressure.",
                ),
                CharacterCard(
                    name="Heroine",
                    role="court witness",
                    occupation="noblewoman",
                    personality="controlled",
                    behavior_pattern="answers indirectly",
                    initial_state="She faces him again under public scrutiny.",
                ),
            ],
            character_milestones=[
                {
                    "character_name": "Hero",
                    "milestone_list": [{"axis": "复仇线", "stages": ["归京受压", "转向间接追查"]}],
                    "axes": [],
                },
                {
                    "character_name": "Heroine",
                    "milestone_list": [{"axis": "关系线", "stages": ["被误解", "关系重估"]}],
                    "axes": [],
                },
            ],
            actual_summaries=[],
            current_chapter_id="ch_001",
        )
        llm = SequenceLLM(
            [
                """{
  "chapter_id": "ch_001",
  "selection_summary_text": "[Selection]\\n- Relevant roles: Hero, Heroine\\n- Relevant twists: twist_01\\n- Relevant lines: line_case\\n- Current time anchor: return day, morning",
  "time_anchor_text": "[Time anchor]\\n- Absolute: return day, morning\\n- Relative to previous chapter: opening chapter\\n- Must not conflict: keep travel fatigue and return pressure visible.",
  "chapter_visible_context_text": "[Chapter visible context]\\n- Reader should know: he is back under pressure.\\n- Reader should believe: she betrayed him.\\n- Reader should not know: her true motive.\\n- Allowed clues: pause, avoid object.",
  "completed_chapter_memory_text": "[Completed chapter memory]\\nNo completed chapter summaries yet.",
  "step_1_story_foundation_text": "[Step 1 story foundation]\\n\\nTitle: Return\\nHigh concept: Preserve the surface conflict, pressure source, and reader misread without stating unrevealed truth.",
  "step_3_character_packets_text": "[Scene character context]\\n\\nHero\\n- Public identity: returned heir / general\\n- Surface goal in this chapter: He returns under pressure.",
  "step_5_character_milestones_text": "[Step 5 relevant character milestones]\\n\\nHeroine\\n- 关系线: 被误解 -> 关系重估\\n  - 关系线 / 被误解\\n    - Keep only visible trigger, pressure, and relationship movement for this phase.",
  "step_6_twists_text": "[Step 6 active twist packets]\\n\\ntwist_01 / Hidden motive\\n- False belief: Readers think she betrayed him.\\n- Reader alignment: Readers side with him before reveal.\\n- Seed from: ch_001\\n- Reveal at: ch_018\\n- Allowed clues: pause; avoid object\\n- Forbidden reveals: do not say she saved him; do not explain hidden motive\\n- POV lock: No true inner thought before reveal.\\n- Related characters: Heroine\\n- Payoff effect: Relationship gets re-priced after reveal.\\n- Truth: hidden until reveal chapter; do not narrate it directly.",
  "step_7_story_lines_text": "[Step 7 active story line packets]\\n\\nline_case / Old case\\n- Type: mystery\\n- Visibility: visible\\n- Core question: How to approach the old case indirectly\\n- Reader hook mode: pressure from rules\\n- Start state: He cannot challenge the verdict directly.\\n- Midpoint shift: Preserve the line's later re-pricing and payoff direction without stating concealed truth in advance.\\n- End state: Preserve the line's later re-pricing and payoff direction without stating concealed truth in advance.\\n- Carried twists: twist_01\\n- Line rules: Only indirect routes early.",
  "step_8_chapter_brief_text": "[Step 8 current chapter brief]\\n\\nChapter id: ch_001\\nTitle: Return\\nChapter type: opening\\nSummary: Hero wants revenge but must move indirectly.",
  "scene_character_context_text": "[Scene character context]\\n\\nHero\\n- Public identity: returned heir / general\\n- Surface goal in this chapter: He returns under pressure.",
  "relationship_state_text": "[Relationship state]\\n\\n- Relationship axis: She shifts from traitor to suspiciously controlled figure.\\n- Emotional temperature: Victory pressure becomes imperial pressure and cold hatred."
}"""
            ]
        )
        sanitizer = ContextSanitizationTask(llm_client=llm)
        context = sanitizer.sanitize_writer_context(
            writer_context=raw_context,
            current_chapter_id="ch_001",
            active_twists=[self.twist],
        )
        self.assertIn("Step 1 story foundation", context.step_1_story_foundation_text)
        self.assertNotIn(self.twist.truth, context.step_1_story_foundation_text)
        self.assertIn("Preserve the surface conflict, pressure source, and reader misread", context.step_1_story_foundation_text)
        self.assertIn("Step 4 full event timeline", context.step_4_event_timeline_text)
        self.assertIn(self.twist.truth, context.step_4_event_timeline_text)
        self.assertIn("Step 5 relevant character milestones", context.step_5_character_milestones_text)
        self.assertIn("Hero", context.step_3_character_packets_text)
        self.assertIn("Objective timeline anchors", context.timeline_anchor_facts_text)
        self.assertIn("forced out of the capital", context.timeline_anchor_facts_text)
        self.assertIn("returns to the capital", context.timeline_anchor_facts_text)
        self.assertIn("4 to 5 year(s)", context.timeline_anchor_facts_text)

    def test_coverage_validator_flags_missing_focus_milestones(self) -> None:
        issues = WriterContextCoverageValidator.validate(
            chapter_brief=self.chapter_brief,
            premise=self.premise,
            story_blueprint={
                "story_engine": {"world_rules": "Imperial verdict cannot be challenged publicly."},
                "event_timeline": [{"event_id": "EVT_1", "title": "Return"}],
                "twist_designs": [self.twist.model_dump(mode="json")],
                "story_lines": [self.line.model_dump(mode="json")],
            },
            character_cards=[CharacterCard(name="Hero", role="lead"), CharacterCard(name="Heroine", role="lead")],
            character_milestones=[{"character_name": "Hero", "milestone_list": [], "axes": []}],
        )
        self.assertTrue(any("step5" in issue for issue in issues))

    def test_context_sanitization_task_uses_llm_and_preserves_skipped_blocks(self) -> None:
        raw_context = ChapterContextAssembler.build(
            chapter_brief=self.chapter_brief,
            premise=self.premise,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding={
                "story_engine": {"world_rules": "Imperial verdict cannot be challenged publicly."},
                "event_timeline": [{"event_id": "EVT_001", "title": f"Timeline note {self.twist.truth}"}],
            },
            character_cards=[],
            character_milestones=[],
            actual_summaries=[],
            current_chapter_id="ch_001",
        )
        llm = SequenceLLM(
            [
                """{
  "chapter_id": "ch_001",
  "selection_summary_text": "[Selection]\\n- Relevant roles: Hero, Heroine\\n- Relevant twists: twist_01\\n- Relevant lines: line_case\\n- Current time anchor: return day, morning",
  "time_anchor_text": "[Time anchor]\\n- Absolute: return day, morning\\n- Relative to previous chapter: opening chapter\\n- Must not conflict: keep travel fatigue and return pressure visible.",
  "chapter_visible_context_text": "[Chapter visible context]\\n- Reader should know: he is back under pressure.\\n- Reader should believe: she betrayed him.\\n- Reader should not know: her true motive.\\n- Allowed clues: pause, avoid object.",
  "completed_chapter_memory_text": "[Completed chapter memory]\\nNo completed chapter summaries yet.",
  "step_1_story_foundation_text": "sanitized step1",
  "step_3_character_packets_text": "sanitized step3",
  "step_5_character_milestones_text": "sanitized step5",
  "step_6_twists_text": "sanitized step6",
  "step_7_story_lines_text": "sanitized step7",
  "step_8_chapter_brief_text": "sanitized step8",
  "scene_character_context_text": "sanitized scene context",
  "relationship_state_text": "sanitized relationship"
}"""
            ]
        )
        sanitizer = ContextSanitizationTask(llm_client=llm)
        context = sanitizer.sanitize_writer_context(
            writer_context=raw_context,
            current_chapter_id="ch_001",
            active_twists=[self.twist],
        )
        self.assertEqual(context.step_1_story_foundation_text, "sanitized step1")
        self.assertEqual(context.step_5_character_milestones_text, "sanitized step5")
        self.assertIn(self.twist.truth, context.step_4_event_timeline_text)
        self.assertIn("Imperial verdict cannot be challenged publicly.", context.step_2_worldbuilding_text)
        self.assertEqual(len(llm.calls), 1)

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
