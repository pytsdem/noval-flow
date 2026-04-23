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


def _sample_matches(matches: list[str], *, limit: int = 2, width: int = 18) -> str:
    if not matches:
        return ""
    trimmed = []
    for item in matches[:limit]:
        value = re.sub(r"\s+", "", str(item or ""))
        trimmed.append(value[:width])
    return "、".join(item for item in trimmed if item)


_DIRECT_THOUGHT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("心里想/告诉自己", re.compile(r"[他她我][^。！？；]{0,10}(心里|心头|脑海里)[^。！？；]{0,6}(想|知道|明白|意识到|告诉自己)")),
    ("知道/明白/意识到", re.compile(r"[他她我][^。！？；]{0,6}(知道|明白|意识到|清楚|懂得|确定)[^。！？；]{0,14}")),
    ("觉得/感到", re.compile(r"[他她我][^。！？；]{0,6}(觉得|感到|感觉到|忽然觉得)[^。！？；]{0,14}")),
]

_EXPLANATORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("解释性总结", re.compile(r"(这让|这使得|于是|因此)[^。！？；]{0,12}[他她我][^。！？；]{0,10}(更加|终于|开始|更)?(明白|知道|意识到|确定|觉得|清楚)")),
    ("抽象情绪命名", re.compile(r"[他她我][^。！？；]{0,8}(更加|终于|顿时|不由得)?(愤怒|难堪|委屈|心疼|慌乱|害怕|紧张|不安|酸涩|难过|痛苦|愧疚)")),
]


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


class AntiSlopRuleAnalyzer:
    def analyze(
        self,
        *,
        chapter_text: str,
        review_reports: dict[str, Any],
    ) -> RomanceMetricDetail:
        direct_hits: list[str] = []
        explanation_hits: list[str] = []
        direct_hit_count = 0
        explanation_hit_count = 0
        for _, pattern in _DIRECT_THOUGHT_PATTERNS:
            matches = [match.group(0) for match in pattern.finditer(str(chapter_text or ""))]
            direct_hit_count += len(matches)
            if matches:
                direct_hits.extend(matches[:2])
        for _, pattern in _EXPLANATORY_PATTERNS:
            matches = [match.group(0) for match in pattern.finditer(str(chapter_text or ""))]
            explanation_hit_count += len(matches)
            if matches:
                explanation_hits.extend(matches[:2])

        review_hits: list[str] = []
        for tool_name, report in review_reports.items():
            raw_issues = report.get("issues", []) if isinstance(report, dict) else []
            report_blob = str(report).lower()
            if any(token in report_blob for token in ("direct_thought", "on_the_nose", "explain", "心理", "直白", "解释", "点题", "总结")):
                review_hits.append(f"{tool_name} 命中过直白心理/解释问题")
                continue
            for issue in raw_issues or []:
                blob = str(issue).lower()
                if any(token in blob for token in ("direct", "thought", "on_the_nose", "explain", "心理", "直白", "解释", "点题", "总结")):
                    review_hits.append(f"{tool_name} 命中过直白心理/解释问题")
                    break

        penalty = 0.0
        penalty += min(direct_hit_count * 0.65, 4.0)
        penalty += min(explanation_hit_count * 0.75, 3.0)
        penalty += min(len(review_hits) * 0.9, 2.0)
        score = max(0.0, min(10.0, 10.0 - penalty))

        evidence_parts: list[str] = []
        if direct_hit_count:
            evidence_parts.append(
                f"直白心理标签 {direct_hit_count} 处（如“{_sample_matches(direct_hits)}”）"
            )
        if explanation_hit_count:
            evidence_parts.append(
                f"解释性总结 {explanation_hit_count} 处（如“{_sample_matches(explanation_hits)}”）"
            )
        evidence_parts.extend(review_hits[:2])
        if not evidence_parts:
            evidence_parts.append("未检测到明显直白心理标签或解释性总结句。")

        if score >= 8.0:
            reason = "规则检测显示正文较少依赖直白心理标签或解释性总结句。"
            hint = "继续让情绪落在动作、停顿、对话余味和误读上，而不是补写判断句。"
        elif score >= 6.0:
            reason = "存在轻中度直白心理解释，常见于“她知道/他意识到/这让她更清楚”这类总结句。"
            hint = "优先删掉解释句，把同一信息改写成动作、视线回避、潜台词或错位反应。"
        else:
            reason = "直白心理标签和解释性总结句偏多，正文更像在说明情绪而不是让读者看见情绪。"
            hint = "先清掉“她知道/他意识到/这让她更明白”类句式，再把篇幅换成新动作、新误读和新关系代价。"

        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary="；".join(evidence_parts),
            improvement_hint=hint,
            source="rule",
        )
