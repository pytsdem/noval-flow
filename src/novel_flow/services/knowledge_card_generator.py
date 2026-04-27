from __future__ import annotations

import re
from pathlib import Path

from novel_flow.config import Settings
from novel_flow.llm.base import LLMClient
from novel_flow.llm.executor import PromptLLMExecutor
from novel_flow.llm.factory import build_llm_client
from novel_flow.models.schemas import KnowledgeCard
from novel_flow.prompting.templates import PromptLibrary
from novel_flow.utils.json_tools import extract_json_object


class KnowledgeCardGenerator:
    _LAYER_ALIASES = {
        "需求层": "需求层",
        "需求": "需求层",
        "need": "需求层",
        "需求层级": "需求层",
        "机制层": "机制层",
        "机制": "机制层",
        "mechanism": "机制层",
        "写法层": "写法层",
        "写法": "写法层",
        "writing": "写法层",
        "结构层": "结构层",
        "结构": "结构层",
        "structure": "结构层",
    }
    _POLARITY_ALIASES = {
        "正向": "正向",
        "positive": "正向",
        "pos": "正向",
        "反向": "反向",
        "negative": "反向",
        "neg": "反向",
        "anti": "反向",
    }

    def __init__(self, llm_client: LLMClient, prompt_library: PromptLibrary | None = None) -> None:
        self.llm_client = llm_client
        self.prompt_library = prompt_library or PromptLibrary()
        self.llm_executor = PromptLLMExecutor(llm_client=self.llm_client, prompt_library=self.prompt_library)

    @classmethod
    def from_settings(cls, settings: Settings) -> "KnowledgeCardGenerator":
        return cls(llm_client=build_llm_client(settings))

    def generate_cards(self, *, raw_text: str, source_name: str, max_cards: int = 4) -> list[KnowledgeCard]:
        if not raw_text.strip():
            raise ValueError("Input text is empty.")

        prompt = self.prompt_library.render(
            "knowledge/generate_cards.txt",
            source_name=source_name,
            max_cards=max_cards,
            raw_text=raw_text,
        )
        raw = self.llm_executor.generate_prompt_text(
            system_path="knowledge/system.txt",
            prompt=prompt,
            temperature=0.2,
            strip=False,
        )
        parsed = extract_json_object(raw)
        return self._normalize_cards(parsed, source_name=source_name)

    def write_cards(self, *, cards: list[KnowledgeCard], output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        return [self._write_card(output_dir, card) for card in cards]

    def _normalize_cards(self, parsed: dict[str, object], *, source_name: str) -> list[KnowledgeCard]:
        raw_cards = parsed.get("cards", [])
        if not isinstance(raw_cards, list) or not raw_cards:
            raise ValueError("Model returned no cards.")

        cards: list[KnowledgeCard] = []
        for index, item in enumerate(raw_cards, start=1):
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload["card_id"] = self._normalize_card_id(str(payload.get("card_id", f"{source_name}_{index}")))
            payload["title"] = self._normalize_title(str(payload.get("title", "")))
            payload["domain"] = self._normalize_text_field(payload.get("domain"))
            payload["layer"] = self._normalize_layer(payload.get("layer"))
            payload["polarity"] = self._normalize_polarity(payload.get("polarity"))
            payload["cluster_id"] = self._normalize_card_id(str(payload.get("cluster_id", "")))
            payload["source"] = str(payload.get("source") or source_name)
            payload["tags"] = self._normalize_tags(payload.get("tags"))
            cards.append(KnowledgeCard.model_validate(payload))

        if not cards:
            raise ValueError("No valid cards after normalization.")
        return cards

    @staticmethod
    def _write_card(output_dir: Path, card: KnowledgeCard) -> Path:
        file_name = f"{card.card_id}.json"
        path = output_dir / file_name
        suffix = 1
        while path.exists():
            existing = KnowledgeCard.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.card_id == card.card_id:
                break
            path = output_dir / f"{card.card_id}_{suffix}.json"
            suffix += 1
        path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _normalize_card_id(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized or "knowledge_card"

    @staticmethod
    def _normalize_title(value: str) -> str:
        title = re.sub(r"^\s*(警惕|避免|禁止|不要)\s*[：:]\s*", "", value.strip())
        title = re.sub(r"^\s*(警惕|避免|禁止|不要)\s+", "", title)
        return title.strip()

    @staticmethod
    def _normalize_text_field(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _normalize_layer(cls, value: object) -> str:
        normalized = cls._normalize_text_field(value).lower()
        return cls._LAYER_ALIASES.get(normalized, cls._normalize_text_field(value))

    @classmethod
    def _normalize_polarity(cls, value: object) -> str:
        normalized = cls._normalize_text_field(value).lower()
        return cls._POLARITY_ALIASES.get(normalized, cls._normalize_text_field(value))

    @staticmethod
    def _normalize_tags(value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            tag = re.sub(r"\s+", " ", item).strip()
            if not tag:
                continue
            if len(tag) > 18:
                continue
            if tag not in normalized:
                normalized.append(tag)
            if len(normalized) >= 5:
                break
        return normalized
