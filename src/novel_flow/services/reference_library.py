from __future__ import annotations

from collections import defaultdict
import re
from pathlib import Path

from novel_flow.models.schemas import KnowledgeCard


class ReferenceLibrary:
    def __init__(self, cards_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3] / "knowledge"
        self.cards_dir = cards_dir or (root / "cards")
        self.legacy_cards_dir = root

    def retrieve(
        self,
        *,
        query: str = "",
        stage: str = "",
        tags: list[str] | None = None,
        focus: list[str] | None = None,
        limit: int = 4,
    ) -> list[KnowledgeCard]:
        cards = self._load_cards()
        if not cards:
            return []

        signals = self._collect_signals(query=query, stage=stage, tags=tags or [], focus=focus or [])
        scored = [(card, self._score(card, stage=stage, signals=signals)) for card in cards]
        ranked = [(card, score) for card, score in scored if score > 0]
        if not ranked:
            return []
        return self._select_cards(ranked=ranked, limit=limit)

    def build_reference_pack(self, cards: list[KnowledgeCard]) -> str:
        if not cards:
            return "暂无额外参考资料。"

        sections: list[str] = []
        for index, card in enumerate(cards, start=1):
            title = card.title or card.card_id
            lines = [
                f"参考卡片 {index}: {title}",
                f"- 类型: {card.kind}",
                f"- 摘要: {card.summary}",
            ]
            taxonomy_bits = [item for item in [card.domain, card.layer, card.polarity] if item]
            if taxonomy_bits:
                lines.append(f"- 体系: {' / '.join(taxonomy_bits)}")
            if card.techniques:
                lines.append(f"- 技法: {'；'.join(card.techniques[:4])}")
            if card.warning_signs:
                lines.append(f"- 预警信号: {'；'.join(card.warning_signs[:3])}")
            if card.dos:
                lines.append(f"- 可借鉴: {'；'.join(card.dos[:3])}")
            if card.donts:
                lines.append(f"- 避免: {'；'.join(card.donts[:3])}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def _load_cards(self) -> list[KnowledgeCard]:
        cards: list[KnowledgeCard] = []
        search_dirs = [self.cards_dir]
        if self.legacy_cards_dir != self.cards_dir:
            search_dirs.append(self.legacy_cards_dir)

        seen_paths: set[Path] = set()
        for directory in search_dirs:
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
                if path.name.startswith("_") or path in seen_paths:
                    continue
                seen_paths.add(path)
                try:
                    cards.append(KnowledgeCard.model_validate_json(path.read_text(encoding="utf-8")))
                except Exception:
                    continue
        return cards

    @staticmethod
    def _collect_signals(*, query: str, stage: str, tags: list[str], focus: list[str]) -> list[str]:
        signals = [query, stage, *tags, *focus]
        tokens: list[str] = []
        for item in signals:
            text = str(item).strip().lower()
            if not text:
                continue
            tokens.append(text)
            tokens.extend(match.group(0) for match in re.finditer(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text))
        deduped: list[str] = []
        for token in tokens:
            if token and token not in deduped:
                deduped.append(token)
        return deduped

    @classmethod
    def _score(cls, card: KnowledgeCard, *, stage: str, signals: list[str]) -> int:
        haystacks = [
            card.title,
            card.domain,
            card.layer,
            card.polarity,
            card.cluster_id,
            *card.tags,
            *card.applicable_stages,
            *card.scene_types,
            *card.emotions,
            *card.warning_signs,
            card.summary,
            *card.techniques,
            *card.dos,
            *card.donts,
        ]
        normalized = [item.lower() for item in haystacks if item]
        score = 0
        if stage and stage in card.applicable_stages:
            score += 4
        for signal in signals:
            for item in normalized:
                if signal == item:
                    score += 3
                elif signal in item or item in signal:
                    score += 1
        return score

    @classmethod
    def _select_cards(cls, *, ranked: list[tuple[KnowledgeCard, int]], limit: int) -> list[KnowledgeCard]:
        grouped: dict[str, list[tuple[KnowledgeCard, int]]] = defaultdict(list)
        for card, score in ranked:
            grouped[cls._group_key(card)].append((card, score))

        ordered_groups = sorted(grouped.items(), key=lambda item: cls._group_priority(item[1]), reverse=True)
        selected: list[KnowledgeCard] = []
        seen_ids: set[str] = set()
        taken_per_group: dict[str, int] = {}

        if ordered_groups:
            top_key, top_items = ordered_groups[0]
            top_take = min(3, len(top_items)) if cls._is_cluster_group(top_key) and len(top_items) > 1 else 1
            for card in cls._ordered_group_cards(top_items)[: min(top_take, limit)]:
                selected.append(card)
                seen_ids.add(card.card_id)
            taken_per_group[top_key] = min(top_take, len(top_items))

        for group_key, items in ordered_groups:
            if len(selected) >= limit:
                break
            if taken_per_group.get(group_key):
                continue
            first = cls._ordered_group_cards(items)[0]
            if first.card_id not in seen_ids:
                selected.append(first)
                seen_ids.add(first.card_id)
            taken_per_group[group_key] = 1

        for group_key, items in ordered_groups:
            if len(selected) >= limit:
                break
            ordered_cards = cls._ordered_group_cards(items)
            start = taken_per_group.get(group_key, 0)
            for card in ordered_cards[start:]:
                if len(selected) >= limit:
                    break
                if card.card_id in seen_ids:
                    continue
                selected.append(card)
                seen_ids.add(card.card_id)

        return selected[:limit]

    @staticmethod
    def _group_key(card: KnowledgeCard) -> str:
        return f"cluster:{card.cluster_id}" if card.cluster_id else f"card:{card.card_id}"

    @staticmethod
    def _is_cluster_group(group_key: str) -> bool:
        return group_key.startswith("cluster:")

    @classmethod
    def _group_priority(cls, items: list[tuple[KnowledgeCard, int]]) -> tuple[int, int, int]:
        max_score = max(score for _, score in items)
        layers = {card.layer for card, _ in items if card.layer}
        polarities = {card.polarity for card, _ in items if card.polarity}
        cluster_bonus = min(max(len(layers) - 1, 0), 2) + (1 if len(polarities) > 1 else 0)
        return (max_score + cluster_bonus, max_score, len(items))

    @staticmethod
    def _ordered_group_cards(items: list[tuple[KnowledgeCard, int]]) -> list[KnowledgeCard]:
        ranked = sorted(items, key=lambda item: item[1], reverse=True)
        ordered: list[KnowledgeCard] = []
        seen_layers: set[str] = set()

        for card, _ in ranked:
            layer = card.layer or ""
            if layer and layer not in seen_layers:
                ordered.append(card)
                seen_layers.add(layer)

        for card, _ in ranked:
            if card.card_id not in {item.card_id for item in ordered}:
                ordered.append(card)

        return ordered
