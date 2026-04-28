# Iteration Report

## 本轮改动
- 保留 sequential beat drafting；未回滚整章首稿。
- 默认 beat 数收窄：3000 字左右 3 个，4000~5500 字 4 个，5500~7000 字 5 个，7000 字以上最多 6 个。
- `plan_content_blocks` prompt 从长字段说明改为 compact beat 规划。
- `draft_content_block` prompt 只保留 8 个顶层输入：`chapter_goal`、`hard_facts`、`character_state`、`beat`、`previous_text_tail`、`chapter_so_far`、`style_rules`、`target_length`。

## 删除/合并字段
- writer prompt 不再默认传：`completed_chapter_memory_text`、`relationship_state_text`、`scene_character_context_text`、`current_chapter_written_blocks_json`、`current_chapter_draft_tail`、`block_card_text`、`delivered_beat_summary_text`。
- 旧 beat 字段兼容保留在 `ContentBlock`；默认起草只使用 compact `beat = goal/start/turn/end/avoid`。
- `must_not_repeat`、`must_hide`、`style_risk_guard` 合并进 `avoid`；`scene_goal/purpose` 合并进 `goal`；`new_value/turn_type` 合并进 `turn`；`end_state` 合并进 `end`。

## 指标变化
- 模板字符：`plan_content_blocks` 9252 -> 1703，`draft_content_block` 9033 -> 1179。
- 同一无网络 happy-path 采样：4 个 draft prompt chars 93511 -> 25989，下降约 72.2%。
- `llm_calls`：采样链路保持 12，未增加。
- `duration_seconds`：未跑真实 LLM eval，本轮仅验证 prompt 体积和本地回归。
- `redundancy`、`romance_tension`、`relationship_progression`、`hook`：未跑真实 LLM judge，因此本报告不声明质量分变化。

## 验证结论
- `prompt_chars` 明显下降：是。
- `llm_calls` 不增加：是。
- `duration_seconds` 下降：待真实 LLM eval 验证，理论上随 prompt chars 和 beat 数下降。
- `redundancy` 不恶化、核心 romance 指标不明显下降：待真实 LLM eval 验证。

## 下一轮唯一建议
- 只跑一个现有 fixture case 对比 sequential baseline，确认成本下降没有换来张力和关系推进回退。
