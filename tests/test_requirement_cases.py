from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from evals.romance.loader import load_case
from evals.romance.requirement_cases import load_requirement_case, seed_requirement_cases
from novel_flow.storage.sqlite_store import SQLiteStore
from tools.seed_self_improve_cases import main as seed_main


def _eval_fixture_payload(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "title": f"{case_id} fixture",
        "description": "Requirement-backed romance fixture.",
        "tags": ["test"],
        "premise": {
            "title": "Fixture Novel",
            "high_concept": "Two leads reunite under pressure.",
            "theme_statement": "Trust changes under pressure.",
            "story_summary": "A reunion drives both plot and romance tension.",
            "genre": "historical romance",
            "target_style": "restrained",
            "emotional_hook": "Old hurt meets unresolved pull.",
            "central_conflict": "They need each other while mistrusting each other.",
            "core_hook": "A public reunion exposes the old wound.",
            "escalation_path": ["reunion", "pressure"],
            "twist_blueprint": ["misread motive"],
            "ending_payoff": "The relationship is repriced.",
            "selling_points": ["chemistry"],
        },
        "chapter_brief": {
            "chapter_id": "ch_001",
            "title": "Public Return",
            "chapter_type": "opening",
            "active_lines": ["line_a"],
            "active_twists": ["twist_a"],
            "summary": "He returns and finds her waiting in public view.",
            "incoming_hook": "He returned to the capital.",
            "opening_hook": "She lifts her eyes before he speaks.",
            "core_scene": "They meet under heavy public pressure.",
            "chapter_object": "old registry",
            "reader_emotion": "Pressure and attraction should coexist.",
            "reader_belief": "Readers believe she betrayed him.",
            "allowed_info": ["He is back."],
            "allowed_clues": ["She hesitates."],
            "forbidden": ["Do not reveal the truth."],
            "world_limit": "He cannot challenge the verdict publicly.",
            "character_focus": ["Lead A", "Lead B"],
            "character_shift": "Anger turns into colder curiosity.",
            "relationship_reprice": "She stops feeling like a simple traitor.",
            "emotional_turn": "Public hostility turns into strategic tension.",
            "backstory_trigger": "",
            "scene_engine": "opening_pressure",
            "clue_reveal_mechanism": {
                "style": "natural_exposure",
                "pressure_source": "court pressure",
                "surface_trigger": "old case term",
                "first_noticer": "Lead A",
                "owner_reaction": "Lead B avoids explaining",
            },
            "character_reentry_focus": {
                "Lead B": "Use restraint to re-establish presence.",
            },
            "human_pain_anchor": "He stands in road dust before the whole court.",
            "romance_seed": "She looks away too quickly.",
            "small_payoff": "He gets one procedural opening.",
            "ending_pull": "The first witness dies before dawn.",
            "info_budget": "target=2800-3400",
        },
        "twist_designs": [
            {
                "twist_id": "twist_a",
                "title": "Hidden motive",
                "false_belief": "She betrayed him.",
                "truth": "She acted to save him.",
                "reader_alignment": "Readers side with him first.",
                "seed_from": "ch_001",
                "reveal_at": "ch_018",
                "allowed_clues": ["She pauses once."],
                "forbidden_reveals": ["Do not reveal the rescue yet."],
                "pov_lock": "No full motive before the reveal.",
                "related_characters": ["Lead B"],
                "payoff_effect": "The relationship gets repriced.",
            }
        ],
        "story_lines": [
            {
                "line_id": "line_a",
                "name": "Old case",
                "line_type": "mystery",
                "visibility": "visible",
                "core_question": "How can he reopen the old case indirectly?",
                "reader_hook_mode": "pressure",
                "start_state": "He is blocked publicly.",
                "midpoint_shift": "A clue changes how readers judge her.",
                "end_state": "The truth is re-evaluated.",
                "carried_twists": ["twist_a"],
                "line_rules": ["Only indirect routes early."],
            }
        ],
        "character_cards": [
            {
                "name": "Lead A",
                "role": "dismissed commander",
                "occupation": "former general",
                "appearance": "travel dust on his cuffs",
                "personality": "controlled under pressure",
                "initial_state": "He wants revenge but cannot act directly.",
                "motivation": "Reopen the old case.",
                "behavior_pattern": "Cuts his own words short.",
                "relationships": "Hostile unresolved history with Lead B",
            },
            {
                "name": "Lead B",
                "role": "court witness",
                "occupation": "archivist",
                "appearance": "sleeves held too steady",
                "personality": "calm and restrained",
                "initial_state": "She does not explain the past.",
                "motivation": "Protect a secret.",
                "behavior_pattern": "Answers indirectly.",
                "relationships": "Hostile unresolved history with Lead A",
            },
        ],
        "worldbuilding": {
            "story_engine": {
                "world_rules": ["The verdict cannot be challenged publicly."],
            }
        },
        "character_milestones": [],
        "actual_chapter_summaries": [],
        "prior_character_mindsets": [],
        "goals": {
            "chapter_goal": "Push the old case and the reunion pressure.",
            "emotional_goal": "Land public humiliation plus unresolved attraction.",
            "relationship_goal": "Move them from hostility to dangerous calculation.",
            "hook_goal": "Open with public pressure and end on a harder clue.",
            "continuation_drive": "Make the reader want the next beat.",
        },
        "context_overrides": {
            "assistant_persona_prompt": "Prioritize relationship movement over polish.",
            "writing_requirements": {"target_words": "2800-3400"},
            "reference_pack": "test references",
            "previous_chapter_full_text": "He returned. She heard his name and did not sleep.",
            "scene_character_context_text": "[Scene character context]\\nBoth leads are under pressure.",
            "relationship_state_text": "[Relationship state]\\nHostility with unresolved pull.",
        },
    }


def _requirement_case_payload(case_id: str, *, book_id: str, query: str = "古言言情，双强误读重逢。") -> dict[str, object]:
    return {
        "case_id": case_id,
        "case_type": "self_improve_requirement_case",
        "title": f"{case_id} requirement",
        "description": "Seed this into the test DB for self-improve runs.",
        "tags": ["self_improve_test_case"],
        "user_input": {
            "title": "测试小说",
            "query": query,
            "style_request": "克制古言言情",
            "user_topic": "误读重逢",
            "assistant_persona_prompt": "你在写高张力古言言情。",
        },
        "self_improve_binding": {
            "book_id": book_id,
            "mode": "test",
            "db_path": "data/novel_flow_test.db",
            "entry_stage": "step",
            "checkpoint_chapters": [1, 2, 3, 4, 5],
            "is_self_improve_test_case": True,
        },
        "eval_fixture": _eval_fixture_payload(case_id),
    }


class RequirementCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("data") / f"test_requirement_cases_{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.case_dir = self.root / "cases"
        self.case_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_loader_reads_requirement_case_and_nested_eval_fixture(self) -> None:
        case_path = self.case_dir / "case.json"
        case_path.write_text(
            json.dumps(_requirement_case_payload("case_requirement", book_id="book_case_requirement"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        requirement_case = load_requirement_case(case_path)
        eval_case = load_case(case_path)

        self.assertEqual(requirement_case.case_id, "case_requirement")
        self.assertEqual(requirement_case.self_improve_binding.book_id, "book_case_requirement")
        self.assertEqual(requirement_case.user_input.title, "测试小说")
        self.assertEqual(eval_case.case_id, "case_requirement")
        self.assertEqual(eval_case.chapter_brief.chapter_id, "ch_001")

    def test_seed_requirement_cases_creates_bound_test_book(self) -> None:
        case_path = self.case_dir / "seed_case.json"
        case_path.write_text(
            json.dumps(_requirement_case_payload("case_seed", book_id="book_seed_case", query="古言言情，雨夜药庐共处。"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        db_path = self.root / "novel_flow_test.db"

        seeded = seed_requirement_cases(db_path=db_path, case_dir=self.case_dir)

        self.assertEqual(seeded[0]["book_id"], "book_seed_case")
        store = SQLiteStore(db_path)
        book = store.load_book("book_seed_case")
        self.assertIsNotNone(book)
        assert book is not None
        self.assertEqual(book.title, "测试小说")
        self.assertEqual(book.metadata["query"], "古言言情，雨夜药庐共处。")
        self.assertTrue(book.metadata["self_improve_test_case"])
        self.assertEqual(book.metadata["self_improve_case_id"], "case_seed")
        self.assertEqual(book.metadata["self_improve_binding"]["book_id"], "book_seed_case")

    def test_seed_tool_writes_registry_file(self) -> None:
        case_path = self.case_dir / "tool_case.json"
        case_path.write_text(
            json.dumps(_requirement_case_payload("case_tool", book_id="book_tool_case"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        db_path = self.root / "novel_flow_test.db"
        registry_path = self.root / "self_improve_registry.json"

        with patch.object(
            sys,
            "argv",
            [
                "seed_self_improve_cases.py",
                "--db",
                str(db_path),
                "--cases-dir",
                str(self.case_dir),
                "--registry-path",
                str(registry_path),
            ],
        ):
            seed_main()

        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "novel_self_improve_registry")
        self.assertEqual(payload["cases"][0]["book_id"], "book_tool_case")


if __name__ == "__main__":
    unittest.main()
