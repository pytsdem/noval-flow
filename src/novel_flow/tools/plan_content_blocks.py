from __future__ import annotations

import json
import re

from novel_flow.models.schemas import (
    ChapterBrief,
    CharacterAnchorLine,
    CharacterReentryMode,
    ClueRevealMechanism,
    ContentBlock,
    ContentBlockPlanPayload,
)
from novel_flow.tools._base import LLMChapterTool


DEFAULT_PARAGRAPH_BUDGET = (
    "建议 2~5 个自然段；单段尽量 30~120 中文字；超过 180 中文字视为过长"
)


class PlanContentBlocksTool(LLMChapterTool):
    name = "plan_content_blocks"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        chapter_brief = ChapterBrief.model_validate(json.loads(str(payload["chapter_brief_json"])))
        try:
            prompt = self.render_prompt(
                "writer/plan_content_blocks.txt",
                chapter_brief_json=payload["chapter_brief_json"],
                completed_chapter_memory_text=payload.get("completed_chapter_memory_text", ""),
                chapter_payload_text=payload.get("chapter_payload_text", ""),
                relevant_world_rules_text=payload.get("relevant_world_rules_text", ""),
                timeline_anchor_facts_text=payload.get("timeline_anchor_facts_text", ""),
                scene_character_context_text=payload.get("scene_character_context_text", ""),
                relationship_state_text=payload.get("relationship_state_text", ""),
                chapter_character_mindsets_text=payload.get("chapter_character_mindsets_text", ""),
                style_card_text=payload.get("style_card_text", ""),
                target_word_count_text=payload.get("target_word_count_text", ""),
            )
            raw = self.generate_json(
                prompt=prompt,
                schema_name=self.name,
                schema_model=ContentBlockPlanPayload,
            )
            blocks = [ContentBlock.model_validate(item) for item in raw.get("blocks", [])]
        except Exception:
            blocks = self._fallback_blocks(chapter_brief)
        normalized = self._normalize_blocks(
            blocks=blocks,
            chapter_brief=chapter_brief,
            target_word_count_text=str(payload.get("target_word_count_text", "") or ""),
        )
        return ContentBlockPlanPayload.model_validate({"blocks": normalized}).model_dump(mode="json")

    def _normalize_blocks(
        self,
        *,
        blocks: list[ContentBlock],
        chapter_brief: ChapterBrief,
        target_word_count_text: str,
    ) -> list[ContentBlock]:
        if len(blocks) < 3:
            blocks = self._fallback_blocks(chapter_brief)
        trimmed = blocks[:10]
        total_target_chars = self._target_total_chars(
            target_word_count_text=target_word_count_text,
            block_count=len(trimmed),
        )
        normalized: list[ContentBlock] = []
        for index, block in enumerate(trimmed, start=1):
            normalized.append(
                block.model_copy(
                    update={
                        "block_id": f"{chapter_brief.chapter_id}.sc_001.b{index:03d}",
                        "chapter_id": chapter_brief.chapter_id,
                        "block_index": index,
                        "purpose": self._clean_text(block.purpose) or self._clean_text(block.scene_goal) or f"Block {index} advances the chapter's main pressure.",
                        "characters": self._clean_list(block.characters) or list(chapter_brief.character_focus or []),
                        "active_lines": self._clean_list(block.active_lines) or list(chapter_brief.active_lines or []),
                        "active_twists": self._clean_list(block.active_twists) or list(chapter_brief.active_twists or []),
                        "scene_goal": self._clean_text(block.scene_goal) or self._clean_text(block.purpose),
                        "must_reveal": self._clean_list(block.must_reveal),
                        "must_hide": self._clean_list(block.must_hide) or list(chapter_brief.forbidden[:4]),
                        "new_value": self._clean_text(block.new_value)
                        or self._fallback_new_value(index=index, chapter_brief=chapter_brief),
                        "must_not_repeat": self._list_or_fallback(
                            block.must_not_repeat,
                            self._fallback_must_not_repeat(index=index, chapter_brief=chapter_brief),
                        ),
                        "relationship_delta": self._clean_text(block.relationship_delta)
                        or self._fallback_relationship_delta(index=index, chapter_brief=chapter_brief),
                        "clue_delta": self._clean_text(block.clue_delta)
                        or self._fallback_clue_delta(index=index, chapter_brief=chapter_brief),
                        "must_land_in_action": self._list_or_fallback(
                            block.must_land_in_action,
                            self._fallback_action_landing(index=index, chapter_brief=chapter_brief),
                        ),
                        "emotional_tone": self._clean_text(block.emotional_tone) or self._clean_text(chapter_brief.reader_emotion),
                        "end_state": self._clean_text(block.end_state) or self._clean_text(chapter_brief.small_payoff) or self._clean_text(chapter_brief.ending_pull),
                        "human_reaction_target": self._list_or_fallback(
                            block.human_reaction_target,
                            self._fallback_human_reaction(index=index),
                        ),
                        "cost_shift": self._clean_text(block.cost_shift) or self._fallback_cost_shift(index=index, chapter_brief=chapter_brief),
                        "reader_feeling_target": self._clean_text(block.reader_feeling_target)
                        or self._fallback_reader_feeling(index=index, chapter_brief=chapter_brief),
                        "paragraph_budget": self._clean_text(block.paragraph_budget) or DEFAULT_PARAGRAPH_BUDGET,
                        "target_chars": (
                            int(block.target_chars or 0)
                            if int(block.target_chars or 0) > 0
                            else self._fallback_target_chars(
                                index=index,
                                total_blocks=len(trimmed),
                                turn_type=self._normalize_turn_type(block.turn_type, index=index),
                                total_target_chars=total_target_chars,
                            )
                        ),
                        "paragraph_shape": self._list_or_fallback(
                            block.paragraph_shape,
                            self._fallback_paragraph_shape(index=index),
                        ),
                        "micro_hook": self._clean_text(block.micro_hook)
                        or self._fallback_micro_hook(index=index, chapter_brief=chapter_brief),
                        "turn_type": self._normalize_turn_type(block.turn_type, index=index),
                        "character_anchor_line": self._normalize_character_anchor_line(
                            block.character_anchor_line,
                            index=index,
                            chapter_brief=chapter_brief,
                        ),
                        "style_risk_guard": self._list_or_fallback(
                            block.style_risk_guard,
                            self._fallback_style_risks(index=index, chapter_brief=chapter_brief),
                        ),
                        "character_reentry_mode": self._normalize_character_reentry_mode(block.character_reentry_mode),
                        "clue_reveal_mechanism": self._normalize_clue_reveal_mechanism(
                            block.clue_reveal_mechanism,
                            index=index,
                            chapter_brief=chapter_brief,
                        ),
                        "text": "",
                        "status": "draft",
                        "version": 1,
                    }
                )
            )
        return normalized

    def _fallback_blocks(self, chapter_brief: ChapterBrief) -> list[ContentBlock]:
        focus_characters = list(chapter_brief.character_focus or [])
        active_lines = list(chapter_brief.active_lines or [])
        active_twists = list(chapter_brief.active_twists or [])
        forbidden = list(chapter_brief.forbidden or [])
        clues = list(chapter_brief.allowed_clues or [])
        clue_mechanism = self._fallback_clue_reveal_mechanism(chapter_brief) if clues else None
        reentry_mode = self._fallback_character_reentry_mode(chapter_brief)
        return [
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b001",
                chapter_id=chapter_brief.chapter_id,
                block_index=1,
                purpose=f"Open with immediate pressure: {chapter_brief.opening_hook}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=self._clean_text(chapter_brief.opening_hook) or self._clean_text(chapter_brief.summary),
                must_reveal=[item for item in [chapter_brief.opening_hook] if self._clean_text(item)],
                must_hide=forbidden[:4],
                new_value="Readers newly feel the opening pressure as an active public trap, not as background setup.",
                must_not_repeat=[
                    "不要把旧案背景或人物旧怨整段复述一遍。",
                    "不要在第一块就解释对方真实动机。",
                ],
                relationship_delta="关系从未正面碰撞的悬置，转为公开场域里必须立刻接招的压迫。",
                clue_delta="这一块主要落地开场压力，不额外偷跑新 clue。",
                must_land_in_action=[
                    "必须把压迫落在动作、礼制或身体反应上。",
                    "不能只用总结句说气氛紧张。",
                ],
                emotional_tone=self._clean_text(chapter_brief.reader_emotion),
                end_state="The opening pressure lands and the focal character loses room to recover before speaking.",
                human_reaction_target=[
                    "Show one bodily or social restraint before the character tries to speak or act.",
                    "Let at least one witness or supporting character react like a living person under public pressure.",
                ],
                cost_shift="The focal character loses face, time, or the chance to choose a gentler opening move.",
                reader_feeling_target="Readers should feel the pressure closing around the character immediately.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                target_chars=420,
                paragraph_shape=[
                    "主动作",
                    "配角反应",
                    "人物细节/情绪泄露",
                    "礼法或环境补压",
                ],
                micro_hook="The character is forced to answer the opening pressure before they can recover their footing.",
                turn_type="pressure_rise",
                style_risk_guard=[
                    "Do not open with background summary.",
                    "Do not turn the character into a plot explainer.",
                    "Do not replace scene with pure mental recap.",
                ],
                character_reentry_mode=reentry_mode,
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b002",
                chapter_id=chapter_brief.chapter_id,
                block_index=2,
                purpose=f"Push the chapter object through live pressure: {chapter_brief.chapter_object}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=self._clean_text(chapter_brief.chapter_object) or "Make the chapter object matter on the page.",
                must_reveal=[item for item in [chapter_brief.chapter_object, chapter_brief.small_payoff] if self._clean_text(item)],
                must_hide=forbidden[:4],
                new_value="The chapter object becomes newly actionable, but only through a more expensive route.",
                must_not_repeat=[
                    "不要再重讲第一块已经建立的公开压迫。",
                    "不要把章目标只讲成抽象信息点。",
                ],
                relationship_delta="关系从单纯受压，转为带着程序和筹码差的试探性交锋。",
                clue_delta="让章目标和小回报真正推进，但不要额外偷跑更高层真相。",
                must_land_in_action=[
                    "章目标必须通过对话、手续、动作选择或旁人反应被推进。",
                    "不能只写人物心里觉得机会出现了。",
                ],
                emotional_tone=self._clean_text(chapter_brief.emotional_turn),
                end_state="The characters gain a small procedural push, but the relational and practical cost rises with it.",
                human_reaction_target=[
                    "Show practical calculation, etiquette pressure, or controlled discomfort while the goal advances.",
                    "Make another person's reaction sharpen the cost of that progress.",
                ],
                cost_shift="The focal character pays an extra social, procedural, or emotional price to move the goal forward.",
                reader_feeling_target="Readers should feel that even progress arrives with humiliation, pressure, or residue.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                target_chars=520,
                paragraph_shape=[
                    "主动作",
                    "礼法或程序阻力",
                    "配角反应",
                    "代价落点",
                ],
                micro_hook="The procedural opening appears, but the price of taking it forward is now visible.",
                turn_type="pressure_rise",
                style_risk_guard=[
                    "Do not explain why the chapter object matters in abstract summary.",
                    "Do not let dialogue become pure information transfer.",
                    "Do not let action pause for a long strategic recap.",
                ],
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b003",
                chapter_id=chapter_brief.chapter_id,
                block_index=3,
                purpose=f"Reprice relationship and expose pressure naturally: {chapter_brief.relationship_reprice}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=self._clean_text(chapter_brief.character_shift) or self._clean_text(chapter_brief.relationship_reprice),
                must_reveal=[item for item in [chapter_brief.character_shift, chapter_brief.relationship_reprice, *clues[:2]] if self._clean_text(item)],
                must_hide=forbidden[:4],
                new_value="Readers newly see the relationship reprice and at least one clue carrier, without getting a clean explanation.",
                must_not_repeat=[
                    "不要重复前一块已经完成的程序推进。",
                    "不要把关系变化再用作者总结句重复一遍。",
                ],
                relationship_delta="关系重新定价为更危险、更难判断，不能再停留在同一层敌意。",
                clue_delta="至少有一个异常、停顿或反应被看见，但它还不能被解释清楚。",
                must_land_in_action=[
                    "关系变化必须落在称呼、停顿、避视、动作失手或他人先发现上。",
                    "不能只说她其实更危险了。",
                ],
                emotional_tone=self._clean_text(chapter_brief.emotional_turn),
                end_state="The relationship or emotional angle is repriced on the page and the situation becomes harder to read safely.",
                human_reaction_target=[
                    "At least one character should show a small failure of composure, bodily leak, silence, or self-directed sting.",
                    "If a clue appears, let somebody else notice it before the owner explains it.",
                ],
                cost_shift="A clue or shift comes closer, but the relationship becomes harder to trust or manage.",
                reader_feeling_target="Readers should remember the changed relationship pressure more than the raw information itself.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                target_chars=560,
                paragraph_shape=[
                    "关系压力",
                    "回避与失手",
                    "他人先发现",
                    "当事人回避解释",
                ],
                micro_hook="The clue is visible enough to keep the reader moving, but nobody will give it a clean explanation yet.",
                turn_type="clue_shift",
                style_risk_guard=[
                    "Do not summarize the emotional reprice in narrator voice.",
                    "Do not repeat the same cold, pain, blood, or frost image.",
                    "Do not turn a person into a puzzle device.",
                ],
                clue_reveal_mechanism=clue_mechanism,
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b004",
                chapter_id=chapter_brief.chapter_id,
                block_index=4,
                purpose=f"Close on changed cost and natural pull: {chapter_brief.ending_pull}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=self._clean_text(chapter_brief.ending_pull),
                must_reveal=[item for item in [chapter_brief.ending_pull] if self._clean_text(item)],
                must_hide=forbidden[:4],
                new_value="The chapter exits on a changed cost and a next move that is harder to avoid than before.",
                must_not_repeat=[
                    "不要把前一块已经落地的关系变化再解释一遍。",
                    "不要把结尾写成预告片口播。",
                ],
                relationship_delta="结尾要让关系或局势的代价更难回头，而不是停在同一位置。",
                clue_delta="若有钩子，必须让钩子来自新代价或新事实，而不是重复旧悬念。",
                must_land_in_action=[
                    "尾钩必须先打到身体、动作、现场变化或实际损失上。",
                    "不能只用一句解释性判断代替收尾。",
                ],
                emotional_tone=self._clean_text(chapter_brief.reader_emotion),
                end_state="The chapter ends with a harder next step and a cost the character cannot step back from easily.",
                human_reaction_target=[
                    "Let the ending hit a body, action, breath, or practical loss before it becomes a hook.",
                    "Do not end on summary language alone.",
                ],
                cost_shift="The character loses a buffer, an option, or a person they needed for the next move.",
                reader_feeling_target="Readers should feel the next step has become both urgent and more expensive.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                target_chars=420,
                paragraph_shape=[
                    "结果落地",
                    "短反应",
                    "额外代价",
                    "尾钩或未竟动作",
                ],
                micro_hook="The chapter closes with a next move that is now harder, costlier, and impossible to ignore.",
                turn_type="false_relief",
                style_risk_guard=[
                    "Do not force a trailer-like ending turn.",
                    "Do not flatten the closing beat into explanation.",
                    "Do not spend the final sentence only naming the hook.",
                ],
            ),
        ]

    @staticmethod
    def _clean_text(value: str | None) -> str:
        return str(value or "").strip()

    @staticmethod
    def _target_total_chars(*, target_word_count_text: str, block_count: int) -> int:
        values = [int(item) for item in re.findall(r"\d+", str(target_word_count_text or ""))]
        if len(values) >= 2:
            estimated = int(round((values[0] + values[1]) / 2))
        elif len(values) == 1:
            estimated = values[0]
        else:
            estimated = 3200 if block_count <= 4 else 4600 if block_count <= 6 else 5600
        return max(1800, min(7200, estimated))

    @staticmethod
    def _fallback_target_chars(*, index: int, total_blocks: int, turn_type: str, total_target_chars: int) -> int:
        if total_blocks <= 0:
            return 420
        base_weights = [1.0] * total_blocks
        base_weights[0] = 0.9
        if total_blocks > 1:
            base_weights[-1] = 0.9
        turn_bonus = {
            "pressure_rise": 1.0,
            "clue_shift": 1.08,
            "emotional_slip": 1.02,
            "relationship_cut": 1.08,
            "ritual_embarrassment": 1.0,
            "witness_reaction": 0.94,
            "false_relief": 0.95,
            "withheld_answer": 0.95,
        }
        base_weights[index - 1] *= turn_bonus.get(turn_type, 1.0)
        total_weight = sum(base_weights) or float(total_blocks)
        target = int(round(total_target_chars * (base_weights[index - 1] / total_weight)))
        return max(260, min(1200, target))

    @classmethod
    def _clean_list(cls, items: list[str] | None) -> list[str]:
        return [cls._clean_text(item) for item in items or [] if cls._clean_text(item)]

    @classmethod
    def _list_or_fallback(cls, items: list[str] | None, fallback: list[str]) -> list[str]:
        cleaned = cls._clean_list(items)
        return cleaned or fallback

    @classmethod
    def _fallback_new_value(cls, *, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "Readers newly feel the opening pressure as a live trap instead of abstract setup."
        if index == 2:
            return "The chapter object becomes newly actionable, but only through a more expensive route."
        if index == 3:
            return "The relationship and clue pressure are newly repriced through what the characters do not cleanly explain."
        if cls._clean_text(chapter_brief.ending_pull):
            return "The situation exits in a newly changed state, with a cost or hook that did not exist before this beat."
        return "This beat must end with a changed situation, not a restatement of prior pressure."

    @classmethod
    def _fallback_must_not_repeat(cls, *, index: int, chapter_brief: ChapterBrief) -> list[str]:
        items = [
            "不要把上一块已经完成的关系判断换句话再讲一遍。",
            "不要重复同一层场景寒意、痛感或压迫感铺垫。",
        ]
        if index > 1:
            items.append("不要重新铺垫整章背景，只推进当前 beat 的新增值。")
        if cls._clean_text(chapter_brief.relationship_reprice):
            items.append("不要用作者总结句直接复述关系重新定价。")
        return items[:4]

    @classmethod
    def _fallback_relationship_delta(cls, *, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "关系从未正面碰撞，变为必须在公开压力下接招。"
        if index == 2:
            return "关系从纯压迫转为带着程序和筹码差的试探。"
        if index == 3:
            return cls._clean_text(chapter_brief.relationship_reprice) or "关系必须出现重新定价，而不是停留在同一层敌意。"
        return "关系或局势代价必须比上一块更难回头。"

    @classmethod
    def _fallback_clue_delta(cls, *, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "这一块主要负责落地开场压迫，不必额外推进新线索。"
        clues = list(chapter_brief.allowed_clues or [])
        if index == 3 and clues:
            return f"至少让一个可见线索真正被看见：{clues[0]}"
        if index >= 4 and cls._clean_text(chapter_brief.ending_pull):
            return "结尾钩子必须来自新事实、新代价或新障碍，而不是重复旧悬念。"
        return "如果没有新线索推进，就明确把这一块写成压力或关系推进，不要假装有新 clue。"

    @staticmethod
    def _fallback_action_landing(*, index: int, chapter_brief: ChapterBrief) -> list[str]:
        if index == 1:
            return [
                "把压力落在动作、礼制、身体反应或现场回声上。",
                "不要只写人物心里知道危险来了。",
            ]
        if index == 2:
            return [
                "把章目标落在对话、手续、动作选择或旁人反应上。",
                "不要只用解释句说明局势推进了。",
            ]
        if index == 3:
            return [
                "把关系变化落在称呼、停顿、避视、动作失手或旁观者先发现上。",
                "不要用作者口吻总结她其实怎样、他其实怎样。",
            ]
        return [
            "把尾钩落在动作、身体、物件变化或实际损失上。",
            "不要用一句解释性判断代替结尾场面。",
        ]

    @classmethod
    def _normalize_character_reentry_mode(cls, mode: CharacterReentryMode | None) -> CharacterReentryMode | None:
        if mode is None:
            return None
        cleaned = CharacterReentryMode(
            target_character=cls._clean_text(mode.target_character),
            identity_already_known=bool(mode.identity_already_known),
            reentry_strategy=cls._clean_text(mode.reentry_strategy),
            first_signal=cls._clean_text(mode.first_signal),
            first_emotional_focus=cls._clean_text(mode.first_emotional_focus),
            must_avoid=cls._clean_list(mode.must_avoid),
        )
        if not any(
            [
                cleaned.target_character,
                cleaned.reentry_strategy,
                cleaned.first_signal,
                cleaned.first_emotional_focus,
                cleaned.must_avoid,
            ]
        ):
            return None
        return cleaned

    @classmethod
    def _normalize_character_anchor_line(
        cls,
        mode: CharacterAnchorLine | None,
        *,
        index: int,
        chapter_brief: ChapterBrief,
    ) -> CharacterAnchorLine | None:
        if mode is None:
            return cls._fallback_character_anchor_line(index=index, chapter_brief=chapter_brief)
        cleaned = CharacterAnchorLine(
            owner=cls._clean_text(mode.owner),
            form=mode.form,
            surface_function=cls._clean_text(mode.surface_function),
            hidden_function=cls._clean_text(mode.hidden_function),
            must_reveal_about_character=cls._clean_text(mode.must_reveal_about_character),
            must_not_do=cls._clean_list(mode.must_not_do),
            preferred_shape=cls._clean_text(mode.preferred_shape) or "短、准、能留余味",
        )
        if not any(
            [
                cleaned.owner,
                cleaned.surface_function,
                cleaned.hidden_function,
                cleaned.must_reveal_about_character,
                cleaned.must_not_do,
            ]
        ):
            return cls._fallback_character_anchor_line(index=index, chapter_brief=chapter_brief)
        return cleaned

    @classmethod
    def _normalize_turn_type(cls, value: str | None, *, index: int) -> str:
        raw = cls._clean_text(value)
        if raw in {
            "pressure_rise",
            "clue_shift",
            "emotional_slip",
            "relationship_cut",
            "ritual_embarrassment",
            "witness_reaction",
            "false_relief",
            "withheld_answer",
        }:
            return raw
        return cls._fallback_turn_type(index=index)

    @classmethod
    def _normalize_clue_reveal_mechanism(
        cls,
        mode: ClueRevealMechanism | None,
        *,
        index: int,
        chapter_brief: ChapterBrief,
    ) -> ClueRevealMechanism | None:
        if mode is None:
            if index != 3 or not chapter_brief.allowed_clues:
                return None
            return cls._fallback_clue_reveal_mechanism(chapter_brief)
        cleaned = ClueRevealMechanism(
            clue=cls._clean_text(mode.clue),
            style=cls._normalize_clue_style(mode.style),
            pressure_source=cls._clean_text(mode.pressure_source),
            surface_trigger=cls._clean_text(mode.surface_trigger),
            first_noticer=cls._clean_text(mode.first_noticer),
            owner_reaction=cls._clean_text(mode.owner_reaction),
        )
        if not any(
            [
                cleaned.clue,
                cleaned.style,
                cleaned.pressure_source,
                cleaned.surface_trigger,
                cleaned.first_noticer,
                cleaned.owner_reaction,
            ]
        ):
            return None
        return cleaned

    @classmethod
    def _fallback_character_reentry_mode(cls, chapter_brief: ChapterBrief) -> CharacterReentryMode | None:
        focus = dict(chapter_brief.character_reentry_focus or {})
        if not focus:
            return None
        target_character, reentry_strategy = next(iter(focus.items()))
        return CharacterReentryMode(
            target_character=cls._clean_text(target_character),
            identity_already_known=True,
            reentry_strategy=cls._clean_text(reentry_strategy),
            first_signal="Use a familiar subordinate, object, title, or power arrangement to signal re-entry immediately.",
            first_emotional_focus=cls._clean_text(chapter_brief.relationship_reprice) or cls._clean_text(chapter_brief.character_shift),
            must_avoid=[
                "Do not re-explain identity in narrator summary.",
                "Do not make the re-entry feel like a fresh character introduction.",
            ],
        )

    @staticmethod
    def _fallback_anchor_owner(chapter_brief: ChapterBrief) -> str:
        return str(next(iter(chapter_brief.character_focus or []), "当前焦点人物")).strip() or "当前焦点人物"

    @classmethod
    def _fallback_character_anchor_line(cls, *, index: int, chapter_brief: ChapterBrief) -> CharacterAnchorLine:
        owner = cls._fallback_anchor_owner(chapter_brief)
        if index == 1:
            return CharacterAnchorLine(
                owner=owner,
                form="reaction_line",
                surface_function="用一句短促反应把开场压力钉在场面上。",
                hidden_function="让读者看见角色在被压住时最先守的东西是体面、控制或骨气。",
                must_reveal_about_character="这个人受压时首先暴露出的不是信息，而是性格里的硬处。",
                must_not_do=[
                    "不要写成功能性口号。",
                    "不要立刻跟解释性旁白。",
                    "不要为了漂亮把句子抻长。",
                ],
            )
        if index == 2:
            return CharacterAnchorLine(
                owner=owner,
                form="dialogue",
                surface_function="在推进程序或交涉时留下一句能顶住场面的短句。",
                hidden_function="通过措辞、克制或算计显出角色真正的处事方式。",
                must_reveal_about_character="这个人做事时先算代价、脸面还是底线。",
                must_not_do=[
                    "不要只传递剧情信息。",
                    "不要把潜台词解释出来。",
                    "不要写成一整段说理。",
                ],
            )
        if index == 3:
            return CharacterAnchorLine(
                owner=owner,
                form="narrative_judgment",
                surface_function="在关系重估或线索露出时留下一个贴近视角的判断句。",
                hidden_function="让读者通过这句判断看见人物的误读、偏执、心虚或本能回避。",
                must_reveal_about_character="这个人看人看事时最深的一层偏向或伤口。",
                must_not_do=[
                    "不要变成作者总结。",
                    "不要把真相说穿。",
                    "不要马上跟着完整解释。",
                ],
            )
        return CharacterAnchorLine(
            owner=owner,
            form="inner_thought",
            surface_function="在结尾变化落地时，用一句短念头或短反应把尾钩钉住。",
            hidden_function="让结尾先立住人，再立住事件。",
            must_reveal_about_character="这个人真正怕失去或真正放不下的东西。",
            must_not_do=[
                "不要写成预告片文案。",
                "不要只负责抛钩子。",
                "不要把情绪解释得太满。",
            ],
        )

    @staticmethod
    def _fallback_turn_type(*, index: int) -> str:
        if index == 1:
            return "pressure_rise"
        if index == 2:
            return "pressure_rise"
        if index == 3:
            return "clue_shift"
        return "false_relief"

    @staticmethod
    def _fallback_micro_hook(*, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "The opening pressure leaves the character with less room and forces the next move immediately."
        if index == 2:
            return "The immediate path forward opens, but it comes attached to a sharper cost."
        if index == 3:
            return "The new clue changes the pressure, but the scene withholds a clean answer."
        return f"The block should hand off into the next beat with the changed burden of: {chapter_brief.ending_pull}"

    @staticmethod
    def _fallback_human_reaction(*, index: int) -> list[str]:
        if index == 1:
            return [
                "Show one bodily or social restraint before the character moves.",
                "Let a witness or supporting character absorb some shock, pity, or unease on the page.",
            ]
        if index == 2:
            return [
                "Show calculation, etiquette pressure, or controlled discomfort inside the action.",
                "Make another character respond in a way that sharpens the relationship cost.",
            ]
        if index == 3:
            return [
                "Let the emotional turn surface through silence, body, pause, object handling, or composure failure.",
                "If a clue appears, let someone else notice it before anyone tries to explain it.",
            ]
        return [
            "Let the hook strike the body, breath, or practical situation before it becomes a chapter pull.",
            "Give the character one short, recognizably human reaction to the new price.",
        ]

    @staticmethod
    def _fallback_cost_shift(*, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "The focal character loses face, time, or a more comfortable opening choice."
        if index == 2:
            return "The focal character pays an extra procedural, social, or relational cost to advance the chapter object."
        if index == 3:
            return "The relationship, misread, or self-judgment becomes more expensive to carry."
        return f"The chapter should close with a harder next burden tied to: {chapter_brief.ending_pull}"

    @staticmethod
    def _fallback_reader_feeling(*, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "Readers should feel pressure and imbalance before they fully process the chapter situation."
        if index == 2:
            return "Readers should feel that progress costs something concrete."
        if index == 3:
            return "Readers should feel the relationship has become harder or more dangerous, not merely be told so."
        return f"Readers should want the next move immediately while sensing the added burden of: {chapter_brief.ending_pull}"

    @classmethod
    def _fallback_style_risks(cls, *, index: int, chapter_brief: ChapterBrief) -> list[str]:
        risks = [
            "Do not replace scene with long interior recap.",
            "Do not turn a character into the author's plot explainer.",
        ]
        if index == 1:
            risks.append("Do not write the opening like a background memo.")
        elif index == 2:
            risks.append("Do not show information gain without the price of getting it.")
        elif index == 3:
            risks.append("Do not complete the relationship reprice in one narrator-summary line.")
        else:
            risks.append("Do not twist the ending unnaturally just to force a hook.")
        if cls._clean_text(chapter_brief.reader_emotion):
            risks.append(f"Do not label the prose with '{chapter_brief.reader_emotion}' instead of dramatizing it.")
        return risks[:4]

    @classmethod
    def _fallback_paragraph_shape(cls, *, index: int) -> list[str]:
        if index == 1:
            return [
                "主动作",
                "配角反应",
                "人物细节/情绪泄露",
                "礼法或环境补压",
            ]
        if index == 2:
            return [
                "主动作",
                "礼法或程序阻力",
                "配角反应",
                "代价落点",
            ]
        if index == 3:
            return [
                "关系压力",
                "回避与失手",
                "他人先发现",
                "当事人回避解释",
            ]
        return [
            "结果落地",
            "短反应",
            "额外代价",
            "尾钩或未竟动作",
        ]

    @classmethod
    def _normalize_clue_style(cls, style: str | None) -> str:
        raw = cls._clean_text(style)
        if raw in {"natural_exposure", "object_accident", "ritual_trigger", "subordinate_report", "withheld_reveal"}:
            return raw
        legacy_map = {
            "direct_pressure": "natural_exposure",
            "overheard": "subordinate_report",
        }
        return legacy_map.get(raw, "")

    @classmethod
    def _fallback_clue_reveal_mechanism(cls, chapter_brief: ChapterBrief) -> ClueRevealMechanism | None:
        clue = cls._clean_text(next(iter(chapter_brief.allowed_clues or []), ""))
        if not clue:
            return None
        focus = cls._clean_text(next(iter(chapter_brief.character_focus or []), "A focal character"))
        chapter_mode = chapter_brief.clue_reveal_mechanism
        return ClueRevealMechanism(
            clue=clue,
            style=cls._normalize_clue_style(chapter_mode.style),
            pressure_source=cls._clean_text(chapter_mode.pressure_source)
            or cls._clean_text(chapter_brief.relationship_reprice)
            or "relationship pressure that makes explanation costly",
            surface_trigger=cls._clean_text(chapter_mode.surface_trigger)
            or cls._clean_text(chapter_brief.chapter_object)
            or "a scene object or phrase under pressure",
            first_noticer=cls._clean_text(chapter_mode.first_noticer) or focus,
            owner_reaction=cls._clean_text(chapter_mode.owner_reaction)
            or "The owner reacts by tightening up, avoiding direct explanation, or controlling the damage.",
        )
