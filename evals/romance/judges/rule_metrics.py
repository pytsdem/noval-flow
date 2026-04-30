from __future__ import annotations

from collections import Counter
import re
from typing import Any

from evals.romance.models import RomanceMetricDetail
from novel_flow.services.prose_lint import analyze_prose_surface


_CN_PUNCTUATION = "，。！？；：、“”‘’（）《》〈〉【】『』「」—…\n\r\t "


def _normalize_text(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch not in _CN_PUNCTUATION).strip()


def _paragraphs(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [item.strip() for item in raw.split("\n\n") if item.strip()]
    if parts:
        return parts
    return [item.strip() for item in raw.split("\n") if item.strip()]


def _sentences(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(?<=[。！？；!?])|\n+", raw)
    return [item.strip() for item in parts if item.strip()]


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

_PRONOUN_LEAD_RE = re.compile(r"^[“\"'‘「『（(【\s]*[他她我](们)?")
_EXPLANATION_SENTENCE_PATTERNS: list[re.Pattern[str]] = [
    *[pattern for _, pattern in _DIRECT_THOUGHT_PATTERNS],
    *[pattern for _, pattern in _EXPLANATORY_PATTERNS],
    re.compile(r"(这说明|这意味着|说到底|归根结底|换句话说|其实她|其实他|原来她|原来他)"),
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
            reason = "规则检测显示段落功能分布较开，重复铺陈信号较弱；有效回环需带来新剧情功能、关系变化、误导、线索推进、情绪升级或读者期待。"
            hint = "继续保持一段一推进，允许有功能的回环，但避免把同层情绪解释回头再说一遍。"
        elif score >= 6.0:
            reason = "存在轻中度重复，常见于相邻段落反复解释同一种心理、情绪或动作模式，而没有带来新功能。"
            hint = "把无功能重复压缩成一次更有效的动作、误读、线索推进或关系变化。"
        else:
            reason = "重复铺陈较明显，部分段落在重复同一心理、情绪、意象或动作模式，且没有形成有效回环。"
            hint = "优先删除重复解释，把腾出的篇幅换成新剧情功能、新代价、新误读、新线索或新关系变化。"

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


class PronounLeadRuleAnalyzer:
    def analyze(self, *, chapter_text: str) -> RomanceMetricDetail:
        sentences = _sentences(chapter_text)
        if not sentences:
            return RomanceMetricDetail(
                score=10.0,
                reason="没有可分析的正文句子。",
                evidence_summary="句子数为 0。",
                improvement_hint="先生成正文，再分析句首代词密度。",
                source="rule",
            )

        pronoun_led = [item for item in sentences if _PRONOUN_LEAD_RE.match(item)]
        total = len(sentences)
        ratio = len(pronoun_led) / total
        consecutive = 0
        for left, right in zip(sentences, sentences[1:]):
            if _PRONOUN_LEAD_RE.match(left) and _PRONOUN_LEAD_RE.match(right):
                consecutive += 1

        penalty = 0.0
        penalty += max(0.0, ratio - 0.08) * 18.0
        penalty += min(consecutive * 0.55, 3.0)
        score = max(0.0, min(10.0, 10.0 - penalty))

        evidence = (
            f"句首代词占比 {ratio:.0%}（{len(pronoun_led)}/{total} 句）"
            if pronoun_led
            else "未检测到明显“他/她/我”句首堆叠。"
        )
        if pronoun_led:
            evidence = f"{evidence}；样例“{_sample_matches(pronoun_led)}”"
        if consecutive:
            evidence = f"{evidence}；连续代词起句 {consecutive} 处"

        if score >= 8.0:
            reason = "句首代词密度较低，句面更容易保留场面感、物件感和人物声口。"
            hint = "继续让场景、物件、动作、冷暖和对话来带起句子，而不是不断用代词起句。"
        elif score >= 6.0:
            reason = "句首代词有轻中度偏高，正文会更像在转述人物状态，而不是让场面自己说话。"
            hint = "优先把至少一半的“他/她”起句改成动作起句、物件起句、环境起句或对话起句。"
        else:
            reason = "句首代词密度偏高，容易形成“他……她……”的平面转述感，削弱古言正文的场面质感。"
            hint = "先删连续代词起句，再把段首改写成景、物、身体、礼法、停顿或台词带入。"

        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary=evidence,
            improvement_hint=hint,
            source="rule",
        )


class ExplanationDensityRuleAnalyzer:
    def analyze(self, *, chapter_text: str) -> RomanceMetricDetail:
        sentences = _sentences(chapter_text)
        if not sentences:
            return RomanceMetricDetail(
                score=10.0,
                reason="没有可分析的正文句子。",
                evidence_summary="句子数为 0。",
                improvement_hint="先生成正文，再分析解释句密度。",
                source="rule",
            )

        explanation_sentences: list[str] = []
        for sentence in sentences:
            if any(pattern.search(sentence) for pattern in _EXPLANATION_SENTENCE_PATTERNS):
                explanation_sentences.append(sentence)

        total = len(sentences)
        ratio = len(explanation_sentences) / total
        penalty = 0.0
        penalty += max(0.0, ratio - 0.10) * 20.0
        penalty += min(len(explanation_sentences) * 0.25, 3.0)
        score = max(0.0, min(10.0, 10.0 - penalty))

        if explanation_sentences:
            evidence = (
                f"解释句占比 {ratio:.0%}（{len(explanation_sentences)}/{total} 句）"
                f"；样例“{_sample_matches(explanation_sentences)}”"
            )
        else:
            evidence = "未检测到明显解释句密度问题。"

        if score >= 8.0:
            reason = "解释句密度较低，正文更多通过场面和动作递送信息。"
            hint = "继续让动作、停顿、物件和旁人反应承担解释工作，不要把结论写在句面上。"
        elif score >= 6.0:
            reason = "解释句有轻中度偏多，常表现为动作后立刻补一句作者翻译。"
            hint = "优先删除动作后的解释句，把同样的信息换成停顿、称呼变化、回避或身体反应。"
        else:
            reason = "解释句密度偏高，正文更像在说明读者该怎么理解，而不是让读者自己感觉到。"
            hint = "把“她知道/他明白/这让她更清楚”类句式当作首要删除对象，再把篇幅换成场面和代价。"

        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary=evidence,
            improvement_hint=hint,
            source="rule",
        )


class ActionCarriedRevealRuleAnalyzer:
    def analyze(self, *, chapter_text: str) -> RomanceMetricDetail:
        surface = analyze_prose_surface(chapter_text)
        evidence = surface.evidence
        score = float(surface.action_carried_reveal_score)
        if score >= 8.0:
            reason = "关键信息主要通过动作、物件、身体和场面自己露出来，解释性翻译较少。"
            hint = "继续先给场面、动作和物件，再让读者自己得出结论。"
        elif score >= 6.0:
            reason = "动作已经承担了一部分信息，但关键变化仍有不少靠解释句交代。"
            hint = "把最重要的结论再往动作、停顿、礼法压力和旁人反应上压一层。"
        else:
            reason = "信息更多靠说明句落地，动作、物件和场面没有真正承担主要叙事功能。"
            hint = "优先删除动作后的解释句，让 clue、关系变化和疼点直接从场面里长出来。"
        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary=(
                f"body_or_object_hits={evidence['body_or_object_hits']} | "
                f"social_pressure_hits={evidence['social_pressure_hits']} | "
                f"dialogue_hits={evidence['dialogue_hits']} | "
                f"explanation_ratio={surface.explanation_ratio:.0%}"
            ),
            improvement_hint=hint,
            source="rule",
        )


class RelationshipCostRealizationRuleAnalyzer:
    def analyze(self, *, chapter_text: str) -> RomanceMetricDetail:
        surface = analyze_prose_surface(chapter_text)
        evidence = surface.evidence
        score = float(surface.relationship_cost_realization_score)
        if score >= 8.0:
            reason = "推进一出现就会变成关系代价或人身代价，人物在场上真有付出。"
            hint = "继续让每一次 clue、动作或试探都立刻改变面子、信任、危险或选择权。"
        elif score >= 6.0:
            reason = "已经有部分关系代价兑现，但仍有推进停在“信息更清楚了”，没有及时伤到人。"
            hint = "一旦程序或 clue 出现，就让它马上改变关系价格、体面或危险程度。"
        else:
            reason = "许多推进仍停在信息层或流程层，没有及时转换成关系代价或人身代价。"
            hint = "压缩流程说明，把省下来的篇幅换成误读、难堪、避让、体面损失或身体反应。"
        return RomanceMetricDetail(
            score=round(score, 2),
            reason=reason,
            evidence_summary=(
                f"social_pressure_hits={evidence['social_pressure_hits']} | "
                f"procedure_hits={evidence['procedure_hits']} | "
                f"pronoun_lead_ratio={surface.pronoun_lead_ratio:.0%} | "
                f"explanation_ratio={surface.explanation_ratio:.0%}"
            ),
            improvement_hint=hint,
            source="rule",
        )
