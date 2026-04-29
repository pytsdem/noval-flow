from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Sequence

from novel_flow.models.schemas import (
    ActualChapterSummary,
    ChapterBeat,
    ChapterContract,
    CharacterCard,
    StoryLine,
    StoryPremise,
    TwistDesign,
    WriterContext,
)
from novel_flow.services.style_cards import render_style_card
from novel_flow.services.selectors import (
    get_character_card_by_name,
    get_character_milestone_by_name,
)


SelectionStrategy = Literal[
    "writer_context",
    "character_mindset_scoped_steps",
]

_CN_NUMERAL_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _normalize_text(value)
        if text:
            return text
    return ""


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_revealed(current_chapter_id: str, reveal_at: str) -> bool:
    return _chapter_order(current_chapter_id) >= _chapter_order(reveal_at)


def _event_timeline(worldbuilding: dict[str, Any]) -> list[dict[str, Any]]:
    raw = worldbuilding.get("event_timeline", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


@dataclass(frozen=True)
class CurrentChapterRuntimeSelection:
    chapter_id: str
    relevant_blocks: list[ChapterBeat]
    recent_blocks: list[ChapterBeat]
    chapter_draft_tail: str


@dataclass(frozen=True)
class CharacterScopedStepContext:
    step_5_character_milestones_text: str
    step_6_twists_text: str


@dataclass(frozen=True)
class WriterContextSelection:
    snapshot: NovelContextSnapshot  # type: ignore[name-defined]
    writer_focus_names: list[str]
    focus_character_cards: dict[str, CharacterCard]
    hidden_character_names: set[str]
    focus_milestone_packets: dict[str, dict[str, Any]]
    full_event_timeline: list[dict[str, Any]]
    selected_timeline_events: list[dict[str, Any]]
    timeline_consistency_notes: list[str]
    relevant_world_rules: list[str]


@dataclass(frozen=True)
class CharacterMindsetScopedSelection:
    snapshot: NovelContextSnapshot  # type: ignore[name-defined]
    character_name: str
    milestone_packet: dict[str, Any] | None
    related_twists: list[TwistDesign]


@dataclass(frozen=True)
class NovelContextSnapshot:
    chapter_brief: ChapterContract
    current_chapter_id: str
    premise: StoryPremise | None
    worldbuilding: dict[str, Any]
    character_cards: Sequence[CharacterCard]
    character_milestones: Sequence[dict[str, Any]]
    actual_summaries: Sequence[ActualChapterSummary]
    active_twists: list[TwistDesign]
    active_story_lines: list[StoryLine]


class NovelContextSelectorService:
    @classmethod
    def create_snapshot(
        cls,
        *,
        chapter_brief: ChapterContract,
        twist_designs: Sequence[TwistDesign],
        story_lines: Sequence[StoryLine],
        worldbuilding: dict[str, Any] | None,
        character_cards: Sequence[CharacterCard] | Sequence[Any],
        character_milestones: Sequence[dict[str, Any]] | None,
        actual_summaries: Sequence[ActualChapterSummary],
        current_chapter_id: str,
        premise: StoryPremise | None = None,
    ) -> NovelContextSnapshot:
        active_twist_ids = set(chapter_brief.active_twists)
        active_line_ids = set(chapter_brief.active_lines)
        return NovelContextSnapshot(
            chapter_brief=chapter_brief,
            current_chapter_id=current_chapter_id,
            premise=premise,
            worldbuilding=dict(worldbuilding or {}),
            character_cards=list(character_cards),
            character_milestones=list(character_milestones or []),
            actual_summaries=list(actual_summaries),
            active_twists=[twist for twist in twist_designs if twist.twist_id in active_twist_ids],
            active_story_lines=[line for line in story_lines if line.line_id in active_line_ids],
        )

    @classmethod
    def select(
        cls,
        *,
        snapshot: NovelContextSnapshot,
        strategy: SelectionStrategy,
        character_name: str = "",
    ) -> WriterContextSelection | CharacterMindsetScopedSelection:
        if strategy == "writer_context":
            return cls._select_writer_context(snapshot=snapshot)
        if strategy == "character_mindset_scoped_steps":
            return cls._select_character_mindset_scoped_steps(
                snapshot=snapshot,
                character_name=character_name,
            )
        raise ValueError(f"Unsupported context selection strategy: {strategy}")

    @classmethod
    def select_current_chapter_context(
        cls,
        chapter_id: str,
        committed_blocks: list[ChapterBeat],
        *,
        max_blocks: int = 4,
        tail_chars: int = 1000,
    ) -> CurrentChapterRuntimeSelection:
        relevant_blocks = [
            item
            for item in committed_blocks
            if item.chapter_id == chapter_id and str(item.status or "").strip() == "committed"
        ]
        recent_blocks = relevant_blocks[-max_blocks:] if max_blocks > 0 else list(relevant_blocks)
        chapter_text = "\n\n".join(
            str(item.text or "").strip()
            for item in relevant_blocks
            if str(item.text or "").strip()
        ).strip()
        tail = chapter_text[-tail_chars:] if chapter_text and tail_chars > 0 else chapter_text
        return CurrentChapterRuntimeSelection(
            chapter_id=chapter_id,
            relevant_blocks=relevant_blocks,
            recent_blocks=recent_blocks,
            chapter_draft_tail=tail,
        )

    @classmethod
    def _select_writer_context(cls, *, snapshot: NovelContextSnapshot) -> WriterContextSelection:
        writer_focus_names = cls._writer_context_focus_names(snapshot)
        focus_character_cards = {
            name: card
            for name in writer_focus_names
            if (card := get_character_card_by_name(snapshot.character_cards, name)) is not None
        }
        hidden_character_names = {
            name
            for twist in snapshot.active_twists
            if not _is_revealed(snapshot.current_chapter_id, twist.reveal_at)
            for name in twist.related_characters
            if _normalize_text(name)
        }
        focus_milestone_packets = {
            name: item
            for name in writer_focus_names
            if isinstance(
                item := get_character_milestone_by_name(snapshot.character_milestones, name),
                dict,
            )
        }
        full_event_timeline = _event_timeline(snapshot.worldbuilding)
        selected_timeline_events: list[dict[str, Any]] = []
        timeline_consistency_notes: list[str] = []
        ranked = cls._rank_events(
            chapter_brief=snapshot.chapter_brief,
            event_timeline=full_event_timeline,
        )
        if ranked:
            anchor_index = ranked[0][0]
            selected_indices = cls._select_context_window(
                anchor_index=anchor_index,
                ranked=ranked,
                event_timeline=full_event_timeline,
                chapter_brief=snapshot.chapter_brief,
            )
            selected_timeline_events = [full_event_timeline[index] for index in selected_indices]
            timeline_consistency_notes = cls._build_consistency_notes(
                anchor_event=full_event_timeline[anchor_index],
                prior_events=[
                    full_event_timeline[index]
                    for index in selected_indices
                    if index < anchor_index
                ],
            )
        return WriterContextSelection(
            snapshot=snapshot,
            writer_focus_names=writer_focus_names,
            focus_character_cards=focus_character_cards,
            hidden_character_names=hidden_character_names,
            focus_milestone_packets=focus_milestone_packets,
            full_event_timeline=full_event_timeline,
            selected_timeline_events=selected_timeline_events,
            timeline_consistency_notes=timeline_consistency_notes,
            relevant_world_rules=cls._select_relevant_world_rules(snapshot),
        )

    @classmethod
    def _select_character_mindset_scoped_steps(
        cls,
        *,
        snapshot: NovelContextSnapshot,
        character_name: str,
    ) -> CharacterMindsetScopedSelection:
        clean_name = _normalize_text(character_name)
        related_twists = [
            twist
            for twist in snapshot.active_twists
            if clean_name in {_normalize_text(name) for name in twist.related_characters}
        ]
        milestone_packet = get_character_milestone_by_name(
            snapshot.character_milestones,
            clean_name,
        )
        return CharacterMindsetScopedSelection(
            snapshot=snapshot,
            character_name=clean_name,
            milestone_packet=milestone_packet if isinstance(milestone_packet, dict) else None,
            related_twists=related_twists,
        )

    @staticmethod
    def _chapter_focus_names(chapter_brief: ChapterContract) -> list[str]:
        return list(
            dict.fromkeys(
                _normalize_text(name)
                for name in chapter_brief.character_focus
                if _normalize_text(name)
            )
        )

    @classmethod
    def _writer_context_focus_names(cls, snapshot: NovelContextSnapshot) -> list[str]:
        names = cls._chapter_focus_names(snapshot.chapter_brief)
        for twist in snapshot.active_twists:
            for name in twist.related_characters:
                clean = _normalize_text(name)
                if clean and clean not in names:
                    names.append(clean)
        return names

    @classmethod
    def _select_relevant_world_rules(cls, snapshot: NovelContextSnapshot) -> list[str]:
        rules: list[str] = [snapshot.chapter_brief.world_limit]
        story_engine = snapshot.worldbuilding.get("story_engine", {})
        if isinstance(story_engine, dict):
            for key in ("world_rules", "power_structure", "objective_conditions", "structural_inertia"):
                value = story_engine.get(key, [])
                if isinstance(value, list):
                    rules.extend(_normalize_text(item) for item in value if _normalize_text(item))
                elif _normalize_text(value):
                    rules.append(_normalize_text(value))
        return list(dict.fromkeys(rule for rule in rules if rule))

    @classmethod
    def _rank_events(
        cls,
        *,
        chapter_brief: ChapterContract,
        event_timeline: list[dict[str, Any]],
    ) -> list[tuple[int, int]]:
        search_terms = cls._collect_search_terms(chapter_brief)
        focus_names = {name for name in chapter_brief.character_focus if _normalize_text(name)}
        ranked: list[tuple[int, int]] = []
        for index, event in enumerate(event_timeline):
            haystack = "\n".join(
                [
                    _normalize_text(event.get("title")),
                    _normalize_text(event.get("time_label")),
                    _normalize_text(event.get("description")),
                    _normalize_text(event.get("trigger")),
                    _normalize_text(event.get("consequence")),
                    " ".join(
                        _normalize_text(item)
                        for item in event.get("affected_characters", [])
                        if _normalize_text(item)
                    ),
                ]
            )
            affected = {
                _normalize_text(item)
                for item in event.get("affected_characters", [])
                if _normalize_text(item)
            }
            score = 0
            if focus_names & affected:
                score += 30 + 5 * len(focus_names & affected)
            for term in search_terms:
                if term and term in haystack:
                    score += 6 if len(term) >= 6 else 3
            chapter_object = _normalize_text(chapter_brief.plot_carrier)
            if chapter_object and chapter_object in haystack:
                score += 12
            backstory_trigger = _normalize_text(chapter_brief.backstory_trigger)
            if backstory_trigger and backstory_trigger in haystack:
                score += 12
            if score > 0:
                ranked.append((index, score))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    @classmethod
    def _select_context_window(
        cls,
        *,
        anchor_index: int,
        ranked: list[tuple[int, int]],
        event_timeline: list[dict[str, Any]],
        chapter_brief: ChapterContract,
    ) -> list[int]:
        focus_names = {name for name in chapter_brief.character_focus if _normalize_text(name)}
        ranked_map = {index: score for index, score in ranked}
        indices: set[int] = {anchor_index}

        for index in range(max(0, anchor_index - 4), anchor_index):
            affected = {
                _normalize_text(item)
                for item in event_timeline[index].get("affected_characters", [])
                if _normalize_text(item)
            }
            if ranked_map.get(index, 0) > 0 or (focus_names and focus_names & affected):
                indices.add(index)

        if len(indices) < 3:
            for index, _score in ranked[1:]:
                if index <= anchor_index:
                    indices.add(index)
                if len(indices) >= 4:
                    break
        return sorted(indices)

    @classmethod
    def _build_consistency_notes(
        cls,
        *,
        anchor_event: dict[str, Any],
        prior_events: list[dict[str, Any]],
    ) -> list[str]:
        notes: list[str] = []
        anchor_title = _normalize_text(anchor_event.get("title")) or "current anchor"
        anchor_time = _normalize_text(anchor_event.get("time_label")) or "unknown time"
        anchor_start, anchor_end = cls._extract_year_bounds(anchor_time)
        if not prior_events:
            notes.append(f"Current chapter anchor is '{anchor_title}' at {anchor_time}.")
            return notes

        latest_prior = prior_events[-1]
        prior_title = _normalize_text(latest_prior.get("title")) or "prior event"
        prior_time = _normalize_text(latest_prior.get("time_label")) or "unknown time"
        prior_start, prior_end = cls._extract_year_bounds(prior_time)
        notes.append(f"Current chapter anchor is '{anchor_title}' at {anchor_time}.")
        notes.append(f"The nearest relevant prehistory is '{prior_title}' at {prior_time}.")
        if None in {anchor_start, anchor_end, prior_start, prior_end}:
            return notes

        lower_gap = max(0, anchor_start - prior_end)
        upper_gap = max(lower_gap, anchor_end - prior_start)
        if lower_gap == upper_gap:
            notes.append(
                f"The supported elapsed window between these anchors is about {lower_gap} year(s). Do not invent a different exact duration."
            )
        else:
            notes.append(
                f"The supported elapsed window between these anchors is about {lower_gap} to {upper_gap} year(s). Do not invent a different exact duration."
            )
        return notes

    @classmethod
    def _collect_search_terms(cls, chapter_brief: ChapterContract) -> list[str]:
        base_terms = [
            chapter_brief.title,
            chapter_brief.chapter_mission,
            chapter_brief.incoming_hook,
            chapter_brief.opening_hook,
            chapter_brief.plot_carrier,
            chapter_brief.backstory_trigger,
            chapter_brief.must_payoff,
            chapter_brief.final_hook,
            *chapter_brief.allowed_info,
            *chapter_brief.allowed_clues,
            *chapter_brief.character_focus,
        ]
        terms: list[str] = []
        for item in base_terms:
            text = _normalize_text(item)
            if not text:
                continue
            terms.append(text)
            parts = re.split(r"[，。；：、（）()《》“”‘’\s/|]+", text)
            for part in parts:
                clean = part.strip()
                if len(clean) >= 2:
                    terms.append(clean)
        return list(dict.fromkeys(term for term in terms if term))

    @classmethod
    def _extract_year_bounds(cls, time_label: str) -> tuple[int | None, int | None]:
        matches = re.findall(r"([0-9零一二两三四五六七八九十]+)年", _normalize_text(time_label))
        years = [cls._parse_cn_number(item) for item in matches]
        filtered = [item for item in years if item is not None]
        if not filtered:
            return None, None
        return min(filtered), max(filtered)

    @staticmethod
    def _parse_cn_number(text: str) -> int | None:
        raw = _normalize_text(text)
        if not raw:
            return None
        if raw.isdigit():
            return int(raw)
        if raw == "十":
            return 10
        if "十" in raw:
            left, _, right = raw.partition("十")
            tens = _CN_NUMERAL_MAP.get(left, 1 if left == "" else -1)
            ones = _CN_NUMERAL_MAP.get(right, 0 if right == "" else -1)
            if tens < 0 or ones < 0:
                return None
            return tens * 10 + ones
        total = 0
        for char in raw:
            if char not in _CN_NUMERAL_MAP:
                return None
            total = total * 10 + _CN_NUMERAL_MAP[char]
        return total


class NovelContextFormatter:
    @classmethod
    def format_writer_context(
        cls,
        selection: WriterContextSelection,
        *,
        context_sanitizer: Any | None = None,
    ) -> WriterContext:
        snapshot = selection.snapshot
        scene_character_context_text = cls._scene_character_context_text(selection)
        context = WriterContext(
            chapter_id=snapshot.chapter_brief.chapter_id,
            selection_summary_text="[Context selection]\n尚未生成 selection 摘要。",
            time_anchor_text="[Time anchor]\n尚未生成时间锚点。",
            chapter_visible_context_text="[Chapter visible context]\n尚未生成章节可见上下文。",
            completed_chapter_memory_text=cls._completed_chapter_memory_text(snapshot.actual_summaries),
            step_1_story_foundation_text=cls._step_1_story_foundation_text(snapshot),
            step_2_worldbuilding_text=cls._step_2_worldbuilding_text(snapshot.worldbuilding),
            step_3_character_packets_text=scene_character_context_text,
            step_4_event_timeline_text=cls._full_event_timeline_text(selection.full_event_timeline),
            step_5_character_milestones_text=cls._step_5_character_milestones_text(
                packets=selection.focus_milestone_packets,
                focus_names=selection.writer_focus_names,
                title="[Step 5 relevant character milestones]",
            ),
            step_6_twists_text=cls._step_6_twists_text(
                current_chapter_id=snapshot.current_chapter_id,
                twists=snapshot.active_twists,
                title="[Step 6 active twist packets]",
            ),
            step_7_story_lines_text=cls._step_7_story_lines_text(snapshot.active_story_lines),
            step_8_chapter_brief_text=cls._step_8_chapter_brief_text(snapshot.chapter_brief),
            chapter_payload_text=cls._chapter_payload_text(snapshot),
            timeline_anchor_facts_text=cls._timeline_anchor_facts_text(
                selection.selected_timeline_events,
                selection.timeline_consistency_notes,
            ),
            relevant_world_rules_text=cls._relevant_world_rules_text(selection.relevant_world_rules),
            style_card_text=render_style_card(
                premise=snapshot.premise,
                chapter_brief=snapshot.chapter_brief,
            ),
            active_twists=snapshot.active_twists,
            active_story_lines=snapshot.active_story_lines,
            scene_character_context_text=scene_character_context_text,
            relationship_state_text=cls._relationship_state_text(snapshot),
        )
        if context_sanitizer is not None:
            return context_sanitizer.sanitize_writer_context(
                writer_context=context,
                current_chapter_id=snapshot.current_chapter_id,
                active_twists=snapshot.active_twists,
            )
        return context

    @classmethod
    def format_character_mindset_scoped_steps(
        cls,
        selection: CharacterMindsetScopedSelection,
    ) -> CharacterScopedStepContext:
        return CharacterScopedStepContext(
            step_5_character_milestones_text=cls._step_5_character_milestones_text(
                packets=(
                    {selection.character_name: selection.milestone_packet}
                    if isinstance(selection.milestone_packet, dict)
                    else {}
                ),
                focus_names=[selection.character_name],
                title="[Step 5 scoped character milestones]",
            ),
            step_6_twists_text=cls._step_6_twists_text(
                current_chapter_id=selection.snapshot.current_chapter_id,
                twists=selection.related_twists,
                title="[Step 6 scoped twist packets]",
                character_name=selection.character_name,
            ),
        )

    @staticmethod
    def format_current_chapter_context(
        selection: CurrentChapterRuntimeSelection,
    ) -> dict[str, Any]:
        if not selection.relevant_blocks:
            return {
                "current_chapter_written_blocks_json": [],
                "current_chapter_draft_tail": "",
            }
        return {
            "current_chapter_written_blocks_json": [
                {
                    "block_id": item.block_id,
                    "block_index": item.block_index,
                    "purpose": item.purpose,
                    "scene_goal": item.scene_goal,
                    "new_value": item.new_value,
                    "relationship_delta": item.relationship_delta,
                    "clue_delta": item.clue_delta,
                    "end_state": item.end_state,
                    "micro_hook": item.micro_hook,
                    "text": str(item.text or "").strip(),
                }
                for item in selection.recent_blocks
            ],
            "current_chapter_draft_tail": selection.chapter_draft_tail,
        }

    @staticmethod
    def _completed_chapter_memory_text(actual_summaries: Sequence[ActualChapterSummary]) -> str:
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
    def _step_1_story_foundation_text(snapshot: NovelContextSnapshot) -> str:
        lines = ["[Step 1 story foundation]"]
        if snapshot.premise is None:
            lines.append("No premise data available.")
            return "\n".join(lines).strip()
        premise = snapshot.premise
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
                f"Current chapter mission inside this foundation: {snapshot.chapter_brief.chapter_mission}",
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
        if not worldbuilding:
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
                value = _normalize_text(story_engine.get(key))
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
                    text = _normalize_text(sub_value)
                    if text:
                        lines.append(f"- {sub_key}: {text}")

        for key, title in (
            ("setpiece_library", "Setpiece library"),
            ("writing_constraints", "Writing constraints"),
        ):
            value = worldbuilding.get(key)
            if isinstance(value, list) and value:
                lines.extend(["", f"{title}:"])
                lines.extend(f"- {_normalize_text(item)}" for item in value if _normalize_text(item))
        return "\n".join(lines).strip()

    @classmethod
    def _scene_character_context_text(cls, selection: WriterContextSelection) -> str:
        snapshot = selection.snapshot
        lines = ["[Scene character context]", ""]
        chapter_object = snapshot.chapter_brief.plot_carrier
        for name in selection.writer_focus_names:
            card = selection.focus_character_cards.get(name)
            if card is None:
                continue
            identity = " / ".join(
                part
                for part in [card.role, card.occupation, card.social_background]
                if _normalize_text(part)
            ) or "Identity should be shown naturally in-scene."
            stable_trait = _first_nonempty(card.personality, "Trait should be shown through selective concrete detail.")
            pressure_behavior = _first_nonempty(card.behavior_pattern, "React through deflection, restraint, or tactical delay.")
            visible_goal = _first_nonempty(card.initial_state, chapter_object, card.motivation)
            internal_drive = _first_nonempty(card.motivation, card.initial_state, chapter_object)
            behavior_rules = [
                rule
                for rule in [
                    pressure_behavior,
                    f"Stay inside chapter limit: {snapshot.chapter_brief.world_limit}",
                ]
                if _normalize_text(rule)
            ]
            is_hidden = card.name in selection.hidden_character_names
            lines.extend(
                [
                    f"{card.name}",
                    f"- Public identity: {identity}",
                    f"- Stable trait (book-level): {stable_trait}",
                    f"- Pressure behavior (scene-usable): {pressure_behavior}",
                    f"- Current drive (chapter-facing): {'Hidden motive exists; keep it abstract for prose layer.' if is_hidden else internal_drive}",
                    f"- Visible scene task: {visible_goal}",
                    f"- Action lane: move around '{visible_goal}' without breaking '{snapshot.chapter_brief.world_limit}'.",
                    f"- Behavioral rules: {'; '.join(behavior_rules)}",
                ]
            )
            if is_hidden:
                lines.append("- Hidden truth lock: do not state unrevealed motive, sacrifice, or final arc destination.")
                lines.append("- Allowed outer signs: pause, deflection, restraint, changed address, avoidance, incomplete answer.")
            else:
                emotional_base = _first_nonempty(
                    card.initial_state,
                    "Emotion should surface through action, address, hesitation, and body cost.",
                )
                lines.append(f"- Emotional starting point (chapter-only): {emotional_base}")
            lines.append("")

        if snapshot.chapter_brief.forbidden:
            lines.append("Global chapter bans:")
            for item in snapshot.chapter_brief.forbidden:
                lines.append(f"- {item}")
        return "\n".join(lines).strip()

    @staticmethod
    def _step_5_character_milestones_text(
        *,
        packets: dict[str, dict[str, Any]],
        focus_names: Sequence[str],
        title: str,
    ) -> str:
        names = list(dict.fromkeys(_normalize_text(name) for name in focus_names if _normalize_text(name)))
        lines = [title]
        if not names:
            lines.append("No focused characters for this chapter.")
            return "\n".join(lines).strip()

        matched_any = False
        for name in names:
            item = packets.get(name)
            if not isinstance(item, dict):
                continue
            matched_any = True
            lines.extend(["", name])
            milestone_list = item.get("milestone_list", [])
            if isinstance(milestone_list, list):
                for milestone in milestone_list:
                    if not isinstance(milestone, dict):
                        continue
                    axis = _normalize_text(milestone.get("axis")) or "未命名发展轴"
                    stages = [
                        _normalize_text(stage)
                        for stage in milestone.get("stages", [])
                        if _normalize_text(stage)
                    ]
                    lines.append(f"- {axis}: {' -> '.join(stages) if stages else 'No stage labels.'}")

            axes = item.get("axes", [])
            if not isinstance(axes, list):
                continue
            for axis_item in axes:
                if not isinstance(axis_item, dict):
                    continue
                axis_name = _normalize_text(axis_item.get("axis"))
                if not axis_name:
                    continue
                phases = axis_item.get("phases", [])
                if not isinstance(phases, list):
                    continue
                for phase_item in phases:
                    if not isinstance(phase_item, dict):
                        continue
                    label = _normalize_text(phase_item.get("label")) or _normalize_text(phase_item.get("phase"))
                    if not label:
                        continue
                    lines.append(f"- {axis_name} / {label}")
                    scenes = phase_item.get("scenes", [])
                    if not isinstance(scenes, list):
                        continue
                    for scene_item in scenes:
                        if not isinstance(scene_item, dict):
                            continue
                        title_text = _normalize_text(scene_item.get("title"))
                        trigger = _normalize_text(scene_item.get("trigger"))
                        psychology = _normalize_text(scene_item.get("psychology"))
                        outcome = _normalize_text(scene_item.get("outcome"))
                        detail = "；".join(
                            part
                            for part in [
                                f"title={title_text}" if title_text else "",
                                f"trigger={trigger}" if trigger else "",
                                f"psychology={psychology}" if psychology else "",
                                f"outcome={outcome}" if outcome else "",
                            ]
                            if part
                        )
                        if detail:
                            lines.append(f"  - {detail}")

        if not matched_any:
            fallback = "No relevant character milestones matched current chapter focus."
            if title == "[Step 5 scoped character milestones]" and names:
                fallback = f"No milestone packet for {names[0]}."
            lines.extend(["", fallback])
        return "\n".join(lines).strip()

    @staticmethod
    def _step_6_twists_text(
        *,
        current_chapter_id: str,
        twists: Sequence[TwistDesign],
        title: str,
        character_name: str = "",
    ) -> str:
        lines = [title]
        if not twists:
            empty_text = "No active twists."
            if character_name:
                empty_text = f"No active twist packet directly tied to {character_name}."
            lines.append(empty_text)
            return "\n".join(lines).strip()

        for twist in twists:
            revealed = _is_revealed(current_chapter_id, twist.reveal_at)
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
                    f"- Truth: {twist.truth if revealed else 'hidden until reveal chapter; do not narrate it directly.'}",
                ]
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _step_7_story_lines_text(active_story_lines: Sequence[StoryLine]) -> str:
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
    def _step_8_chapter_brief_text(chapter_brief: ChapterContract) -> str:
        contract = chapter_brief.contract_view()
        lines = [
            "[Step 8 current chapter contract]",
            "",
            f"Chapter id: {chapter_brief.chapter_id}",
            f"Title: {chapter_brief.title}",
            f"Chapter type: {chapter_brief.chapter_type}",
            f"Chapter mission: {contract['chapter_mission']}",
            f"Incoming hook: {chapter_brief.incoming_hook}",
            f"Opening hook: {chapter_brief.opening_hook}",
            f"Core scene: {chapter_brief.core_scene or 'None.'}",
            f"Plot carrier: {contract['plot_carrier']}",
            f"Reader emotion: {chapter_brief.reader_emotion}",
            f"Reader belief: {chapter_brief.reader_belief}",
            f"World limit: {chapter_brief.world_limit}",
            f"Character delta: {contract['character_delta']}",
            f"Relationship delta: {contract['relationship_delta']}",
            f"Emotional turn: {chapter_brief.emotional_turn}",
            f"Cost of progress: {contract['cost_of_progress'] or 'None.'}",
            f"Hook kind: {contract['hook_kind']}",
            f"Pace curve: {contract['pace_curve']}",
            f"Must not repeat: {'; '.join(contract['must_not_repeat']) or 'None.'}",
            f"Backstory trigger: {chapter_brief.backstory_trigger or 'None.'}",
            f"Scene engine: {chapter_brief.scene_engine}",
            f"Clue reveal mechanism: {chapter_brief.clue_reveal_mechanism.model_dump(mode='json') if chapter_brief.clue_reveal_mechanism else {}}",
            f"Character reentry focus: {chapter_brief.character_reentry_focus or {}}",
            f"Human pain anchor: {chapter_brief.human_pain_anchor or 'None.'}",
            f"Romance seed: {chapter_brief.romance_seed or 'None.'}",
            f"Must payoff: {contract['must_payoff']}",
            f"Final hook: {contract['final_hook']}",
            f"Pace contract: {contract['pace_contract']}",
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
    def _chapter_payload_text(snapshot: NovelContextSnapshot) -> str:
        chapter_brief = snapshot.chapter_brief
        contract = chapter_brief.contract_view()
        lines = [
            "[Chapter contract payload]",
            "",
            f"Chapter: {chapter_brief.chapter_id} / {chapter_brief.title}",
            f"Chapter type: {chapter_brief.chapter_type}",
            f"Chapter mission: {contract['chapter_mission']}",
            f"Incoming hook: {chapter_brief.incoming_hook or 'No previous hook.'}",
            f"Opening hook: {chapter_brief.opening_hook}",
            f"Core scene: {chapter_brief.core_scene or 'None.'}",
            f"Plot carrier: {contract['plot_carrier']}",
            f"Scene engine: {chapter_brief.scene_engine}",
            f"Clue reveal mechanism: {chapter_brief.clue_reveal_mechanism.model_dump(mode='json') if chapter_brief.clue_reveal_mechanism else {}}",
            f"Character reentry focus: {chapter_brief.character_reentry_focus or {}}",
            f"Reader emotion target: {chapter_brief.reader_emotion}",
            f"Reader belief to preserve: {chapter_brief.reader_belief}",
            f"Character delta: {contract['character_delta']}",
            f"Relationship delta: {contract['relationship_delta']}",
            f"Emotional turn: {chapter_brief.emotional_turn}",
            f"Cost of progress: {contract['cost_of_progress'] or 'None.'}",
            f"Hook kind: {contract['hook_kind']}",
            f"Pace curve: {contract['pace_curve']}",
            f"Must not repeat: {'; '.join(contract['must_not_repeat']) or 'None.'}",
            f"Backstory trigger: {chapter_brief.backstory_trigger or 'None.'}",
            f"Human pain anchor: {chapter_brief.human_pain_anchor or 'None.'}",
            f"Romance seed: {chapter_brief.romance_seed or 'None.'}",
            f"Must payoff: {contract['must_payoff']}",
            f"Final hook: {contract['final_hook']}",
            f"Pace contract: {contract['pace_contract']}",
            "",
            "Active story lines:",
        ]
        if snapshot.active_story_lines:
            for line in snapshot.active_story_lines:
                rules = "; ".join(line.line_rules) or "None."
                lines.append(
                    f"- {line.line_id}: {line.core_question} | visibility={line.visibility} | rules={rules}"
                )
        else:
            lines.append("- None.")

        lines.extend(["", "Active twists:"])
        if snapshot.active_twists:
            for twist in snapshot.active_twists:
                if _is_revealed(snapshot.current_chapter_id, twist.reveal_at):
                    lines.append(
                        f"- {twist.twist_id}: already at or after reveal chapter; keep only chapter-allowed information and do not overwrite continuity."
                    )
                    continue
                allowed_clues = "; ".join(twist.allowed_clues) or "None."
                forbidden = "; ".join(twist.forbidden_reveals) or "None."
                lines.append(
                    f"- {twist.twist_id}: preserve false belief '{twist.false_belief}'; reader alignment='{twist.reader_alignment}'; "
                    f"allowed clues={allowed_clues}; forbidden reveals={forbidden}; POV lock={twist.pov_lock}"
                )
        else:
            lines.append("- None.")

        hidden_items = list(chapter_brief.forbidden)
        for twist in snapshot.active_twists:
            if not _is_revealed(snapshot.current_chapter_id, twist.reveal_at):
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
    def _relationship_state_text(snapshot: NovelContextSnapshot) -> str:
        focus = NovelContextSelectorService._chapter_focus_names(snapshot.chapter_brief)
        lines = ["[Relationship state]", ""]
        if len(focus) >= 2:
            center = focus[0]
            for other in focus[1:]:
                lines.extend(
                    [
                        f"{center} -> {other}",
                        f"- Current public read: {snapshot.chapter_brief.relationship_delta}",
                        f"- Emotional pressure now: {snapshot.chapter_brief.emotional_turn}",
                        f"- Target relationship delta this chapter: {snapshot.chapter_brief.relationship_delta}",
                        f"- Cost that must land: {snapshot.chapter_brief.cost_of_progress}",
                        "- Forbidden shortcut: do not skip misreading, cost, or unrevealed truth.",
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    f"- Relationship axis now: {snapshot.chapter_brief.relationship_delta}",
                    f"- Emotional pressure now: {snapshot.chapter_brief.emotional_turn}",
                    f"- Target relationship delta this chapter: {snapshot.chapter_brief.relationship_delta}",
                    f"- Cost that must land: {snapshot.chapter_brief.cost_of_progress}",
                    "",
                ]
            )
        if snapshot.actual_summaries:
            latest = snapshot.actual_summaries[-1]
            if latest.relationship_state:
                lines.append("Carry-over from previous chapter:")
                for item in latest.relationship_state[:3]:
                    lines.append(f"- {item}")
        return "\n".join(lines).strip()

    @staticmethod
    def _relevant_world_rules_text(rules: Sequence[str]) -> str:
        lines = ["[Relevant world rules]", ""]
        for index, rule in enumerate(list(rules)[:6], start=1):
            lines.append(f"{index}. {rule}")
        return "\n".join(lines).strip()

    @staticmethod
    def _full_event_timeline_text(event_timeline: Sequence[dict[str, Any]]) -> str:
        if not event_timeline:
            return "[Step 4 full event timeline]\nNo event_timeline facts available."

        lines = ["[Step 4 full event timeline]"]
        for event in event_timeline:
            event_id = _normalize_text(event.get("event_id")) or "unknown_event"
            title = _normalize_text(event.get("title")) or "Untitled event"
            time_label = _normalize_text(event.get("time_label")) or "Unknown time"
            description = _normalize_text(event.get("description")) or "No description."
            trigger = _normalize_text(event.get("trigger")) or "No trigger."
            consequence = _normalize_text(event.get("consequence")) or "No consequence recorded."
            affected = ", ".join(
                _normalize_text(item)
                for item in event.get("affected_characters", [])
                if _normalize_text(item)
            ) or "None"
            lines.extend(
                [
                    "",
                    f"- {event_id} | {time_label}",
                    f"  Title: {title}",
                    f"  Description: {description}",
                    f"  Trigger: {trigger}",
                    f"  Consequence: {consequence}",
                    f"  Affected characters: {affected}",
                ]
            )
        return "\n".join(lines).strip()

    @staticmethod
    def _timeline_anchor_facts_text(
        selected_events: Sequence[dict[str, Any]],
        consistency_notes: Sequence[str],
    ) -> str:
        if not selected_events:
            return "[Objective timeline anchors]\nNo strongly relevant timeline anchors found for this chapter."

        lines = ["[Objective timeline anchors]", ""]
        lines.append("Relevant prehistory and current anchor from step 4:")
        for event in selected_events:
            event_id = _normalize_text(event.get("event_id")) or "unknown_event"
            title = _normalize_text(event.get("title")) or "Untitled event"
            time_label = _normalize_text(event.get("time_label")) or "Unknown time"
            description = _normalize_text(event.get("description")) or "No description."
            consequence = _normalize_text(event.get("consequence")) or "No consequence recorded."
            affected = ", ".join(
                _normalize_text(item)
                for item in event.get("affected_characters", [])
                if _normalize_text(item)
            ) or "None"
            lines.extend(
                [
                    f"- {event_id} | {time_label}",
                    f"  Title: {title}",
                    f"  Description: {description}",
                    f"  Consequence: {consequence}",
                    f"  Affected characters: {affected}",
                ]
            )
        if consistency_notes:
            lines.extend(["", "Consistency notes:"])
            lines.extend(f"- {note}" for note in consistency_notes)
        return "\n".join(lines).strip()


def build_current_chapter_context(
    chapter_id: str,
    committed_blocks: list[ChapterBeat],
    *,
    max_blocks: int = 4,
    tail_chars: int = 1000,
) -> dict[str, Any]:
    selection = NovelContextSelectorService.select_current_chapter_context(
        chapter_id,
        committed_blocks,
        max_blocks=max_blocks,
        tail_chars=tail_chars,
    )
    return NovelContextFormatter.format_current_chapter_context(selection)
