from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from novel_flow.agents.writer import WriterAgent
from novel_flow.agents.writing_chapter_agent import WritingChapterAgent
from novel_flow.llm.base import LLMClient, LLMMessage
from novel_flow.models.schemas import (
    ActualChapterSummary,
    BookBlueprint,
    ChapterBeat,
    ChapterContract,
    ChapterExecutionResult,
    CharacterCard,
    CriticReport,
    StoryLine,
    StoryPremise,
    TwistDesign,
)
from novel_flow.services.novel_context import build_current_chapter_context
from novel_flow.services.patcher import PatchExecutor
from novel_flow.services.prose_lint import ProseSurfaceSignals, analyze_prose_surface
from novel_flow.services.skill_manager import SkillManager
from novel_flow.services.skill_registry import SkillRegistry
from novel_flow.services.tool_registry import ToolRegistry
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
        self.chapter_brief = ChapterContract(
            chapter_id="ch_002",
            title="Cold Return",
            chapter_type="opening",
            active_lines=["line_case"],
            active_twists=["twist_01"],
            summary="He returns under pressure and chooses an indirect path.",
            incoming_hook="He has come back to the capital.",
            opening_hook="An imperial order lands before he can speak.",
            core_scene="He is forced to take the order in public before he can choose his own opening move.",
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
            clue_reveal_style="natural_exposure",
            character_reentry_focus={"Heroine": "Use the court's reaction and her restraint to re-establish presence; do not re-explain her identity."},
            human_pain_anchor="He has to accept public pressure while travel dust and fatigue are still hanging on him.",
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
        self.sanitized_context_json = json.dumps(
            {
                "chapter_id": "ch_002",
                "selection_summary_text": "[Selection]\n- Relevant roles: Hero, Heroine\n- Relevant twists: twist_01\n- Relevant lines: line_case\n- Current time anchor: return day, morning",
                "time_anchor_text": "[Time anchor]\n- Absolute: return day, morning\n- Relative to previous chapter: immediately after the return\n- Must not conflict: keep travel dust, fatigue, and unfinished court pressure on the body.",
                "chapter_visible_context_text": "[Chapter visible context]\n- Reader should know: the old verdict still stands.\n- Reader should believe: she betrayed him.\n- Reader should not know: her true motive.\n- Allowed clues: a pause at the old case term.",
                "completed_chapter_memory_text": "[Completed chapter memory]\n\nch_001\n- Actual events: He returned to the capital.\n- Reader now knows: The old verdict still stands.\n- Reader now believes: She betrayed him.\n- Open questions: Why did she testify?\n- Character states: He is under public pressure.\n- Relationship state: They face each other like enemies.\n- Seeded clues: She paused once.\n- Locked truths: Her real motive is still hidden.",
                "step_1_story_foundation_text": "[Step 1 story foundation]\n\nTitle: Test\nHigh concept: Preserve the surface conflict, pressure source, and reader misread without stating unrevealed truth.",
                "step_3_character_packets_text": "[Scene character context]\n\nHero\n- Public identity: dismissed commander / former general\n- Surface goal in this chapter: He wants revenge but cannot act directly.",
                "step_5_character_milestones_text": "[Step 5 relevant character milestones]\n\nHero\n- Revenge line: return under pressure -> shift to indirect investigation",
                "step_6_twists_text": "[Step 6 active twist packets]\n\ntwist_01 / Hidden motive\n- False belief: Readers think she betrayed him.\n- Reader alignment: Readers side with him before reveal.\n- Seed from: ch_001\n- Reveal at: ch_018\n- Allowed clues: She pauses at the case term.\n- Forbidden reveals: Do not reveal she saved him.\n- POV lock: No true inner thought before reveal.\n- Related characters: Heroine\n- Payoff effect: Relationship gets re-priced after reveal.\n- Truth: hidden until reveal chapter; do not narrate it directly.",
                "step_7_story_lines_text": "[Step 7 active story line packets]\n\nline_case / Old case\n- Type: mystery\n- Visibility: visible\n- Core question: How can he reopen the case indirectly?\n- Reader hook mode: pressure\n- Start state: He is blocked publicly.\n- Midpoint shift: Preserve later re-pricing without stating concealed truth.\n- End state: Preserve later re-pricing without stating concealed truth.\n- Carried twists: twist_01\n- Line rules: Only indirect routes early.",
                "step_8_chapter_brief_text": "[Step 8 current chapter contract]\n\nChapter id: ch_002\nTitle: Cold Return\nChapter type: opening\nChapter mission: He returns under pressure and chooses an indirect path.",
                "scene_character_context_text": "[Scene character context]\n\nHero\n- Public identity: dismissed commander / former general\n- Surface goal in this chapter: He wants revenge but cannot act directly.",
                "relationship_state_text": "[Relationship state]\n\nHero -> Heroine\n- Current public relationship: She feels less like a simple traitor and more like a controlled threat.\n- Emotional temperature: Hatred turns into cold strategic pressure.\n- This chapter should move toward: Hatred turns into cold strategic pressure.\n- Forbidden shortcut: do not skip misreading, cost, or unrevealed truth.",
            },
            ensure_ascii=False,
        )

    def _character_mindset_json(self, *, character_name: str, other_name: str) -> str:
        return json.dumps(
            {
                "character_id": character_name,
                "character_name": character_name,
                "surface_emotion": f"{character_name}表层克制",
                "core_emotion": f"{character_name}内里绷紧",
                "primary_goal": f"{character_name}想先稳住本章局面",
                "hidden_need": f"{character_name}需要确认对方真实站位",
                "fear": f"{character_name}害怕先失控就失去主动",
                "attitude_to_key_others": {
                    other_name: f"对{other_name}既警惕又不得不试探"
                },
                "self_control_level": "medium_high",
                "breaking_point_hint": f"{character_name}一旦被当众逼到无路可退就会露出裂口",
                "known_but_unspoken": f"{character_name}知道本章真正危险不止表面命令",
                "misbelief": f"{character_name}仍误判对方此刻的真实意图",
                "chapter_change_hint": f"{character_name}会从纯粹对抗转向更复杂的提防",
            },
            ensure_ascii=False,
        )

    def _character_mindset_jsons(self) -> list[str]:
        return [
            self._character_mindset_json(character_name="Hero", other_name="Heroine"),
            self._character_mindset_json(character_name="Heroine", other_name="Hero"),
        ]

    def _planned_blocks_json(self) -> str:
        paragraph_budget = "建议 2~5 个自然段；单段尽量 30~120 中文字；超过 180 中文字视为过长"
        blocks = [
            {
                "block_id": "ch_002.sc_001.b001",
                "chapter_id": "ch_002",
                "block_index": 1,
                "purpose": "Open with immediate court pressure.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Land the imperial order before he can settle himself.",
                "must_reveal": ["An imperial order lands before he can speak."],
                "must_hide": ["Do not explain her true motive."],
                "new_value": "Readers newly feel the opening pressure as an active public trap.",
                "must_not_repeat": [
                    "Do not restate the old case backstory.",
                    "Do not explain her motive yet.",
                ],
                "relationship_delta": "Their relationship moves from suspended distance into public pressure.",
                "clue_delta": "No new clue yet; only the opening pressure becomes active.",
                "must_land_in_action": [
                    "Land the pressure through gesture, etiquette, and witness reaction.",
                    "Do not summarize the pressure in narrator explanation.",
                ],
                "emotional_tone": "Readers should side with him and distrust her restraint.",
                "end_state": "He is forced into the chapter's pressure without room to recover.",
                "human_reaction_target": [
                    "Show the hero's bodily restraint before he speaks.",
                    "Let the room react to the order as a real public threat.",
                ],
                "cost_shift": "He loses the chance to choose his own opening move.",
                "reader_feeling_target": "Readers should feel the public pressure close around him immediately.",
                "paragraph_budget": paragraph_budget,
                "target_chars": 420,
                "micro_hook": "He now has to answer the public pressure before he can reclaim the opening move.",
                "turn_type": "pressure_rise",
                "paragraph_shape": [
                    "主动作",
                    "配角反应",
                    "人物细节/情绪泄露",
                    "礼法或环境补压",
                ],
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "reaction_line",
                    "surface_function": "Let the public pressure land in one short beat.",
                    "hidden_function": "Show that he protects his own bearing before he explains anything.",
                    "must_reveal_about_character": "He is still trying to hold dignity under pressure.",
                    "must_not_do": [
                        "Do not turn it into a slogan.",
                        "Do not explain it immediately after it appears.",
                    ],
                    "preferred_shape": "短、准、能留余味",
                },
                "style_risk_guard": [
                    "Do not open with background summary.",
                    "Do not let the prose sound like an outline.",
                ],
                "character_reentry_mode": {
                    "target_character": "Hero",
                    "identity_already_known": True,
                    "reentry_strategy": "Use the court's reaction and his unfinished military bearing to re-establish presence.",
                    "first_signal": "Travel dust still clinging to his cuffs beneath formal dress.",
                    "first_emotional_focus": "He cares first about not surrendering his opening move.",
                    "must_avoid": ["Do not re-explain his past rank in narrator summary."],
                },
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": "ch_002.sc_001.b002",
                "chapter_id": "ch_002",
                "block_index": 2,
                "purpose": "Push the chapter object into a live negotiation.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Make the transfer register matter through scene pressure.",
                "must_reveal": ["Transfer register", "He finds a procedural opening."],
                "must_hide": ["Do not explain her true motive."],
                "new_value": "The chapter object becomes actionable, but only through a more expensive route.",
                "must_not_repeat": [
                    "Do not replay the opening pressure in abstract summary.",
                    "Do not restate the same public threat without new movement.",
                ],
                "relationship_delta": "Their clash turns from public pressure into procedural negotiation.",
                "clue_delta": "The register becomes newly usable, but no deeper truth is exposed.",
                "must_land_in_action": [
                    "Move the register through dialogue, procedure, or another person's reaction.",
                    "Do not explain the procedural opening as pure summary.",
                ],
                "emotional_tone": "Hatred turns into cold strategic pressure.",
                "end_state": "He gains a procedural path, but it costs him leverage.",
                "human_reaction_target": [
                    "Show practical calculation under etiquette pressure.",
                    "Let another person's reaction make the pressure legible.",
                ],
                "cost_shift": "He must ask through the same court order that humiliates him.",
                "reader_feeling_target": "Readers should feel that even progress comes with humiliation and constraint.",
                "paragraph_budget": paragraph_budget,
                "target_chars": 520,
                "micro_hook": "The register can move the case, but asking for it exposes him further.",
                "turn_type": "pressure_rise",
                "paragraph_shape": [
                    "主动作",
                    "礼法或程序阻力",
                    "配角反应",
                    "代价落点",
                ],
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "dialogue",
                    "surface_function": "Carry the negotiation through one short line.",
                    "hidden_function": "Show his restraint and practical calculation.",
                    "must_reveal_about_character": "He is already choosing controlled method over raw anger.",
                    "must_not_do": [
                        "Do not make it pure exposition.",
                        "Do not let the next sentence unpack it completely.",
                    ],
                    "preferred_shape": "短、准、能留余味",
                },
                "style_risk_guard": [
                    "Do not explain why the register matters in abstract summary.",
                    "Do not let dialogue become pure information transfer.",
                ],
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": "ch_002.sc_001.b003",
                "chapter_id": "ch_002",
                "block_index": 3,
                "purpose": "Reprice the relationship through a visible hesitation.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Turn her pause into relationship pressure.",
                "must_reveal": [
                    "He turns from fury to disciplined action.",
                    "She feels less like a simple traitor and more like a controlled threat.",
                    "She pauses at the old case term.",
                ],
                "must_hide": ["Do not explain her true motive."],
                "new_value": "The relationship is newly repriced through her pause, and the clue becomes legible without explanation.",
                "must_not_repeat": [
                    "Do not repeat the negotiation result from the prior beat.",
                    "Do not explain the pause after showing it.",
                ],
                "relationship_delta": "She becomes less like a fixed traitor and more like a controlled danger.",
                "clue_delta": "Her pause is newly visible as a clue carrier, but still unreadable in motive.",
                "must_land_in_action": [
                    "Land the change through pause, gaze, witness reaction, or failed composure.",
                    "Do not narrate the relationship change as a flat conclusion.",
                ],
                "emotional_tone": "Hatred turns into cold strategic pressure.",
                "end_state": "Her restraint becomes more threatening than a direct answer.",
                "human_reaction_target": [
                    "Show a small failure of composure instead of direct confession.",
                    "Let witnesses react to the pause like real people in the room.",
                ],
                "cost_shift": "The old case moves one step closer while their relationship becomes harder to read and harder to trust.",
                "reader_feeling_target": "Readers should remember the pause and feel the relationship has become more dangerous.",
                "paragraph_budget": paragraph_budget,
                "target_chars": 560,
                "micro_hook": "The pause becomes visible, but nobody in the room will explain it cleanly.",
                "turn_type": "clue_shift",
                "paragraph_shape": [
                    "关系压力",
                    "回避与失手",
                    "他人先发现",
                    "当事人回避解释",
                ],
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "narrative_judgment",
                    "surface_function": "Mark the changed relationship pressure in one close judgment.",
                    "hidden_function": "Reveal his mistrust and the way he reads her restraint as threat.",
                    "must_reveal_about_character": "He is more prepared to believe danger than innocence.",
                    "must_not_do": [
                        "Do not turn it into omniscient summary.",
                        "Do not explain the clue right after it lands.",
                    ],
                    "preferred_shape": "短、准、能留余味",
                },
                "style_risk_guard": [
                    "Do not explain the clue after showing it.",
                    "Do not summarize the relationship change in narrator voice.",
                ],
                "clue_reveal_mechanism": {
                    "clue": "She pauses at the old case term.",
                    "style": "natural_exposure",
                    "pressure_source": "He presses her in public where she cannot answer freely.",
                    "surface_trigger": "The old case title is spoken aloud in a formal setting.",
                    "first_noticer": "Hero",
                    "owner_reaction": "Heroine avoids explaining and lets the room grow more suspicious.",
                },
                "text": "",
                "status": "draft",
                "version": 1,
            },
            {
                "block_id": "ch_002.sc_001.b004",
                "chapter_id": "ch_002",
                "block_index": 4,
                "purpose": "End with a concrete next-step loss.",
                "characters": ["Hero"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Make the ending pull land through a changed situation.",
                "must_reveal": ["The first witness is already dead."],
                "must_hide": ["Do not explain her true motive."],
                "new_value": "The chapter exits on a harder route and a narrower next move.",
                "must_not_repeat": [
                    "Do not restate the pause and relationship reprice from the prior beat.",
                    "Do not end in trailer-like explanation.",
                ],
                "relationship_delta": "The cost of moving against her and the case both become harder to walk back.",
                "clue_delta": "The witness death is a new fact, not a restatement of prior suspicion.",
                "must_land_in_action": [
                    "Land the hook through body, breath, loss, or the changed route forward.",
                    "Do not explain the ending hook in summary voice.",
                ],
                "emotional_tone": "Readers should side with him and distrust her restraint.",
                "end_state": "The chapter closes on a harder route and a sharper cost.",
                "human_reaction_target": [
                    "Let the hook strike the hero's body or breathing before it becomes a plot point.",
                    "Do not end on summary language alone.",
                ],
                "cost_shift": "He loses the first witness before the investigation can even begin.",
                "reader_feeling_target": "Readers should feel the next step has become both urgent and harder.",
                "paragraph_budget": paragraph_budget,
                "target_chars": 420,
                "micro_hook": "The case can still move, but only through a worse and narrower path.",
                "turn_type": "false_relief",
                "paragraph_shape": [
                    "结果落地",
                    "短反应",
                    "额外代价",
                    "尾钩或未竟动作",
                ],
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "inner_thought",
                    "surface_function": "Pin the ending cost through one short internal beat.",
                    "hidden_function": "Reveal what failure or loss hits him first.",
                    "must_reveal_about_character": "He feels the case through personal cost before strategy.",
                    "must_not_do": [
                        "Do not write it like trailer copy.",
                        "Do not explain the hook in the next sentence.",
                    ],
                    "preferred_shape": "短、准、能留余味",
                },
                "style_risk_guard": [
                    "Do not force a trailer-like ending sentence.",
                    "Do not flatten the final beat into explanation.",
                ],
                "text": "",
                "status": "draft",
                "version": 1,
            },
        ]
        return json.dumps({"blocks": blocks}, ensure_ascii=False)

    @staticmethod
    def _block_quality_pass() -> str:
        return json.dumps(
            {
                "tool_id": "review_block_quality",
                "passed": True,
                "severity": "low",
                "scene_goal_completed": True,
                "human_reaction_target_hit": True,
                "cost_shift_landed": True,
                "reader_feeling_landed": True,
                "paragraphs_readable": True,
                "issues": [],
                "rewrite_guidance": "",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _evidence_review_pass() -> str:
        return json.dumps({"passed": True, "level": "low", "issues": [], "rewrite_guidance": "", "evidence_focus": []}, ensure_ascii=False)

    @staticmethod
    def _humanity_review_pass() -> str:
        return json.dumps(
            {
                "passed": True,
                "level": "low",
                "human_warmth_score": 8,
                "character_has_real_world_tradeoff": True,
                "emotion_is_grounded_in_specific_loss": True,
                "supporting_character_reacts_humanly": True,
                "self_talk_feels_specific": True,
                "pain_is_not_generic": True,
                "issues": [],
                "rewrite_guidance": "",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _prose_review_pass() -> str:
        return json.dumps(
            {
                "prose_score": 8,
                "tension_score": 8,
                "subtext_score": 7,
                "exposition_score": 3,
                "cliche_score": 2,
                "double_duty_detail_score": 7,
                "scene_texture_score": 8,
                "emotion_externalization_score": 8,
                "dialogue_subtext_score": 8,
                "human_warmth_score": 8,
                "memorability_score": 8,
                "pressure_authenticity_score": 8,
                "rewrite_needed": False,
                "rewrite_guidance": "",
                "issues": [],
                "evidence_notes": ["detail works", "emotion lands"],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _targeted_review_pass(summary: str) -> str:
        return json.dumps(
            {
                "pass": True,
                "issues": [],
                "summary": summary,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _targeted_review_fail(*, issue_id: str, problem_type: str, target_blocks: list[str], patch_hint: str, reason: str) -> str:
        return json.dumps(
            {
                "pass": False,
                "issues": [
                    {
                        "issue_id": issue_id,
                        "severity": "high",
                        "problem_type": problem_type,
                        "reason": reason,
                        "target_blocks": target_blocks,
                        "patch_hint": patch_hint,
                    }
                ],
                "summary": reason,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _patch_plan_single_target(block_id: str) -> str:
        return json.dumps(
            {
                "patch_targets": [
                    {
                        "target_type": "block",
                        "target_id": block_id,
                        "problem_type": "duplicate_emotion",
                        "goal": "压缩重复情绪并加强交接。",
                        "instructions": [
                            "删掉重复的冷意描写。",
                            "保留男主的克制和试探。",
                            "结尾给下一段留下紧绷感。",
                        ],
                        "local_context_needed": ["prev_block", "next_block", "relationship_state"],
                        "source_issue_ids": ["I1"],
                    }
                ],
                "unchanged_blocks": [
                    "ch_002.sc_001.b001",
                    "ch_002.sc_001.b003",
                    "ch_002.sc_001.b004",
                ],
                "global_constraints": [
                    "不得引入新设定。",
                    "未命中的 block 不要改动。",
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _patch_judge_pass() -> str:
        return json.dumps(
            {
                "pass": True,
                "remaining_issues": [],
                "newly_introduced_issues": [],
                "recommendation": "可以结束。",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _patch_judge_fail(reason: str) -> str:
        return json.dumps(
            {
                "pass": False,
                "remaining_issues": [
                    {
                        "problem_type": "handoff_weak",
                        "target_blocks": ["ch_002.sc_001.b002", "ch_002.sc_001.b003"],
                        "reason": reason,
                    }
                ],
                "newly_introduced_issues": [],
                "recommendation": "建议再补一次 patch；若仍失败则切到 deep。",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _patch_judge_inconsistent_pass(reason: str) -> str:
        return json.dumps(
            {
                "pass": True,
                "remaining_issues": [
                    {
                        "problem_type": "handoff_weak",
                        "target_blocks": ["ch_002.sc_001.b002", "ch_002.sc_001.b003"],
                        "reason": reason,
                    }
                ],
                "newly_introduced_issues": [],
                "recommendation": "建议补一次patch，修正交接后再继续。",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _four_block_outputs() -> list[str]:
        return [
            "Paragraph one keeps the opening pressure on him before he can settle his breath.",
            "Paragraph two repeats the cold pressure and delays the actual negotiation too long.",
            "Paragraph three turns her pause into sharper relationship pressure.",
            "Paragraph four closes on the dead witness and a narrower road forward.",
        ]

    @classmethod
    def _four_block_draft(cls) -> str:
        return "\n\n".join(cls._four_block_outputs())

    @staticmethod
    def _merge_four_block_draft(block_two: str) -> str:
        return "\n\n".join(
            [
                "Paragraph one keeps the opening pressure on him before he can settle his breath.",
                block_two,
                "Paragraph three turns her pause into sharper relationship pressure.",
                "Paragraph four closes on the dead witness and a narrower road forward.",
            ]
        )

    def _block_review_pass_once(self) -> list[str]:
        return [
            self._evidence_review_pass(),
            self._evidence_review_pass(),
            self._evidence_review_pass(),
            self._block_quality_pass(),
        ]

    def _chapter_review_pass_sequence(self) -> list[str]:
        return [
            self._targeted_review_pass("结构和连续性通过。"),
            self._targeted_review_pass("文风和人味通过。"),
        ]

    def test_skill_manager_discovers_guard_skills(self) -> None:
        manager = SkillManager(registry=SkillRegistry())
        review_reports = {
            "review_prose_quality": {
                "prose_score": 6,
                "tension_score": 6,
                "memorability_score": 6,
                "pressure_authenticity_score": 6,
                "exposition_score": 5,
                "rewrite_needed": True,
            },
            "review_reveal_leak": {"passed": False, "level": "high", "issues": ["Leak"]},
            "review_plot_logic": {"passed": False, "level": "high", "issues": ["Logic"]},
            "review_clue_origin": {"passed": False, "level": "high", "issues": ["Clue"]},
            "review_humanity": {"passed": False, "level": "medium", "human_warmth_score": 5, "issues": []},
            "review_chapter_engine": {"passed": False, "level": "medium", "issues": ["Opening is weak."]},
        }
        chapter_skills = [item.skill_id for item in manager.discover(chapter_brief=self.chapter_brief, review_reports=review_reports)]
        block_skills = [item.skill_id for item in manager.initial_skills(stage="block")]

        self.assertIn("base_style", block_skills)
        self.assertIn("reveal_guard", block_skills)
        self.assertIn("character_integrity", block_skills)
        self.assertIn("time_consistency_guard", block_skills)

        self.assertIn("base_style", chapter_skills)
        self.assertIn("prose_improvement", chapter_skills)
        self.assertIn("opening_boost", chapter_skills)
        self.assertIn("humanity_boost", chapter_skills)
        self.assertNotIn("reveal_guard", chapter_skills)
        self.assertNotIn("plot_guard", chapter_skills)
        self.assertNotIn("clue_consistency", chapter_skills)

    def test_plan_review_tools_keeps_chapter_hot_path_converged(self) -> None:
        agent = WritingChapterAgent(llm_client=RecordingSequenceLLM([]))
        content_blocks = [ChapterBeat.model_validate(item) for item in json.loads(self._planned_blocks_json())["blocks"]]

        tool_names = agent._plan_review_tools(
            chapter_brief=self.chapter_brief,
            review_reports={},
            active_skills=agent.skill_manager.initial_skills(stage="chapter"),
            content_blocks=content_blocks,
        )

        self.assertEqual(
            tool_names,
            [
                "review_structure_and_continuity",
                "review_prose_and_humanity",
            ],
        )

    def test_deep_block_review_gate_skips_strong_surface(self) -> None:
        strong_surface = ProseSurfaceSignals(
            pronoun_lead_ratio=0.08,
            explanation_ratio=0.04,
            action_carried_reveal_score=8.4,
            relationship_cost_realization_score=8.2,
            procedure_pressure=1.0,
            overall_score=8.9,
            evidence={},
        )
        weak_surface = ProseSurfaceSignals(
            pronoun_lead_ratio=0.31,
            explanation_ratio=0.24,
            action_carried_reveal_score=5.8,
            relationship_cost_realization_score=5.9,
            procedure_pressure=4.2,
            overall_score=6.2,
            evidence={},
        )

        self.assertFalse(WritingChapterAgent._should_run_block_review(strong_surface))
        self.assertTrue(WritingChapterAgent._should_run_block_review(weak_surface))

    def test_writing_chapter_agent_defaults_to_fast_mode(self) -> None:
        agent = WritingChapterAgent(llm_client=RecordingSequenceLLM([]))

        self.assertEqual(agent.mode, "fast")
        self.assertEqual(agent.max_iterations, 1)

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

    def test_build_current_chapter_context_keeps_recent_blocks_and_tail(self) -> None:
        blocks = [
            ChapterBeat(
                block_id=f"ch_002.sc_001.b{index:03d}",
                chapter_id="ch_002",
                block_index=index,
                purpose=f"Block {index}",
                characters=["Hero"],
                active_lines=[],
                active_twists=[],
                scene_goal=f"Goal {index}",
                must_reveal=[],
                must_hide=[],
                new_value=f"New {index}",
                relationship_delta=f"Rel {index}",
                clue_delta=f"Clue {index}",
                emotional_tone="tight",
                end_state=f"End {index}",
                micro_hook=f"Hook {index}",
                text=f"第{index}块正文。这里是连续内容{index}。",
                status="committed",
                version=1,
            )
            for index in range(1, 6)
        ]

        payload = build_current_chapter_context("ch_002", blocks, max_blocks=4, tail_chars=20)

        self.assertEqual(len(payload["current_chapter_written_blocks_json"]), 4)
        self.assertEqual(payload["current_chapter_written_blocks_json"][0]["block_id"], "ch_002.sc_001.b002")
        self.assertEqual(payload["current_chapter_written_blocks_json"][-1]["block_id"], "ch_002.sc_001.b005")
        self.assertEqual(payload["current_chapter_written_blocks_json"][0]["new_value"], "New 2")
        self.assertEqual(payload["current_chapter_written_blocks_json"][-1]["micro_hook"], "Hook 5")
        self.assertTrue(payload["current_chapter_draft_tail"].endswith("第5块正文。这里是连续内容5。"))

    def test_writing_chapter_agent_happy_path(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                "Cold wind pressed against the vermilion steps. He bowed, but not low enough to forget himself.",
                "The order arrived before his first breath settled, and the transfer register stayed tucked beneath the eunuch's sleeve.",
                "When the old case title surfaced, she paused only once, and the pause sharpened every eye in the hall.",
                "By the time he reached the lower steps again, he already knew the first witness was dead.",
                *self._chapter_review_pass_sequence(),
                "Cold wind pressed against the vermilion steps. He bowed, counted the breaths between orders, and saw her pause only once at the old case title.",
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He returns to court under pressure.", "He finds a procedural opening."],
                        "reader_now_knows": ["The old verdict still stands.", "A transfer register may help him move indirectly."],
                        "reader_now_believes": ["She betrayed him but is hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He chooses disciplined action."],
                        "relationship_state": ["Their hostility gains a layer of calculation."],
                        "seeded_clues": ["She pauses at the old case term."],
                        "locked_truths": ["Her true motive remains hidden."],
                        "time_state": {"chapter_end_time": "return day, noon", "continuity_note": "He still carries the return pressure in his body."},
                    },
                    ensure_ascii=False,
                ),
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
        self.assertEqual(len(result.character_mindsets), 2)
        self.assertIn("vermilion steps", result.chapter_text)
        first_beat_prompt = llm.calls[4][-1].content
        second_beat_prompt = llm.calls[5][-1].content
        self.assertNotIn(self.twist.truth, first_beat_prompt)
        self.assertIn(self.twist.false_belief, first_beat_prompt)
        self.assertIn("[beat]", first_beat_prompt)
        self.assertIn('"goal":', first_beat_prompt)
        self.assertIn('"start":', first_beat_prompt)
        self.assertIn('"turn":', first_beat_prompt)
        self.assertIn('"end":', first_beat_prompt)
        self.assertIn('"avoid":', first_beat_prompt)
        self.assertIn("[target_length]", first_beat_prompt)
        self.assertNotIn("[Current block card]", first_beat_prompt)
        self.assertNotIn("current_chapter_written_blocks_json", first_beat_prompt)
        self.assertNotIn("character_reentry_mode:", first_beat_prompt)
        self.assertIn("Hero表层克制", first_beat_prompt)
        self.assertIn("No beat has landed yet.", first_beat_prompt)
        self.assertIn("Cold wind pressed against the vermilion steps", second_beat_prompt)

    def test_fast_mode_direct_pass_skips_patch_tools(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                *self._four_block_outputs(),
                self._targeted_review_pass("结构和连续性通过。"),
                self._targeted_review_pass("文风和人味通过。"),
                self._four_block_draft(),
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He returns to court under pressure."],
                        "reader_now_knows": ["The court still controls the opening move."],
                        "reader_now_believes": ["She is still hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He stays disciplined."],
                        "relationship_state": ["Their hostility sharpens."],
                        "seeded_clues": ["She pauses once."],
                        "locked_truths": ["Her true motive remains hidden."],
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        class RecordingToolRegistry:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls: list[str] = []

            def execute(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
                self.calls.append(tool_name)
                return self.inner.execute(tool_name, payload)

        registry = RecordingToolRegistry(ToolRegistry.build_default(llm_client=llm))
        agent = WritingChapterAgent(llm_client=llm, tool_registry=registry)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )

        self.assertTrue(result.final_judge["passed"])
        self.assertNotIn("build_chapter_patch_plan", registry.calls)
        self.assertNotIn("rewrite_blocks_by_plan", registry.calls)
        self.assertNotIn("rewrite_by_plan", registry.calls)

    def test_fast_mode_patch_success_rewrites_only_targeted_blocks(self) -> None:
        rewritten_block = "Paragraph two stops repeating the cold and pushes the negotiation forward under tighter restraint."
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                *self._four_block_outputs(),
                self._targeted_review_fail(
                    issue_id="I1",
                    problem_type="duplicate_emotion",
                    target_blocks=["ch_002.sc_001.b002"],
                    patch_hint="删掉重复冷意描写，直接推进谈判。",
                    reason="第二段重复铺陈寒意，推进不足。",
                ),
                self._targeted_review_pass("文风和人味通过。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                rewritten_block,
                self._patch_judge_pass(),
                self._merge_four_block_draft(rewritten_block),
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He turns public pressure into a procedural opening."],
                        "reader_now_knows": ["The register can move the case indirectly."],
                        "reader_now_believes": ["She is still hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He chooses a colder, more disciplined route."],
                        "relationship_state": ["Their hostility gains calculation."],
                        "seeded_clues": ["She pauses once."],
                        "locked_truths": ["Her true motive remains hidden."],
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        class RecordingToolRegistry:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls: list[str] = []

            def execute(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
                self.calls.append(tool_name)
                return self.inner.execute(tool_name, payload)

        registry = RecordingToolRegistry(ToolRegistry.build_default(llm_client=llm))
        agent = WritingChapterAgent(llm_client=llm, tool_registry=registry)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )

        block_map = {block.block_id: block.text for block in result.content_blocks}
        self.assertTrue(result.final_judge["passed"])
        self.assertIn("build_chapter_patch_plan", registry.calls)
        self.assertIn("rewrite_blocks_by_plan", registry.calls)
        self.assertNotIn("rewrite_by_plan", registry.calls)
        self.assertEqual(block_map["ch_002.sc_001.b001"], "Paragraph one keeps the opening pressure on him before he can settle his breath.")
        self.assertEqual(block_map["ch_002.sc_001.b002"], rewritten_block)
        self.assertEqual(block_map["ch_002.sc_001.b003"], "Paragraph three turns her pause into sharper relationship pressure.")
        self.assertEqual(block_map["ch_002.sc_001.b004"], "Paragraph four closes on the dead witness and a narrower road forward.")

    def test_patch_gate_rejects_pass_flag_when_remaining_issues_exist(self) -> None:
        result = WritingChapterAgent._normalize_patch_judge_result(
            judge_result={
                "pass": True,
                "remaining_issues": [
                    {
                        "problem_type": "handoff_weak",
                        "target_blocks": ["ch_002.sc_001.b002", "ch_002.sc_001.b003"],
                        "reason": "第二段到第三段的交接还是偏弱。",
                    }
                ],
                "newly_introduced_issues": [],
                "recommendation": "建议补一次patch，修正交接后再继续。",
            },
            patch_round=1,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["metrics"]["llm_pass_flag"], True)
        self.assertEqual(result["metrics"]["remaining_issue_count"], 1)
        self.assertIn("Patch judge requested follow-up", result["blocking_reasons"][-1])

    def test_patch_gate_accepts_explicit_llm_pass_when_recommendation_says_no_followup(self) -> None:
        result = WritingChapterAgent._normalize_patch_judge_result(
            judge_result={
                "pass": False,
                "passed": False,
                "llm_pass": True,
                "remaining_issues": [],
                "newly_introduced_issues": [],
                "recommendation": "当前补丁已完全解决所有目标问题，无需再补补丁，可保留当前版本。",
            },
            patch_round=1,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["metrics"]["llm_pass_flag"], True)
        self.assertEqual(result["metrics"]["remaining_issue_count"], 0)
        self.assertEqual(result["metrics"]["introduced_issue_count"], 0)
        self.assertEqual(result["blocking_reasons"], [])

    def test_patch_plan_detects_structural_reorder_or_delete_requests(self) -> None:
        structural = {
            "patch_targets": [
                {
                    "target_id": "ch_002.sc_001.b002",
                    "problem_type": "block_order",
                    "goal": "将 b002 移至 b004 之后，并删除重复的 b003。",
                    "instructions": ["重排顺序。", "移除 b003。"],
                }
            ]
        }
        local = {
            "patch_targets": [
                {
                    "target_id": "ch_002.sc_001.b002",
                    "problem_type": "duplicate_emotion",
                    "goal": "压缩重复情绪并加强交接。",
                    "instructions": ["删掉重复的冷意描写。"],
                }
            ]
        }

        self.assertTrue(WritingChapterAgent._patch_plan_requires_structural_rebuild(structural))
        self.assertFalse(WritingChapterAgent._patch_plan_requires_structural_rebuild(local))

    def test_beat_boundary_revision_trigger_flags_length_overrun(self) -> None:
        block = ChapterBeat(
            block_id="ch_002.sc_001.b001",
            chapter_id="ch_002",
            block_index=1,
            purpose="Open with pressure.",
            target_chars=500,
            end_state="The pressure lands.",
        )

        self.assertFalse(
            WritingChapterAgent._needs_beat_boundary_revision(
                block=block,
                block_text="短句落地。\n\n第二段收住。",
            )
        )
        self.assertTrue(
            WritingChapterAgent._needs_beat_boundary_revision(
                block=block,
                block_text="这是一段会明显超过字数上限的文字。" * 60,
            )
        )

    def test_candidate_strategies_prioritize_voice_and_relationship_cost(self) -> None:
        block = ChapterBeat(
            block_id="ch_002.sc_001.b003",
            chapter_id="ch_002",
            block_index=3,
            purpose="Reprice the relationship.",
            relationship_delta="She becomes more dangerous to read.",
            clue_delta="A pause becomes legible as clue pressure.",
            end_state="The room reads her silence differently.",
        )

        strategies = WritingChapterAgent._candidate_strategies_for_block(block)

        self.assertEqual(strategies[0], "voice_and_body_first")
        self.assertIn("relationship_cost_first", strategies)
        self.assertNotIn("balanced_scene", strategies)

    def test_surface_revision_prefers_lower_explanation_and_stronger_cost(self) -> None:
        original = "她知道自己不能退。她明白他不会信。她只是站着，说明今晚已经没有余地。"
        revised = "雪光压在她袖口上，她没退，只把那句称呼压得更低。案前的人都听见了，他也没法当作没听见。"
        self.assertTrue(
            WritingChapterAgent._should_keep_revised_block(
                original_text=original,
                revised_text=revised,
                original_surface=analyze_prose_surface(original),
                revised_surface=analyze_prose_surface(revised),
            )
        )

    def test_fast_mode_retries_when_patch_judge_sets_pass_true_but_requests_followup(self) -> None:
        first_rewrite = "Paragraph two is less blunt, but the handoff still frays at the edge."
        second_rewrite = "Paragraph two now carries the pressure cleanly into the next beat."
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                *self._four_block_outputs(),
                self._targeted_review_fail(
                    issue_id="I1",
                    problem_type="duplicate_emotion",
                    target_blocks=["ch_002.sc_001.b002"],
                    patch_hint="删掉重复冷意描写，直接推进谈判。",
                    reason="第二段重复铺陈寒意，推进不足。",
                ),
                self._targeted_review_pass("文风和人味通过。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                first_rewrite,
                self._patch_judge_inconsistent_pass("第二段到第三段的交接还是偏弱。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                second_rewrite,
                self._patch_judge_pass(),
                self._merge_four_block_draft(second_rewrite),
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He still forces a procedural opening."],
                        "reader_now_knows": ["The register can still move the case indirectly."],
                        "reader_now_believes": ["She is still hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He stays controlled."],
                        "relationship_state": ["The handoff now lands cleanly under pressure."],
                        "seeded_clues": ["She pauses once."],
                        "locked_truths": ["Her true motive remains hidden."],
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        class RecordingToolRegistry:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls: list[str] = []

            def execute(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
                self.calls.append(tool_name)
                return self.inner.execute(tool_name, payload)

        registry = RecordingToolRegistry(ToolRegistry.build_default(llm_client=llm))
        agent = WritingChapterAgent(llm_client=llm, tool_registry=registry)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )

        block_map = {block.block_id: block.text for block in result.content_blocks}
        self.assertTrue(result.final_judge["passed"])
        self.assertEqual(registry.calls.count("rewrite_blocks_by_plan"), 2)
        self.assertEqual(block_map["ch_002.sc_001.b002"], second_rewrite)
        self.assertEqual(result.final_judge["metrics"]["remaining_issue_count"], 0)

    def test_fast_mode_stops_after_patch_when_tool_marks_llm_pass_and_no_followup(self) -> None:
        rewrite = "Paragraph two keeps the pressure public; her courtesy turns colder, and his hand tightens before he answers."
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                *self._four_block_outputs(),
                self._targeted_review_fail(
                    issue_id="I1",
                    problem_type="flat_emotion",
                    target_blocks=["ch_002.sc_001.b002"],
                    patch_hint="删掉直白结论句，改成动作和称呼里的压迫。",
                    reason="第二段的关系变化说得太直。",
                ),
                self._targeted_review_pass("文风和人味通过。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                rewrite,
                json.dumps(
                    {
                        "pass": True,
                        "remaining_issues": [],
                        "newly_introduced_issues": [],
                        "recommendation": "当前补丁已完全解决所有目标问题，无需再补补丁，可保留当前版本。",
                    },
                    ensure_ascii=False,
                ),
                self._merge_four_block_draft(rewrite),
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He still forces a procedural opening."],
                        "reader_now_knows": ["The register can still move the case indirectly."],
                        "reader_now_believes": ["She is still hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He stays controlled."],
                        "relationship_state": ["The pressure now stays public and lands cleanly."],
                        "seeded_clues": ["She pauses once."],
                        "locked_truths": ["Her true motive remains hidden."],
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        class RecordingToolRegistry:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls: list[str] = []

            def execute(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
                self.calls.append(tool_name)
                return self.inner.execute(tool_name, payload)

        registry = RecordingToolRegistry(ToolRegistry.build_default(llm_client=llm))
        agent = WritingChapterAgent(llm_client=llm, tool_registry=registry)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )

        self.assertTrue(result.final_judge["passed"])
        self.assertEqual(registry.calls.count("rewrite_blocks_by_plan"), 1)
        stage_names = [entry.get("stage") for entry in result.stage_log]
        self.assertNotIn("patch_round_2", stage_names)
        self.assertNotIn("patch_round_2_no_targets", stage_names)

    def test_fast_mode_patch_failure_stops_and_suggests_deep(self) -> None:
        first_rewrite = "Paragraph two is shorter, but the handoff into the pause is still weak."
        second_rewrite = "Paragraph two tightens again, yet the next beat still feels slightly detached."
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                *self._four_block_outputs(),
                self._targeted_review_fail(
                    issue_id="I1",
                    problem_type="duplicate_emotion",
                    target_blocks=["ch_002.sc_001.b002"],
                    patch_hint="删掉重复冷意描写，直接推进谈判。",
                    reason="第二段重复铺陈寒意，推进不足。",
                ),
                self._targeted_review_pass("文风和人味通过。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                first_rewrite,
                self._patch_judge_fail("第二段到第三段的交接还是偏弱。"),
                self._patch_plan_single_target("ch_002.sc_001.b002"),
                second_rewrite,
                self._patch_judge_fail("第二段到第三段的交接仍然偏弱。"),
                self._merge_four_block_draft(second_rewrite),
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He still forces a procedural opening."],
                        "reader_now_knows": ["The public pressure remains unresolved."],
                        "reader_now_believes": ["She is still hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He stays controlled."],
                        "relationship_state": ["The handoff still feels tense and incomplete."],
                        "seeded_clues": ["She pauses once."],
                        "locked_truths": ["Her true motive remains hidden."],
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        class RecordingToolRegistry:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls: list[str] = []

            def execute(self, tool_name: str, payload: dict[str, object]) -> dict[str, object]:
                self.calls.append(tool_name)
                return self.inner.execute(tool_name, payload)

        registry = RecordingToolRegistry(ToolRegistry.build_default(llm_client=llm))
        agent = WritingChapterAgent(llm_client=llm, tool_registry=registry)
        result = agent.write_chapter(
            chapter_brief=self.chapter_brief,
            twist_designs=[self.twist],
            story_lines=[self.line],
            character_cards=self.characters,
            worldbuilding={"story_engine": {"world_rules": ["The imperial verdict cannot be challenged publicly."]}},
            actual_chapter_summaries=self.actual_summaries,
        )

        self.assertFalse(result.final_judge["passed"])
        self.assertTrue(result.requires_human_review)
        self.assertIn("deep", result.final_judge["recommendation"].lower())
        self.assertEqual(registry.calls.count("rewrite_blocks_by_plan"), 2)
        self.assertNotIn("rewrite_by_plan", registry.calls)

    def test_writing_chapter_agent_emits_live_stage_events(self) -> None:
        llm = RecordingSequenceLLM(
            [
                self.sanitized_context_json,
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                "Cold wind pressed against the vermilion steps. He bowed, but not low enough to forget himself.",
                "The order arrived before his first breath settled, and the transfer register stayed tucked beneath the eunuch's sleeve.",
                "When the old case title surfaced, she paused only once, and the room tilted toward that pause.",
                "Before he reached the lower steps, he learned the first witness was dead.",
                *self._chapter_review_pass_sequence(),
                "Cold wind pressed against the vermilion steps. He bowed, counted the breaths between orders, and saw her pause only once at the old case title.",
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He returns to court under pressure.", "He finds a procedural opening."],
                        "reader_now_knows": ["The old verdict still stands."],
                        "reader_now_believes": ["She betrayed him but is hiding something."],
                        "open_questions": ["Why did she pause?"],
                        "character_states": ["He chooses disciplined action."],
                        "relationship_state": ["Their hostility gains a layer of calculation."],
                        "seeded_clues": ["She pauses at the old case term."],
                        "locked_truths": ["Her true motive remains hidden."],
                        "time_state": {"chapter_end_time": "return day, noon"},
                    },
                    ensure_ascii=False,
                ),
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
        self.assertIn("write_chapter_full_done", stage_names)
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
                *self._character_mindset_jsons(),
                self._planned_blocks_json(),
                "He returned in silence, but the hall refused him even that small mercy.",
                "Every eye counted what he no longer had, and the clerk would not touch the register until the eunuch nodded.",
                "She paused at the old case name and looked away too quickly.",
                "By the time he stepped back into the wind, he had found the indirect route he needed, and it came with the news that the first witness would never speak again.",
                *self._chapter_review_pass_sequence(),
                "He returned in silence, and the hall gave him no mercy.",
                json.dumps(
                    {
                        "chapter_id": "ch_002",
                        "actual_events": ["He returns."],
                        "reader_now_knows": ["The hall is hostile."],
                        "reader_now_believes": ["She betrayed him."],
                        "open_questions": ["What is she hiding?"],
                        "character_states": ["He stays disciplined."],
                        "relationship_state": ["They stand on cold terms."],
                        "seeded_clues": ["A brief pause."],
                        "locked_truths": ["Her motive is hidden."],
                        "time_state": {"chapter_end_time": "return day, noon", "continuity_note": "He still stands inside unresolved hostility."},
                    },
                    ensure_ascii=False,
                ),
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
            chapter_briefs=[],
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
                    "time_label": "year 7 winter to year 8 spring",
                    "description": "He is forced away from the capital.",
                    "trigger": "Court pressure cuts him off.",
                    "consequence": "He loses his place and goes to the frontier.",
                    "affected_characters": ["Hero", "Heroine"],
                },
                {
                    "event_id": "EVT_0000",
                    "title": "Hero returns to the capital",
                    "time_label": "year 12 spring",
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
            {"character_name": "Hero", "milestone_list": [{"axis": "Revenge", "stages": ["Return under pressure", "Shift to indirect investigation"]}], "axes": []},
            {"character_name": "Heroine", "milestone_list": [{"axis": "Relationship", "stages": ["Misread", "Relationship repriced"]}], "axes": []},
        ]
        book.metadata["assistant_persona_prompt"] = "你要盯住场面压力，不要写成剧情说明。"
        book.metadata["style_request"] = "多视角"
        book.metadata["user_topic"] = "复仇与误解并行"
        book.metadata["total_word_target"] = "100万字左右"
        book.metadata["chapter_count_target"] = "120章左右"
        book.metadata["chapter_word_target"] = "5000字"
        book.metadata["pace_notes"] = "每章一个小钩子，2到3章一个关系/利益小冲突。"
        updated_book, chapter = writer.write_next_chapter(book=book)
        self.assertEqual(chapter.id, "ch_002")
        self.assertTrue(chapter.is_finalized)
        self.assertIn("hall gave him no mercy", chapter.final_text)
        self.assertEqual(chapter.scenes[0].summary, "Committed chapter beats")
        self.assertIn("He returned in silence", chapter.scenes[0].blocks[0].text)
        self.assertGreaterEqual(len(chapter.content_blocks), 4)
        self.assertEqual(len(chapter.character_mindsets), 2)
        self.assertEqual(updated_book.metadata["actual_chapter_summaries"][-1]["chapter_id"], "ch_002")
        self.assertIn("ch_002", updated_book.metadata["writing_chapter_runs"])
        self.assertGreaterEqual(len(updated_book.metadata["writing_chapter_runs"]["ch_002"]["content_blocks"]), 4)
        self.assertEqual(len(updated_book.metadata["writing_chapter_runs"]["ch_002"]["character_mindsets"]), 2)
        first_beat_prompt = llm.calls[4][-1].content
        self.assertIn("你要盯住场面压力，不要写成剧情说明。", first_beat_prompt)
        self.assertIn("多视角", first_beat_prompt)
        self.assertIn("5000字", first_beat_prompt)
        self.assertIn("每章一个小钩子", first_beat_prompt)
        self.assertIn("Hero表层克制", first_beat_prompt)

    def test_writer_persists_live_preview_to_runtime_store(self) -> None:
        writer = WriterAgent(llm_client=RecordingSequenceLLM([]), patch_executor=PatchExecutor())
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
            blueprint_id="bp_preview",
            premise=premise,
            characters=self.characters,
            volume_titles=["Volume 1"],
            chapter_briefs=[],
        )
        book = writer.create_book(blueprint=blueprint, source_query="query")
        book.metadata["story_blueprint"] = {
            "chapter_briefs": [self.chapter_brief.model_dump(mode="json")],
            "twist_designs": [],
            "story_lines": [],
        }

        class RuntimeStoreRecorder:
            def __init__(self) -> None:
                self.blocks: list[dict[str, object]] = []
                self.outputs: list[dict[str, object]] = []

            def save_chapter_block(self, **kwargs: object) -> None:
                self.blocks.append(kwargs)

            def save_run_output(self, **kwargs: object) -> None:
                self.outputs.append(kwargs)

        runtime_store = RuntimeStoreRecorder()
        dummy_context = SimpleNamespace(
            completed_chapter_memory_text="",
            step_1_story_foundation_text="",
            step_2_worldbuilding_text="",
            step_3_character_packets_text="",
            step_4_event_timeline_text="",
            step_5_character_milestones_text="",
            step_6_twists_text="",
            step_7_story_lines_text="",
            step_8_chapter_brief_text="",
            chapter_payload_text="",
            timeline_anchor_facts_text="",
            relevant_world_rules_text="",
            scene_character_context_text="",
            relationship_state_text="",
            style_card_text="",
        )
        committed_block = ChapterBeat(
            block_id="ch_002.sc_001.b001",
            chapter_id="ch_002",
            block_index=1,
            purpose="Open pressure",
            characters=["Hero"],
            active_lines=[],
            active_twists=[],
            scene_goal="Open the chapter",
            must_reveal=["A public order arrives."],
            must_hide=[],
            emotional_tone="tight",
            end_state="He is trapped in pressure.",
            text="The order landed before he could breathe.",
            status="committed",
            version=1,
        )

        def fake_write_chapter(self, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["on_block_committed"](committed_block)
            kwargs["on_chapter_preview_updated"](
                {
                    "chapter_id": "ch_002",
                    "chapter_title": "Cold Return",
                    "content_blocks": [committed_block.model_dump(mode="json")],
                    "final_text": "Full rewritten chapter preview.",
                    "final_version": 2,
                    "is_finalized": False,
                    "preview_mode": "chapter_rewrite",
                }
            )
            return ChapterExecutionResult(
                chapter_text="Full rewritten chapter preview.",
                content_blocks=[committed_block],
                actual_chapter_summary=ActualChapterSummary(
                    chapter_id="ch_002",
                    actual_events=["A public order interrupts him."],
                    reader_now_knows=["The hall still controls the opening move."],
                    reader_now_believes=["He must move indirectly."],
                    open_questions=["Who arranged the order?"],
                    character_states=["He stays controlled."],
                    relationship_state=["Pressure hardens the encounter."],
                    seeded_clues=[],
                    locked_truths=[],
                ),
                stage_log=[],
                review_reports={},
                final_judge={"passed": True},
                requires_human_review=False,
            )

        with patch.object(WriterAgent, "_writer_context_for_chapter", return_value=dummy_context), patch.object(
            WriterAgent, "_actual_summaries_from_book", return_value=[]
        ), patch.object(
            WriterAgent,
            "_aggregate_loop_critic_report",
            return_value=CriticReport(report_id="critic_preview", summary="ok", issues=[]),
        ), patch.object(WritingChapterAgent, "write_chapter", new=fake_write_chapter):
            _, chapter = writer.write_next_chapter(book=book, runtime_store=runtime_store, run_id="run_preview")

        self.assertEqual(chapter.final_text, "Full rewritten chapter preview.")
        self.assertEqual(len(runtime_store.blocks), 1)
        self.assertEqual(len(runtime_store.outputs), 1)
        self.assertEqual(runtime_store.outputs[0]["output_type"], "chapter_live_preview")
        self.assertEqual(runtime_store.outputs[0]["payload"]["preview_mode"], "chapter_rewrite")
        self.assertEqual(runtime_store.outputs[0]["payload"]["final_text"], "Full rewritten chapter preview.")


if __name__ == "__main__":
    unittest.main()
