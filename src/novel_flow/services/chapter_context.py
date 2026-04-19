from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novel_flow.models.schemas import ActualChapterSummary, ChapterBrief, StoryLine, TwistDesign, WriterContext


_STYLE_CARD_TEXT = """【文风卡】

类型：
古风言情，复仇误会，权谋压迫，情绪克制。

叙述：
第三人称受限视角，贴近当前 POV 的误判和感受，不用上帝视角解释真相。

语言：
现代可读性为骨，古风质感为皮。不要堆生僻文言，不要现代网文腔。

句式：
紧张处短句，情绪处留白，动作和对白交替。

对话：
每段对话必须带有试探、遮掩、误会、威胁、礼法压力或未说出口的情意。

情绪：
不要直接写“她很痛苦”“他心动了”。情绪要落到动作、停顿、称谓、距离、物件上。

言情张力：
克制、误判、靠近后撤、身份压迫、旧债未清、话不说尽。

前史：
过去信息必须被当前动作或道具逼出来，禁止无触发回忆。

关系：
重要信息必须重新定价至少一段关系。

礼法：
称谓、跪拜、座次、是否叫起身、是否使用旧名，必须服务关系张力。

细节：
重要细节必须有双重功能，不能只是装饰。

禁用：
心中一震、眸光复杂、空气凝固、命运的齿轮、说不清道不明、不得不如此、为了他好。"""


def _chapter_order(chapter_id: str) -> int:
    digits = "".join(ch for ch in str(chapter_id or "") if ch.isdigit())
    return int(digits or "0")


def _is_revealed(current_chapter_id: str, reveal_at: str) -> bool:
    return _chapter_order(current_chapter_id) >= _chapter_order(reveal_at)


@dataclass
class ChapterContextAssembler:
    @classmethod
    def build(
        cls,
        *,
        chapter_brief: ChapterBrief,
        twist_designs: list[TwistDesign],
        story_lines: list[StoryLine],
        worldbuilding: dict[str, Any] | None,
        character_cards: list[Any],
        actual_summaries: list[ActualChapterSummary],
        current_chapter_id: str,
        reference_pack: str = "",
        style_settings: dict[str, Any] | None = None,
    ) -> WriterContext:
        del character_cards, reference_pack, style_settings
        active_twists = [
            twist for twist in twist_designs if twist.twist_id in set(chapter_brief.active_twists)
        ]
        active_story_lines = [
            line for line in story_lines if line.line_id in set(chapter_brief.active_lines)
        ]
        return WriterContext(
            completed_chapter_memory_text=cls._completed_chapter_memory_text(actual_summaries),
            chapter_payload_text=cls._chapter_payload_text(
                chapter_brief=chapter_brief,
                current_chapter_id=current_chapter_id,
                active_twists=active_twists,
                active_story_lines=active_story_lines,
            ),
            relevant_world_rules_text=cls._relevant_world_rules_text(chapter_brief, worldbuilding or {}),
            style_card_text=_STYLE_CARD_TEXT,
            active_twists=active_twists,
            active_story_lines=active_story_lines,
        )

    @staticmethod
    def _completed_chapter_memory_text(actual_summaries: list[ActualChapterSummary]) -> str:
        if not actual_summaries:
            return "暂无已完成章节"
        blocks: list[str] = ["【已完成章节记忆】"]
        for item in sorted(actual_summaries, key=lambda entry: _chapter_order(entry.chapter_id)):
            blocks.extend(
                [
                    f"",
                    f"{item.chapter_id}",
                    f"- 实际发生：{'；'.join(item.actual_events) or '无'}",
                    f"- 读者已知：{'；'.join(item.reader_now_knows) or '无'}",
                    f"- 读者当前相信：{'；'.join(item.reader_now_believes) or '无'}",
                    f"- 未解问题：{'；'.join(item.open_questions) or '无'}",
                    f"- 角色状态：{'；'.join(item.character_states) or '无'}",
                    f"- 关系状态：{'；'.join(item.relationship_state) or '无'}",
                    f"- 已埋线索：{'；'.join(item.seeded_clues) or '无'}",
                    f"- 仍锁住的真相：{'；'.join(item.locked_truths) or '无'}",
                ]
            )
        return "\n".join(blocks).strip()

    @classmethod
    def _chapter_payload_text(
        cls,
        *,
        chapter_brief: ChapterBrief,
        current_chapter_id: str,
        active_twists: list[TwistDesign],
        active_story_lines: list[StoryLine],
    ) -> str:
        lines = [
            "【本章写作包】",
            "",
            f"章节：{chapter_brief.chapter_id}《{chapter_brief.title}》",
            "",
            "本章一句话目标：",
            chapter_brief.summary,
            "",
            "本章承接钩子：",
            chapter_brief.incoming_hook or "第一章无前章钩子。",
            "",
            "本章开场发动：",
            chapter_brief.opening_hook,
            "",
            "本章承载物：",
            chapter_brief.chapter_object,
            "",
            "本章场景发动机：",
            chapter_brief.scene_engine,
            "",
            "本章关系重估：",
            chapter_brief.relationship_reprice,
            "",
            "本章情绪翻转：",
            chapter_brief.emotional_turn,
            "",
            "本章回忆触发：",
            chapter_brief.backstory_trigger or "无。",
            "",
            "本章推进故事线：",
        ]
        for line in active_story_lines:
            lines.append(f"- {line.line_id}：{line.core_question} / 规则：{'；'.join(line.line_rules) or '无'}")
        if not active_story_lines:
            lines.append("- 无")
        lines.extend(["", "本章涉及反转："])
        if not active_twists:
            lines.append("- 无")
        for twist in active_twists:
            if _is_revealed(current_chapter_id, twist.reveal_at):
                lines.append(
                    f"- {twist.twist_id}：已到揭露章，仅可在 allowed_info 内转化为当前可写信息。"
                )
            else:
                lines.append(
                    f"- {twist.twist_id}：维护误判={twist.false_belief}；读者站队={twist.reader_alignment}；允许线索={'；'.join(twist.allowed_clues) or '无'}；禁止={'；'.join(twist.forbidden_reveals) or '无'}；POV 锁={twist.pov_lock}"
                )
        lines.extend(
            [
                "",
                "读者本章结束时应该相信：",
                chapter_brief.reader_belief,
                "",
                "读者本章不能知道：",
            ]
        )
        hidden_items = list(chapter_brief.forbidden)
        for twist in active_twists:
            if not _is_revealed(current_chapter_id, twist.reveal_at):
                hidden_items.extend(twist.forbidden_reveals)
        for item in dict.fromkeys(hidden_items):
            lines.append(f"- {item}")
        lines.extend(
            [
                "",
                "本章允许明写：",
            ]
        )
        for item in chapter_brief.allowed_info:
            lines.append(f"- {item}")
        lines.extend(["", "本章允许暗示："])
        for item in chapter_brief.allowed_clues:
            lines.append(f"- {item}")
        lines.extend(["", "本章禁止："])
        for item in chapter_brief.forbidden:
            lines.append(f"- {item}")
        lines.extend(
            [
                "",
                "本章信息预算：",
                chapter_brief.info_budget,
                "",
                "结尾牵引：",
                chapter_brief.ending_pull,
            ]
        )
        return "\n".join(lines).strip()

    @staticmethod
    def _relevant_world_rules_text(chapter_brief: ChapterBrief, worldbuilding: dict[str, Any]) -> str:
        rules: list[str] = [chapter_brief.world_limit]
        story_engine = worldbuilding.get("story_engine", {}) if isinstance(worldbuilding, dict) else {}
        for key in ("world_rules", "power_structure", "objective_conditions"):
            value = story_engine.get(key, [])
            if isinstance(value, list):
                rules.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                rules.append(value.strip())
        deduped: list[str] = []
        seen: set[str] = set()
        for rule in rules:
            if rule and rule not in seen:
                seen.add(rule)
                deduped.append(rule)
        lines = ["【本章相关世界规则】", ""]
        for index, rule in enumerate(deduped[:5], start=1):
            lines.append(f"{index}. {rule}")
        return "\n".join(lines).strip()
