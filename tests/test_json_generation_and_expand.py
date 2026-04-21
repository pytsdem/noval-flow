from __future__ import annotations

import unittest

from novel_flow.agents.writer import WriterAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    BookBlueprint,
    BookDocument,
    Chapter,
    ChapterBrief,
    CharacterCard,
    PatchOperation,
    Scene,
    StoryPremise,
    TextBlock,
    TwistDesignsPayload,
    Volume,
)
from novel_flow.services.patcher import PatchExecutor
from novel_flow.utils.json_generation import safe_json_generate


class SequenceLLM(LLMClient):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[float] = []

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        self.calls.append(temperature)
        if not self.outputs:
            raise AssertionError("No more fake outputs available")
        return self.outputs.pop(0)


class JsonGenerationAndExpandTests(unittest.TestCase):
    def test_safe_json_generate_repairs_and_validates(self) -> None:
        llm = SequenceLLM(
            [
                '{"twist_designs": [{"twist_id": "twist_01"}]}',
                '{"twist_designs": [{"twist_id": "twist_01", "title": "", "false_belief": "", "truth": "", "reader_alignment": "", "seed_from": "ch_001", "reveal_at": "ch_001", "allowed_clues": [], "forbidden_reveals": [], "pov_lock": "", "related_characters": [], "payoff_effect": ""}]}',
            ]
        )
        payload = safe_json_generate(
            llm,
            [LLMMessage(role="user", content="test")],
            schema_name="twist_designs",
            schema_model=TwistDesignsPayload,
        )
        self.assertEqual(payload["twist_designs"][0]["twist_id"], "twist_01")
        self.assertEqual(llm.calls, [0.2, 0.0])

    def test_expand_replaces_instead_of_appending(self) -> None:
        llm = SequenceLLM(["Expanded replacement paragraph."])
        writer = WriterAgent(llm_client=llm, patch_executor=PatchExecutor())
        book = self._book_with_minimum_new_structure()
        updated = writer.expand(book=book, block_id="ch_001.sc_001.b001", expansion_goal="add tension")
        block = updated.volumes[0].chapters[0].scenes[0].blocks[0]
        self.assertEqual(block.text, "Expanded replacement paragraph.")
        self.assertNotIn("Original paragraph.", block.text)

    def test_writer_create_book_does_not_seed_legacy_chapter_plans(self) -> None:
        premise = StoryPremise(
            title="Test",
            high_concept="hc",
            story_summary="",
            genre="genre",
            target_style="style",
            emotional_hook="hook",
            central_conflict="conflict",
            core_hook="core",
        )
        blueprint = BookBlueprint(
            blueprint_id="bp_002",
            premise=premise,
            characters=[CharacterCard(name="Hero", role="general")],
            volume_titles=["Volume 1"],
            chapter_plans=[],
        )
        writer = WriterAgent(llm_client=SequenceLLM([]), patch_executor=PatchExecutor())
        book = writer.create_book(blueprint=blueprint, source_query="query")
        self.assertNotIn("chapter_plans", book.metadata)

    @staticmethod
    def _book_with_minimum_new_structure() -> BookDocument:
        premise = StoryPremise(
            title="Test",
            high_concept="hc",
            story_summary="",
            genre="genre",
            target_style="style",
            emotional_hook="hook",
            central_conflict="conflict",
            core_hook="core",
        )
        blueprint = BookBlueprint(
            blueprint_id="bp_001",
            premise=premise,
            characters=[CharacterCard(name="Hero", role="general")],
            volume_titles=["Volume 1"],
            chapter_plans=[],
        )
        writer = BookDocument(
            id="book_001",
            title="Test",
            premise=blueprint.premise,
            characters=blueprint.characters,
            volumes=[
                Volume(
                    id="vol_001",
                    title="Volume 1",
                    summary="",
                    chapters=[
                        Chapter(
                            id="ch_001",
                            title="Chapter 1",
                            summary="summary",
                            scenes=[
                                Scene(
                                    id="ch_001.sc_001",
                                    title="Scene 1",
                                    summary="scene summary",
                                    blocks=[TextBlock(id="ch_001.sc_001.b001", text="Original paragraph.", purpose="paragraph")],
                                )
                            ],
                        )
                    ],
                )
            ],
            metadata={
                "story_blueprint": {
                    "twist_designs": [
                        {
                            "twist_id": "twist_01",
                            "title": "Hidden motive",
                            "false_belief": "Readers think betrayal was real.",
                            "truth": "Hidden author truth.",
                            "reader_alignment": "Side with hero early.",
                            "seed_from": "ch_001",
                            "reveal_at": "ch_018",
                            "allowed_clues": ["pause"],
                            "forbidden_reveals": ["do not reveal truth"],
                            "pov_lock": "No true inner thought.",
                            "related_characters": ["Hero"],
                            "payoff_effect": "Relationship re-priced.",
                        }
                    ],
                    "story_lines": [
                        {
                            "line_id": "line_case",
                            "name": "Case line",
                            "line_type": "mystery",
                            "visibility": "visible",
                            "core_question": "How to investigate indirectly",
                            "reader_hook_mode": "pressure",
                            "start_state": "blocked",
                            "midpoint_shift": "reprice",
                            "end_state": "resolved",
                            "carried_twists": ["twist_01"],
                            "line_rules": ["indirect only"],
                        }
                    ],
                    "chapter_briefs": [
                        ChapterBrief(
                            chapter_id="ch_001",
                            title="Return",
                            chapter_type="opening",
                            active_lines=["line_case"],
                            active_twists=["twist_01"],
                            summary="He wants revenge but must act indirectly.",
                            incoming_hook="",
                            opening_hook="An imperial order lands immediately.",
                            core_scene="He is forced to accept the order in public before he can act.",
                            chapter_object="Transfer register",
                            reader_emotion="Readers side with him and suspect her.",
                            reader_belief="Readers believe she betrayed him.",
                            allowed_info=["He lost everything in the case."],
                            allowed_clues=["A brief pause."],
                            forbidden=["Do not reveal the true motive."],
                            world_limit="He cannot challenge the verdict publicly.",
                            character_focus=["Hero"],
                            character_shift="He restrains himself.",
                            relationship_reprice="A known enemy becomes more suspicious.",
                            emotional_turn="Pride turns into pressure.",
                            backstory_trigger="",
                            scene_engine="opening_pressure",
                            clue_reveal_style="natural_exposure",
                            character_reentry_focus={"Heroine": "Use the room's reaction to bring her back; do not re-introduce her identity."},
                            human_pain_anchor="He must keep his body controlled while being publicly pinned in place.",
                            small_payoff="A legal route appears.",
                            ending_pull="A witness is dead.",
                            info_budget="new clues=1",
                        ).model_dump(mode="json")
                    ],
                }
            },
        )
        return writer


if __name__ == "__main__":
    unittest.main()
