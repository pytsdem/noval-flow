from __future__ import annotations

import unittest
from unittest.mock import patch

from novel_flow.agents.writer import WriterAgent
from novel_flow.agents.writing_chapter_agent import WritingChapterAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    ActualChapterSummary,
    BookBlueprint,
    ChapterBrief,
    CharacterCard,
    StoryLine,
    StoryPremise,
    TwistDesign,
)
from novel_flow.services.patcher import PatchExecutor
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.tools.final_judge import FinalJudgeTool


class RecordingSequenceLLM(LLMClient):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[list[LLMMessage]] = []

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        self.calls.append(messages)
        if not self.outputs:
            raise AssertionError("No more fake outputs available")
        return self.outputs.pop(0)


class WritingChapterAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.twist = TwistDesign(
            twist_id="twist_01",
            title="Hidden motive",
            false_belief="Readers think she betrayed him.",
            truth="She framed him to save him.",
            reader_alignment="Readers side with him before reveal.",
            seed_from="ch_001",
            reveal_at="ch_018",
            allowed_clues=["She pauses at the case term."],
            forbidden_reveals=["Do not reveal she saved him."],
            pov_lock="No true inner thought before reveal.",
            related_characters=["Heroine"],
            payoff_effect="Relationship gets re-priced after reveal.",
        )
        self.line = StoryLine(
            line_id="line_case",
            name="Old case",
            line_type="mystery",
            visibility="visible",
            core_question="How can he reopen the case indirectly?",
            reader_hook_mode="pressure",
            start_state="He is blocked publicly.",
            midpoint_shift="A clue changes how readers see her.",
            end_state="The truth is re-evaluated.",
            carried_twists=["twist_01"],
            line_rules=["Only indirect routes early."],
        )
        self.chapter_brief = ChapterBrief(
            chapter_id="ch_002",
            title="Cold Return",
            chapter_type="opening",
            active_lines=["line_case"],
            active_twists=["twist_01"],
            summary="He returns under pressure and chooses an indirect path.",
            incoming_hook="He has come back to the capital.",
            opening_hook="An imperial order lands before he can speak.",
            chapter_object="Transfer register",
            reader_emotion="Readers should side with him and distrust her restraint.",
            reader_belief="Readers believe she betrayed him.",
            allowed_info=["He lost everything in the old case."],
            allowed_clues=["She pauses at the old case term."],
            forbidden=["Do not explain her true motive."],
            world_limit="He cannot overturn the verdict in public.",
            character_focus=["Hero", "Heroine"],
            character_shift="He turns from fury to disciplined action.",
            relationship_reprice="She feels less like a simple traitor and more like a controlled threat.",
            emotional_turn="Hatred turns into cold strategic pressure.",
            backstory_trigger="",
            scene_engine="opening_pressure",
            small_payoff="He finds a procedural opening.",
            ending_pull="The first witness is already dead.",
            info_budget="new clues=1",
        )
        self.characters = [
            CharacterCard(
                name="Hero",
                role="dismissed commander",
                occupation="former general",
                personality="controlled under pressure",
                initial_state="He wants revenge but cannot act directly.",
                motivation="reopen the old case",
                behavior_pattern="keeps cutting his own words short",
            ),
            CharacterCard(
                name="Heroine",
                role="court witness",
                occupation="noblewoman",
                personality="calm and restrained",
                initial_state="She does not explain the past.",
                motivation="protect a secret",
                behavior_pattern="answers indirectly",
            ),
        ]
        self.actual_summaries = [
            ActualChapterSummary(
                chapter_id="ch_001",
                actual_events=["He returned to the capital."],
                reader_now_knows=["The old verdict still stands."],
                reader_now_believes=["She betrayed him."],
                open_questions=["Why did she testify?"],
                character_states=["He is under public pressure."],
                relationship_state=["They face each other like enemies."],
                seeded_clues=["She paused once."],
                locked_truths=["Her real motive is still hidden."],
            )
        ]
        self.sanitized_context_json = """{
  "chapter_id": "ch_002",
  "selection_summary_text": "[Selection]\\n- Relevant roles: Hero, Heroine\\n- Relevant twists: twist_01\\n- Relevant lines: line_case\\n- Current time anchor: return day, morning",
  "time_anchor_text": "[Time anchor]\\n- Absolute: return day, morning\\n- Relative to previous chapter: immediately after the return\\n- Must not conflict: keep travel dust, fatigue, and unfinished court pressure on the body.",
  "chapter_visible_context_text": "[Chapter visible context]\\n- Reader should know: the old verdict still stands.\\n- Reader should believe: she betrayed him.\\n- Reader should not know: her true motive.\\n- Allowed clues: a pause at the old case term.",
  "completed_chapter_memory_text": "[Completed chapter memory]\\n\\nch_001\\n- Actual events: He returned to the capital.\\n- Reader now knows: The old verdict still stands.\\n- Reader now believes: She betrayed him.\\n- Open questions: Why did she testify?\\n- Character states: He is under public pressure.\\n- Relationship state: They face each other like enemies.\\n- Seeded clues: She paused once.\\n- Locked truths: Her real motive is still hidden.",
  "step_1_story_foundation_text": "[Step 1 story foundation]\\n\\nTitle: Test\\nHigh concept: Preserve the surface conflict, pressure source, and reader misread without stating unrevealed truth.",
  "step_3_character_packets_text": "[Scene character context]\\n\\nHero\\n- Public identity: dismissed commander / former general\\n- Surface goal in this chapter: He wants revenge but cannot act directly.",
  "step_5_character_milestones_text": "[Step 5 relevant character milestones]\\n\\nHero\\n- 复仇线: 归京受压 -> 转向间接追查",
  "step_6_twists_text": "[Step 6 active twist packets]\\n\\ntwist_01 / Hidden motive\\n- False belief: Readers think she betrayed him.\\n- Reader alignment: Readers side with him before reveal.\\n- Seed from: ch_001\\n- Reveal at: ch_018\\n- Allowed clues: She pauses at the case term.\\n- Forbidden reveals: Do not reveal she saved him.\\n- POV lock: No true inner thought before reveal.\\n- Related characters: Heroine\\n- Payoff effect: Relationship gets re-priced after reveal.\\n- Truth: hidden until reveal chapter; do not narrate it directly.",
  "step_7_story_lines_text": "[Step 7 active story line packets]\\n\\nline_case / Old case\\n- Type: mystery\\n- Visibility: visible\\n- Core question: How can he reopen the case indirectly?\\n- Reader hook mode: pressure\\n- Start state: He is blocked publicly.\\n- Midpoint shift: Preserve the line's later re-pricing and payoff direction without stating concealed truth in advance.\\n- End state: Preserve the line's later re-pricing and payoff direction without stating concealed truth in advance.\\n- Carried twists: twist_01\\n- Line rules: Only indirect routes early.",
  "step_8_chapter_brief_text": "[Step 8 current chapter brief]\\n\\nChapter id: ch_002\\nTitle: Cold Return\\nChapter type: opening\\nSummary: He returns under pressure and chooses an indirect path.",
  "scene_character_context_text": "[Scene character context]\\n\\nHero\\n- Public identity: dismissed commander / former general\\n- Surface goal in this chapter: He wants revenge but cannot act directly.",
  "relationship_state_text": "[Relationship state]\\n\\nHero -> Heroine\\n- Current public relationship: She feels less like a simple traitor and more like a controlled threat.\\n- Emotional temperature: Hatred turns into cold strategic pressure.\\n- This chapter should move toward: Hatred turns into cold strategic pressure.\\n- Forbidden shortcut: do not skip misreading, cost, or unrevealed truth."
}"""

    def test_skill_manager_discovers_guard_skills(self) -> None:
        manager = SkillManager(registry=SkillRegistry())
        review_reports = {
            "review_prose_quality": {"prose_score": 6, "tension_score": 6, "exposition_score": 5, "rewrite_needed": True},
            "review_reveal_leak": {"passed": False, "level": "high", "issues": ["Leak"]},
            "review_plot_logic": {"passed": False, "level": "high", "issues": ["Logic"]},
            "review_clue_origin": {"passed": False, "level": "high", "issues": ["Clue"]},
            "review_humanity": {"passed": False, "level": "medium", "human_warmth_score": 5, "issues": []},
            "review_character_integrity": {"passed": False, "level": "high", "issues": []},
            "review_time_consistency": {"passed": False, "level": "high", "issues": []},
            "review_chapter_engine": {"passed": False, "level": "medium", "issues": ["Opening is weak."]},
        }
        skills = [item.skill_id for item in manager.discover(chapter_brief=self.chapter_brief, review_reports=review_reports)]
        self.assertIn("prose_improvement", skills)
        self.assertIn("reveal_guard", skills)
        self.assertIn("plot_guard", skills)
        self.assertIn("clue_consistency", skills)
        self.assertIn("opening_boost", skills)
        self.assertIn("humanity_boost", skills)
        self.assertIn("character_integrity", skills)
        self.assertIn("time_consistency_guard", skills)

    def test_final_judge_blocks_failed_reports(self) -> None:
        result = FinalJudgeTool().run(
            {
                "review_reports": {
                    "review_instruction_compliance": {"passed": False, "level": "medium"},
                    "review_continuity": {"passed": True, "level": "low"},
                    "review_reveal_leak": {"passed": True, "level": "low"},
                    "review_plot_logic": {"passed": True, "level": "low"},
                    "review_clue_origin": {"passed": True, "level": "low"},
                    "review_prose_quality": {"prose_score": 6, "tension_score": 7, "exposition_score": 4},
                }
            }
        )
        self.assertFalse(result["passed"])
        self.assertIn("Instruction compliance did not pass.", result["blocking_reasons"])
        self.assertIn("Prose score is below 7.", result["blocking_reasons"])

    def test_writing_chapter_agent_happy_path(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                "Cold wind pressed against the vermilion steps. He bowed, but not low enough to forget himself. The order had arrived before his first breath settled.",
                "The transfer register stayed tucked beneath the eunuch's sleeve. He asked for it in a level voice, as if the request cost him nothing at all.",
                "When the old case title surfaced, she paused only once. That single hesitation tightened every gaze in the hall and turned restraint into suspicion.",
                "He left with the legal opening in hand, but the courtyard had already changed its face. Before he reached the lower steps, he learned the first witness was dead.",
                '{"tool_calls":[{"tool_name":"review_instruction_compliance","reason":"hard gate"},{"tool_name":"review_continuity","reason":"hard gate"},{"tool_name":"review_time_consistency","reason":"time"},{"tool_name":"review_character_integrity","reason":"behavior"},{"tool_name":"review_humanity","reason":"humanity"},{"tool_name":"review_hook_appearance","reason":"hook and appearance"},{"tool_name":"review_reveal_leak","reason":"reveal safety"},{"tool_name":"review_plot_logic","reason":"logic"},{"tool_name":"review_clue_origin","reason":"clue source"},{"tool_name":"review_prose_quality","reason":"style"}]}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "human_warmth_score": 8, "character_has_real_world_tradeoff": true, "emotion_is_grounded_in_specific_loss": true, "supporting_character_reacts_humanly": true, "self_talk_feels_specific": true, "pain_is_not_generic": true, "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"prose_score": 8, "tension_score": 8, "subtext_score": 7, "exposition_score": 3, "cliche_score": 2, "double_duty_detail_score": 7, "scene_texture_score": 8, "emotion_externalization_score": 8, "dialogue_subtext_score": 8, "human_warmth_score": 8, "rewrite_needed": false, "rewrite_guidance": "", "evidence_notes": ["detail works", "emotion lands"]}',
                "Cold wind pressed against the vermilion steps. He bowed, counted the breaths between orders, and saw her pause only once at the old case title.",
                '{"chapter_id":"ch_002","actual_events":["He returns to court under pressure.","He finds a procedural opening."],"reader_now_knows":["The old verdict still stands.","A transfer register may help him move indirectly."],"reader_now_believes":["She betrayed him but is hiding something."],"open_questions":["Why did she pause?"],"character_states":["He chooses disciplined action."],"relationship_state":["Their hostility gains a layer of calculation."],"seeded_clues":["She pauses at the old case term."],"locked_truths":["Her true motive remains hidden."],"time_state":{"chapter_end_time":"回京当日，午后","continuity_note":"他仍带着入宫时的疲态，旧案名目已经压在心头。"}}',
            ]
        )
        agent = WritingChapterAgent(llm_client=llm)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )
        self.assertEqual(result.actual_chapter_summary.chapter_id, "ch_002")
        self.assertTrue(result.final_judge["passed"])
        self.assertIn("vermilion steps", result.chapter_text)
        first_prompt = llm.calls[1][-1].content
        self.assertNotIn(self.twist.truth, first_prompt)
        self.assertIn(self.twist.false_belief, first_prompt)

    def test_writing_chapter_agent_emits_live_stage_events(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                "Cold wind pressed against the vermilion steps. He bowed, but not low enough to forget himself. The order had arrived before his first breath settled.",
                "The transfer register stayed tucked beneath the eunuch's sleeve. He asked for it in a level voice, as if the request cost him nothing at all.",
                "When the old case title surfaced, she paused only once. That single hesitation tightened every gaze in the hall and turned restraint into suspicion.",
                "He left with the legal opening in hand, but the courtyard had already changed its face. Before he reached the lower steps, he learned the first witness was dead.",
                '{"tool_calls":[{"tool_name":"review_instruction_compliance","reason":"hard gate"},{"tool_name":"review_continuity","reason":"hard gate"},{"tool_name":"review_time_consistency","reason":"time"},{"tool_name":"review_character_integrity","reason":"behavior"},{"tool_name":"review_humanity","reason":"humanity"},{"tool_name":"review_hook_appearance","reason":"hook and appearance"},{"tool_name":"review_reveal_leak","reason":"reveal safety"},{"tool_name":"review_plot_logic","reason":"logic"},{"tool_name":"review_clue_origin","reason":"clue source"},{"tool_name":"review_prose_quality","reason":"style"}]}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "human_warmth_score": 8, "character_has_real_world_tradeoff": true, "emotion_is_grounded_in_specific_loss": true, "supporting_character_reacts_humanly": true, "self_talk_feels_specific": true, "pain_is_not_generic": true, "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"prose_score": 8, "tension_score": 8, "subtext_score": 7, "exposition_score": 3, "cliche_score": 2, "double_duty_detail_score": 7, "scene_texture_score": 8, "emotion_externalization_score": 8, "dialogue_subtext_score": 8, "human_warmth_score": 8, "rewrite_needed": false, "rewrite_guidance": "", "evidence_notes": ["detail works", "emotion lands"]}',
                "Cold wind pressed against the vermilion steps. He bowed, counted the breaths between orders, and saw her pause only once at the old case title.",
                '{"chapter_id":"ch_002","actual_events":["He returns to court under pressure.","He finds a procedural opening."],"reader_now_knows":["The old verdict still stands.","A transfer register may help him move indirectly."],"reader_now_believes":["She betrayed him but is hiding something."],"open_questions":["Why did she pause?"],"character_states":["He chooses disciplined action."],"relationship_state":["Their hostility gains a layer of calculation."],"seeded_clues":["She pauses at the old case term."],"locked_truths":["Her true motive remains hidden."],"time_state":{"chapter_end_time":"回京当日，午后","continuity_note":"他仍带着入宫时的疲态。"}}',
            ]
        )
        agent = WritingChapterAgent(llm_client=llm)
        with patch("novel_flow.agents.writing_chapter_agent.ev.emit") as emit_mock:
            agent.write_chapter(
                chapter_brief=self.chapter_brief,
                twist_designs=[self.twist],
                story_lines=[self.line],
                character_cards=self.characters,
                worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
                actual_chapter_summaries=self.actual_summaries,
            )
        stage_payloads = [call.kwargs for call in emit_mock.call_args_list if call.args and call.args[0] == "stage"]
        stage_names = [payload.get("stage") for payload in stage_payloads]
        self.assertIn("plan_content_blocks_start", stage_names)
        self.assertIn("block_1_committed", stage_names)
        self.assertIn("review_iteration_1_plan", stage_names)
        self.assertIn("review_iteration_1_tool_done", stage_names)
        self.assertIn("final_polish_done", stage_names)
        self.assertIn("format_adjustment_done", stage_names)
        self.assertIn("summarize_actual_chapter_done", stage_names)
        tool_done = next(payload for payload in stage_payloads if payload.get("stage") == "review_iteration_1_tool_done")
        self.assertIn("tool_name", tool_done)
        self.assertIn("tool_result", tool_done)

    def test_writer_agent_persists_actual_summary_from_new_loop(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                "He returned in silence, but the hall refused him even that small mercy. Every eye counted what he no longer had.",
                "The clerk would not touch the register until the eunuch nodded. He understood then that even procedure had become a guarded door.",
                "She paused at the old case name and looked away too quickly. That small break in her calm made the room colder, not kinder.",
                "By the time he stepped back into the wind, he had found the indirect route he needed. It came with the news that the first witness would never speak again.",
                '{"tool_calls":[{"tool_name":"review_instruction_compliance","reason":"hard gate"},{"tool_name":"review_continuity","reason":"hard gate"},{"tool_name":"review_time_consistency","reason":"time"},{"tool_name":"review_character_integrity","reason":"behavior"},{"tool_name":"review_humanity","reason":"humanity"},{"tool_name":"review_hook_appearance","reason":"hook and appearance"},{"tool_name":"review_reveal_leak","reason":"reveal safety"},{"tool_name":"review_plot_logic","reason":"logic"},{"tool_name":"review_clue_origin","reason":"clue source"},{"tool_name":"review_prose_quality","reason":"style"}]}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "human_warmth_score": 8, "character_has_real_world_tradeoff": true, "emotion_is_grounded_in_specific_loss": true, "supporting_character_reacts_humanly": true, "self_talk_feels_specific": true, "pain_is_not_generic": true, "issues": [], "rewrite_guidance": ""}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"passed": true, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}',
                '{"prose_score": 8, "tension_score": 8, "subtext_score": 7, "exposition_score": 3, "cliche_score": 2, "double_duty_detail_score": 7, "scene_texture_score": 8, "emotion_externalization_score": 8, "dialogue_subtext_score": 8, "human_warmth_score": 8, "rewrite_needed": false, "rewrite_guidance": "", "evidence_notes": ["detail works", "emotion lands"]}',
                "He returned in silence, and the hall gave him no mercy.",
                '{"chapter_id":"ch_002","actual_events":["He returns."],"reader_now_knows":["The hall is hostile."],"reader_now_believes":["She betrayed him."],"open_questions":["What is she hiding?"],"character_states":["He stays disciplined."],"relationship_state":["They stand on cold terms."],"seeded_clues":["A brief pause."],"locked_truths":["Her motive is hidden."],"time_state":{"chapter_end_time":"回京当日，午后","continuity_note":"他仍在敌意未散的殿中。"}}',
            ]
        )
        writer = WriterAgent(llm_client=llm, patch_executor=PatchExecutor())
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
            characters=self.characters,
            volume_titles=["Volume 1"],
            chapter_plans=[],
        )
        book = writer.create_book(blueprint=blueprint, source_query="query")
        book.metadata["story_blueprint"] = {
            "story_engine": {
                "world_rules": "The imperial verdict cannot be challenged publicly.",
                "power_structure": "Court procedure and imperial hierarchy decide what can move.",
            },
            "event_timeline": [
                {
                    "event_id": "EVT_0016",
                    "title": "Hero is forced out of the capital",
                    "time_label": "景和七年冬—景和八年春",
                    "description": "He is forced away from the capital.",
                    "trigger": "Court pressure cuts him off.",
                    "consequence": "He loses his place and goes to the frontier.",
                    "affected_characters": ["Hero", "Heroine"],
                },
                {
                    "event_id": "EVT_0000",
                    "title": "Hero returns to the capital",
                    "time_label": "景和十二年春",
                    "description": "He returns with frontier merit.",
                    "trigger": "Years of service bring him back.",
                    "consequence": "The old case regains pressure.",
                    "affected_characters": ["Hero", "Heroine"],
                },
            ],
            "twist_designs": [self.twist.model_dump(mode="json")],
            "story_lines": [self.line.model_dump(mode="json")],
            "chapter_briefs": [self.chapter_brief.model_dump(mode="json")],
        }
        book.metadata["character_milestones"] = [
            {"character_name": "Hero", "milestone_list": [{"axis": "复仇线", "stages": ["归京受压", "转向间接追查"]}], "axes": []},
            {"character_name": "Heroine", "milestone_list": [{"axis": "关系线", "stages": ["被误解", "关系重估"]}], "axes": []},
        ]
        updated_book, chapter = writer.write_next_chapter(book=book)
        self.assertEqual(chapter.id, "ch_002")
        self.assertTrue(chapter.is_finalized)
        self.assertIn("hall gave him no mercy", chapter.final_text)
        self.assertGreaterEqual(len(chapter.content_blocks), 4)
        self.assertEqual(updated_book.metadata["actual_chapter_summaries"][-1]["chapter_id"], "ch_002")
        self.assertIn("ch_002", updated_book.metadata["writing_chapter_runs"])
        self.assertGreaterEqual(len(updated_book.metadata["writing_chapter_runs"]["ch_002"]["content_blocks"]), 4)


if __name__ == "__main__":
    unittest.main()
