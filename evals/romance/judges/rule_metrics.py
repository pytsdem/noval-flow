from __future__ import annotations

from collections import Counter
import re
from typing import Any

from evals.romance.models import RomanceMetricDetail


_CN_PUNCTUATION = "，。！？；：、“”‘’（）《》〈〉【】『』「」—…\n\r\t "


def _normalize_text(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch not in _CN_PUNCTUATION).strip()


def _paragraphs(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [item.strip() for item in raw.split("\n\n") if item.strip()]
    if parts:
        return parts
    return [item.strip() for item in raw.split("\n") if item.strip()]


def _char_ngrams(text: str, size: int = 4) -> set[str]:
    cleaned = _normalize_text(text)
    if len(cleaned) < size:
        return {cleaned} if cleaned else set()
    return {cleaned[index : index + size] for index in range(len(cleaned) - size + 1)}


class RedundancyRuleAnalyzer:
    def analyze(
        self,
        *,
        chapter_text: str,
        stage_log: list[dict[str, Any]],
        review_reports: dict[str, Any],
    ) -> RomanceMetricDetail:
        paragraphs = _paragraphs(chapter_text)
        repeated_pairs: list[str] = []
        for left_index, left in enumerate(paragraphs):
            grams_left = _char_ngrams(left)
            if not grams_left:
                continue
            for right_index in range(left_index + 1, len(paragraphs)):
                grams_right = _char_ngrams(paragraphs[right_index])
                if not grams_right:
                    continue
                union = grams_left | grams_right
                if not union:
                    continue
                similarity = len(grams_left & grams_right) / len(union)
                if similarity >= 0.58:
                    repeated_pairs.append(
                        f"第{left_index + 1}段与第{right_index + 1}段语义形状过近（相似度约 {similarity:.2f}）"
                    )

        cleaned = _normalize_text(chapter_text)
        phrase_counter: Counter[str] = Counter()
        if len(cleaned) >= 6:
            for index in range(len(cleaned) - 5):
                phrase = cleaned[index : index + 6]
                if len(set(phrase)) <= 2:
                    continue
                phrase_counter[phrase] += 1
        repeated_phrases = [
            f"“{phrase}”重复 {count} 次"
            for phrase, count in phrase_counter.most_common(5)
            if count >= 3
        ]

        review_hits: list[str] = []
        for tool_name, report in review_reports.items():
            raw_issues = report.get("issues", []) if isinstance(report, dict) else []
            for issue in raw_issues or []:
                blob = str(issue).lower()
                if any(token in blob for token in ("repeat", "redund", "duplicate", "重复", "铺陈")):
                    review_hits.append(f"{tool_name} 命中过重复相关问题")
                    break

        penalty = 0.0
        penalty += min(len(repeated_pairs) * 1.2, 4.0)
        penalty += min(len(repeated_phrases) * 0.7, 3.0)
        penalty += min(len(review_hits) * 0.9, 2.0)
        score = max(0.0, min(10.0, 10.0 - penalty))

        evidence_parts = [*repeated_pairs[:2], *repeated_phrases[:3], *review_hits[:2]]
        if not evidence_parts:
            evidence_parts.append("未检测到明显高相似段落或高频重复短语。")
        if score >= 8.0:
            reason = "规则检测显示段落功能分布较开，重复铺陈信号较弱。"
            hint = "继续保持一段一推进，避免把同层情绪解释回头再说一遍。"
        elif score >= 6.0:
            reason = "存在轻中度重复，常见于相邻段落反复解释同一种防备、迟疑或压迫感。"
            hint = "把重复段落压缩成一次更有效的动作或潜台词，让中段承担新的关系变化。"
        else:
            reason = "重复铺陈较明显，部分段落在重复同一情绪或关系判断，削弱了追读速度。"
            hint = "优先删除重复解释，把腾出的篇幅换成新代价、新误读或新靠近/拉开。"

        if stage_log and any(str(item.get("stage", "")).startswith("patch_round_") for item in stage_log):
            hint = f"{hint} 同时检查 patch 是否只改字面而没改 block 功能。"

        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary="；".join(evidence_parts),
            improvement_hint=hint,
            source="rule",
        )
