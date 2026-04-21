from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from novel_flow.models.schemas import ChapterBrief


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


def _collect_search_terms(chapter_brief: ChapterBrief) -> list[str]:
    base_terms = [
        chapter_brief.title,
        chapter_brief.summary,
        chapter_brief.incoming_hook,
        chapter_brief.opening_hook,
        chapter_brief.chapter_object,
        chapter_brief.backstory_trigger,
        chapter_brief.small_payoff,
        chapter_brief.ending_pull,
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
            part = part.strip()
            if len(part) >= 2:
                terms.append(part)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


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


def _extract_year_bounds(time_label: str) -> tuple[int | None, int | None]:
    matches = re.findall(r"([0-9零一二两三四五六七八九十]+)年", _normalize_text(time_label))
    years = [_parse_cn_number(item) for item in matches]
    years = [item for item in years if item is not None]
    if not years:
        return None, None
    return min(years), max(years)


@dataclass
class TimelineContextBuilder:
    @classmethod
    def build_full_text(cls, *, worldbuilding: dict[str, Any] | None) -> str:
        event_timeline = []
        if isinstance(worldbuilding, dict):
            raw = worldbuilding.get("event_timeline", [])
            if isinstance(raw, list):
                event_timeline = [item for item in raw if isinstance(item, dict)]
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
            affected = ", ".join(_normalize_text(item) for item in event.get("affected_characters", []) if _normalize_text(item)) or "None"
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

    @classmethod
    def build(cls, *, chapter_brief: ChapterBrief, worldbuilding: dict[str, Any] | None) -> str:
        event_timeline = []
        if isinstance(worldbuilding, dict):
            raw = worldbuilding.get("event_timeline", [])
            if isinstance(raw, list):
                event_timeline = [item for item in raw if isinstance(item, dict)]
        if not event_timeline:
            return "[Objective timeline anchors]\nNo event_timeline facts available."

        ranked = cls._rank_events(chapter_brief=chapter_brief, event_timeline=event_timeline)
        if not ranked:
            return "[Objective timeline anchors]\nNo strongly relevant timeline anchors found for this chapter."

        anchor_index = ranked[0][0]
        selected_indices = cls._select_context_window(
            anchor_index=anchor_index,
            ranked=ranked,
            event_timeline=event_timeline,
            chapter_brief=chapter_brief,
        )
        selected_events = [event_timeline[index] for index in selected_indices]
        anchor_event = event_timeline[anchor_index]
        consistency_notes = cls._build_consistency_notes(
            anchor_event=anchor_event,
            prior_events=[event_timeline[index] for index in selected_indices if index < anchor_index],
        )

        lines = ["[Objective timeline anchors]", ""]
        if selected_events:
            lines.append("Relevant prehistory and current anchor from step 4:")
            for event in selected_events:
                event_id = _normalize_text(event.get("event_id")) or "unknown_event"
                title = _normalize_text(event.get("title")) or "Untitled event"
                time_label = _normalize_text(event.get("time_label")) or "Unknown time"
                description = _normalize_text(event.get("description")) or "No description."
                consequence = _normalize_text(event.get("consequence")) or "No consequence recorded."
                affected = ", ".join(_normalize_text(item) for item in event.get("affected_characters", []) if _normalize_text(item)) or "None"
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

    @classmethod
    def _rank_events(
        cls,
        *,
        chapter_brief: ChapterBrief,
        event_timeline: list[dict[str, Any]],
    ) -> list[tuple[int, int]]:
        search_terms = _collect_search_terms(chapter_brief)
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
                    " ".join(_normalize_text(item) for item in event.get("affected_characters", []) if _normalize_text(item)),
                ]
            )
            affected = {_normalize_text(item) for item in event.get("affected_characters", []) if _normalize_text(item)}
            score = 0
            if focus_names & affected:
                score += 30 + 5 * len(focus_names & affected)
            for term in search_terms:
                if term and term in haystack:
                    score += 6 if len(term) >= 6 else 3
            if _normalize_text(chapter_brief.chapter_object) and _normalize_text(chapter_brief.chapter_object) in haystack:
                score += 12
            if _normalize_text(chapter_brief.backstory_trigger) and _normalize_text(chapter_brief.backstory_trigger) in haystack:
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
        chapter_brief: ChapterBrief,
    ) -> list[int]:
        focus_names = {name for name in chapter_brief.character_focus if _normalize_text(name)}
        ranked_map = {index: score for index, score in ranked}
        indices: set[int] = {anchor_index}

        for index in range(max(0, anchor_index - 4), anchor_index):
            affected = {_normalize_text(item) for item in event_timeline[index].get("affected_characters", []) if _normalize_text(item)}
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
        anchor_start, anchor_end = _extract_year_bounds(anchor_time)
        if prior_events:
            latest_prior = prior_events[-1]
            prior_title = _normalize_text(latest_prior.get("title")) or "prior event"
            prior_time = _normalize_text(latest_prior.get("time_label")) or "unknown time"
            prior_start, prior_end = _extract_year_bounds(prior_time)
            notes.append(f"Current chapter anchor is '{anchor_title}' at {anchor_time}.")
            notes.append(f"The nearest relevant prehistory is '{prior_title}' at {prior_time}.")
            if None not in {anchor_start, anchor_end, prior_start, prior_end}:
                lower_gap = max(0, anchor_start - prior_end)
                upper_gap = max(lower_gap, anchor_end - prior_start)
                if lower_gap == upper_gap:
                    notes.append(f"The supported elapsed window between these anchors is about {lower_gap} year(s). Do not invent a different exact duration.")
                else:
                    notes.append(
                        f"The supported elapsed window between these anchors is about {lower_gap} to {upper_gap} year(s). Do not invent a different exact duration."
                    )
        else:
            notes.append(f"Current chapter anchor is '{anchor_title}' at {anchor_time}.")
        return notes
