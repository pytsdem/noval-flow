from __future__ import annotations

from typing import Any, Sequence

from novel_flow.models.schemas import CharacterCard


def _normalize_character_name(value: Any) -> str:
    return str(value or "").strip()


def get_character_card_by_name(
    character_cards: Sequence[CharacterCard],
    name: Any,
) -> CharacterCard | None:
    target_name = _normalize_character_name(name)
    if not target_name:
        return None
    return next(
        (card for card in character_cards if _normalize_character_name(card.name) == target_name),
        None,
    )


def get_character_milestone_by_name(
    character_milestones: Sequence[dict[str, Any]],
    name: Any,
) -> dict[str, Any] | None:
    target_name = _normalize_character_name(name)
    if not target_name:
        return None
    return next(
        (
            item
            for item in character_milestones
            if isinstance(item, dict)
            and (
                _normalize_character_name(item.get("character_name")) == target_name
                or _normalize_character_name(item.get("character_card_name")) == target_name
            )
        ),
        None,
    )
