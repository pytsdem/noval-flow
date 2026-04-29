from __future__ import annotations

from datetime import datetime, timezone
import shutil
import unittest
from uuid import uuid4
from pathlib import Path

from evals.romance.case_exporter import HistoricalCaseExporter
from evals.romance.loader import load_cases, load_historical_cases
from novel_flow.models.schemas import (
    ActualChapterSummary,
    BookDocument,
    Chapter,
    ChapterBrief,
    CharacterCard,
    CharacterMindset,
    ContentBlock,
    StoryLine,
    StoryPremise,
    TwistDesign,
    Volume,
    WorkflowStage,
    WorkflowState,
)
from novel_flow.storage.sqlite_store import SQLiteStore


def _premise() -> StoryPremise:
    return StoryPremise(
        title="Return to Court",
        high_concept="A disgraced commander returns and clashes with the woman who condemned him.",
        theme_statement="Love and power both demand visible cost.",
        story_summary="He returns to court to reopen an old case while a forbidden attraction resurfaces.",
        genre="historical romance",
        target_style="restrained pressure",
        emotional_hook="Old hurt becomes dangerous attraction.",
        central_conflict="He wants justice but cannot attack openly.",
        core_hook="public return",
        escalation_path=["return", "pressure"],
        twist_blueprint=["she hid the truth"],
        ending_payoff="Their relationship is repriced.",
        selling_points=["court pressure"],
    )


def _twist() -> TwistDesign:
    return TwistDesign(
        twist_id="twist_01",
        title="Hidden motive",
        false_belief="Readers think she sold him out.",
        truth="She framed him to stop the emperor from killing him.",
        reader_alignment="Readers side with him.",
        seed_from="ch_001",
        reveal_at="ch_020",
        allowed_clues=["she hesitates"],
        forbidden_reveals=["do not reveal her motive"],
        pov_lock="No true inner thought before the reveal.",
        related_characters=["Lady Su"],
        payoff_effect="The relationship gets repriced.",
    )


def _line() -> StoryLine:
    return StoryLine(
        line_id="line_case",
        name="Old case",
        line_type="mystery",
        visibility="visible",
        core_question="How can he reopen the old case indirectly?",
        reader_hook_mode="pressure",
        start_state="He is blocked publicly.",
        midpoint_shift="A clue changes how readers see her.",
        end_state="The truth is re-evaluated.",
        carried_twists=["twist_01"],
        line_rules=["Only indirect investigation early."],
    )


def _brief(chapter_id: str = "ch_001") -> ChapterBrief:
    return ChapterBrief(
        chapter_id=chapter_id,
        title="Cold Return",
        chapter_type="opening",
        active_lines=["line_case"],
        active_twists=["twist_01"],
        summary="He returns under court pressure and tests her in public.",
        incoming_hook="He returned to the capital.",
        opening_hook="The order lands before he can breathe.",
        core_scene="He must kneel before her in the return ritual.",
        chapter_object="return certificate",
        reader_emotion="Readers should feel pressure and unresolved attraction.",
        reader_belief="Readers believe she betrayed him.",
        allowed_info=["He lost the old case."],
        allowed_clues=["She hesitates once."],
        forbidden=["Do not reveal her true motive."],
        world_limit="He cannot challenge the verdict publicly.",
        character_focus=["Hero", "Lady Su"],
        character_shift="He turns from raw anger to tactical restraint.",
        relationship_reprice="She feels less like a villain and more like a controlled threat.",
        emotional_turn="Hatred becomes dangerous restraint.",
        backstory_trigger="",
        scene_engine="opening_pressure",
        clue_reveal_mechanism={
            "style": "natural_exposure",
            "pressure_source": "court pressure",
            "surface_trigger": "the old case name",
            "first_noticer": "Hero",
            "owner_reaction": "Lady Su steadies the cup",
        },
        character_reentry_focus={"Lady Su": "Use controlled ritual behavior."},
        human_pain_anchor="He is forced to bow before he has even washed off the road dust.",
        romance_seed="She avoids his eyes too quickly.",
        small_payoff="He finds one legal angle.",
        ending_pull="The first witness is already dead.",
        info_budget="new_clues=1",
    )


def _block(chapter_id: str = "ch_001") -> ContentBlock:
    return ContentBlock(
        block_id=f"{chapter_id}.sc_001.b001",
        chapter_id=chapter_id,
        block_index=1,
        purpose="Open under public pressure.",
        characters=["Hero", "Lady Su"],
        active_lines=["line_case"],
        active_twists=["twist_01"],
        scene_goal="Land the ritual before he can act.",
        must_reveal=["He must bow in public."],
        must_hide=["Do not reveal her motive."],
        emotional_tone="Cold pressure",
        end_state="He decides to investigate indirectly.",
        human_reaction_target=["jaw tightens"],
        cost_shift="public humiliation",
        reader_feeling_target="Readers feel pressure and unresolved pull.",
        paragraph_budget="4-6",
        paragraph_shape=["tight", "readable"],
        micro_hook="Her fingers slip on the cup.",
        turn_type="pressure_rise",
        style_risk_guard=["avoid exposition"],
        text="He knelt, and the court watched the pause in her hand before she told him to rise.",
        status="committed",
        version=2,
    )


def _mindset() -> CharacterMindset:
    return CharacterMindset(
        character_id="hero",
        character_name="Hero",
        surface_emotion="cold restraint",
        core_emotion="injured anger",
        primary_goal="find one crack in the old case",
        hidden_need="see whether she regrets anything",
        fear="lose control in public",
        attitude_to_key_others={"Lady Su": "wants distance but watches her too closely"},
        self_control_level="high",
        breaking_point_hint="If she uses the wrong title, he will sharpen visibly.",
        known_but_unspoken="He cares too much about how she looks at him.",
        misbelief="He thinks all of her restraint is calculation.",
        chapter_change_hint="His certainty about her will weaken.",
    )


def _book(
    *,
    book_id: str = "book_export",
    missing_context: bool = False,
    include_chapter_mindsets: bool = True,
    include_stage_mindsets: bool = True,
) -> BookDocument:
    brief = _brief()
    block = _block()
    actual_summary = ActualChapterSummary(
        chapter_id="ch_001",
        actual_events=["He returns to court."],
        reader_now_knows=["The old verdict still stands."],
        reader_now_believes=["She betrayed him."],
        open_questions=["Why did she hesitate?"],
        character_states=["He is under public pressure."],
        relationship_state=["They act like ritual kin and hidden enemies."],
        seeded_clues=["She hesitates with the cup."],
        locked_truths=["Her real motive is hidden."],
        time_state={"chapter_end_time": "same day"},
    )
    writer_context_debug = {}
    if not missing_context:
        writer_context_debug = {
            "ch_001": {
                "chapter_payload_text": "sanitized chapter payload",
                "relationship_state_text": "ritual kin on the surface, enemies underneath",
                "scene_character_context_text": "Hero and Lady Su are both trapped by ritual.",
                "selection_summary_text": "selected active line and twist",
                "completed_chapter_memory_text": "no prior chapter",
                "step_1_story_foundation_text": "story foundation",
                "step_2_worldbuilding_text": "world rules",
                "step_3_character_packets_text": "character packets",
                "step_4_event_timeline_text": "event timeline",
                "step_5_character_milestones_text": "character milestones",
                "step_6_twists_text": "twist packets",
                "step_7_story_lines_text": "story line packets",
                "step_8_chapter_brief_text": "chapter contract packet",
                "timeline_anchor_facts_text": "same day, court hall",
                "relevant_world_rules_text": "No open challenge during the ritual.",
                "style_card_text": "restrained, pressure-heavy",
                "reference_pack": "reference pack",
                "writing_requirements_json": "{\"target_words\": 2800}",
                "assistant_persona_prompt": "Prioritize relationship movement over polish.",
                "previous_chapter_full_text": "",
            }
        }
    review_iteration = {
        "stage": "review_iteration_1",
        "tool_calls": ["review_continuity", "review_plot_logic"],
        "review_reports": {
            "review_continuity": {
                "passed": False,
                "level": "medium",
                "issues": [
                    {
                        "category": "continuity",
                        "severity": "medium",
                        "evidence": "The ending repeats the same threat twice.",
                        "reason": "It weakens the chapter pull.",
                        "fix": "Keep one threat line.",
                    }
                ],
                "rewrite_guidance": "Keep one threat line.",
            },
            "review_plot_logic": {
                "passed": False,
                "level": "high",
                "issues": [
                    {
                        "category": "plot_logic",
                        "severity": "high",
                        "evidence": "The ritual certificate does not constrain him enough.",
                        "reason": "The chapter object is underused.",
                        "fix": "Make the certificate visibly limit his behavior.",
                    }
                ],
                "rewrite_guidance": "Make the chapter object do double duty.",
            },
        },
        "final_judge": {
            "passed": False,
            "blocking_reasons": ["Continuity still weak.", "Plot logic remains high risk."],
            "metrics": {"continuity_passed": False, "plot_level": "high"},
        },
        "chapter_revision_plan": {"priority": ["ending_pull", "chapter_object"]},
        "dynamic_instruction": {"must_fix": ["keep one threat line"]},
    }
    stage_log = [
        {
            "stage": "plan_content_blocks",
            "block_count": 1,
            "blocks": [block.model_dump(mode="json")],
            "skill_ids": ["base_style"],
        }
    ]
    if include_stage_mindsets:
        stage_log.append(
            {
                "stage": "build_character_mindsets",
                "character_mindsets": [_mindset().model_dump(mode="json")],
            }
        )
    stage_log.extend(
        [
            review_iteration,
            {
                "stage": "rewrite_iteration_1",
                "chapter_length": 1200,
                "skill_ids": ["base_style"],
            },
        ]
    )
    metadata = {
        "story_blueprint": {
            "story_engine": {"world_rules": ["No open challenge during the ritual."]},
            "chapter_briefs": [brief.model_dump(mode="json")],
            "twist_designs": [_twist().model_dump(mode="json")],
            "story_lines": [_line().model_dump(mode="json")],
        },
        "character_milestones": [{"character_name": "Hero", "milestone_list": ["return"], "axes": ["pressure"]}],
        "writer_context_debug": writer_context_debug,
        "writing_chapter_runs": {
            "ch_001": {
                "content_blocks": [block.model_dump(mode="json")],
                "final_text": "He bowed in public, then threatened her once as he left the hall.",
                "final_version": 2,
                "review_reports": review_iteration["review_reports"],
                "final_judge": review_iteration["final_judge"],
                "stage_log": stage_log,
                "actual_chapter_summary": actual_summary.model_dump(mode="json"),
            }
        },
        "actual_chapter_summaries": [actual_summary.model_dump(mode="json")],
    }
    return BookDocument(
        id=book_id,
        title="Export Test",
        premise=_premise(),
        characters=[
            CharacterCard(name="Hero", role="returned commander", occupation="general"),
            CharacterCard(name="Lady Su", role="ritual matriarch", occupation="noblewoman"),
        ],
        volumes=[
            Volume(
                id="vol_001",
                title="Volume 1",
                summary="",
                chapters=[
                    Chapter(
                        id="ch_001",
                        title="Cold Return",
                        summary="He returns to court under pressure.",
                        content_blocks=[block],
                        character_mindsets=[_mindset()] if include_chapter_mindsets else [],
                        final_text="He bowed in public, then threatened her once as he left the hall.",
                        final_version=2,
                        is_finalized=True,
                    )
                ],
            )
        ],
        metadata=metadata,
    )


class EvalCaseExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_eval_case_exporter_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.db_path = self.root / "novel_flow.db"
        self.store = SQLiteStore(self.db_path)

    def _seed_run(
        self,
        *,
        run_id: str,
        missing_context: bool = False,
        updated_at: str | None = None,
        include_chapter_mindsets: bool = True,
        include_stage_mindsets: bool = True,
    ) -> str:
        book = _book(
            book_id=f"book_{run_id}",
            missing_context=missing_context,
            include_chapter_mindsets=include_chapter_mindsets,
            include_stage_mindsets=include_stage_mindsets,
        )
        self.store.save_book(book)
        state = WorkflowState(
            run_id=run_id,
            stage=WorkflowStage.COMPLETE,
            current_book_id=book.id,
            updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(timezone.utc),
        )
        self.store.save_workflow_state(state, mode="formal")
        self.store.save_run_output(
            run_id=run_id,
            agent="WritingChapterAgent",
            output_type="chapter_final_text",
            title="Final chapter text",
            payload={"chapter_id": "ch_001", "final_text": "He bowed in public."},
            created_at=state.updated_at.isoformat(),
        )
        self.store.save_run_output(
            run_id=run_id,
            agent="WritingChapterAgent",
            output_type="chapter_stage_log",
            title="Chapter stage log",
            payload={"chapter_id": "ch_001", "stage_log": book.metadata["writing_chapter_runs"]["ch_001"]["stage_log"]},
            created_at=state.updated_at.isoformat(),
        )
        return book.id

    def test_exporter_writes_standardized_case_and_replay_loader(self) -> None:
        self._seed_run(run_id="run_001")
        output_dir = self.root / "exported"
        summary = HistoricalCaseExporter(self.db_path).export(output_dir=output_dir, limit=1, sample_mode="latest")

        self.assertEqual(summary.exported_case_ids, ["ch_001_run_001"])
        historical_cases = load_historical_cases(output_dir)
        self.assertEqual(len(historical_cases), 1)
        case = historical_cases[0]
        self.assertEqual(case.inputs.chapter_payload, "sanitized chapter payload")
        self.assertEqual(case.intermediates.block_plan["block_count"], 1)
        self.assertEqual(case.outputs.final_status, "failed_partial")
        self.assertEqual(case.metrics.review_rounds, 1)
        self.assertEqual(case.metrics.patch_rounds, 1)
        self.assertFalse(case.metrics.used_full_rewrite)
        self.assertTrue(any(note.field == "metadata.mode" for note in case.export_notes))

        replay_cases = load_cases(output_dir)
        self.assertEqual(len(replay_cases), 1)
        self.assertEqual(replay_cases[0].case_id, "ch_001_run_001")
        self.assertEqual(replay_cases[0].title, "Cold Return")

    def test_exporter_marks_missing_fields_when_context_missing(self) -> None:
        self._seed_run(run_id="run_missing", missing_context=True)
        output_dir = self.root / "missing_export"
        HistoricalCaseExporter(self.db_path).export(output_dir=output_dir, limit=1, sample_mode="latest")
        case = load_historical_cases(output_dir)[0]
        warning_fields = {note.field for note in case.export_notes if note.level == "warning"}
        self.assertIn("inputs.sanitized_writer_context", warning_fields)

    def test_exporter_infers_character_mindsets_from_writer_context_when_persisted_data_missing(self) -> None:
        book_id = self._seed_run(
            run_id="run_inferred",
            include_chapter_mindsets=False,
            include_stage_mindsets=False,
        )
        book = self.store.load_book(book_id)
        self.assertIsNotNone(book)
        assert book is not None
        book.metadata["writer_context_debug"]["ch_001"].update(
            {
                "scene_character_context_text": "Hero: road-worn, outwardly cold restraint, watching every move. Lady Su: outwardly calm restraint, holding the ritual line under pressure.",
                "relationship_state_text": "Hero and Lady Su are ritual kin on the surface but hidden enemies underneath; Hero watches Lady Su too closely, while Lady Su hides strain behind etiquette.",
                "step_3_character_packets_text": "Hero: core goal is force one crack in the old case, outwardly cold restraint, carries dangerous attachment beneath anger. Lady Su: core goal is keep the ritual stable, outwardly calm restraint, hides strain behind etiquette and control.",
                "chapter_payload_text": "[Chapter payload]\nReader belief to preserve: Readers believe Lady Su betrayed Hero on purpose.",
            }
        )
        book.characters[0].initial_state = "He returned to court under pressure and cannot afford to lose control first."
        book.characters[0].motivation = "Surface: force one crack in the old case. Deeper: find out whether she regrets anything."
        book.characters[1].initial_state = "She is holding the ritual together and is most afraid of a public fracture."
        book.characters[1].motivation = "Surface: keep the ritual stable. Deeper: keep him alive long enough to leave the hall safely."
        self.store.save_book(book)

        output_dir = self.root / "inferred_export"
        HistoricalCaseExporter(self.db_path).export(output_dir=output_dir, limit=1, sample_mode="latest")
        case = load_historical_cases(output_dir)[0]

        self.assertEqual([item["character_name"] for item in case.inputs.character_mind_states], ["Hero", "Lady Su"])
        self.assertTrue(all(str(item["primary_goal"]).strip() for item in case.inputs.character_mind_states))
        self.assertTrue(all(str(item["hidden_need"]).strip() for item in case.inputs.character_mind_states))
        self.assertEqual(case.replay_case["prior_character_mindsets"][0]["character_name"], "Hero")
        self.assertTrue(
            any(
                note.field == "inputs.character_mind_states"
                and "inferred" in note.message.lower()
                for note in case.export_notes
            )
        )

    def test_low_score_sampling_prefers_riskier_run(self) -> None:
        self._seed_run(run_id="run_low", updated_at="2026-04-21T10:00:00+00:00")
        high_book_id = self._seed_run(run_id="run_high", updated_at="2026-04-21T11:00:00+00:00")
        book = self.store.load_book(high_book_id)
        self.assertIsNotNone(book)
        assert book is not None
        book.metadata["writing_chapter_runs"]["ch_001"]["final_judge"]["blocking_reasons"] = [
            "Continuity still weak.",
            "Plot logic remains high risk.",
            "Mind-state alignment is unclear.",
        ]
        book.metadata["writing_chapter_runs"]["ch_001"]["review_reports"]["review_instruction_compliance"] = {
            "passed": False,
            "level": "high",
            "issues": [
                {
                    "category": "instruction_violation",
                    "severity": "high",
                    "evidence": "Too many clues are exposed.",
                    "reason": "It breaks the information budget.",
                    "fix": "Keep one clue only.",
                }
            ],
        }
        self.store.save_book(book)

        output_dir = self.root / "risk_export"
        summary = HistoricalCaseExporter(self.db_path).export(output_dir=output_dir, limit=1, sample_mode="low_score")
        self.assertEqual(summary.exported_case_ids, ["ch_001_run_high"])


if __name__ == "__main__":
    unittest.main()
