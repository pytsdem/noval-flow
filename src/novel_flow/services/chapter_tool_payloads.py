from __future__ import annotations

import json
from typing import Any

from novel_flow.models.schemas import CharacterCard, CharacterMindset, ChapterBrief, ContentBlock
from novel_flow.services.novel_context import (
    CharacterScopedStepContext,
    NovelContextFormatter,
    NovelContextSelectorService,
)


class ChapterToolPayloadBuilder:
    @classmethod
    def build_plan_content_blocks_payload(
        cls,
        *,
        chapter_brief: ChapterBrief,
        context: Any,
    ) -> dict[str, Any]:
        return {
            "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "chapter_payload_text": context.chapter_payload_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
            "style_card_text": context.style_card_text,
            "target_word_count_text": chapter_brief.info_budget,
        }

    @classmethod
    def build_write_chapter_full_payload(
        cls,
        *,
        chapter_brief: ChapterBrief,
        context: Any,
        planned_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        return {
            "assistant_persona_prompt": getattr(context, "assistant_persona_prompt", ""),
            "chapter_id": chapter_brief.chapter_id,
            "chapter_title": chapter_brief.title,
            "chapter_summary": chapter_brief.summary,
            "chapter_plan_json": cls.chapter_plan_json(planned_blocks),
            "step_1_to_7_outputs_json": cls.step_1_to_7_outputs_json(context),
            "chapter_payload_text": context.chapter_payload_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
            "style_card_text": context.style_card_text,
            "previous_chapter_full_text": getattr(context, "previous_chapter_full_text", ""),
            "completed_chapter_summary_bundle": getattr(
                context,
                "completed_chapter_summary_bundle",
                context.completed_chapter_memory_text,
            ),
            "writing_requirements_json": getattr(context, "writing_requirements_json", "{}"),
            "reference_pack": getattr(context, "reference_pack", ""),
        }

    @classmethod
    def build_character_mindset_payload(
        cls,
        *,
        context: Any,
        character_card: CharacterCard,
        previous_mindset: CharacterMindset | None,
        scoped_steps: CharacterScopedStepContext,
        character_id: str,
    ) -> dict[str, Any]:
        return {
            "current_character_mindset_json": (
                cls.json_text(previous_mindset.model_dump(mode="json"))
                if previous_mindset is not None
                else "{}"
            ),
            "character_card_json": cls.json_text(character_card.model_dump(mode="json")),
            "character_id": character_id,
            "character_name": character_card.name,
            "step_1_story_foundation_text": context.step_1_story_foundation_text,
            "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
            "step_3_character_packets_text": context.step_3_character_packets_text,
            "step_4_event_timeline_text": context.step_4_event_timeline_text,
            "step_5_scoped_text": scoped_steps.step_5_character_milestones_text,
            "step_6_scoped_text": scoped_steps.step_6_twists_text,
            "step_7_story_lines_text": context.step_7_story_lines_text,
            "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
        }

    @classmethod
    def build_block_runtime_context(
        cls,
        *,
        context: Any,
        block: ContentBlock,
        committed_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        current_chapter_context = NovelContextFormatter.format_current_chapter_context(
            NovelContextSelectorService.select_current_chapter_context(
                block.chapter_id,
                committed_blocks,
                max_blocks=4,
                tail_chars=700,
            )
        )
        prior_summary_lines = ["[Earlier committed blocks]"]
        current_written_blocks = list(current_chapter_context["current_chapter_written_blocks_json"])
        if current_written_blocks:
            for item in current_written_blocks:
                prior_summary_lines.extend(
                    [
                        "",
                        f"{item['block_id']} / {item['purpose']}",
                        f"- End state: {item['end_state']}",
                        f"- Text tail: {cls.tail_text(str(item['text']), max_chars=220)}",
                    ]
                )
        else:
            prior_summary_lines.append("No committed blocks yet.")
        delivered_summary_lines = ["[Already delivered in this chapter]"]
        if current_written_blocks:
            for item in current_written_blocks:
                delivered_summary_lines.extend(
                    [
                        "",
                        f"{item['block_id']} / {item['purpose']}",
                        f"- scene_goal: {item.get('scene_goal', '') or 'None.'}",
                        f"- new_value: {item.get('new_value', '') or 'None.'}",
                        f"- relationship_delta: {item.get('relationship_delta', '') or 'None.'}",
                        f"- clue_delta: {item.get('clue_delta', '') or 'None.'}",
                        f"- end_state: {item.get('end_state', '') or 'None.'}",
                        f"- micro_hook: {item.get('micro_hook', '') or 'None.'}",
                    ]
                )
        else:
            delivered_summary_lines.append("No beat has landed yet.")
        prior_tail = str(current_chapter_context["current_chapter_draft_tail"] or "")
        return {
            "chapter_goal": cls.compact_chapter_goal(context=context),
            "hard_facts": cls.compact_hard_facts(context=context, block=block),
            "character_state": cls.compact_character_state(context=context),
            "previous_text_tail": cls.tail_text(prior_tail, max_chars=700),
            "chapter_so_far": cls.compact_chapter_so_far(committed_blocks=committed_blocks),
            "style_rules": cls.compact_style_rules(context=context),
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "chapter_payload_text": context.chapter_payload_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "assistant_persona_prompt": getattr(context, "assistant_persona_prompt", ""),
            "writing_requirements_json": getattr(context, "writing_requirements_json", "{}"),
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
            "current_chapter_written_blocks_json": cls.json_text(current_written_blocks),
            "current_chapter_draft_tail": prior_tail,
            "prior_block_summary_text": "\n".join(prior_summary_lines).strip(),
            "delivered_beat_summary_text": "\n".join(delivered_summary_lines).strip(),
            "prior_chapter_text_tail": prior_tail,
            "style_card_text": context.style_card_text,
        }

    @classmethod
    def build_draft_block_payload(
        cls,
        *,
        block: ContentBlock,
        block_context: dict[str, Any],
        loaded_skill_instructions_text: str,
    ) -> dict[str, Any]:
        return {
            "chapter_goal": block_context.get("chapter_goal", ""),
            "hard_facts": block_context.get("hard_facts", ""),
            "character_state": block_context.get("character_state", ""),
            "beat": cls.compact_beat_json(block=block, block_context=block_context),
            "previous_text_tail": block_context.get("previous_text_tail", ""),
            "chapter_so_far": block_context.get("chapter_so_far", ""),
            "style_rules": block_context.get("style_rules", ""),
            "target_length": cls.target_length_guard(block.target_chars),
        }

    @classmethod
    def build_revise_block_payload(
        cls,
        *,
        block: ContentBlock,
        block_context: dict[str, Any],
        block_text: str,
        review_reports: dict[str, Any],
        block_revision_plan: dict[str, Any],
        loaded_skill_instructions_text: str,
    ) -> dict[str, Any]:
        return {
            **cls.build_draft_block_payload(
                block=block,
                block_context=block_context,
                loaded_skill_instructions_text=loaded_skill_instructions_text,
            ),
            "block_text": block_text,
            "review_json": cls.json_text(review_reports),
            "block_revision_plan_json": cls.json_text(block_revision_plan),
        }

    @classmethod
    def build_block_review_payload(
        cls,
        *,
        tool_name: str,
        context: Any,
        block: ContentBlock,
        block_text: str,
        block_context: dict[str, Any],
    ) -> dict[str, Any]:
        block_card_text = cls.block_card_text(block)
        if tool_name == "review_block_quality":
            return {
                "chapter_payload_text": context.chapter_payload_text,
                "relevant_world_rules_text": context.relevant_world_rules_text,
                "scene_character_context_text": context.scene_character_context_text,
                "relationship_state_text": context.relationship_state_text,
                "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
                "current_chapter_written_blocks_json": block_context["current_chapter_written_blocks_json"],
                "current_chapter_draft_tail": block_context["current_chapter_draft_tail"],
                "block_card_text": block_card_text,
                "prior_block_summary_text": block_context["prior_block_summary_text"],
                "prior_chapter_text_tail": block_context["prior_chapter_text_tail"],
                "block_text": block_text,
                **cls.block_prompt_fields(block),
            }

        review_scope_text = (
            "Review only the current content block. "
            "Keep the review light and local: catch reveal leakage, character-forced behavior, "
            "time carry-over conflicts, and whether the block actually feels like a live fiction beat."
        )
        return {
            "chapter_payload_text": context.chapter_payload_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "time_anchor_text": context.time_anchor_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_text": block_text,
            "block_card_text": block_card_text,
            "active_twists_json": cls.json_text(
                [item.model_dump(mode="json") for item in context.active_twists]
            ),
            "review_scope_text": review_scope_text,
        }

    @classmethod
    def build_chapter_review_payload(
        cls,
        *,
        chapter_brief: ChapterBrief,
        context: Any,
        chapter_text: str,
        planned_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        active_twists = [item.model_dump(mode="json") for item in context.active_twists]
        return {
            "selection_summary_text": context.selection_summary_text,
            "time_anchor_text": context.time_anchor_text,
            "chapter_visible_context_text": context.chapter_visible_context_text,
            "completed_chapter_memory_text": context.completed_chapter_memory_text,
            "step_1_story_foundation_text": context.step_1_story_foundation_text,
            "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
            "step_3_character_packets_text": context.step_3_character_packets_text,
            "step_4_event_timeline_text": context.step_4_event_timeline_text,
            "step_5_character_milestones_text": context.step_5_character_milestones_text,
            "step_6_twists_text": context.step_6_twists_text,
            "step_7_story_lines_text": context.step_7_story_lines_text,
            "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
            "chapter_payload_text": context.chapter_payload_text,
            "timeline_anchor_facts_text": context.timeline_anchor_facts_text,
            "relevant_world_rules_text": context.relevant_world_rules_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "style_card_text": context.style_card_text,
            "chapter_text": chapter_text,
            "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
            "planned_blocks_json": cls.chapter_plan_json(planned_blocks),
            "active_twists": active_twists,
            "active_twists_json": cls.json_text(active_twists),
        }

    @classmethod
    def build_chapter_patch_plan_payload(
        cls,
        *,
        chapter_text: str,
        chapter_brief: ChapterBrief,
        context: Any,
        review_reports: dict[str, Any],
        planned_blocks: list[ContentBlock],
    ) -> dict[str, Any]:
        return {
            "chapter_text": chapter_text,
            "planned_blocks_json": cls.chapter_plan_json(planned_blocks),
            "review_reports": review_reports,
            "chapter_summary_context_text": cls.chapter_summary_context(
                chapter_brief=chapter_brief,
                context=context,
            ),
            "relationship_state_text": context.relationship_state_text,
        }

    @classmethod
    def build_rewrite_blocks_by_plan_payload(
        cls,
        *,
        context: Any,
        planned_blocks: list[ContentBlock],
        patch_plan: dict[str, Any],
    ) -> dict[str, Any]:
        chapter_plan_json = cls.chapter_plan_json(planned_blocks)
        return {
            "planned_blocks_json": chapter_plan_json,
            "original_blocks_json": chapter_plan_json,
            "patch_plan": patch_plan,
            "chapter_payload_text": context.chapter_payload_text,
            "scene_character_context_text": context.scene_character_context_text,
            "relationship_state_text": context.relationship_state_text,
            "chapter_character_mindsets_text": getattr(context, "chapter_character_mindsets_text", ""),
            "style_card_text": context.style_card_text,
        }

    @classmethod
    def build_judge_patched_chapter_payload(
        cls,
        *,
        chapter_text: str,
        chapter_brief: ChapterBrief,
        context: Any,
        content_blocks: list[ContentBlock],
        patch_plan: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "merged_chapter_text": chapter_text,
            "patch_plan_json": cls.json_text(patch_plan),
            "patched_block_contexts_json": cls.patched_block_contexts_json(
                content_blocks=content_blocks,
                patch_plan=patch_plan,
            ),
            "minimal_context_text": cls.minimal_patch_context(
                chapter_brief=chapter_brief,
                context=context,
            ),
        }

    @staticmethod
    def build_final_polish_payload(
        *,
        context: Any,
        chapter_text: str,
        loaded_skill_instructions_text: str,
        chapter_brief: ChapterBrief | None = None,
    ) -> dict[str, Any]:
        return {
            "chapter_payload_text": context.chapter_payload_text,
            "style_card_text": context.style_card_text,
            "chapter_text": chapter_text,
            "target_length": ChapterToolPayloadBuilder.chapter_target_length_guard(
                chapter_brief=chapter_brief,
                fallback_text=getattr(context, "step_8_chapter_brief_text", ""),
            ),
            "loaded_skill_instructions_text": loaded_skill_instructions_text,
        }

    @staticmethod
    def target_length_guard(target_chars: int | str | None) -> str:
        try:
            target = int(target_chars or 0)
        except (TypeError, ValueError):
            target = 0
        if target <= 0:
            return "No numeric target. Keep this beat as short as possible and stop once the turn lands."
        ideal_low = max(180, int(round(target * 0.75)))
        return (
            f"Hard ceiling: {target} Chinese characters. "
            f"Ideal range: {ideal_low}-{target}. "
            "Stop immediately after this beat's turn and end_state land; do not add a second action cycle or explanation."
        )

    @staticmethod
    def chapter_target_length_guard(*, chapter_brief: ChapterBrief | None, fallback_text: str = "") -> str:
        raw = chapter_brief.info_budget if chapter_brief is not None else str(fallback_text or "")
        import re

        values = [int(item) for item in re.findall(r"\d+", raw)]
        if len(values) >= 2:
            low, high = min(values[0], values[1]), max(values[0], values[1])
            return (
                f"Hard ceiling: {high} Chinese characters. Ideal range: {low}-{high}. "
                "If current text is over the ceiling, shorten by deleting repeated process steps, repeated explanations, and after-turn psychology."
            )
        if len(values) == 1:
            high = values[0]
            low = max(800, int(round(high * 0.8)))
            return (
                f"Hard ceiling: {high} Chinese characters. Ideal range: {low}-{high}. "
                "If current text is over the ceiling, shorten instead of adding polish."
            )
        return "No numeric chapter target. Final polish should not expand the chapter."

    @staticmethod
    def build_format_adjustment_payload(
        *,
        context: Any,
        chapter_text: str,
        output_format_rules: list[str],
    ) -> dict[str, Any]:
        return {
            "final_polished_text": chapter_text,
            "output_format_rules": output_format_rules,
            "loaded_tool_context": context.chapter_payload_text,
        }

    @classmethod
    def build_summarize_actual_chapter_payload(
        cls,
        *,
        chapter_text: str,
        chapter_brief: ChapterBrief,
        context: Any,
    ) -> dict[str, Any]:
        return {
            "chapter_text": chapter_text,
            "chapter_brief_json": chapter_brief.model_dump_json(indent=2),
            "step_1_story_foundation_text": context.step_1_story_foundation_text,
            "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
            "step_3_character_packets_text": context.step_3_character_packets_text,
            "step_4_event_timeline_text": context.step_4_event_timeline_text,
            "step_5_character_milestones_text": context.step_5_character_milestones_text,
            "step_6_twists_text": context.step_6_twists_text,
            "step_7_story_lines_text": context.step_7_story_lines_text,
            "step_8_chapter_brief_text": context.step_8_chapter_brief_text,
            "chapter_payload_text": context.chapter_payload_text,
            "time_anchor_text": context.time_anchor_text,
            "active_twists": [item.model_dump(mode="json") for item in context.active_twists],
            "active_story_lines": [item.model_dump(mode="json") for item in context.active_story_lines],
        }

    @classmethod
    def chapter_plan_json(cls, planned_blocks: list[ContentBlock]) -> str:
        return cls.json_text({"blocks": [block.model_dump(mode="json") for block in planned_blocks]})

    @classmethod
    def step_1_to_7_outputs_json(cls, context: Any) -> str:
        return cls.json_text(
            {
                "step_1_story_foundation_text": context.step_1_story_foundation_text,
                "step_2_worldbuilding_text": context.step_2_worldbuilding_text,
                "step_3_character_packets_text": context.step_3_character_packets_text,
                "step_4_event_timeline_text": context.step_4_event_timeline_text,
                "step_5_character_milestones_text": context.step_5_character_milestones_text,
                "step_6_twists_text": context.step_6_twists_text,
                "step_7_story_lines_text": context.step_7_story_lines_text,
            }
        )

    @classmethod
    def block_card_text(cls, block: ContentBlock) -> str:
        lines = [
            "[Content block card]",
            "",
            f"block_id: {block.block_id}",
            f"chapter_id: {block.chapter_id}",
            f"block_index: {block.block_index}",
            f"purpose: {block.purpose}",
            f"scene_goal: {block.scene_goal}",
            f"new_value: {block.new_value}",
            f"relationship_delta: {block.relationship_delta}",
            f"clue_delta: {block.clue_delta}",
            f"emotional_tone: {block.emotional_tone}",
            f"end_state: {block.end_state}",
            f"cost_shift: {block.cost_shift}",
            f"reader_feeling_target: {block.reader_feeling_target}",
            f"paragraph_budget: {block.paragraph_budget}",
            f"target_chars: {block.target_chars}",
            f"micro_hook: {block.micro_hook}",
            f"turn_type: {block.turn_type}",
            "paragraph_shape:",
        ]
        for item in block.paragraph_shape or ["None."]:
            lines.append(f"- {item}")
        lines.append("character_anchor_line:")
        if block.character_anchor_line is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- owner: {block.character_anchor_line.owner or 'None.'}",
                    f"- form: {block.character_anchor_line.form or 'None.'}",
                    f"- surface_function: {block.character_anchor_line.surface_function or 'None.'}",
                    f"- hidden_function: {block.character_anchor_line.hidden_function or 'None.'}",
                    f"- must_reveal_about_character: {block.character_anchor_line.must_reveal_about_character or 'None.'}",
                    f"- preferred_shape: {block.character_anchor_line.preferred_shape or 'None.'}",
                    "- must_not_do:",
                ]
            )
            for item in block.character_anchor_line.must_not_do or ["None."]:
                lines.append(f"  - {item}")
        lines.append("characters:")
        for item in block.characters or ["None."]:
            lines.append(f"- {item}")
        lines.append("active_lines:")
        for item in block.active_lines or ["None."]:
            lines.append(f"- {item}")
        lines.append("active_twists:")
        for item in block.active_twists or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_reveal:")
        for item in block.must_reveal or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_hide:")
        for item in block.must_hide or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_not_repeat:")
        for item in block.must_not_repeat or ["None."]:
            lines.append(f"- {item}")
        lines.append("must_land_in_action:")
        for item in block.must_land_in_action or ["None."]:
            lines.append(f"- {item}")
        lines.append("human_reaction_target:")
        for item in block.human_reaction_target or ["None."]:
            lines.append(f"- {item}")
        lines.append("style_risk_guard:")
        for item in block.style_risk_guard or ["None."]:
            lines.append(f"- {item}")
        lines.append("character_reentry_mode:")
        if block.character_reentry_mode is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- target_character: {block.character_reentry_mode.target_character or 'None.'}",
                    f"- identity_already_known: {block.character_reentry_mode.identity_already_known}",
                    f"- reentry_strategy: {block.character_reentry_mode.reentry_strategy or 'None.'}",
                    f"- first_signal: {block.character_reentry_mode.first_signal or 'None.'}",
                    f"- first_emotional_focus: {block.character_reentry_mode.first_emotional_focus or 'None.'}",
                    "- must_avoid:",
                ]
            )
            for item in block.character_reentry_mode.must_avoid or ["None."]:
                lines.append(f"  - {item}")
        lines.append("clue_reveal_mechanism:")
        if block.clue_reveal_mechanism is None:
            lines.append("- None.")
        else:
            lines.extend(
                [
                    f"- clue: {block.clue_reveal_mechanism.clue or 'None.'}",
                    f"- style: {block.clue_reveal_mechanism.style or 'None.'}",
                    f"- pressure_source: {block.clue_reveal_mechanism.pressure_source or 'None.'}",
                    f"- surface_trigger: {block.clue_reveal_mechanism.surface_trigger or 'None.'}",
                    f"- first_noticer: {block.clue_reveal_mechanism.first_noticer or 'None.'}",
                    f"- owner_reaction: {block.clue_reveal_mechanism.owner_reaction or 'None.'}",
                ]
            )
        return "\n".join(lines).strip()

    @classmethod
    def block_prompt_fields(cls, block: ContentBlock) -> dict[str, str]:
        return {
            "human_reaction_target": cls.json_text(list(block.human_reaction_target or [])),
            "cost_shift": str(block.cost_shift or "").strip(),
            "reader_feeling_target": str(block.reader_feeling_target or "").strip(),
            "paragraph_budget": str(block.paragraph_budget or "").strip(),
            "target_chars": str(int(block.target_chars or 0)),
            "new_value": str(block.new_value or "").strip(),
            "must_not_repeat": cls.json_text(list(block.must_not_repeat or [])),
            "relationship_delta": str(block.relationship_delta or "").strip(),
            "clue_delta": str(block.clue_delta or "").strip(),
            "must_land_in_action": cls.json_text(list(block.must_land_in_action or [])),
            "micro_hook": str(block.micro_hook or "").strip(),
            "turn_type": str(block.turn_type or "").strip(),
            "paragraph_shape": cls.json_text(list(block.paragraph_shape or [])),
            "character_anchor_line": (
                cls.json_text(block.character_anchor_line.model_dump(mode="json"))
                if block.character_anchor_line is not None
                else ""
            ),
            "style_risk_guard": cls.json_text(list(block.style_risk_guard or [])),
            "clue_reveal_mechanism": (
                cls.json_text(block.clue_reveal_mechanism.model_dump(mode="json"))
                if block.clue_reveal_mechanism is not None
                else ""
            ),
            "character_reentry_mode": (
                cls.json_text(block.character_reentry_mode.model_dump(mode="json"))
                if block.character_reentry_mode is not None
                else ""
            ),
        }

    @classmethod
    def compact_beat_json(cls, *, block: ContentBlock, block_context: dict[str, Any] | None = None) -> str:
        previous = str((block_context or {}).get("prior_block_summary_text") or "").strip()
        start = ""
        if previous and "No committed blocks yet." not in previous:
            start = cls.tail_text(previous, max_chars=420)
        else:
            start = "Open from the chapter's live pressure; do not recap."
        payload = {
            "goal": cls.first_nonempty(block.scene_goal, block.purpose, block.new_value),
            "start": start,
            "turn": cls.first_nonempty(block.new_value, block.relationship_delta, block.clue_delta, block.turn_type),
            "end": cls.first_nonempty(block.end_state, block.micro_hook),
            "avoid": cls.compact_avoid(block),
        }
        return cls.json_text(payload)

    @classmethod
    def compact_avoid(cls, block: ContentBlock) -> list[str]:
        avoid = list(block.must_not_repeat or [])
        avoid.extend(block.must_hide or [])
        avoid.extend(block.style_risk_guard[:1] if block.style_risk_guard else [])
        cleaned = [str(item or "").strip() for item in avoid if str(item or "").strip()]
        return cleaned[:5]

    @classmethod
    def compact_chapter_goal(cls, *, context: Any) -> str:
        lines = [
            str(getattr(context, "chapter_payload_text", "") or "").strip(),
            str(getattr(context, "assistant_persona_prompt", "") or "").strip(),
            str(getattr(context, "writing_requirements_json", "") or "").strip(),
        ]
        return cls.tail_text("\n\n".join(item for item in lines if item), max_chars=1800)

    @classmethod
    def compact_hard_facts(cls, *, context: Any, block: ContentBlock) -> str:
        lines = [
            "[World / timeline]",
            str(getattr(context, "relevant_world_rules_text", "") or "").strip(),
            str(getattr(context, "timeline_anchor_facts_text", "") or "").strip(),
            "",
            "[Must reveal]",
            cls.json_text(list(block.must_reveal or [])),
            "",
            "[Must hide]",
            cls.json_text(list(block.must_hide or [])),
        ]
        return cls.tail_text("\n".join(lines), max_chars=1400)

    @classmethod
    def compact_character_state(cls, *, context: Any) -> str:
        text = str(getattr(context, "chapter_character_mindsets_text", "") or "").strip()
        if not text:
            text = str(getattr(context, "chapter_visible_context_text", "") or "").strip()
        return cls.tail_text(text, max_chars=1200)

    @classmethod
    def compact_chapter_so_far(cls, *, committed_blocks: list[ContentBlock]) -> str:
        if not committed_blocks:
            return "No beat has landed yet."
        lines: list[str] = []
        for block in committed_blocks[-3:]:
            lines.append(
                " / ".join(
                    item
                    for item in [
                        block.end_state,
                        block.micro_hook,
                        cls.tail_text(str(block.text or ""), max_chars=180),
                    ]
                    if str(item or "").strip()
                )
            )
        return "\n".join(lines).strip()

    @classmethod
    def compact_style_rules(cls, *, context: Any) -> str:
        return cls.tail_text(str(getattr(context, "style_card_text", "") or "").strip(), max_chars=1000)

    @staticmethod
    def first_nonempty(*items: str) -> str:
        for item in items:
            text = str(item or "").strip()
            if text:
                return text
        return ""

    @classmethod
    def chapter_summary_context(cls, *, chapter_brief: ChapterBrief, context: Any) -> str:
        lines = [
            f"chapter_id: {chapter_brief.chapter_id}",
            f"title: {chapter_brief.title}",
            f"summary: {chapter_brief.summary}",
            "",
            "[Step 8 chapter brief]",
            str(context.step_8_chapter_brief_text or "").strip(),
            "",
            "[Chapter payload]",
            str(context.chapter_payload_text or "").strip(),
        ]
        return "\n".join(item for item in lines if item is not None).strip()

    @classmethod
    def patched_block_contexts_json(
        cls,
        *,
        content_blocks: list[ContentBlock],
        patch_plan: dict[str, Any],
    ) -> str:
        block_map = {block.block_id: block for block in content_blocks}
        ordered_ids = [block.block_id for block in content_blocks]
        contexts: list[dict[str, Any]] = []
        for target in list(patch_plan.get("patch_targets") or []):
            block_id = str(target.get("target_id") or "").strip()
            if not block_id or block_id not in block_map:
                continue
            current = block_map[block_id]
            previous_block = cls.neighbor_by_id(content_blocks, block_id, offset=-1)
            next_block = cls.neighbor_by_id(content_blocks, block_id, offset=1)
            contexts.append(
                {
                    "block_id": block_id,
                    "problem_type": target.get("problem_type", ""),
                    "goal": target.get("goal", ""),
                    "instructions": list(target.get("instructions") or []),
                    "current_block_text": current.text,
                    "previous_block_text": previous_block.text if previous_block is not None else "",
                    "next_block_text": next_block.text if next_block is not None else "",
                    "all_block_ids": ordered_ids,
                }
            )
        return cls.json_text(contexts)

    @classmethod
    def minimal_patch_context(cls, *, chapter_brief: ChapterBrief, context: Any) -> str:
        lines = [
            f"chapter_id: {chapter_brief.chapter_id}",
            f"chapter_title: {chapter_brief.title}",
            f"chapter_summary: {chapter_brief.summary}",
            "",
            "[Relationship state]",
            str(context.relationship_state_text or "").strip(),
            "",
            "[Time anchor]",
            str(context.time_anchor_text or "").strip(),
        ]
        return "\n".join(lines).strip()

    @staticmethod
    def neighbor_by_id(
        blocks: list[ContentBlock],
        block_id: str,
        *,
        offset: int,
    ) -> ContentBlock | None:
        ordered_ids = [block.block_id for block in blocks]
        if block_id not in ordered_ids:
            return None
        index = ordered_ids.index(block_id) + offset
        if index < 0 or index >= len(blocks):
            return None
        return blocks[index]

    @staticmethod
    def tail_text(text: str, *, max_chars: int = 1200) -> str:
        clean = str(text or "").strip()
        return clean[-max_chars:] if clean else ""

    @staticmethod
    def json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)
