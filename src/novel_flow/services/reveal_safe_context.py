from __future__ import annotations

import re

from novel_flow.models.schemas import TwistDesign


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_hidden(current_chapter_id: str, twist: TwistDesign) -> bool:
    return _chapter_order(current_chapter_id) < _chapter_order(twist.reveal_at)


class RevealSafeContextRedactor:
    PLACEHOLDER = "[REDACTED BEFORE REVEAL]"

    @classmethod
    def redact_text(
        cls,
        *,
        text: str,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
    ) -> str:
        clean = str(text or "")
        if not clean:
            return clean
        redacted = clean
        for term in cls._protected_terms(current_chapter_id=current_chapter_id, active_twists=active_twists):
            if term and term in redacted:
                redacted = redacted.replace(term, cls.PLACEHOLDER)
        return redacted

    @classmethod
    def _protected_terms(cls, *, current_chapter_id: str, active_twists: list[TwistDesign]) -> list[str]:
        terms: list[str] = []
        for twist in active_twists:
            if not _is_hidden(current_chapter_id, twist):
                continue
            terms.extend(cls._expand_term_variants(str(twist.truth or "")))
            for item in twist.forbidden_reveals:
                terms.extend(cls._expand_term_variants(str(item or "")))
        deduped: list[str] = []
        seen: set[str] = set()
        for term in sorted(terms, key=len, reverse=True):
            if term and term not in seen:
                seen.add(term)
                deduped.append(term)
        return deduped

    @staticmethod
    def _expand_term_variants(raw: str) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        variants = [text]
        parts = re.split(r"[，。；：!！?？、/\n]+", text)
        for part in parts:
            part = part.strip(" '\"“”‘’()（）[]【】")
            if len(part) >= 4:
                variants.append(part)
        return [item for item in variants if item]
