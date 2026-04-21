from __future__ import annotations

import json

from novel_flow.models.schemas import (
    ChapterBrief,
    CharacterReentryMode,
    ClueRevealMechanism,
    ContentBlock,
    ContentBlockPlanPayload,
)
from novel_flow.tools._base import LLMChapterTool


DEFAULT_PARAGRAPH_BUDGET = "Use 2-4 natural paragraphs, usually 30-120 Chinese characters each, with 180 as a danger line."


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
        normalized = self._normalize_blocks(blocks=blocks, chapter_brief=chapter_brief)
        return ContentBlockPlanPayload.model_validate({"blocks": normalized}).model_dump(mode="json")

    def _normalize_blocks(self, *, blocks: list[ContentBlock], chapter_brief: ChapterBrief) -> list[ContentBlock]:
        if len(blocks) < 3:
            blocks = self._fallback_blocks(chapter_brief)
        trimmed = blocks[:6]
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
                emotional_tone=self._clean_text(chapter_brief.reader_emotion),
                end_state="The opening pressure lands and the focal character loses room to recover before speaking.",
                human_reaction_target=[
                    "Show one bodily or social restraint before the character tries to speak or act.",
                    "Let at least one witness or supporting character react like a living person under public pressure.",
                ],
                cost_shift="The focal character loses face, time, or the chance to choose a gentler opening move.",
                reader_feeling_target="Readers should feel the pressure closing around the character immediately.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                style_risk_guard=[
                    "Do not open with background summary.",
                    "Do not turn the character into a plot explainer.",
                    "Do not replace scene with pure mental recap.",
                ],
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
                emotional_tone=self._clean_text(chapter_brief.emotional_turn),
                end_state="The characters gain a small procedural push, but the relational and practical cost rises with it.",
                human_reaction_target=[
                    "Show practical calculation, etiquette pressure, or controlled discomfort while the goal advances.",
                    "Make another person's reaction sharpen the cost of that progress.",
                ],
                cost_shift="The focal character pays an extra social, procedural, or emotional price to move the goal forward.",
                reader_feeling_target="Readers should feel that even progress arrives with humiliation, pressure, or residue.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
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
                emotional_tone=self._clean_text(chapter_brief.emotional_turn),
                end_state="The relationship or emotional angle is repriced on the page and the situation becomes harder to read safely.",
                human_reaction_target=[
                    "At least one character should show a small failure of composure, bodily leak, silence, or self-directed sting.",
                    "If a clue appears, let somebody else notice it before the owner explains it.",
                ],
                cost_shift="A clue or shift comes closer, but the relationship becomes harder to trust or manage.",
                reader_feeling_target="Readers should remember the changed relationship pressure more than the raw information itself.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
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
                emotional_tone=self._clean_text(chapter_brief.reader_emotion),
                end_state="The chapter ends with a harder next step and a cost the character cannot step back from easily.",
                human_reaction_target=[
                    "Let the ending hit a body, action, breath, or practical loss before it becomes a hook.",
                    "Do not end on summary language alone.",
                ],
                cost_shift="The character loses a buffer, an option, or a person they needed for the next move.",
                reader_feeling_target="Readers should feel the next step has become both urgent and more expensive.",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
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

    @classmethod
    def _clean_list(cls, items: list[str] | None) -> list[str]:
        return [cls._clean_text(item) for item in items or [] if cls._clean_text(item)]

    @classmethod
    def _list_or_fallback(cls, items: list[str] | None, fallback: list[str]) -> list[str]:
        cleaned = cls._clean_list(items)
        return cleaned or fallback

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
            surface_trigger=cls._clean_text(mode.surface_trigger),
            relationship_pressure=cls._clean_text(mode.relationship_pressure),
            body_or_object_failure=cls._clean_text(mode.body_or_object_failure),
            who_notices=cls._clean_text(mode.who_notices),
            who_avoids_explaining=cls._clean_text(mode.who_avoids_explaining),
            after_effect=cls._clean_text(mode.after_effect),
        )
        if not any(
            [
                cleaned.clue,
                cleaned.surface_trigger,
                cleaned.relationship_pressure,
                cleaned.body_or_object_failure,
                cleaned.who_notices,
                cleaned.who_avoids_explaining,
                cleaned.after_effect,
            ]
        ):
            return None
        return cleaned

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
    def _fallback_clue_reveal_mechanism(cls, chapter_brief: ChapterBrief) -> ClueRevealMechanism | None:
        clue = cls._clean_text(next(iter(chapter_brief.allowed_clues or []), ""))
        if not clue:
            return None
        focus = cls._clean_text(next(iter(chapter_brief.character_focus or []), "A focal character"))
        return ClueRevealMechanism(
            clue=clue,
            surface_trigger=cls._clean_text(chapter_brief.chapter_object) or "a scene object or phrase under pressure",
            relationship_pressure=cls._clean_text(chapter_brief.relationship_reprice) or "relationship pressure that makes explanation costly",
            body_or_object_failure="A hand pauses, breath catches, or an object gives away more than the speaker wants.",
            who_notices=focus,
            who_avoids_explaining="The person most entangled with the clue",
            after_effect="The clue becomes visible, but the scene should stay tighter rather than fully explained.",
        )
