from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_flow.models.schemas import (
    ActualChapterSummary,
    ChapterBrief,
    CharacterCard,
    StoryLine,
    StoryPremise,
    TwistDesign,
    WriterContext,
)
from novel_flow.services.character_context import CharacterContextBuilder
from novel_flow.services.character_milestone_context import CharacterMilestoneContextBuilder
from novel_flow.services.relationship_state import RelationshipStateBuilder
from novel_flow.services.timeline_context import TimelineContextBuilder


_STYLE_CARD_TEXT = """[Style card]
Genre: restrained historical romance with pressure, mistrust, and emotional misreading.
POV: stay in limited perspective; never explain hidden truth from an omniscient distance.
Language: readable modern Chinese prose with historical texture, not archaic imitation and not web-novel slang.
Texture: scenes should feel lived-in and physically present. Let setting, objects, labor, etiquette, weather, money, and bodily discomfort quietly shape the page.
Emotion: avoid naming feelings too quickly. Let emotion emerge through what the POV notices, avoids, says, misreads, touches, or cannot bring itself to do.
Dialogue: keep it human and motivated. People should speak from position, need, habit, fear, and relationship history, not to serve the outline.
Character landing: make people convincing through selective concrete detail such as posture, hands, clothing, injuries, routine, and forms of address, without turning detail into a checklist.
Reveal discipline: clues may appear, but allowed clues must not be over-explained before reveal.
Relationship movement: every chapter should deepen, strain, tilt, or re-price at least one relationship beat in a believable way.
Backstory rule: if the past appears, let it arise naturally from present pressure, memory trigger, or action; do not paste in explanatory blocks.
Rhythm: vary sentence weight and scene pace with the dramatic moment. Do not let the prose sound mechanically patterned.
Immersion goal: the reader should feel inside the room, inside the body's reaction, and inside the character's limited understanding.
"""


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_revealed(current_chapter_id: str, reveal_at: str) -> bool:
    return _chapter_order(current_chapter_id) >= _chapter_order(reveal_at)


@dataclass
class ChapterContextAssembler:
    @classmethod
    def build(
        cls,
        *,
        chapter_brief: ChapterBrief,
        twist_designs: list[TwistDesign],
        story_lines: list[StoryLine],
        worldbuilding: dict[str, Any] | None,
        character_cards: list[CharacterCard] | list[Any],
        actual_summaries: list[ActualChapterSummary],
        current_chapter_id: str,
        premise: StoryPremise | None = None,
        character_milestones: list[dict[str, Any]] | None = None,
        context_sanitizer: Any | None = None,
        reference_pack: str = "",
        style_settings: dict[str, Any] | None = None,
    ) -> WriterContext:
        del reference_pack, style_settings
        active_twist_ids = set(chapter_brief.active_twists)
        active_line_ids = set(chapter_brief.active_lines)
        active_twists = [twist for twist in twist_designs if twist.twist_id in active_twist_ids]
        active_story_lines = [line for line in story_lines if line.line_id in active_line_ids]
        completed_chapter_memory_text = cls._completed_chapter_memory_text(actual_summaries)
        scene_character_context_text = CharacterContextBuilder.build_chapter_context(
            character_cards=character_cards,
            chapter_brief=chapter_brief,
            current_chapter_id=current_chapter_id,
            active_twists=active_twists,
        )
        relationship_state_text = RelationshipStateBuilder.build_chapter_state(
            chapter_brief=chapter_brief,
            actual_summaries=actual_summaries,
        )
        worldbuilding = worldbuilding or {}
        context = WriterContext(
            chapter_id=chapter_brief.chapter_id,
            selection_summary_text="[Context selection]\n尚未生成 selection 摘要。",
            time_anchor_text="[Time anchor]\n尚未生成时间锚点。",
            chapter_visible_context_text="[Chapter visible context]\n尚未生成章节可见上下文。",
            completed_chapter_memory_text=completed_chapter_memory_text,
            step_1_story_foundation_text=cls._step_1_story_foundation_text(
                chapter_brief=chapter_brief,
                premise=premise,
            ),
            step_2_worldbuilding_text=cls._step_2_worldbuilding_text(worldbuilding),
            step_3_character_packets_text=scene_character_context_text,
            step_4_event_timeline_text=TimelineContextBuilder.build_full_text(worldbuilding=worldbuilding),
            step_5_character_milestones_text=CharacterMilestoneContextBuilder.build(
                character_milestones=character_milestones or [],
                chapter_brief=chapter_brief,
                active_twists=active_twists,
            ),
            step_6_twists_text=cls._step_6_twists_text(
                current_chapter_id=current_chapter_id,
                active_twists=active_twists,
            ),
            step_7_story_lines_text=cls._step_7_story_lines_text(active_story_lines=active_story_lines),
            step_8_chapter_brief_text=cls._step_8_chapter_brief_text(chapter_brief=chapter_brief),
            chapter_payload_text=cls._chapter_payload_text(
                chapter_brief=chapter_brief,
                current_chapter_id=current_chapter_id,
                active_twists=active_twists,
                active_story_lines=active_story_lines,
            ),
            timeline_anchor_facts_text=TimelineContextBuilder.build(
                chapter_brief=chapter_brief,
                worldbuilding=worldbuilding,
            ),
            relevant_world_rules_text=cls._relevant_world_rules_text(chapter_brief, worldbuilding),
            style_card_text=_STYLE_CARD_TEXT.strip(),
            active_twists=active_twists,
            active_story_lines=active_story_lines,
            scene_character_context_text=scene_character_context_text,
            relationship_state_text=relationship_state_text,
        )
        if context_sanitizer is not None:
            return context_sanitizer.sanitize_writer_context(
                writer_context=context,
                current_chapter_id=current_chapter_id,
                active_twists=active_twists,
            )
        return context

    @staticmethod
    def _completed_chapter_memory_text(actual_summaries: list[ActualChapterSummary]) -> str:
        if not actual_summaries:
            return "[Completed chapter memory]\nNo completed chapter summaries yet."
        blocks: list[str] = ["[Completed chapter memory]"]
        for item in sorted(actual_summaries, key=lambda entry: _chapter_order(entry.chapter_id)):
            blocks.extend(
                [
                    "",
                    f"{item.chapter_id}",
                    f"- Actual events: {'; '.join(item.actual_events) or 'None.'}",
                    f"- Reader now knows: {'; '.join(item.reader_now_knows) or 'None.'}",
                    f"- Reader now believes: {'; '.join(item.reader_now_believes) or 'None.'}",
                    f"- Open questions: {'; '.join(item.open_questions) or 'None.'}",
                    f"- Character states: {'; '.join(item.character_states) or 'None.'}",
                    f"- Relationship state: {'; '.join(item.relationship_state) or 'None.'}",
                    f"- Seeded clues: {'; '.join(item.seeded_clues) or 'None.'}",
                    f"- Locked truths: {'; '.join(item.locked_truths) or 'None.'}",
                ]
            )
        return "\n".join(blocks).strip()

    @staticmethod
    def _step_1_story_foundation_text(*, chapter_brief: ChapterBrief, premise: StoryPremise | None) -> str:
        lines = ["[Step 1 story foundation]"]
        if premise is None:
            lines.append("No premise data available.")
            return "\n".join(lines).strip()
        lines.extend(
            [
                "",
                f"Title: {premise.title}",
                f"High concept: {premise.high_concept}",
                f"Theme statement: {premise.theme_statement}",
                f"Story summary: {premise.story_summary}",
                f"Genre: {premise.genre}",
                f"Target style: {premise.target_style}",
                f"Emotional hook: {premise.emotional_hook}",
                f"Central conflict: {premise.central_conflict}",
                f"Core hook: {premise.core_hook}",
                f"Ending payoff: {premise.ending_payoff}",
                "",
                f"Current chapter mission inside this foundation: {chapter_brief.summary}",
            ]
        )
        if premise.escalation_path:
            lines.append("Escalation path:")
            lines.extend(f"- {item}" for item in premise.escalation_path)
        if premise.twist_blueprint:
            lines.append("Twist blueprint:")
            lines.extend(f"- {item}" for item in premise.twist_blueprint)
        if premise.selling_points:
            lines.append("Selling points:")
            lines.extend(f"- {item}" for item in premise.selling_points)
        return "\n".join(lines).strip()

    @staticmethod
    def _step_2_worldbuilding_text(worldbuilding: dict[str, Any]) -> str:
        lines = ["[Step 2 worldbuilding and structural rules]"]
        if not isinstance(worldbuilding, dict) or not worldbuilding:
            lines.append("No worldbuilding package available.")
            return "\n".join(lines).strip()

        story_engine = worldbuilding.get("story_engine", {})
        if isinstance(story_engine, dict) and story_engine:
            lines.extend(["", "Story engine:"])
            for key, label in (
                ("engine_sentence", "Engine sentence"),
                ("default_track", "Default track"),
                ("narrative_mode", "Narrative mode"),
                ("viewpoint_strategy", "Viewpoint strategy"),
                ("reveal_strategy", "Reveal strategy"),
                ("hook_strategy", "Hook strategy"),
                ("world_rules", "World rules"),
                ("power_structure", "Power structure"),
                ("world_map", "World map"),
                ("structural_inertia", "Structural inertia"),
                ("rebound_mechanism", "Rebound mechanism"),
                ("story_trigger", "Story trigger"),
                ("objective_conditions", "Objective conditions"),
            ):
                value = str(story_engine.get(key) or "").strip()
                if value:
                    lines.append(f"- {label}: {value}")

        for key, title in (
            ("core_theme", "Core theme"),
            ("structure_blueprint", "Structure blueprint"),
        ):
            value = worldbuilding.get(key)
            if isinstance(value, dict) and value:
                lines.extend(["", f"{title}:"])
                for sub_key, sub_value in value.items():
                    text = str(sub_value or "").strip()
                    if text:
                        lines.append(f"- {sub_key}: {text}")

        for key, title in (
            ("setpiece_library", "Setpiece library"),
            ("writing_constraints", "Writing constraints"),
        ):
            value = worldbuilding.get(key)
            if isinstance(value, list) and value:
                lines.extend(["", f"{title}:"])
                lines.extend(f"- {str(item).strip()}" for item in value if str(item).strip())
        return "\n".join(lines).strip()

    @classmethod
    def _chapter_payload_text(
        cls,
        *,
        chapter_brief: ChapterBrief,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
        active_story_lines: list[StoryLine],
    ) -> str:
        lines = [
            "[Chapter payload]",
            "",
            f"Chapter: {chapter_brief.chapter_id} / {chapter_brief.title}",
            f"Chapter type: {chapter_brief.chapter_type}",
            f"One-line mission: {chapter_brief.summary}",
            f"Incoming hook: {chapter_brief.incoming_hook or 'No previous hook.'}",
            f"Opening hook: {chapter_brief.opening_hook}",
            f"Core scene: {chapter_brief.core_scene or 'None.'}",
            f"Chapter object: {chapter_brief.chapter_object}",
            f"Scene engine: {chapter_brief.scene_engine}",
            f"Clue reveal style: {chapter_brief.clue_reveal_style or 'None.'}",
            f"Character reentry focus: {chapter_brief.character_reentry_focus or {}}",
            f"Reader emotion target: {chapter_brief.reader_emotion}",
            f"Reader belief to preserve: {chapter_brief.reader_belief}",
            f"Character shift: {chapter_brief.character_shift}",
            f"Relationship reprice: {chapter_brief.relationship_reprice}",
            f"Emotional turn: {chapter_brief.emotional_turn}",
            f"Backstory trigger: {chapter_brief.backstory_trigger or 'None.'}",
            f"Human pain anchor: {chapter_brief.human_pain_anchor or 'None.'}",
            f"Small payoff: {chapter_brief.small_payoff}",
            f"Ending pull: {chapter_brief.ending_pull}",
            f"Info budget: {chapter_brief.info_budget}",
            "",
            "Active story lines:",
        ]
        if active_story_lines:
            for line in active_story_lines:
                rules = "; ".join(line.line_rules) or "None."
                lines.append(f"- {line.line_id}: {line.core_question} | visibility={line.visibility} | rules={rules}")
        else:
            lines.append("- None.")

        lines.extend(["", "Active twists:"])
        if active_twists:
            for twist in active_twists:
                if _is_revealed(current_chapter_id, twist.reveal_at):
                    lines.append(
                        f"- {twist.twist_id}: already at or after reveal chapter; keep only chapter-allowed information and do not overwrite continuity."
                    )
                else:
                    allowed_clues = "; ".join(twist.allowed_clues) or "None."
                    forbidden = "; ".join(twist.forbidden_reveals) or "None."
                    lines.append(
                        f"- {twist.twist_id}: preserve false belief '{twist.false_belief}'; reader alignment='{twist.reader_alignment}'; "
                        f"allowed clues={allowed_clues}; forbidden reveals={forbidden}; POV lock={twist.pov_lock}"
                    )
        else:
            lines.append("- None.")

        hidden_items = list(chapter_brief.forbidden)
        for twist in active_twists:
            if not _is_revealed(current_chapter_id, twist.reveal_at):
                hidden_items.extend(twist.forbidden_reveals)

        lines.extend(["", "Allowed explicit information:"])
        for item in chapter_brief.allowed_info or ["None."]:
            lines.append(f"- {item}")
        lines.extend(["", "Allowed clues without explanation:"])
        for item in chapter_brief.allowed_clues or ["None."]:
            lines.append(f"- {item}")
        lines.extend(["", "Forbidden content:"])
        for item in dict.fromkeys(hidden_items) or ["None."]:
            lines.append(f"- {item}")
        return "\n".join(lines).strip()

    @staticmethod
    def _step_6_twists_text(*, current_chapter_id: str, active_twists: list[TwistDesign]) -> str:
        lines = ["[Step 6 active twist packets]"]
        if not active_twists:
            lines.append("No active twists.")
            return "\n".join(lines).strip()
        for twist in active_twists:
            lines.extend(
                [
                    "",
                    f"{twist.twist_id} / {twist.title}",
                    f"- False belief: {twist.false_belief}",
                    f"- Reader alignment: {twist.reader_alignment}",
                    f"- Seed from: {twist.seed_from}",
                    f"- Reveal at: {twist.reveal_at}",
                    f"- Allowed clues: {'; '.join(twist.allowed_clues) or 'None.'}",
                    f"- Forbidden reveals: {'; '.join(twist.forbidden_reveals) or 'None.'}",
                    f"- POV lock: {twist.pov_lock}",
                    f"- Related characters: {'; '.join(twist.related_characters) or 'None.'}",
                    f"- Payoff effect: {twist.payoff_effect}",
                ]
            )
            if _is_revealed(current_chapter_id, twist.reveal_at):
                lines.append(f"- Truth: {twist.truth}")
            else:
                lines.append("- Truth: hidden until reveal chapter; do not narrate it directly.")
        return "\n".join(lines).strip()

    @staticmethod
    def _step_7_story_lines_text(*, active_story_lines: list[StoryLine]) -> str:
        lines = ["[Step 7 active story line packets]"]
        if not active_story_lines:
            lines.append("No active story lines.")
            return "\n".join(lines).strip()
        for line in active_story_lines:
            lines.extend(
                [
                    "",
                    f"{line.line_id} / {line.name}",
                    f"- Type: {line.line_type}",
                    f"- Visibility: {line.visibility}",
                    f"- Core question: {line.core_question}",
                    f"- Reader hook mode: {line.reader_hook_mode}",
                    f"- Start state: {line.start_state}",
                    f"- Midpoint shift: {line.midpoint_shift}",
                    f"- End state: {line.end_state}",
                    f"- Carried twists: {'; '.join(line.carried_twists) or 'None.'}",
                    f"- Line rules: {'; '.join(line.line_rules) or 'None.'}",
                ]
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _step_8_chapter_brief_text(*, chapter_brief: ChapterBrief) -> str:
        lines = [
            "[Step 8 current chapter brief]",
            "",
            f"Chapter id: {chapter_brief.chapter_id}",
            f"Title: {chapter_brief.title}",
            f"Chapter type: {chapter_brief.chapter_type}",
            f"Summary: {chapter_brief.summary}",
            f"Incoming hook: {chapter_brief.incoming_hook}",
            f"Opening hook: {chapter_brief.opening_hook}",
            f"Core scene: {chapter_brief.core_scene or 'None.'}",
            f"Chapter object: {chapter_brief.chapter_object}",
            f"Reader emotion: {chapter_brief.reader_emotion}",
            f"Reader belief: {chapter_brief.reader_belief}",
            f"World limit: {chapter_brief.world_limit}",
            f"Character shift: {chapter_brief.character_shift}",
            f"Relationship reprice: {chapter_brief.relationship_reprice}",
            f"Emotional turn: {chapter_brief.emotional_turn}",
            f"Backstory trigger: {chapter_brief.backstory_trigger or 'None.'}",
            f"Scene engine: {chapter_brief.scene_engine}",
            f"Clue reveal style: {chapter_brief.clue_reveal_style or 'None.'}",
            f"Character reentry focus: {chapter_brief.character_reentry_focus or {}}",
            f"Human pain anchor: {chapter_brief.human_pain_anchor or 'None.'}",
            f"Small payoff: {chapter_brief.small_payoff}",
            f"Ending pull: {chapter_brief.ending_pull}",
            f"Info budget: {chapter_brief.info_budget}",
        ]
        for label, values in (
            ("Active lines", chapter_brief.active_lines),
            ("Active twists", chapter_brief.active_twists),
            ("Allowed info", chapter_brief.allowed_info),
            ("Allowed clues", chapter_brief.allowed_clues),
            ("Forbidden", chapter_brief.forbidden),
            ("Character focus", chapter_brief.character_focus),
        ):
            lines.append(f"{label}: {'; '.join(values) or 'None.'}")
        return "\n".join(lines).strip()

    @staticmethod
    def _relevant_world_rules_text(chapter_brief: ChapterBrief, worldbuilding: dict[str, Any]) -> str:
        rules: list[str] = [chapter_brief.world_limit]
        story_engine = worldbuilding.get("story_engine", {}) if isinstance(worldbuilding, dict) else {}
        for key in ("world_rules", "power_structure", "objective_conditions", "structural_inertia"):
            value = story_engine.get(key, [])
            if isinstance(value, list):
                rules.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                rules.append(value.strip())
        deduped: list[str] = []
        seen: set[str] = set()
        for rule in rules:
            if rule and rule not in seen:
                seen.add(rule)
                deduped.append(rule)
        lines = ["[Relevant world rules]", ""]
        for index, rule in enumerate(deduped[:6], start=1):
            lines.append(f"{index}. {rule}")
        return "\n".join(lines).strip()
