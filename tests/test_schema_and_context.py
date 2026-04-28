from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from novel_flow.config import Settings
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    ActualChapterSummary,
    BookDocument,
    ChapterBrief,
    CharacterCard,
    CharacterCandidateLink,
    CharacterMindset,
    Chapter,
    ContentBlock,
    CriticReport,
    NewCharacterCandidate,
    StoryLine,
    StoryPremise,
    TwistDesign,
    Volume,
)
from novel_flow.server import NovelApp
from novel_flow.services.context_sanitization_task import ContextSanitizationTask
from novel_flow.services.context_coverage import WriterContextCoverageValidator
from novel_flow.services.chapter_tool_payloads import ChapterToolPayloadBuilder
from novel_flow.services.character_mindset_formatter import CharacterMindsetFormatter
from novel_flow.services.novel_context import NovelContextFormatter, NovelContextSelectorService
from novel_flow.services.selectors import (
    get_character_card_by_name,
    get_character_milestone_by_name,
)
from novel_flow.tools.plan_content_blocks import PlanContentBlocksTool


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
            core_scene="He must receive the order in public before he can reclaim any ground.",
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
            clue_reveal_style="natural_exposure",
            character_reentry_focus={"Heroine": "Use the room's restraint and her refusal to meet his eyes; do not restate who she is."},
            human_pain_anchor="He has to stand under public scrutiny before the dust of the road has even left his body.",
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

    def _snapshot(
        self,
        *,
        chapter_brief: ChapterBrief | None = None,
        worldbuilding: dict | None = None,
        character_cards: list[CharacterCard] | None = None,
        character_milestones: list[dict] | None = None,
        actual_summaries: list[ActualChapterSummary] | None = None,
        current_chapter_id: str = "ch_001",
    ):
        return NovelContextSelectorService.create_snapshot(
            chapter_brief=chapter_brief or self.chapter_brief,
            premise=self.premise,
            twist_designs=[self.twist],
            story_lines=[self.line],
            worldbuilding=worldbuilding or {},
            character_cards=character_cards or [],
            character_milestones=character_milestones or [],
            actual_summaries=actual_summaries or [],
            current_chapter_id=current_chapter_id,
        )

    def _writer_context(self, **snapshot_kwargs):
        selection = NovelContextSelectorService.select(
            snapshot=self._snapshot(**snapshot_kwargs),
            strategy="writer_context",
        )
        return NovelContextFormatter.format_writer_context(selection)

    def _scoped_steps(self, *, character_name: str, **snapshot_kwargs):
        selection = NovelContextSelectorService.select(
            snapshot=self._snapshot(**snapshot_kwargs),
            strategy="character_mindset_scoped_steps",
            character_name=character_name,
        )
        return NovelContextFormatter.format_character_mindset_scoped_steps(selection)

    def test_strict_models_reject_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            TwistDesign.model_validate({**self.twist.model_dump(mode="json"), "extra_field": "x"})

    def test_step_normalization_rejects_legacy_payloads(self) -> None:
        with self.assertRaises(ValueError):
            NovelApp._normalize_step_payload("step_7", {"story_lines": [], "chapter_briefs": []})
        with self.assertRaises(ValueError):
            NovelApp._normalize_step_payload("step_8", {"chapter_plans": []})

    def test_step8_input_payload_uses_explicit_sections(self) -> None:
        book = BookDocument(
            id="book_step8",
            title="Return",
            premise=self.premise,
            characters=[
                CharacterCard(
                    name="Hero",
                    role="returned heir",
                    occupation="general",
                    appearance="dust still on his cuffs",
                    personality="cold restraint",
                    motivation="reopen the old case",
                    behavior_pattern="cuts his own words short",
                ),
                CharacterCard(
                    name="Heroine",
                    role="court witness",
                    occupation="noblewoman",
                    appearance="sleeves held too steady",
                    personality="controlled silence",
                    motivation="protect a buried truth",
                    behavior_pattern="answers indirectly",
                ),
            ],
            metadata={
                "query": "写一部 120 章古言权谋误会文",
                "character_milestones": [{"character_name": "Hero", "milestone_list": [], "axes": []}],
                "story_blueprint": {
                    "story_engine": {
                        "world_rules": "Imperial verdicts cannot be overturned in public.",
                        "power_structure": "The court controls formal justice.",
                        "world_map": "Capital and frontier command route.",
                        "hook_strategy": "Open with direct court pressure.",
                    },
                    "event_timeline": [{"event_id": "evt_001", "title": "He was driven from the capital."}],
                    "twist_designs": [self.twist.model_dump(mode="json")],
                    "story_lines": [self.line.model_dump(mode="json")],
                    "chapter_briefs": [self.chapter_brief.model_dump(mode="json")],
                },
            },
        )

        batch = NovelApp._step8_batch_window(total_chapters=120, start_index=1, batch_size=1)
        payload = NovelApp._step8_input_payload(book, batch=batch, reference_pack="refs")

        self.assertEqual(payload["batch"]["chapter_ids"], ["ch_002"])
        self.assertEqual(payload["target_chapter_count"], 120)
        self.assertNotIn("planning_context_json", payload)
        self.assertIn("story_spine_json", payload)
        self.assertIn("worldbuilding_json", payload)
        self.assertIn("character_bible_json", payload)
        self.assertEqual(payload["twist_designs_json"][0]["twist_id"], "twist_01")
        self.assertEqual(payload["story_lines_json"][0]["line_id"], "line_case")
        self.assertEqual(payload["previous_chapter_briefs_json"][0]["chapter_id"], "ch_001")

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

    def test_run_preview_prefers_live_chapter_preview_output(self) -> None:
        preview = NovelApp._build_chapter_preview(
            outputs=[
                {
                    "output_type": "chapter_live_preview",
                    "payload": {
                        "chapter_id": "ch_002",
                        "chapter_title": "Cold Return",
                        "content_blocks": [{"block_id": "ch_002.sc_001.b001", "text": "first block"}],
                        "character_mindsets": [{"character_id": "Hero", "character_name": "Hero"}],
                        "final_text": "full rewrite preview",
                        "final_version": 2,
                        "is_finalized": False,
                        "preview_mode": "chapter_rewrite",
                    },
                }
            ],
            chapter_blocks=[
                {
                    "chapter_id": "ch_002",
                    "chapter_title": "Cold Return",
                    "payload": {"block_id": "legacy"},
                }
            ],
        )
        self.assertEqual(preview["chapter_id"], "ch_002")
        self.assertEqual(preview["final_text"], "full rewrite preview")
        self.assertEqual(preview["preview_mode"], "chapter_rewrite")
        self.assertEqual(len(preview["content_blocks"]), 1)
        self.assertEqual(len(preview["character_mindsets"]), 1)

    def test_delete_chapter_cleans_chapter_level_metadata(self) -> None:
        critic_ch1 = CriticReport(report_id="critic_ch1", summary="critic 1", issues=[]).model_dump(mode="json")
        critic_ch2 = CriticReport(report_id="critic_ch2", summary="critic 2", issues=[]).model_dump(mode="json")
        book = BookDocument(
            id="book_delete",
            title="Delete Test",
            premise=self.premise,
            characters=self.characters if hasattr(self, "characters") else [],
            volumes=[
                Volume(
                    id="vol_001",
                    title="Volume 1",
                    summary="",
                    chapters=[
                        Chapter(id="ch_001", title="One", summary="first"),
                        Chapter(id="ch_002", title="Two", summary="second"),
                    ],
                )
            ],
            metadata={
                "completed_chapter_ids": ["ch_001", "ch_002"],
                "last_written_chapter_id": "ch_002",
                "actual_chapter_summaries": [
                    {"chapter_id": "ch_001", "actual_events": ["first"]},
                    {"chapter_id": "ch_002", "actual_events": ["second"]},
                ],
                "latest_critic_report": critic_ch2,
                "critic_reports": {
                    "ch_001": {"aggregate": critic_ch1},
                    "ch_002": {"aggregate": critic_ch2},
                },
                "writing_chapter_runs": {"ch_001": {"final_text": "one"}, "ch_002": {"final_text": "two"}},
                "writer_context_debug": {"ch_001": {"ctx": 1}, "ch_002": {"ctx": 2}},
                "story_blueprint": {
                    "chapter_briefs": [
                        {"chapter_id": "ch_001"},
                        {"chapter_id": "ch_002"},
                        {"chapter_id": "ch_003"},
                    ]
                },
                "next_chapter_index": 2,
            },
        )

        class DummyStore:
            def __init__(self, book_doc: BookDocument) -> None:
                self.book = book_doc

            def load_book(self, book_id: str) -> BookDocument | None:
                return self.book if self.book.id == book_id else None

            def save_book(self, book_doc: BookDocument) -> None:
                self.book = book_doc

            def list_books(self) -> list[dict[str, str]]:
                return []

            def latest_run_for_book(self, book_id: str) -> None:
                return None

            def list_runs(self, *, book_id: str | None = None, limit: int = 50) -> list[dict[str, str]]:
                return []

            def load_latest_critic_report(self, book_id: str) -> CriticReport | None:
                return None

        store = DummyStore(book)
        app = NovelApp(SimpleNamespace(formal=store, test=store, settings=Settings()))
        result = app.delete_chapter("formal", book_id="book_delete", chapter_id="ch_002")
        updated = result["book"]
        self.assertEqual([item["chapter_id"] for item in updated["metadata"]["actual_chapter_summaries"]], ["ch_001"])
        self.assertEqual(updated["metadata"]["last_written_chapter_id"], "ch_001")
        self.assertEqual(updated["metadata"]["latest_critic_report"]["summary"], "critic 1")
        self.assertNotIn("ch_002", updated["metadata"]["critic_reports"])
        self.assertNotIn("ch_002", updated["metadata"]["writing_chapter_runs"])
        self.assertNotIn("ch_002", updated["metadata"]["writer_context_debug"])

    def test_get_novel_prefers_book_metadata_latest_critic(self) -> None:
        metadata_critic = CriticReport(report_id="critic_meta", summary="metadata critic", issues=[])
        store_critic = CriticReport(report_id="critic_store", summary="store critic", issues=[])
        book = BookDocument(
            id="book_novel",
            title="Novel",
            premise=self.premise,
            characters=[],
            volumes=[Volume(id="vol_001", title="Volume 1", summary="", chapters=[Chapter(id="ch_001", title="One", summary="")])],
            metadata={"latest_critic_report": metadata_critic.model_dump(mode="json")},
        )

        class DummyStore:
            def save_book(self, book_doc: BookDocument) -> None:
                self.book = book_doc

            def load_book(self, book_id: str) -> BookDocument | None:
                return book if book.id == book_id else None

            def latest_run_for_book(self, book_id: str) -> None:
                return None

            def list_runs(self, *, book_id: str | None = None, limit: int = 50) -> list[dict[str, str]]:
                return []

            def load_latest_critic_report(self, book_id: str) -> CriticReport | None:
                return store_critic

            def list_run_outputs(self, run_id: str) -> list[dict[str, str]]:
                return []

        store = DummyStore()
        app = NovelApp(SimpleNamespace(formal=store, test=store, settings=Settings()))
        result = app.get_novel("formal", "book_novel")
        self.assertEqual(result["critic"]["summary"], "metadata critic")

    def test_get_novel_prunes_stale_deleted_chapter_metadata(self) -> None:
        critic_payload = CriticReport(report_id="critic_stale", summary="stale critic", issues=[]).model_dump(mode="json")
        stale_store_critic = CriticReport(report_id="critic_store_stale", summary="store stale critic", issues=[])
        book = BookDocument(
            id="book_stale",
            title="Stale",
            premise=self.premise,
            characters=[],
            volumes=[],
            metadata={
                "actual_chapter_summaries": [{"chapter_id": "ch_001", "actual_events": ["stale"]}],
                "critic_reports": {"ch_001": {"aggregate": critic_payload}},
                "latest_critic_report": critic_payload,
                "writing_chapter_runs": {"ch_001": {"final_text": "stale"}},
                "writer_context_debug": {"ch_001": {"ctx": 1}},
                "scene_plans": {"ch_001": {"plan": 1}},
                "scene_only_characters": [{"candidate_id": "cand_1", "name": "Guest"}],
                "completed_chapter_ids": ["ch_001"],
                "last_written_chapter_id": "ch_001",
            },
        )

        class DummyStore:
            def __init__(self, book_doc: BookDocument) -> None:
                self.book = book_doc
                self.saved = 0

            def load_book(self, book_id: str) -> BookDocument | None:
                return self.book if self.book.id == book_id else None

            def save_book(self, book_doc: BookDocument) -> None:
                self.book = book_doc
                self.saved += 1

            def latest_run_for_book(self, book_id: str) -> None:
                return None

            def list_runs(self, *, book_id: str | None = None, limit: int = 50) -> list[dict[str, str]]:
                return []

            def load_latest_critic_report(self, book_id: str) -> CriticReport | None:
                return stale_store_critic

            def list_run_outputs(self, run_id: str) -> list[dict[str, str]]:
                return []

        store = DummyStore(book)
        app = NovelApp(SimpleNamespace(formal=store, test=store, settings=Settings()))
        result = app.get_novel("formal", "book_stale")
        self.assertEqual(store.saved, 1)
        self.assertEqual(result["book"]["metadata"]["actual_chapter_summaries"], [])
        self.assertEqual(result["book"]["metadata"]["critic_reports"], {})
        self.assertIsNone(result["book"]["metadata"]["latest_critic_report"])
        self.assertNotIn("scene_plans", result["book"]["metadata"])
        self.assertNotIn("planning_phase", result["book"]["metadata"])
        self.assertNotIn("style", result["book"]["metadata"])
        self.assertNotIn("blueprint_review", result["book"]["metadata"])
        self.assertNotIn("scene_only_characters", result["book"]["metadata"])
        self.assertIsNone(result["critic"])

    def test_resolve_character_candidate_adds_character_and_rejects_scene_only(self) -> None:
        candidate = NewCharacterCandidate(
            candidate_id="cand_001",
            name="Gate Keeper",
            first_appearance_chapter="ch_001",
            role_in_scene="守门人",
            why_needed="提供进入旧案现场的阻力",
            provisional_traits=["谨慎", "寡言"],
            links_to_existing_characters=[CharacterCandidateLink(target="Hero", relation="阻拦者")],
        )
        book = BookDocument(
            id="book_candidates",
            title="Candidates",
            premise=self.premise,
            characters=[],
            volumes=[],
            metadata={"new_character_candidates": [candidate.model_dump(mode="json")]},
        )

        class DummyStore:
            def __init__(self, book_doc: BookDocument) -> None:
                self.book = book_doc

            def load_book(self, book_id: str) -> BookDocument | None:
                return self.book if self.book.id == book_id else None

            def save_book(self, book_doc: BookDocument) -> None:
                self.book = book_doc

        store = DummyStore(book)
        app = NovelApp(SimpleNamespace(formal=store, test=store, settings=Settings()))

        result = app.resolve_character_candidate("formal", book_id="book_candidates", candidate_id="cand_001", action="add")
        updated = result["book"]
        self.assertEqual(updated["characters"][0]["name"], "Gate Keeper")
        self.assertEqual(updated["characters"][0]["role"], "守门人")
        self.assertEqual(updated["metadata"]["new_character_candidates"], [])

        store.book.metadata["new_character_candidates"] = [candidate.model_dump(mode="json")]
        with self.assertRaises(ValueError):
            app.resolve_character_candidate("formal", book_id="book_candidates", candidate_id="cand_001", action="scene_only")

    def test_chapter_payload_masks_unrevealed_truth(self) -> None:
        context = self._writer_context(
            worldbuilding={"story_engine": {"world_rules": ["Imperial verdict cannot be challenged publicly."]}},
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
        context = self._writer_context(character_cards=[card], current_chapter_id="ch_001")
        text = context.step_3_character_packets_text
        self.assertIn("Hidden truth lock", text)
        self.assertNotIn("protect him from death", text)
        self.assertNotIn("reconcile", text)

    def test_character_context_separates_scope_and_relationship_targets(self) -> None:
        card = CharacterCard(
            name="Hero",
            role="returned heir",
            occupation="general",
            personality="controlled restraint",
            initial_state="He cannot strike directly yet.",
            motivation="reopen the old case",
            behavior_pattern="cuts his own words short under pressure",
            arc="learn to trust her version later",
        )
        context = self._writer_context(character_cards=[card], current_chapter_id="ch_001")
        text = context.scene_character_context_text
        self.assertIn("Stable trait (book-level): controlled restraint", text)
        self.assertIn("Pressure behavior (scene-usable): cuts his own words short under pressure", text)
        self.assertIn("Current drive (chapter-facing): reopen the old case", text)
        self.assertIn("Visible scene task: He cannot strike directly yet.", text)
        self.assertNotIn("learn to trust her version later", text)
        self.assertIn("Current public read:", context.relationship_state_text)
        self.assertIn("Emotional pressure now:", context.relationship_state_text)
        self.assertIn("Target reprice this chapter:", context.relationship_state_text)

    def test_character_selectors_lookup_by_name(self) -> None:
        hero = CharacterCard(name="Hero", role="returned heir")
        heroine = CharacterCard(name="Heroine", role="court witness")
        milestones = [
            {
                "character_name": "Heroine",
                "character_card_name": "Heroine",
                "milestone_list": [{"axis": "情感线", "stages": ["压抑", "松动"]}],
                "axes": [],
            }
        ]
        self.assertIs(get_character_card_by_name([hero, heroine], "Heroine"), heroine)
        self.assertIs(get_character_milestone_by_name(milestones, "Heroine"), milestones[0])

    def test_character_milestone_context_uses_selector_lookup(self) -> None:
        scoped = self._scoped_steps(
            character_name="Heroine",
            character_milestones=[
                {
                    "character_name": "",
                    "character_card_name": "Heroine",
                    "milestone_list": [{"axis": "情感线", "stages": ["压抑", "松动"]}],
                    "axes": [],
                }
            ],
        )
        text = scoped.step_5_character_milestones_text
        self.assertIn("Heroine", text)
        self.assertIn("情感线: 压抑 -> 松动", text)

    def test_character_mindset_formatter_formats_text(self) -> None:
        text = CharacterMindsetFormatter.format_text(
            [
                CharacterMindset(
                    character_id="Hero",
                    character_name="Hero",
                    surface_emotion="冷",
                    core_emotion="痛",
                    primary_goal="查旧案",
                    hidden_need="被理解",
                    fear="再次失去",
                    attitude_to_key_others={"Heroine": "怀疑又在意"},
                    self_control_level="high",
                    breaking_point_hint="她再提旧案证词",
                    known_but_unspoken="她当年有难言之隐",
                    misbelief="她纯粹背叛了他",
                    chapter_change_hint="克制转为试探",
                )
            ]
        )
        self.assertIn("Hero / Hero", text)
        self.assertIn("Visible emotional mask: 冷", text)
        self.assertIn("Inner emotional driver: 痛", text)
        self.assertIn("Chapter tension: wants 查旧案; secretly needs 被理解; fears 再次失去", text)
        self.assertIn("Expected drift after this chapter: 克制转为试探", text)
        self.assertIn("Attitude to key others", text)
        self.assertIn("Heroine: 怀疑又在意", text)
        self.assertNotIn("Primary goal:", text)

    def test_chapter_tool_payload_builder_converges_writing_and_review_payloads(self) -> None:
        context = self._writer_context(current_chapter_id="ch_001")
        planned_blocks = [
            ContentBlock(
                block_id="ch_001.sc_001.b001",
                chapter_id="ch_001",
                block_index=1,
                purpose="open pressure",
                end_state="pressure lands",
            )
        ]
        plan_payload = ChapterToolPayloadBuilder.build_plan_content_blocks_payload(
            chapter_brief=self.chapter_brief,
            context=context,
        )
        write_payload = ChapterToolPayloadBuilder.build_write_chapter_full_payload(
            chapter_brief=self.chapter_brief,
            context=context,
            planned_blocks=planned_blocks,
        )
        review_payload = ChapterToolPayloadBuilder.build_chapter_review_payload(
            chapter_brief=self.chapter_brief,
            context=context,
            chapter_text="正文",
            planned_blocks=planned_blocks,
        )

        self.assertEqual(plan_payload["target_word_count_text"], self.chapter_brief.info_budget)
        self.assertIn("chapter_plan_json", write_payload)
        self.assertIn("step_1_to_7_outputs_json", write_payload)
        self.assertEqual(review_payload["chapter_text"], "正文")
        self.assertIn("twist_01", review_payload["active_twists_json"])

    def test_block_runtime_context_exposes_delivered_beat_summary(self) -> None:
        context = self._writer_context(current_chapter_id="ch_001")
        committed_blocks = [
            ContentBlock(
                block_id="ch_001.sc_001.b001",
                chapter_id="ch_001",
                block_index=1,
                purpose="open pressure",
                characters=["Hero"],
                active_lines=[],
                active_twists=[],
                scene_goal="Public pressure lands first.",
                must_reveal=[],
                must_hide=[],
                new_value="Readers feel the public trap activate.",
                relationship_delta="Distance turns public and costly.",
                clue_delta="None yet.",
                emotional_tone="tight",
                end_state="He has to answer in public.",
                micro_hook="He still has not touched the register.",
                text="第一块把公开压力压到他身上。",
                status="committed",
            )
        ]
        block = ContentBlock(
            block_id="ch_001.sc_001.b002",
            chapter_id="ch_001",
            block_index=2,
            purpose="Her pause changes the room.",
            end_state="The pause becomes legible.",
        )

        runtime_payload = ChapterToolPayloadBuilder.build_block_runtime_context(
            context=context,
            block=block,
            committed_blocks=committed_blocks,
        )

        self.assertIn("[Already delivered in this chapter]", runtime_payload["delivered_beat_summary_text"])
        self.assertIn("Readers feel the public trap activate.", runtime_payload["delivered_beat_summary_text"])
        self.assertIn("Distance turns public and costly.", runtime_payload["delivered_beat_summary_text"])
        self.assertIn("He still has not touched the register.", runtime_payload["delivered_beat_summary_text"])

    def test_plan_content_blocks_tool_enriches_blocks_into_beat_cards(self) -> None:
        context = self._writer_context(current_chapter_id="ch_001")
        payload = ChapterToolPayloadBuilder.build_plan_content_blocks_payload(
            chapter_brief=self.chapter_brief,
            context=context,
        )
        llm = SequenceLLM(
            [
                json.dumps(
                    {
                        "blocks": [
                            {
                                "block_id": "ch_001.sc_001.b009",
                                "chapter_id": "ch_001",
                                "block_index": 9,
                                "purpose": "Public pressure forces him to receive the order in full view.",
                                "end_state": "He has less room to recover before answering.",
                                "turn_type": "pressure_rise",
                            },
                            {
                                "block_id": "ch_001.sc_001.b010",
                                "chapter_id": "ch_001",
                                "block_index": 10,
                                "purpose": "He reaches for the register through a more expensive route.",
                                "end_state": "The chapter object becomes actionable at a social cost.",
                                "turn_type": "pressure_rise",
                            },
                            {
                                "block_id": "ch_001.sc_001.b011",
                                "chapter_id": "ch_001",
                                "block_index": 11,
                                "purpose": "Her pause makes the clue legible without explaining it.",
                                "end_state": "The room now reads the pause differently, but no one explains it.",
                                "turn_type": "clue_shift",
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ]
        )
        tool = PlanContentBlocksTool(llm_client=llm)

        result = tool.run(payload)
        blocks = result["blocks"]

        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["block_id"], "ch_001.sc_001.b001")
        self.assertEqual(blocks[2]["block_id"], "ch_001.sc_001.b003")
        self.assertEqual(blocks[0]["chapter_id"], "ch_001")
        self.assertEqual(blocks[1]["block_index"], 2)
        self.assertGreaterEqual(len(llm.calls), 1)

        for block in blocks:
            self.assertTrue(block["new_value"])
            self.assertTrue(block["must_not_repeat"])
            self.assertTrue(block["relationship_delta"])
            self.assertTrue(block["clue_delta"])
            self.assertTrue(block["must_land_in_action"])
            self.assertGreater(block["target_chars"], 0)
            self.assertLessEqual(block["target_chars"], 1200)
            self.assertIn("硬上限", block["paragraph_budget"])
            self.assertTrue(any("硬字数上限" in item for item in block["style_risk_guard"]))
            self.assertTrue(any("连续解规则" in item for item in block["must_not_repeat"]))

        self.assertIn("Readers newly feel the opening pressure", blocks[0]["new_value"])
        self.assertIn("不要", blocks[0]["must_not_repeat"][0])
        self.assertIn("关系", blocks[1]["relationship_delta"])
        self.assertIn("线索", blocks[2]["clue_delta"])

    def test_block_payloads_make_target_length_a_hard_ceiling(self) -> None:
        context = self._writer_context(current_chapter_id="ch_001")
        block_context = ChapterToolPayloadBuilder.build_block_runtime_context(
            context=context,
            block=ContentBlock(
                block_id="ch_001.sc_001.b001",
                chapter_id="ch_001",
                block_index=1,
                purpose="Pressure beat.",
                target_chars=500,
                end_state="The beat lands.",
            ),
            committed_blocks=[],
        )
        draft_payload = ChapterToolPayloadBuilder.build_draft_block_payload(
            block=ContentBlock(
                block_id="ch_001.sc_001.b001",
                chapter_id="ch_001",
                block_index=1,
                purpose="Pressure beat.",
                target_chars=500,
                end_state="The beat lands.",
            ),
            block_context=block_context,
            loaded_skill_instructions_text="",
        )
        polish_payload = ChapterToolPayloadBuilder.build_final_polish_payload(
            context=context,
            chapter_text="正文",
            loaded_skill_instructions_text="",
            chapter_brief=self.chapter_brief,
        )

        self.assertIn("Hard ceiling: 500", draft_payload["target_length"])
        self.assertIn("Stop immediately", draft_payload["target_length"])
        self.assertIn("Hard ceiling", polish_payload["target_length"])
        self.assertIn("shorten", polish_payload["target_length"])

    def test_plan_content_blocks_default_count_keeps_5000_char_chapter_to_four_beats(self) -> None:
        self.assertEqual(PlanContentBlocksTool._target_block_count("3000字左右"), 3)
        self.assertEqual(PlanContentBlocksTool._target_block_count("5000字"), 4)
        self.assertEqual(PlanContentBlocksTool._target_block_count("target=4000-5500"), 4)
        self.assertEqual(PlanContentBlocksTool._target_block_count("target=5500-7000"), 5)
        self.assertEqual(PlanContentBlocksTool._target_block_count("8000字"), 6)
        self.assertEqual(PlanContentBlocksTool._target_block_count("new clues=1", fallback_count=4), 4)

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
        context = self._writer_context(actual_summaries=[summary], current_chapter_id="ch_002")
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
        raw_context = self._writer_context(
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
        raw_context = self._writer_context(
            worldbuilding={
                "story_engine": {"world_rules": "Imperial verdict cannot be challenged publicly."},
                "event_timeline": [{"event_id": "EVT_001", "title": f"Timeline note {self.twist.truth}"}],
            },
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
