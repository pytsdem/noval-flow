from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid
import unittest

from evals.romance.harness import RomanceEvalHarness
from evals.romance.models import RomanceJudgePayload, RomanceMetricDetail
from novel_flow.llm.base import LLMClient, LLMMessage


class SequenceLLM(LLMClient):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[list[LLMMessage]] = []

    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        self.calls.append(messages)
        if not self.outputs:
            raise AssertionError("No more fake outputs available")
        return self.outputs.pop(0)


def _case_payload(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "title": f"{case_id} title",
        "description": "Test romance eval case",
        "tags": ["test"],
        "genre_profile": "historical_romance_intrigue",
        "premise": {
            "title": "Test",
            "high_concept": "High concept",
            "theme_statement": "Theme",
            "story_summary": "Summary",
            "genre": "historical romance",
            "target_style": "restrained",
            "emotional_hook": "Hook",
            "central_conflict": "Conflict",
            "core_hook": "Core hook",
            "escalation_path": ["one"],
            "twist_blueprint": ["twist"],
            "ending_payoff": "Payoff",
            "selling_points": ["chemistry"],
        },
        "chapter_brief": {
            "chapter_id": "ch_002",
            "title": "Cold Return",
            "chapter_type": "opening",
            "active_lines": ["line_case"],
            "active_twists": ["twist_01"],
            "summary": "He returns under pressure and chooses an indirect path.",
            "incoming_hook": "He returned to the capital.",
            "opening_hook": "An imperial order lands before he can speak.",
            "core_scene": "He must receive the order in public before he can act.",
            "chapter_object": "Transfer register",
            "reader_emotion": "Readers should feel pressure and unresolved attraction.",
            "reader_belief": "Readers believe she betrayed him.",
            "allowed_info": ["He lost the old case."],
            "allowed_clues": ["She pauses at the old case term."],
            "forbidden": ["Do not reveal her true motive."],
            "world_limit": "He cannot overturn the verdict in public.",
            "character_focus": ["Hero", "Heroine"],
            "character_shift": "He moves from anger to restraint.",
            "relationship_reprice": "She feels less like a traitor and more like a controlled threat.",
            "emotional_turn": "Hatred becomes strategic tension.",
            "backstory_trigger": "",
            "scene_engine": "opening_pressure",
            "clue_reveal_mechanism": {
                "style": "natural_exposure",
                "pressure_source": "court pressure",
                "surface_trigger": "old case term",
                "first_noticer": "Hero",
                "owner_reaction": "Heroine avoids explaining"
            },
            "character_reentry_focus": {
                "Heroine": "Use restraint to re-establish presence."
            },
            "human_pain_anchor": "He still carries road dust and public humiliation.",
            "romance_seed": "She avoids his eyes too fast.",
            "small_payoff": "He gets one procedural opening.",
            "ending_pull": "The first witness is already dead.",
            "info_budget": "target=2800-3400"
        },
        "twist_designs": [
            {
                "twist_id": "twist_01",
                "title": "Hidden motive",
                "false_belief": "Readers think she betrayed him.",
                "truth": "She framed him to save him.",
                "reader_alignment": "Readers side with him.",
                "seed_from": "ch_001",
                "reveal_at": "ch_018",
                "allowed_clues": ["She pauses once."],
                "forbidden_reveals": ["Do not reveal she saved him."],
                "pov_lock": "No true inner thought before reveal.",
                "related_characters": ["Heroine"],
                "payoff_effect": "Relationship gets repriced."
            }
        ],
        "story_lines": [
            {
                "line_id": "line_case",
                "name": "Old case",
                "line_type": "mystery",
                "visibility": "visible",
                "core_question": "How can he reopen the case indirectly?",
                "reader_hook_mode": "pressure",
                "start_state": "He is blocked publicly.",
                "midpoint_shift": "A clue changes how readers see her.",
                "end_state": "The truth is re-evaluated.",
                "carried_twists": ["twist_01"],
                "line_rules": ["Only indirect routes early."]
            }
        ],
        "character_cards": [
            {
                "name": "Hero",
                "role": "dismissed commander",
                "occupation": "former general",
                "appearance": "travel dust still on his cuffs",
                "personality": "controlled under pressure",
                "initial_state": "He wants revenge but cannot act directly.",
                "motivation": "reopen the old case",
                "behavior_pattern": "cuts his own words short",
                "relationships": "Hostile unresolved history with Heroine"
            },
            {
                "name": "Heroine",
                "role": "court witness",
                "occupation": "noblewoman",
                "appearance": "sleeves held too steady",
                "personality": "calm and restrained",
                "initial_state": "She does not explain the past.",
                "motivation": "protect a secret",
                "behavior_pattern": "answers indirectly",
                "relationships": "Hostile unresolved history with Hero"
            }
        ],
        "worldbuilding": {
            "story_engine": {
                "world_rules": [
                    "The imperial verdict cannot be challenged publicly."
                ]
            },
            "event_timeline": [
                {
                    "event_id": "evt_001",
                    "title": "He returned to the capital.",
                    "time_label": "today",
                    "description": "He returned under pressure.",
                    "trigger": "return order",
                    "consequence": "He must face the court again.",
                    "affected_characters": ["Hero", "Heroine"]
                }
            ]
        },
        "character_milestones": [
            {
                "character_name": "Hero",
                "milestone_list": ["Return under pressure", "Shift to indirect investigation"],
                "axes": ["revenge", "restraint"]
            }
        ],
        "actual_chapter_summaries": [
            {
                "chapter_id": "ch_001",
                "actual_events": ["He returned to the capital."],
                "reader_now_knows": ["The old verdict still stands."],
                "reader_now_believes": ["She betrayed him."],
                "open_questions": ["Why did she testify?"],
                "character_states": ["He is under public pressure."],
                "relationship_state": ["They face each other like enemies."],
                "seeded_clues": ["She paused once."],
                "locked_truths": ["Her real motive is still hidden."],
                "time_state": {
                    "chapter_end_time": "return day, morning",
                    "continuity_note": "Public pressure is still active."
                }
            }
        ],
        "prior_character_mindsets": [
            {
                "character_id": "Hero",
                "character_name": "Hero",
                "surface_emotion": "cold restraint",
                "core_emotion": "wound-tightened anger",
                "primary_goal": "take one step into the old case",
                "hidden_need": "see whether she regrets anything",
                "fear": "lose control first",
                "attitude_to_key_others": {
                    "Heroine": "警惕又在意"
                },
                "self_control_level": "high",
                "breaking_point_hint": "If she keeps calling him by title, he will edge toward sharper aggression.",
                "known_but_unspoken": "He cares too much about how she looks at him.",
                "misbelief": "He thinks all her restraint is calculation.",
                "chapter_change_hint": "His judgment of her will become less stable."
            }
        ],
        "goals": {
            "chapter_goal": "Push the old case and the reunion pressure.",
            "emotional_goal": "Land public humiliation plus unresolved attraction.",
            "relationship_goal": "Move them from pure hostility to dangerous calculation.",
            "hook_goal": "Open with public pressure and end on a harder clue.",
            "continuation_drive": "Make the reader want the next investigation beat."
        },
        "context_overrides": {
            "assistant_persona_prompt": "Prioritize relationship movement over polish.",
            "writing_requirements": {
                "target_words": "2800-3400"
            },
            "reference_pack": "test references",
            "previous_chapter_full_text": "He returned. She heard his name and did not sleep.",
            "scene_character_context_text": "[Scene character context]\\nHero and Heroine are both under pressure.",
            "relationship_state_text": "[Relationship state]\\nHostility with unresolved pull."
        }
    }


def _sanitized_context_json() -> str:
    return json.dumps(
        {
            "chapter_id": "ch_002",
            "selection_summary_text": "relevant roles and twists selected",
            "time_anchor_text": "absolute=return day morning; relative_to_previous=immediately after return; must_not_conflict=keep the public pressure on the body",
            "chapter_visible_context_text": "reader_should_know=old verdict stands; reader_should_believe=she betrayed him; allowed_clues=she pauses once",
            "completed_chapter_memory_text": "[Completed chapter memory]\\nch_001\\n- Relationship state: They face each other like enemies.",
            "step_1_story_foundation_text": "High concept and conflict",
            "step_3_character_packets_text": "Hero and Heroine packets",
            "step_5_character_milestones_text": "Relevant milestone packets",
            "step_6_twists_text": "Active twist packets",
            "step_7_story_lines_text": "Active story line packets",
            "step_8_chapter_brief_text": "Current chapter contract packet",
            "scene_character_context_text": "[Scene character context]\\nHero under pressure\\nHeroine hiding a reaction",
            "relationship_state_text": "[Relationship state]\\nHostility with unresolved pull"
        },
        ensure_ascii=False,
    )


def _mindset_json(name: str, other: str) -> str:
    return json.dumps(
        {
            "character_id": name,
            "character_name": name,
            "surface_emotion": f"{name}表层克制",
            "core_emotion": f"{name}心里绷紧",
            "primary_goal": f"{name}想先稳住眼前局面",
            "hidden_need": f"{name}需要确认{other}的真实立场",
            "fear": f"{name}害怕先失控",
            "attitude_to_key_others": {
                other: f"对{other}既警惕又在意"
            },
            "self_control_level": "medium_high",
            "breaking_point_hint": f"{name}一旦被逼到没有退路就会露出裂口",
            "known_but_unspoken": f"{name}知道真正危险不止表面命令",
            "misbelief": f"{name}误判了{other}此刻的真实意图",
            "chapter_change_hint": f"{name}会从纯敌意走向更复杂的提防"
        },
        ensure_ascii=False,
    )


def _planned_blocks_json() -> str:
    blocks = {
        "blocks": [
            {
                "block_id": "ch_002.sc_001.b001",
                "chapter_id": "ch_002",
                "block_index": 1,
                "purpose": "Open with public pressure.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Land the imperial order before he can recover.",
                "must_reveal": ["An imperial order lands before he can speak."],
                "must_hide": ["Do not reveal her true motive."],
                "emotional_tone": "Readers should feel the public pressure close around him.",
                "end_state": "He is forced into the court pressure.",
                "human_reaction_target": ["Show one bodily restraint before he speaks."],
                "cost_shift": "He loses the chance to choose his own opening move.",
                "reader_feeling_target": "Readers should feel public pressure.",
                "paragraph_budget": "建议 2~5 个自然段；单段尽量 30~120 中文字；超过 180 中文字视为过长",
                "paragraph_shape": ["主动作", "配角反应", "情绪泄露"],
                "micro_hook": "He must answer the pressure before he can reclaim control.",
                "turn_type": "pressure_rise",
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "reaction_line",
                    "surface_function": "Let the pressure land",
                    "hidden_function": "Show he protects his own bearing",
                    "must_reveal_about_character": "He still guards his dignity",
                    "must_not_do": ["Do not turn it into a slogan."],
                    "preferred_shape": "短、准、留余味"
                },
                "style_risk_guard": ["Do not open with summary prose."],
                "character_reentry_mode": {
                    "target_character": "Heroine",
                    "identity_already_known": True,
                    "reentry_strategy": "Use the court's reaction to wake reader memory.",
                    "first_signal": "Her sleeves are held too steady.",
                    "first_emotional_focus": "She wants to hide her reaction.",
                    "must_avoid": ["Do not re-explain her identity."]
                },
                "text": "",
                "status": "draft",
                "version": 1
            },
            {
                "block_id": "ch_002.sc_001.b002",
                "chapter_id": "ch_002",
                "block_index": 2,
                "purpose": "Push the chapter object into negotiation.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Make the register matter through live pressure.",
                "must_reveal": ["Transfer register", "He finds a procedural opening."],
                "must_hide": ["Do not reveal her true motive."],
                "emotional_tone": "Hatred becomes strategic tension.",
                "end_state": "He gains a narrow procedural path.",
                "human_reaction_target": ["Show practical calculation under pressure."],
                "cost_shift": "He must ask through the same order that humiliates him.",
                "reader_feeling_target": "Readers should feel progress costs more pressure.",
                "paragraph_budget": "建议 2~5 个自然段；单段尽量 30~120 中文字；超过 180 中文字视为过长",
                "paragraph_shape": ["主动作", "关系压力", "代价落点"],
                "micro_hook": "The register can move the case, but asking for it exposes him more.",
                "turn_type": "pressure_rise",
                "character_anchor_line": {
                    "owner": "Heroine",
                    "form": "dialogue",
                    "surface_function": "Answer the request",
                    "hidden_function": "Hide the real reason she hesitates",
                    "must_reveal_about_character": "She protects herself through restraint",
                    "must_not_do": ["Do not explain her heart directly."],
                    "preferred_shape": "短、准、留余味"
                },
                "style_risk_guard": ["Do not turn dialogue into pure exposition."],
                "text": "",
                "status": "draft",
                "version": 1
            },
            {
                "block_id": "ch_002.sc_001.b003",
                "chapter_id": "ch_002",
                "block_index": 3,
                "purpose": "Reprice the relationship and close on a harder hook.",
                "characters": ["Hero", "Heroine"],
                "active_lines": ["line_case"],
                "active_twists": ["twist_01"],
                "scene_goal": "Turn her pause into sharper relationship pressure and ending pull.",
                "must_reveal": ["She pauses at the old case term.", "The first witness is already dead."],
                "must_hide": ["Do not reveal her true motive."],
                "emotional_tone": "Cold hostility gains a layer of charge.",
                "end_state": "The relationship feels more dangerous and the next step narrows.",
                "human_reaction_target": ["Let at least one character fail composure for a beat."],
                "cost_shift": "He gains a clue but loses any easy road forward.",
                "reader_feeling_target": "Readers should feel the changed relationship pressure and the hard next-step pull.",
                "paragraph_budget": "建议 2~5 个自然段；单段尽量 30~120 中文字；超过 180 中文字视为过长",
                "paragraph_shape": ["关系压力", "回避与停顿", "尾钩"],
                "micro_hook": "Nobody will explain the pause, and the dead witness makes the next step urgent.",
                "turn_type": "clue_shift",
                "character_anchor_line": {
                    "owner": "Hero",
                    "form": "dialogue",
                    "surface_function": "Land the closing threat",
                    "hidden_function": "Show he is more shaken than he wants to be",
                    "must_reveal_about_character": "His control is becoming costly",
                    "must_not_do": ["Do not explain it afterwards."],
                    "preferred_shape": "短、准、留余味"
                },
                "style_risk_guard": ["Do not over-explain the clue."],
                "clue_reveal_mechanism": {
                    "clue": "She pauses at the old case term.",
                    "style": "natural_exposure",
                    "pressure_source": "court pressure",
                    "surface_trigger": "the old case title",
                    "first_noticer": "Hero",
                    "owner_reaction": "Heroine avoids explaining"
                },
                "text": "",
                "status": "draft",
                "version": 1
            }
        ]
    }
    return json.dumps(blocks, ensure_ascii=False)


def _review_pass(summary: str = "通过") -> str:
    return json.dumps({"pass": True, "issues": [], "summary": summary}, ensure_ascii=False)


def _actual_summary() -> str:
    return json.dumps(
        {
            "chapter_id": "ch_002",
            "actual_events": [
                "He returns to court under pressure.",
                "He wins one narrow path into the old case."
            ],
            "reader_now_knows": [
                "The register can move the case indirectly.",
                "The first witness is already dead."
            ],
            "reader_now_believes": [
                "She still hides something important."
            ],
            "open_questions": [
                "Why did she pause?"
            ],
            "character_states": [
                "He chooses colder restraint."
            ],
            "relationship_state": [
                "Their hostility gains a layer of dangerous calculation."
            ],
            "seeded_clues": [
                "She pauses at the old case term."
            ],
            "locked_truths": [
                "Her motive remains hidden."
            ],
            "time_state": {
                "chapter_end_time": "return day, noon",
                "continuity_note": "Public pressure and the emotional residue both remain active."
            }
        },
        ensure_ascii=False,
    )


def _judge_payload(
    *,
    tension: float = 8.4,
    progression: float = 7.9,
    resonance: float = 8.1,
    male: float = 8.3,
    female: float = 7.8,
    chemistry: float = 8.5,
    opening: float = 8.2,
    ending: float = 8.6,
    continuity: float = 7.7,
    redundancy: float = 7.1,
    mind: float = 7.8,
    genre_fit: float = 8.0,
) -> str:
    def metric(score: float, reason: str, evidence: str, hint: str) -> dict:
        return {
            "score": score,
            "reason": reason,
            "evidence_summary": evidence,
            "improvement_hint": hint,
            "source": "llm"
        }

    payload = {
        "romance_tension": metric(tension, "拉扯感成立。", "两人在公开压力下互相试探。", "让中段再多一次更明确的靠近/拉开。"),
        "relationship_progression": metric(progression, "关系有变化。", "敌意里出现更危险的牵制。", "把变化再落到一个更不可逆的动作上。"),
        "emotional_resonance": metric(resonance, "情绪有余波。", "动作、停顿和视角感受都在工作。", "减少一处解释，换成更具体的身体反应。"),
        "male_lead_attraction": metric(male, "男主有锋利记忆点。", "他在受压时的冷硬反应很立。", "再给一处更私人但克制的泄露。"),
        "female_lead_attraction": metric(female, "女主克制但有主体性。", "她的回避和应对都有个人性格。", "让她的反击更再多半步。"),
        "lead_pair_chemistry": metric(chemistry, "双人化学反应足够强。", "同场时每句都带着旧账和试探。", "让结尾前再出现一次更明显的电流。"),
        "opening_hook": metric(opening, "开头抓人快。", "开篇立刻有公开压力和关系异样感。", "第一段再压缩一点说明。"),
        "ending_hook": metric(ending, "尾钩有效。", "结尾把旧案和关系一起推向下一章。", "让尾句更利一点。"),
        "continuity": metric(continuity, "承接基本自然。", "前章余波仍在，人物状态没有断。", "中段过渡再紧一点。"),
        "redundancy": metric(redundancy, "有轻微重复。", "同一种防备被解释了两次。", "压缩重复的防备描写，换成新的试探动作。"),
        "mind_state_consistency": metric(mind, "角色心智基本稳定。", "高自控与误判都还能对上。", "避免让高自控角色过早说太满。"),
        "genre_fit": metric(genre_fit, "类型承诺基本兑现。", "公开压力、误读和旧案线服务了关系重新定价。", "避免把权谋压力写成替代 romance 的主体。"),
        "diagnosis": {
            "strengths": [
                "男女主对手戏有持续电流感",
                "结尾钩子能自然带向下一章"
            ],
            "weaknesses": [
                "中段有一处关系压力重复解释",
                "女主主动性还能再往前推半步"
            ],
            "improvement_hints": [
                "压缩重复的防备描写",
                "在中段增加一次更明确的关系状态变化"
            ]
        }
    }
    return json.dumps(payload, ensure_ascii=False)


def _generation_sequence() -> list[str]:
    beat_outputs = [
        "殿门一开，寒意先贴着谢临川的靴面往上爬。圣旨未落地，殿中视线已经先压到他肩上。",
        "他接旨时连指节都稳得过分，偏偏在求取档册时把每个字都压得更慢。那条窄得可怜的查档口子，也只能从这道命令里硬生生抠出来。",
        "沈知微在“旧案”两个字上短了一拍，袖口绷出的褶被他看得清楚。等殿外消息送到时，昨夜替旧案抄档的书吏已经死了。",
    ]
    chapter_text = (
        "殿门一开，寒意先贴着谢临川的靴面往上爬。圣旨念到旧案时，沈知微终于抬眼，那一眼像刀锋轻轻擦过，又立刻被礼数收回。\n\n"
        "他接旨时连指节都稳得过分，偏偏在求取档册时把每个字都压得更慢。她回话极冷，句句都守规矩，却在“旧案”两个字上短了一拍。\n\n"
        "谢临川看见那一拍，也看见她袖口绷出的褶。等他拿到那条窄得可怜的查档口子，殿外风雪里已经有人送来消息：昨夜替旧案抄档的书吏死了。"
    )
    return [
        _sanitized_context_json(),
        _mindset_json("Hero", "Heroine"),
        _mindset_json("Heroine", "Hero"),
        _planned_blocks_json(),
        *beat_outputs,
        _review_pass("结构通过"),
        _review_pass("文风通过"),
        chapter_text,
        _actual_summary(),
        _judge_payload(),
    ]


class RomanceEvalHarnessTests(unittest.TestCase):
    def _workspace_dir(self) -> Path:
        root = (Path.cwd() / "data" / f"romance_eval_test_{uuid.uuid4().hex[:8]}").resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_cases(self, root: Path, case_ids: list[str]) -> None:
        cases_dir = root / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)
        for case_id in case_ids:
            payload = _case_payload(case_id)
            (cases_dir / f"{case_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def test_single_case_run_generates_reports(self) -> None:
        root = self._workspace_dir()
        self._write_cases(root, ["romance_case_single"])
        reports_root = root / "reports"
        llm = SequenceLLM(_generation_sequence())
        harness = RomanceEvalHarness(
            llm_client=llm,
            case_dir=root / "cases",
            reports_root=reports_root,
        )

        summary, diff = harness.run(label="single_case")

        self.assertIsNone(diff)
        self.assertEqual(len(summary.case_results), 1)
        run_dir = Path(summary.run_dir)
        self.assertTrue((run_dir / "chapter_eval_summary.json").exists())
        self.assertTrue((run_dir / "chapter_eval_report.md").exists())
        self.assertTrue((run_dir / "summary.json").exists())
        case_result = summary.case_results[0]
        self.assertEqual(case_result.verdict, "pass")
        self.assertIn("romance_tension_score", case_result.scores)
        self.assertIn("genre_fit_score", case_result.scores)
        self.assertIn("historical_romance_intrigue", llm.calls[-1][-1].content)
        self.assertIn("restrained_angst", llm.calls[-1][-1].content)
        self.assertTrue(Path(case_result.artifacts.final_text_txt).exists())
        self.assertTrue(Path(case_result.artifacts.final_text_txt).name == "chapter_text__final.txt")
        self.assertGreater(case_result.cost_metrics.llm_calls, 0)
        self.assertEqual(summary.verdict_counts.get("pass"), 1)

    def test_multi_case_run_supports_diff_report(self) -> None:
        root = self._workspace_dir()
        self._write_cases(root, ["romance_case_a", "romance_case_b"])
        reports_root = root / "reports"

        baseline_llm = SequenceLLM(_generation_sequence() + _generation_sequence())
        baseline = RomanceEvalHarness(
            llm_client=baseline_llm,
            case_dir=root / "cases",
            reports_root=reports_root,
        )
        baseline_summary, _ = baseline.run(label="baseline")

        improved_sequence = _generation_sequence()
        improved_sequence[-1] = _judge_payload(tension=8.9, progression=8.5, ending=8.9, redundancy=7.6)
        improved_baseline = _generation_sequence()
        improved_baseline[-1] = _judge_payload(tension=8.9, progression=8.5, ending=8.9, redundancy=7.6)
        candidate_llm = SequenceLLM(improved_sequence + improved_baseline)
        candidate = RomanceEvalHarness(
            llm_client=candidate_llm,
            case_dir=root / "cases",
            reports_root=reports_root,
        )
        candidate_summary, diff = candidate.run(
            label="candidate",
            compare_to=baseline_summary.report_json,
        )

        self.assertIsNotNone(diff)
        assert diff is not None
        self.assertTrue((Path(candidate_summary.run_dir) / "chapter_eval_diff_vs_baseline.md").exists())
        self.assertTrue((Path(candidate_summary.run_dir) / "diff_vs_baseline.md").exists())
        self.assertGreater(
            diff.average_score_deltas["romance_tension_score"].delta,
            0.0,
        )
        self.assertEqual(len(candidate_summary.case_results), 2)

    def test_judge_failure_does_not_crash_run(self) -> None:
        root = self._workspace_dir()
        self._write_cases(root, ["romance_case_failure"])
        reports_root = root / "reports"
        outputs = _generation_sequence()[:-1] + [
            json.dumps({"bad": True}, ensure_ascii=False),
            json.dumps({"bad": True}, ensure_ascii=False),
            json.dumps({"bad": True}, ensure_ascii=False),
        ]
        llm = SequenceLLM(outputs)
        harness = RomanceEvalHarness(
            llm_client=llm,
            case_dir=root / "cases",
            reports_root=reports_root,
        )

        summary, diff = harness.run(label="judge_failure")

        self.assertIsNone(diff)
        self.assertEqual(len(summary.case_results), 1)
        case_result = summary.case_results[0]
        self.assertTrue(case_result.errors)
        self.assertEqual(case_result.verdict, "blocked")
        self.assertEqual(case_result.metrics["romance_tension_score"].source, "fallback")
        self.assertEqual(case_result.metrics["redundancy_score"].source, "rule")
        self.assertTrue(any(target.issue_type == "judge_reliability" for target in case_result.optimization_targets))

    def test_low_guard_scores_produce_blockers_and_targets(self) -> None:
        root = self._workspace_dir()
        self._write_cases(root, ["romance_case_blocked"])
        reports_root = root / "reports"
        outputs = _generation_sequence()
        outputs[-1] = _judge_payload(
            tension=5.2,
            progression=3.2,
            resonance=5.1,
            opening=4.1,
            ending=3.4,
            continuity=3.5,
            redundancy=4.3,
            mind=2.9,
        )
        llm = SequenceLLM(outputs)
        harness = RomanceEvalHarness(
            llm_client=llm,
            case_dir=root / "cases",
            reports_root=reports_root,
        )

        summary, _ = harness.run(label="blocked_case")

        case_result = summary.case_results[0]
        self.assertEqual(case_result.verdict, "blocked")
        flag_types = {flag.flag_type for flag in case_result.hard_fail_flags}
        self.assertIn("relationship_progression_break", flag_types)
        self.assertIn("continuity_break", flag_types)
        self.assertIn("mind_state_break", flag_types)
        target_modules = {target.target_module for target in case_result.optimization_targets}
        self.assertIn("prompts/writer/step_8_chapter_briefs.txt", target_modules)
        self.assertIn("prompts/writer/build_character_mindset.txt", target_modules)
        self.assertIn("prompts/writer/write_chapter_full.txt", target_modules)
        self.assertEqual(summary.blocked_case_ids, ["romance_case_blocked"])

    def test_redundancy_rule_cannot_rescue_low_judge_score(self) -> None:
        judge = RomanceJudgePayload.model_validate_json(_judge_payload(redundancy=2.0))
        rule_redundancy = RomanceMetricDetail(
            score=10.0,
            reason="规则层未命中重复。",
            evidence_summary="未检测到高相似段落。",
            improvement_hint="保持段落功能分布差异。",
            source="rule",
        )
        rule_anti_slop = RomanceMetricDetail(
            score=10.0,
            reason="规则层未命中直白心理解释。",
            evidence_summary="未检测到明显直白心理标签。",
            improvement_hint="保持动作化表达。",
            source="rule",
        )

        metrics = RomanceEvalHarness._judge_metrics_to_core(
            judge=judge,
            rule_redundancy=rule_redundancy,
            rule_anti_slop=rule_anti_slop,
        )

        self.assertLessEqual(metrics["redundancy_score"].score, judge.redundancy.score)
        self.assertEqual(metrics["redundancy_score"].score, 2.0)

    def test_anti_slop_rule_can_pull_down_hybrid_redundancy(self) -> None:
        judge = RomanceJudgePayload.model_validate_json(_judge_payload(redundancy=8.0))
        rule_redundancy = RomanceMetricDetail(
            score=9.5,
            reason="规则层未命中高相似重复。",
            evidence_summary="未检测到高相似段落。",
            improvement_hint="保持段落功能差异。",
            source="rule",
        )
        rule_anti_slop = RomanceMetricDetail(
            score=4.0,
            reason="存在明显直白心理解释。",
            evidence_summary="“她知道自己不能露怯”与“这让她更明白”反复出现。",
            improvement_hint="把解释句改成动作和潜台词。",
            source="rule",
        )

        metrics = RomanceEvalHarness._judge_metrics_to_core(
            judge=judge,
            rule_redundancy=rule_redundancy,
            rule_anti_slop=rule_anti_slop,
        )

        self.assertLess(metrics["redundancy_score"].score, judge.redundancy.score)
        self.assertIn("Anti-slop", metrics["redundancy_score"].evidence_summary)

    def test_non_romance_pressure_gets_romance_mode_blocker(self) -> None:
        judge = RomanceJudgePayload.model_validate_json(
            _judge_payload(
                tension=0.0,
                progression=0.0,
                resonance=0.0,
                male=2.0,
                female=2.0,
                chemistry=0.0,
                opening=3.0,
                ending=0.0,
                continuity=8.0,
                redundancy=4.0,
                mind=9.0,
            )
        )
        rule_redundancy = RomanceMetricDetail(
            score=6.2,
            reason="规则层检测到少量重复。",
            evidence_summary="结尾处有重复威胁句式。",
            improvement_hint="把重复威胁替换成新的关系代价。",
            source="rule",
        )
        rule_anti_slop = RomanceMetricDetail(
            score=7.5,
            reason="直白心理解释较少。",
            evidence_summary="未检测到明显解释句。",
            improvement_hint="继续保持潜台词表达。",
            source="rule",
        )
        metrics = RomanceEvalHarness._judge_metrics_to_core(
            judge=judge,
            rule_redundancy=rule_redundancy,
            rule_anti_slop=rule_anti_slop,
        )
        verdict, flags, targets = RomanceEvalHarness._derive_actionability(
            metrics=metrics,
            breakdowns={
                "male_lead_attraction": judge.male_lead_attraction,
                "female_lead_attraction": judge.female_lead_attraction,
                "lead_pair_chemistry": judge.lead_pair_chemistry,
                "opening_hook_score": judge.opening_hook,
                "ending_hook_score": judge.ending_hook,
                "judge_redundancy_score": judge.redundancy,
                "rule_redundancy_score": rule_redundancy,
                "rule_anti_slop_score": rule_anti_slop,
                "rule_pronoun_lead_score": RomanceMetricDetail(
                    score=4.5,
                    reason="句首代词过密。",
                    evidence_summary="句首代词占比 30%。",
                    improvement_hint="改写句首。",
                    source="rule",
                ),
                "rule_explanation_density_score": RomanceMetricDetail(
                    score=4.8,
                    reason="解释句偏多。",
                    evidence_summary="解释句占比 25%。",
                    improvement_hint="减少解释句。",
                    source="rule",
                ),
            },
            diagnosis=judge.diagnosis,
            judge_errors=[],
        )

        self.assertEqual(verdict, "blocked")
        flag_types = {flag.flag_type for flag in flags}
        self.assertIn("romance_mode_miss", flag_types)
        issue_types = {target.issue_type for target in targets}
        self.assertIn("romance_mode_miss", issue_types)

    def test_summary_like_text_gets_summary_prose_blocker(self) -> None:
        judge = RomanceJudgePayload.model_validate_json(
            _judge_payload(
                tension=0.0,
                progression=0.0,
                resonance=0.0,
                male=0.0,
                female=0.0,
                chemistry=0.0,
                opening=0.0,
                ending=1.0,
                continuity=2.0,
                redundancy=0.0,
                mind=5.0,
            )
        )
        rule_redundancy = RomanceMetricDetail(
            score=9.5,
            reason="规则层未检测到高相似段落，但 judge 已判断为严重重复。",
            evidence_summary="表面看段落很短，实则反复复述同一判断。",
            improvement_hint="把重复标签替换成具体对手戏。",
            source="rule",
        )
        rule_anti_slop = RomanceMetricDetail(
            score=5.0,
            reason="存在解释性总结句。",
            evidence_summary="“这让她更明白”类句式过多。",
            improvement_hint="把总结句改写成动作和停顿。",
            source="rule",
        )
        metrics = RomanceEvalHarness._judge_metrics_to_core(
            judge=judge,
            rule_redundancy=rule_redundancy,
            rule_anti_slop=rule_anti_slop,
        )
        verdict, flags, targets = RomanceEvalHarness._derive_actionability(
            metrics=metrics,
            breakdowns={
                "male_lead_attraction": judge.male_lead_attraction,
                "female_lead_attraction": judge.female_lead_attraction,
                "lead_pair_chemistry": judge.lead_pair_chemistry,
                "opening_hook_score": judge.opening_hook,
                "ending_hook_score": judge.ending_hook,
                "judge_redundancy_score": judge.redundancy,
                "rule_redundancy_score": rule_redundancy,
                "rule_anti_slop_score": rule_anti_slop,
                "rule_pronoun_lead_score": RomanceMetricDetail(
                    score=4.2,
                    reason="句首代词过密。",
                    evidence_summary="句首代词占比 35%。",
                    improvement_hint="改写句首。",
                    source="rule",
                ),
                "rule_explanation_density_score": RomanceMetricDetail(
                    score=4.0,
                    reason="解释句偏多。",
                    evidence_summary="解释句占比 33%。",
                    improvement_hint="减少解释句。",
                    source="rule",
                ),
            },
            diagnosis=judge.diagnosis,
            judge_errors=[],
        )

        self.assertEqual(verdict, "blocked")
        flag_types = {flag.flag_type for flag in flags}
        self.assertIn("summary_prose_fail", flag_types)
        issue_types = {target.issue_type for target in targets}
        self.assertIn("summary_prose_fail", issue_types)


if __name__ == "__main__":
    unittest.main()
