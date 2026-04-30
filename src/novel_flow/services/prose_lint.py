from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_PRONOUN_LEAD_RE = re.compile(r"^[\"'“‘「『（(\s]*[他她我]")
_EXPLANATION_RE = re.compile(
    r"(知道|明白|意识到|觉得|其实|原来|这让|这使得|意味着|说明|更清楚|更明白|终于明白)"
)
_BODY_OR_OBJECT_RE = re.compile(
    r"(手|指|袖|腕|眼|喉|肩|背|唇|膝|呼吸|汗|血|雪|风|灯|烛|茶|杯|纸|书|婚书|门|窗|阶|案|衣|裙|发|伞|马)"
)
_SOCIAL_PRESSURE_RE = re.compile(
    r"(称呼|目光|众目|体面|礼|规矩|殿|宫|堂|跪|退|让|欠身|避|停|顿|收手|压低|沉默|失声)"
)
_PROCEDURE_HEAVY_RE = re.compile(
    r"(卷宗|档册|司礼监|印鉴|签押|呈文|手续|流程|查验|名册|名录|案卷|转运|挂号|条款|册页|抄录)"
)
_DIALOGUE_RE = re.compile(r"[“\"「『]")


@dataclass(slots=True)
class ProseSurfaceSignals:
    pronoun_lead_ratio: float
    explanation_ratio: float
    action_carried_reveal_score: float
    relationship_cost_realization_score: float
    procedure_pressure: float
    overall_score: float
    evidence: dict[str, Any]


def _sentences(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n+", "\n", raw)
    pieces = re.findall(r"[^。！？!?；;\n]+(?:[。！？!?；;]+|$)", normalized)
    return [item.strip() for item in pieces if item and item.strip()]


def _paragraphs(text: str) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [item.strip() for item in re.split(r"\n\s*\n+", raw) if item.strip()]
    if blocks:
        return blocks
    return [item.strip() for item in raw.split("\n") if item.strip()]


def _sample(items: list[str], *, limit: int = 2, width: int = 16) -> list[str]:
    out: list[str] = []
    for item in items[:limit]:
        compact = re.sub(r"\s+", "", item)
        out.append(compact[:width])
    return out


def analyze_prose_surface(text: str, *, block: Any | None = None) -> ProseSurfaceSignals:
    sentences = _sentences(text)
    paragraphs = _paragraphs(text)
    if not sentences:
        return ProseSurfaceSignals(
            pronoun_lead_ratio=0.0,
            explanation_ratio=0.0,
            action_carried_reveal_score=0.0,
            relationship_cost_realization_score=0.0,
            procedure_pressure=0.0,
            overall_score=0.0,
            evidence={
                "sentence_count": 0,
                "pronoun_leads": [],
                "explanation_sentences": [],
                "body_or_object_hits": 0,
                "social_pressure_hits": 0,
                "dialogue_hits": 0,
                "procedure_hits": 0,
            },
        )

    pronoun_leads = [item for item in sentences if _PRONOUN_LEAD_RE.match(item)]
    explanation_sentences = [item for item in sentences if _EXPLANATION_RE.search(item)]
    pronoun_lead_ratio = len(pronoun_leads) / len(sentences)
    explanation_ratio = len(explanation_sentences) / len(sentences)

    body_or_object_hits = len(_BODY_OR_OBJECT_RE.findall(text))
    social_pressure_hits = len(_SOCIAL_PRESSURE_RE.findall(text))
    dialogue_hits = len(_DIALOGUE_RE.findall(text))
    procedure_hits = len(_PROCEDURE_HEAVY_RE.findall(text))

    paragraph_density = len(paragraphs) / max(len(sentences), 1)

    action_carried_reveal_score = 7.0
    action_carried_reveal_score += min(body_or_object_hits * 0.10, 1.2)
    action_carried_reveal_score += min(social_pressure_hits * 0.12, 1.2)
    action_carried_reveal_score += min(dialogue_hits * 0.15, 0.8)
    action_carried_reveal_score -= max(explanation_ratio - 0.10, 0.0) * 10.0
    action_carried_reveal_score -= min(procedure_hits * 0.10, 1.2)
    action_carried_reveal_score = max(0.0, min(10.0, action_carried_reveal_score))

    relationship_cost_score = 6.6
    if block is not None and (getattr(block, "relationship_delta", "") or getattr(block, "cost_shift", "")):
        relationship_cost_score += 0.6
    relationship_cost_score += min(social_pressure_hits * 0.14, 1.2)
    relationship_cost_score += min(body_or_object_hits * 0.08, 0.9)
    relationship_cost_score += min(dialogue_hits * 0.08, 0.7)
    relationship_cost_score -= min(procedure_hits * 0.12, 1.4)
    relationship_cost_score -= max(explanation_ratio - 0.12, 0.0) * 8.0
    relationship_cost_score = max(0.0, min(10.0, relationship_cost_score))

    procedure_pressure = max(0.0, min(10.0, float(procedure_hits)))

    overall = 10.0
    overall -= max(pronoun_lead_ratio - 0.10, 0.0) * 10.0
    overall -= max(explanation_ratio - 0.12, 0.0) * 12.0
    overall += (action_carried_reveal_score - 7.0) * 0.45
    overall += (relationship_cost_score - 7.0) * 0.45
    overall -= min(max(procedure_hits - 2, 0) * 0.35, 1.6)
    if paragraph_density < 0.22:
        overall -= 0.5
    overall = max(0.0, min(10.0, overall))

    return ProseSurfaceSignals(
        pronoun_lead_ratio=round(pronoun_lead_ratio, 4),
        explanation_ratio=round(explanation_ratio, 4),
        action_carried_reveal_score=round(action_carried_reveal_score, 2),
        relationship_cost_realization_score=round(relationship_cost_score, 2),
        procedure_pressure=round(procedure_pressure, 2),
        overall_score=round(overall, 2),
        evidence={
            "sentence_count": len(sentences),
            "paragraph_count": len(paragraphs),
            "pronoun_leads": _sample(pronoun_leads),
            "explanation_sentences": _sample(explanation_sentences),
            "body_or_object_hits": body_or_object_hits,
            "social_pressure_hits": social_pressure_hits,
            "dialogue_hits": dialogue_hits,
            "procedure_hits": procedure_hits,
        },
    )


def build_revision_brief(
    *,
    block: Any,
    review_reports: dict[str, Any],
    surface: ProseSurfaceSignals,
) -> str:
    keep_parts: list[str] = []
    if getattr(block, "scene_goal", ""):
        keep_parts.append(f"保留当前场面职责：{str(block.scene_goal).strip()}")
    if getattr(block, "end_state", ""):
        keep_parts.append(f"保留当前落点：{str(block.end_state).strip()}")

    fix_parts: list[str] = []
    for tool_name, report in review_reports.items():
        if not isinstance(report, dict):
            continue
        issues = list(report.get("issues") or [])
        if issues:
            first = issues[0]
            if isinstance(first, dict):
                reason = str(first.get("reason") or first.get("fix") or "").strip()
            else:
                reason = str(first).strip()
            if reason:
                fix_parts.append(f"{tool_name}: {reason}")
                continue
        if not bool(report.get("passed", True)):
            summary = str(report.get("rewrite_guidance") or report.get("summary") or "").strip()
            if summary:
                fix_parts.append(f"{tool_name}: {summary}")
    if surface.pronoun_lead_ratio > 0.18:
        fix_parts.append("减少连续“他/她”起句，改用动作、物件、环境或对话起句。")
    if surface.explanation_ratio > 0.16:
        fix_parts.append("删掉动作后的解释句，改用停顿、身体反应或旁人反应承载结论。")
    if surface.relationship_cost_realization_score < 7.0:
        fix_parts.append("让本 beat 的关系代价或人身代价落到场面上，不要只推进信息。")
    if surface.action_carried_reveal_score < 7.0:
        fix_parts.append("让信息先通过动作、物件、身体或礼法压力露出。")
    if int(surface.evidence.get("body_or_object_hits") or 0) < 3:
        fix_parts.append("补足冷暖、视线、袖口、器物、疼痛或呼吸等可见锚点，不要只剩抽象判断。")
    if int(surface.evidence.get("dialogue_hits") or 0) == 0 and (
        getattr(block, "relationship_delta", "") or getattr(block, "cost_shift", "")
    ):
        fix_parts.append("给主角或对手补一记短对话、称呼变化或顶回去的话，让人物声口先活起来。")

    forbid_parts = [
        "不要提前兑现后续 beat 的线索、对峙或结尾负担。",
        "不要新增新的 clue、人物或大段说明。",
    ]

    lines = ["[Revision brief]"]
    if keep_parts:
        lines.append("保留：")
        lines.extend(f"- {item}" for item in keep_parts[:2])
    if fix_parts:
        lines.append("必须改：")
        lines.extend(f"- {item}" for item in fix_parts[:4])
    lines.append("绝不能引入：")
    lines.extend(f"- {item}" for item in forbid_parts)
    return "\n".join(lines).strip()
