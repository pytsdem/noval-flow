from __future__ import annotations

import json

from novel_flow.models.schemas import ChapterBrief, ContentBlock, ContentBlockPlanPayload
from novel_flow.tools._base import LLMChapterTool


DEFAULT_PARAGRAPH_BUDGET = "建议 2-4 个自然段，每段 30-120 中文字，最长不超过 180 中文字"


class PlanContentBlocksTool(LLMChapterTool):
    name = "plan_content_blocks"

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        chapter_brief = ChapterBrief.model_validate(json.loads(str(payload["chapter_brief_json"])))
        try:
            prompt = self.render_prompt(
                "writer/plan_content_blocks.txt",
                chapter_brief_json=payload["chapter_brief_json"],
                completed_chapter_memory_text=payload.get("completed_chapter_memory_text", ""),
                chapter_payload_text=payload.get("chapter_payload_text", ""),
                relevant_world_rules_text=payload.get("relevant_world_rules_text", ""),
                timeline_anchor_facts_text=payload.get("timeline_anchor_facts_text", ""),
                scene_character_context_text=payload.get("scene_character_context_text", ""),
                relationship_state_text=payload.get("relationship_state_text", ""),
                style_card_text=payload.get("style_card_text", ""),
                target_word_count_text=payload.get("target_word_count_text", ""),
            )
            raw = self.generate_json(
                prompt=prompt,
                schema_name=self.name,
                schema_model=ContentBlockPlanPayload,
            )
            blocks = [ContentBlock.model_validate(item) for item in raw.get("blocks", [])]
        except Exception:
            blocks = self._fallback_blocks(chapter_brief)
        normalized = self._normalize_blocks(blocks=blocks, chapter_brief=chapter_brief)
        return ContentBlockPlanPayload.model_validate({"blocks": normalized}).model_dump(mode="json")

    def _normalize_blocks(self, *, blocks: list[ContentBlock], chapter_brief: ChapterBrief) -> list[ContentBlock]:
        if len(blocks) < 3:
            blocks = self._fallback_blocks(chapter_brief)
        trimmed = blocks[:6]
        normalized: list[ContentBlock] = []
        for index, block in enumerate(trimmed, start=1):
            normalized.append(
                block.model_copy(
                    update={
                        "block_id": f"{chapter_brief.chapter_id}.sc_001.b{index:03d}",
                        "chapter_id": chapter_brief.chapter_id,
                        "block_index": index,
                        "characters": list(block.characters or chapter_brief.character_focus or []),
                        "active_lines": list(block.active_lines or chapter_brief.active_lines or []),
                        "active_twists": list(block.active_twists or chapter_brief.active_twists or []),
                        "scene_goal": str(block.scene_goal or block.purpose or "").strip(),
                        "must_reveal": list(block.must_reveal or []),
                        "must_hide": list(block.must_hide or chapter_brief.forbidden[:4]),
                        "end_state": str(block.end_state or chapter_brief.small_payoff or chapter_brief.ending_pull or "").strip(),
                        "human_reaction_target": self._list_or_fallback(
                            block.human_reaction_target,
                            self._fallback_human_reaction(index=index, chapter_brief=chapter_brief),
                        ),
                        "cost_shift": str(block.cost_shift or self._fallback_cost_shift(index=index, chapter_brief=chapter_brief)).strip(),
                        "reader_feeling_target": str(
                            block.reader_feeling_target or self._fallback_reader_feeling(index=index, chapter_brief=chapter_brief)
                        ).strip(),
                        "paragraph_budget": str(block.paragraph_budget or DEFAULT_PARAGRAPH_BUDGET).strip(),
                        "style_risk_guard": self._list_or_fallback(
                            block.style_risk_guard,
                            self._fallback_style_risks(index=index, chapter_brief=chapter_brief),
                        ),
                        "text": "",
                        "status": "draft",
                        "version": 1,
                    }
                )
            )
        return normalized

    def _fallback_blocks(self, chapter_brief: ChapterBrief) -> list[ContentBlock]:
        focus_characters = list(chapter_brief.character_focus or [])
        active_lines = list(chapter_brief.active_lines or [])
        active_twists = list(chapter_brief.active_twists or [])
        forbidden = list(chapter_brief.forbidden or [])
        clues = list(chapter_brief.allowed_clues or [])
        blocks = [
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b001",
                chapter_id=chapter_brief.chapter_id,
                block_index=1,
                purpose=f"用当前压迫和立刻发生的事情把读者拉进章节：{chapter_brief.opening_hook}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=chapter_brief.opening_hook or chapter_brief.summary,
                must_reveal=[item for item in [chapter_brief.opening_hook] if item],
                must_hide=forbidden[:4],
                emotional_tone=chapter_brief.reader_emotion,
                end_state="开场压力落地，人物被迫进入这章的主要局面。",
                human_reaction_target=[
                    "主角要先表现出被现实压住的一瞬，不只是在脑中分析局势。",
                    "配角至少有一个替读者受惊、犹疑或避让的反应。",
                ],
                cost_shift="人物先失去体面、缓冲时间，或一个更从容的选择。",
                reader_feeling_target="读者先被拉进当下的压迫，再意识到这章不会轻松展开。",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                style_risk_guard=[
                    "不要先铺一大段背景再进入场面。",
                    "不要把人物写成解释设定的嘴。",
                ],
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b002",
                chapter_id=chapter_brief.chapter_id,
                block_index=2,
                purpose=f"围绕章节对象推进外部行动，同时让关系出现可感知摩擦：{chapter_brief.chapter_object}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=chapter_brief.chapter_object,
                must_reveal=[item for item in [chapter_brief.chapter_object, chapter_brief.small_payoff] if item],
                must_hide=forbidden[:4],
                emotional_tone=chapter_brief.emotional_turn,
                end_state="人物拿到一小步推进，但代价和误读也同步加重。",
                human_reaction_target=[
                    "人物的克制要露出身体代价、礼法代价或现实算计。",
                    "关系对象不能只给信息，要在互动里重估对方。",
                ],
                cost_shift="人物为了推进目标多付出一次现实成本，关系也更难收回。",
                reader_feeling_target="读者感觉到推进不是白拿到的，关系在变贵。",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                style_risk_guard=[
                    "不要整块都在解释章节对象为什么重要。",
                    "不要让对话只承担情报转述。",
                ],
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b003",
                chapter_id=chapter_brief.chapter_id,
                block_index=3,
                purpose=f"让情绪或关系完成一次真正在场的翻价：{chapter_brief.relationship_reprice}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=chapter_brief.character_shift or chapter_brief.relationship_reprice,
                must_reveal=[item for item in [chapter_brief.character_shift, chapter_brief.relationship_reprice, *clues[:2]] if item],
                must_hide=forbidden[:4],
                emotional_tone=chapter_brief.emotional_turn,
                end_state="人物立场、误解或关系温度被重新定价。",
                human_reaction_target=[
                    "至少一个人物在强撑时露出短暂失手、停顿或自嘲。",
                    "若有 clue 出现，配角或对手的反应要帮助放大它，而不是作者解释它。",
                ],
                cost_shift="旧案、关系或自我判断都比上一块更难处理一步。",
                reader_feeling_target="读者记住的不是信息本身，而是这层关系重新变得危险。",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                style_risk_guard=[
                    "不要把情绪翻转写成总结句。",
                    "不要重复同一种寒冷、疼痛或压迫意象。",
                ],
            ),
            ContentBlock(
                block_id=f"{chapter_brief.chapter_id}.sc_001.b004",
                chapter_id=chapter_brief.chapter_id,
                block_index=4,
                purpose=f"把这一章收在新的问题和代价上，形成自然续读拉力：{chapter_brief.ending_pull}",
                characters=focus_characters,
                active_lines=active_lines,
                active_twists=active_twists,
                scene_goal=chapter_brief.ending_pull,
                must_reveal=[item for item in [chapter_brief.ending_pull] if item],
                must_hide=forbidden[:4],
                emotional_tone=chapter_brief.reader_emotion,
                end_state="这一章结束时，读者知道下一步更难，而且人物已经没法轻易退回去。",
                human_reaction_target=[
                    "结尾消息或动作要落在人物的具体反应上，而不是只写一句钩子结论。",
                    "让结尾的代价先落到一个人身上，再把读者拖去下一章。",
                ],
                cost_shift="人物失去一个缓冲机会，或被迫面对更坏的下一步。",
                reader_feeling_target="读者带着不安、惋惜或强烈的下一步问题离章。",
                paragraph_budget=DEFAULT_PARAGRAPH_BUDGET,
                style_risk_guard=[
                    "不要为了制造钩子硬转折。",
                    "不要用总结式旁白代替结尾冲击。",
                ],
            ),
        ]
        return blocks

    @staticmethod
    def _list_or_fallback(items: list[str], fallback: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        return cleaned or fallback

    @staticmethod
    def _fallback_human_reaction(*, index: int, chapter_brief: ChapterBrief) -> list[str]:
        if index == 1:
            return [
                "主角要先有一个被现实压住的具体反应，再进入行动。",
                "配角或旁观者要替读者先受一下惊。",
            ]
        if index == 2:
            return [
                "推进目标时要露出算计、迟疑或礼法下的失衡。",
                "对手或关系对象要有一个不完全可控的反应。",
            ]
        if index == 3:
            return [
                "情绪翻转要靠身体、沉默、错称或失态来显形。",
                "人物不能只总结关系变化，要在互动里露出代价。",
            ]
        return [
            "结尾冲击要先打在人物身上，而不是直接做摘要。",
            "让人物对下一步的代价有一个短而真的反应。",
        ]

    @staticmethod
    def _fallback_cost_shift(*, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "人物先失去体面、余地或一个更轻松的开场。"
        if index == 2:
            return "人物为了推进章节对象多付出一次现实成本。"
        if index == 3:
            return "关系、误解或自我判断被抬高了处理成本。"
        return f"这一章收尾时，人物必须带着新的负担面对：{chapter_brief.ending_pull}"

    @staticmethod
    def _fallback_reader_feeling(*, index: int, chapter_brief: ChapterBrief) -> str:
        if index == 1:
            return "先感到压迫和失衡，再被拉进人物的难处。"
        if index == 2:
            return "感觉推进来之不易，而且关系正在变坏。"
        if index == 3:
            return "感觉到关系张力被重新定价，而不是只被通知发生变化。"
        return "读者想立刻知道下一步会怎样，同时知道人物已经更难了。"

    @staticmethod
    def _fallback_style_risks(*, index: int, chapter_brief: ChapterBrief) -> list[str]:
        risks = [
            "不要用整段心理复盘代替场面。",
            "不要把人物写成剧情解释器。",
        ]
        if index == 1:
            risks.append("不要把开场写成背景说明书。")
        elif index == 2:
            risks.append("不要只写拿到信息，忽略推进的代价。")
        elif index == 3:
            risks.append("不要用一句总结完成关系翻价。")
        else:
            risks.append("不要为了钩子把结尾写成硬拐弯。")
        if chapter_brief.reader_emotion:
            risks.append(f"不要把 {chapter_brief.reader_emotion} 直接写成标签句。")
        return risks[:4]
