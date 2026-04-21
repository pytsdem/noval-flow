from __future__ import annotations

from typing import Any

from novel_flow.models.schemas import DynamicInstructionPayload, RevisionPlan


class DynamicInstructionBuilder:
    @classmethod
    def build(
        cls,
        *,
        review_reports: dict[str, dict[str, Any]],
        revision_plan: RevisionPlan,
        active_skill_ids: list[str] | None = None,
    ) -> DynamicInstructionPayload:
        focus: list[str] = []
        must_fix = list(revision_plan.must_fix[:6])
        skills = list(active_skill_ids or revision_plan.triggered_skills)
        tone_adjustment = "保持简体中文小说语感，压低解释欲，优先让情绪落到具体反应、现实代价和关系摩擦上。"
        scene_strategy_parts: list[str] = []

        hook = review_reports.get("review_hook_appearance", {})
        if cls._has_issues(hook):
            focus.append("前段尽快落下当前冲突、打击物和此刻得不到的目标。")
            scene_strategy_parts.append("开头优先安排当前事件、障碍和下一步问题，不先空铺背景。")

        humanity = review_reports.get("review_humanity", {})
        if cls._has_issues(humanity):
            focus.append("把情绪改成具体生活代价、身体露馅、自我判断和配角反应。")
            scene_strategy_parts.append("至少补一个具体代价、一个身体反应、一个像真人会有的具体念头。")

        integrity = review_reports.get("review_character_integrity", {})
        if cls._has_issues(integrity):
            focus.append("关键行为必须能从角色当前认知、处境和性格里推出来。")
            scene_strategy_parts.append("优先修正像作者硬推剧情的动作，让选择更像角色自己会做的。")

        time_consistency = review_reports.get("review_time_consistency", {})
        if cls._has_issues(time_consistency):
            focus.append("所有场景都要服从时间锚点，需要时补出明确过渡。")
            scene_strategy_parts.append("延续上一章结尾的身体状态、昼夜和物件位置，不要无说明跳时。")

        prose = review_reports.get("review_prose_quality", {})
        if int(prose.get("scene_texture_score") or 0) < 7:
            focus.append("补足场景触感、礼法压力、劳动痕迹、天气和物件重量。")
        if int(prose.get("dialogue_subtext_score") or 0) < 7:
            focus.append("让对话里带上遮掩、试探、称谓张力和没说出口的意思。")
        if int(prose.get("emotion_externalization_score") or 0) < 7:
            focus.append("少写抽象情绪，多写动作、停顿、回避和后果。")

        if not focus:
            focus.append("在不突破边界的前提下，继续增强现场感、人物气味和情绪质地。")

        return DynamicInstructionPayload(
            focus=cls._dedupe(focus),
            skills_to_emphasize=cls._dedupe(skills),
            must_fix=cls._dedupe(must_fix),
            tone_adjustment=tone_adjustment,
            scene_strategy=" ".join(scene_strategy_parts).strip() or "按 revision_plan 定点修补，不扩写真相，不扩大解释。",
        )

    @staticmethod
    def _has_issues(report: dict[str, Any]) -> bool:
        if not report:
            return False
        if not bool(report.get("passed", True)):
            return True
        return bool(report.get("issues"))

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result
