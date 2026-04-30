# Self-Improve Iteration Ledger

这份文件是 `report.md` 的简明账本版，用来快速回看每轮迭代改了什么、结论是什么、下一步是什么。

## Iteration 0

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: 基础链路打通
- Root layer: `provider_infrastructure`
- Files changed: `src/novel_flow/llm/codex_cli.py`, `tests/test_codex_cli_client.py`
- Success snapshot:
  - 暴露 `codex exec` 的真实 stderr，并定位到 `Access denied / Broken pipe`
  - requirement `case01` 在 `LLM_PROVIDER=doubao` 下完整跑通
- Next step: 补齐另外两个 requirement cases 的可运行基线
- Report ref: `report.md` / `Iteration 0`

## Iteration 1

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: requirement case 03 可运行性确认
- Root layer: `requirement_case_coverage`
- Files changed: 无新增代码改动
- Success snapshot:
  - `case03` 从 provider 级失败变为完整可评测
  - requirement case 覆盖率继续补齐
- Next step: 继续处理 `case02`
- Report ref: `report.md` / `Iteration 1`

## Iteration 2

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: 调整为单点评测优先
- Root layer: `provider_timeout_and_eval_strategy`
- Files changed: `src/novel_flow/llm/doubao.py`, `tests/test_doubao_client.py`
- Success snapshot:
  - 给 `doubao` 增加更宽松的读超时和一次重试
  - 自优化默认策略切到 `step eval / diagnostics / artifact 检查`
- Next step: 先跑单点评测，再决定是否需要端到端
- Report ref: `report.md` / `Iteration 2`

## Iteration 3

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: 修正历史回放 case 的状态与成本保真度
- Root layer: `historical_replay_fidelity`
- Files changed: `evals/romance/case_exporter.py`, `tests/test_eval_case_exporter.py`
- Success snapshot:
  - 补回 historical replay 缺失的 `character_mind_states`
  - 修掉普通 `rewrite_iteration` 被误标成 `used_full_rewrite=true`
  - historical step gate 从 `10/10 blocked` 变成 `10/10 warn`
- Next step: 转向真实的 `draft_execution_layer`
- Report ref: `report.md` / `Iteration 3`

## Iteration 4

- Date: `2026-04-23`
- Outcome: `reject`
- Theme: 首稿+patch 宽约束 prompt 未换来稳定收益
- Root layer: `draft_execution_prompt_guardrails`
- Files changed: `prompts/writer/write_chapter_full.txt`, `prompts/writer/rewrite_blocks_by_plan.txt`, `tests/test_prompt_rendering.py`
- Success snapshot:
  - 证实宽约束 prompt 会伤到更高优先级的 `romance_tension / continuity / redundancy`
- Next step: 不再同时给首稿和 patch 叠宽约束，改打更窄的 patch 根因
- Report ref: `report.md` / `Iteration 4`

## Iteration 5

- Date: `2026-04-23`
- Outcome: `reject`
- Theme: 直接裁掉低优先级 patch block 会伤到关系张力块
- Root layer: `patch_scope_pruning`
- Files changed: `src/novel_flow/tools/build_chapter_patch_plan.py`, `tests/test_build_chapter_patch_plan.py`
- Success snapshot:
  - 证实某些看似低优先级的 patch block 实际承载关系张力，不能直接裁掉
- Next step: 改试更窄的 line-level 指令裁剪
- Report ref: `report.md` / `Iteration 5`

## Iteration 6

- Date: `2026-04-23`
- Outcome: `reject`
- Theme: 只裁低价值 line-level 指令仍未形成净收益
- Root layer: `patch_instruction_pruning`
- Files changed: `src/novel_flow/tools/build_chapter_patch_plan.py`, `tests/test_build_chapter_patch_plan.py`
- Success snapshot:
  - 证实 line-level 指令裁剪同样不稳，不能继续在这条路上堆成本
- Next step: 先补强评测与诊断层
- Report ref: `report.md` / `Iteration 6`

## Iteration 7

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: 补上 case 级加权 pairwise 比较，避免均分掩盖坏优化
- Root layer: `evaluation_comparison`
- Files changed: `evals/romance/comparison.py`, `tests/test_case_comparison.py`
- Success snapshot:
  - comparison 不再只看均分，而会看 case 级 pairwise 偏好
  - 更早拦住“局部指标涨、整体体验变差”的候选
- Next step: 增加 anti-slop / direct-thought 的低成本单点信号
- Report ref: `report.md` / `Iteration 7`

## Iteration 8

- Date: `2026-04-23`
- Outcome: `keep`
- Theme: 新增 anti-slop / direct-thought 单点诊断
- Root layer: `evaluation_anti_slop_observability`
- Files changed: `evals/romance/judges/rule_metrics.py`, `evals/romance/harness.py`, `evals/romance/workflow_diagnostics.py` 等
- Success snapshot:
  - 新增 `AntiSlopRuleAnalyzer`
  - diagnostics 和 harness breakdown 都能看到 `rule_anti_slop_score`
- Next step: 用最小生成改动验证 anti-slop 是否真的提升 romance 体验
- Report ref: `report.md` / `Iteration 8`

## Iteration 9

- Date: `2026-04-24`
- Outcome: `reject`
- Theme: final polish 级 anti-slop prompt 成功去解释化，但把关系拉扯一起磨平了
- Root layer: `final_polish_anti_slop`
- Files changed: `prompts/writer/chapter_final_polish.txt`, `tests/test_final_polish_prompt.py`
- Success snapshot:
  - 证实在 `final_polish` 直接强压解释句会把 romance 电流一起削弱
- Next step: 把目标收窄到局部 rewrite，而不是全章 final polish
- Report ref: `report.md` / `Iteration 9`

## Iteration 10

- Date: `2026-04-24`
- Outcome: `reject`
- Theme: 局部 rewrite anti-slop brief 虽然显著降了解释句，但把 block 间场景交接打坏了
- Root layer: `rewrite_local_anti_slop`
- Files changed: `src/novel_flow/tools/rewrite_blocks_by_plan.py`, `prompts/writer/rewrite_blocks_by_plan.txt`, `tests/test_prompt_rendering.py`, `tests/test_writing_chapter_agent.py`
- Success snapshot:
  - 定位到真正该打的是 `patch acceptance gate`，不是继续叠 rewrite prompt 规则
- Next step: 修 `patch_judge / final_judge` 的 acceptance gate
- Report ref: `report.md` / `Iteration 10`

## Iteration 11

- Date: `2026-04-26`
- Outcome: `keep`
- Theme: 收紧 patch acceptance gate，拦住“明明还有问题却直接放行”的坏候选
- Root layer: `patch_acceptance_gate`
- Files changed: `src/novel_flow/tools/judge_patched_chapter.py`, `src/novel_flow/agents/writing_chapter_agent.py`, `tests/test_writing_chapter_agent.py`
- Success snapshot:
  - 只要还有 `remaining_issues / introduced_issues / follow-up recommendation`，系统就不会再错误放行
  - 回归样例证明“口头 pass 但实际未通过”时会继续 patch
- Next step: 在更可信的 patch gate 之上，再试 candidate rewrite + rerank
- Report ref: `report.md` / `Iteration 11`

## Iteration 12

- Date: `2026-04-26`
- Outcome: `reject`
- Theme: block 级 multi-candidate rerank 还没有打赢 baseline
- Root layer: `rewrite_candidate_rerank`
- Files changed: `src/novel_flow/tools/rewrite_blocks_by_plan.py`, `tests/test_writing_chapter_agent.py`
- Success snapshot:
  - 证实 block 级局部 rerank 启发式目前还不值得作为默认成本引入
- Next step: 如果再走 multi-candidate 路线，先升级 rerank 信号，而不是继续用局部启发式
- Report ref: `report.md` / `Iteration 12`

## Iteration 13

- Date: `2026-04-26`
- Outcome: `keep`
- Theme: 修正 patch judge 的“无需再补”口径，避免 satisfied verdict 被误判成 follow-up
- Root layer: `patch_followup_normalization`
- Files changed: `src/novel_flow/tools/judge_patched_chapter.py`, `src/novel_flow/agents/writing_chapter_agent.py`, `tests/test_writing_chapter_agent.py`
- Success snapshot:
  - 修掉“无需再补补丁”因命中“再补”子串而被误判 follow-up 的 bug
  - fast mode 在 satisfied recommendation 场景下不再错误进入下一轮 patch
- Next step: 把精力转回真正影响 romance 体验的上游层
- Report ref: `report.md` / `Iteration 13`

## Iteration 14

- Date: `2026-04-27`
- Outcome: `keep`
- Theme: 把 chapter planning 从信息块收紧成更有排他职责的 beat card
- Root layer: `chapter_planning_beat_card`
- Files changed: `src/novel_flow/models/schemas.py`, `src/novel_flow/tools/plan_content_blocks.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `prompts/writer/plan_content_blocks.txt`, `prompts/writer/write_chapter_full.txt`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`
- Success snapshot:
  - `ContentBlock` 新增 `new_value / must_not_repeat / relationship_delta / clue_delta / must_land_in_action / target_chars`
  - planner 即使收到旧式最小 block 输出，也会自动补齐 beat 字段并把它们传进 writer prompt
  - 这轮先保留结构升级，不提前宣称正文指标已净提升
- Next step: 在隔离旧实验 runtime 改动后，跑干净的 `case01` single-case 对照，验证重复控制、scene pressure 和 heroine agency
- Report ref: `report.md` / `Iteration 14`

## Iteration 15

- Date: `2026-04-27`
- Outcome: `reject`
- Theme: clean `case01` 已出现 hook 与 pairwise 收益，但还不足以把 beat card 宣称为正文稳定提升
- Root layer: `clean_requirement_validation`
- Files changed: `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`, `evals/romance/reports/runs/20260426/chapter_eval/doubao__doubao-seed-1-8-251228/romance_case_01_court_return/candidate_beat_card_case01_clean/*`
- Success snapshot:
  - 在隔离 worktree 里，beat card 版本对 `case01` 的 `hook_score` 从 `8.3 -> 8.75`
  - pairwise comparison 已经偏向 candidate，但 `redundancy` 轻微回撤且 `duration +36.27s`
- Next step: 不再反复证明 beat card 本身，改打基于 beat card 的正文执行层，优先补 heroine agency 和双人微动作
- Report ref: `report.md` / `Iteration 15`

## Iteration 16

- Date: `2026-04-27`
- Outcome: `reject`
- Theme: 全局追加女主主动性与错位微动作纪律，反而把 beat-card baseline 的含蓄张力打散了
- Root layer: `write_chapter_full_global_agency_prompt`
- Files changed: `prompts/writer/write_chapter_full.txt`, `tests/test_writing_chapter_agent.py`（实验后未保留），以及 `evals/romance/reports/runs/20260427/chapter_eval/doubao__doubao-seed-1-8-251228/romance_case_01_court_return/candidate_agency_microaction_case01/*`
- Success snapshot:
  - prompt 回归证明新纪律真实进入了 full chapter prompt
  - 但 clean `case01` 对比 beat-card baseline 后，`pairwise` 明确站回 baseline，且 `redundancy / continuity / hook` 一起回撤
- Next step: 不再给整章全局 prompt 叠“女主主动性”硬要求，改打更局部、可兑现的 beat 级职责约束
- Report ref: `report.md` / `Iteration 16`

## Iteration 17

- Date: `2026-04-27`
- Outcome: `reject`
- Theme: 把 heroine agency 前移成 beat 级“主动方 / 主动动作”字段，但 `case01` core romance 仍不如 clean beat-card baseline；仅保留 DeepSeek provider 支持
- Root layer: `beat_planning_initiative_owner_move`
- Files changed: `src/novel_flow/config.py`, `src/novel_flow/llm/factory.py`, `.env.example`, `README.md`, `tests/test_llm_factory.py`（保留）；以及 `src/novel_flow/models/schemas.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/tools/plan_content_blocks.py`, `prompts/writer/plan_content_blocks.txt`, `prompts/writer/write_chapter_full.txt`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`（实验后未保留），并新增 `evals/romance/reports/runs/20260427/chapter_eval/doubao__doubao-seed-1-8-251228/romance_case_01_court_return/candidate_beat_card_initiative_case01/*`
- Success snapshot:
  - 新增显式 `deepseek` provider，可独立配置 `DEEPSEEK_API_KEY / MODEL / BASE_URL`，也可作为 `codex` fallback
  - 但 `case01` 对比 clean beat-card baseline 时，`romance_tension 8.5 -> 7.5`、`character_attraction 8.25 -> 7.45`、`hook 8.75 -> 8.5`，`pairwise` 仍站回 baseline
- Next step: 保留 DeepSeek provider；继续 beat-card 时不要再加 schema 级主动性字段，改试局部 guidance 或 chapter payload 约束
- Report ref: `report.md` / `Iteration 17`


## Iteration 18

- Date: `2026-04-27`
- Outcome: `partial_keep`
- Theme: keep `DeepSeek V4-Pro` as default runtime, reject the local relationship-beat guidance prompt tweak
- Root layer: `provider_default_switch_and_validation`
- Files changed: `src/novel_flow/config.py`, `src/novel_flow/llm/factory.py`, `src/novel_flow/server.py`, `evals/romance/harness.py`, `.env.example`, `README.md`, `tests/test_llm_factory.py`, plus `evals/romance/reports/runs/20260427/chapter_eval/deepseek__deepseek-v4-pro/romance_case_01_court_return/deepseek_v4_pro_case01_candidate/*`
- Success snapshot:
  - repo defaults, `codex` fallback priority, UI model dropdown, and eval model naming all now point to `DeepSeek V4-Pro`
  - direct UI fetch confirmed the page now exposes `DeepSeek V4-Pro` as the default model option
  - current `DeepSeek V4-Pro` candidate improved `hook_score` to `9.25` and reduced `llm_calls` / `patch_rounds`, but still lost to the clean beat-card baseline on pairwise preference and core romance metrics
- Next step: keep the `DeepSeek` switch, but move the next optimization target to post-draft / pre-polish execution rather than adding more planner or full-chapter relationship guidance
- Report ref: `report.md` / `Iteration 18`

## Iteration 19

- Date: `2026-04-27`
- Outcome: `partial_keep`
- Theme: 收紧人物字段作用域，把 writer 侧人物控制信息从重复标签改成分层控制语
- Root layer: `character_context_scope_dedup`
- Files changed: `src/novel_flow/services/novel_context.py`, `src/novel_flow/services/character_mindset_formatter.py`, `prompts/writer/step_3_character_bible.txt`, `prompts/writer/build_character_mindset.txt`, `tests/test_schema_and_context.py`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - `scene_character_context_text` 不再把 `personality / behavior_pattern / motivation / arc / initial_state` 混成几条大而虚的提示
  - `chapter_character_mindsets_text` 改成更短、更可执行的 writer 控制语，减少同义字段平铺
  - 上游 prompt 定义明确区分了稳定底色、本章状态、长期变化，降低任务输出互相重写同一层信息的概率
- Next step: 跑隔离 `case01`，验证人物标签重复是否下降，并观察 `redundancy / tension / relationship_progression`
- Report ref: `report.md` / `Iteration 19`

## Iteration 20

- Date: `2026-04-28`
- Outcome: `partial_keep`
- Theme: 把正文执行从整章首稿切成顺序 beat 起草，并显式把已交付 beat 价值带给下一 beat
- Root layer: `sequential_beat_drafting_mvp`
- Files changed: `src/novel_flow/agents/writing_chapter_agent.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/services/novel_context.py`, `src/novel_flow/tools/draft_block.py`, `src/novel_flow/tools/revise_block.py`, `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `tests/test_prompt_rendering.py`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - `WritingChapterAgent` 现在默认按 beat 顺序逐个 `draft_block`，不再先整章一把写
  - 每个 beat 都会拿到 `[Already delivered in this chapter]`，显式看到前面已落地的 `new_value / relationship_delta / clue_delta / micro_hook`
  - beat prompt 已补回 `assistant_persona_prompt` 和 `writing_requirements_json`，不会因为切成 sequential drafting 就丢掉风格和节奏约束
- Next step: 跑干净 `case01`，验证跨 beat 重复、`redundancy`、`romance_tension` 和 `relationship_progression`
- Report ref: `report.md` / `Iteration 20`

## Iteration 21

- Date: `2026-04-28`
- Outcome: `reject`
- Theme: 顺序 beat 起草在 `case01` 上把 romance 主指标和 pairwise 拉起来了，但成本和重复仍未过 keep 门
- Root layer: `sequential_beat_drafting_validation`
- Files changed: `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - `romance_tension 8.5 -> 9.2`
  - `relationship_progression 8.0 -> 9.0`
  - `hook 8.75 -> 9.65`
  - `mind_state_consistency 8.7 -> 9.4`
  - `pairwise_preferred_side = candidate`
  - 但 `redundancy 8.84 -> 8.62`、`duration_seconds 1214.45 -> 1768.8`、`llm_calls 18 -> 20`，所以 comparison 仍判 `accept_change = false`
- Next step: 收缩 beat 数和上下文体积，专打 `redundancy` 与 prompt cost，再复跑 isolated `case01`
- Report ref: `report.md` / `Iteration 21`

## Iteration 22

- Date: `2026-04-28`
- Outcome: `partial_keep`
- Theme: 三案跨类型/跨 tone 正文 smoke 验证 prompt/beat 瘦身后的质量与成本
- Root layer: `chapter_generation_length_and_beat_overrun`
- Files changed: `evals/romance/reports/runs/20260428/chapter_eval_rollup/mixed__doubao-plus-deepseek/multi_case__3cases/cross_tone_smoke_prompt_beat_slim_mixed_provider/summary.json`, `evals/romance/reports/runs/20260428/chapter_eval_rollup/mixed__doubao-plus-deepseek/multi_case__3cases/cross_tone_smoke_prompt_beat_slim_mixed_provider/summary.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot: all 3 cases passed; `genre_fit` = 9.0 / 9.2 / 9.2, `hook` >= 8.9, `continuity` >= 9.0, `mind_state_consistency` >= 8.9
- Cost snapshot: `llm_calls` = 17 / 18 / 16, `generation_prompt_chars` = 202700 / 279843 / 240464, `duration_seconds` = 1182.64 / 1639.99 / 1185.57
- Main issue: output length and late-beat repetition; case02 final `9680 chars`, case03 repeated b003 before patch
- Next step: enforce `target_chars` as hard cap in draft/revise/final polish, add per-beat stop condition, and prevent later beats from re-narrating delivered events
- Report ref: `report.md` / `Iteration 22`; detail ref: `evals/romance/reports/runs/20260428/chapter_eval_rollup/mixed__doubao-plus-deepseek/multi_case__3cases/cross_tone_smoke_prompt_beat_slim_mixed_provider/summary.md`

## Iteration 23

- Date: `2026-04-28`
- Outcome: `keep_without_llm_eval`
- Theme: 针对三案读感做长度硬约束与 beat 价值转折收紧
- Root layer: `beat_value_turn_and_length_control`
- Files changed: `prompts/writer/plan_content_blocks.txt`, `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `prompts/writer/chapter_final_polish.txt`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/tools/plan_content_blocks.py`, `src/novel_flow/tools/final_polish.py`, `src/novel_flow/agents/writing_chapter_agent.py`, `src/novel_flow/agents/writer.py`, `tests/test_schema_and_context.py`
- Success snapshot:
  - `target_chars` 从软建议改成 draft/revise/final polish 的硬上限语义，final polish 默认不得扩写
  - block planner 现在要求每个 beat 有明确 `value_turn`，并阻止相邻 beat 只重复解规则、同类危机或同一动作循环
  - normalize 阶段会收紧异常偏大的 block `target_chars`，并把硬字数、停止条件和有效转折写入 beat guard
- Verification: `tests.test_prompt_rendering tests.test_schema_and_context tests.test_writing_chapter_agent` 通过；`tests.test_step_plan_evals tests.test_step_fixtures tests.test_romance_cross_tone_suite tests.test_requirement_cases tests.test_romance_eval_harness` 通过；`py_compile`、`git diff --check`、`scripts/check_prompt_encoding.py` 通过
- LLM eval: 本轮未跑，避免在静态修正后立即重复花费
- Next step: 先单跑 `romance_case_02_xianxia_rival_trial`，看 `final_chars / redundancy / genre_fit / hook` 是否同时改善，再决定是否复跑三案 suite
- Report ref: `report.md` / `Iteration 23`
## Iteration 24

- Date: `2026-04-28`
- Outcome: `reject`
- Title: `Compact beat payload / review / planner tightening on case02`
- Root layer: `beat_payload_dedup_and_dramatic_job_tightening`
- Files changed: `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/tools/review_block_quality.py`, `src/novel_flow/tools/plan_content_blocks.py`, `src/novel_flow/services/review_aggregator.py`, `src/novel_flow/agents/writing_chapter_agent.py`, `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `prompts/writer/review_block_quality.txt`, `prompts/writer/plan_content_blocks.txt`, `tests/test_schema_and_context.py`
- Success snapshot:
  - payload dedup reduced `generation_prompt_chars` on `case02` from `279843 -> 255210`
  - `patched_block_ratio` dropped from `0.50 -> 0.25`
  - `redundancy_score` improved from `7.42 -> 7.82`
  - but `romance_tension 8.2 -> 8.0`, `emotional_resonance 8.4 -> 7.5`, `character_attraction 8.67 -> 8.05`, `hook 9.0 -> 8.25`, `genre_fit 9.2 -> 8.5`
- Next step: revert this candidate code and next target the active `draft_block` path directly, especially translator-like explanation sentences and loss of playful banter in `light_adventure_banter`
- Report ref: `report.md` / `Iteration 24`

## Iteration 25

- Date: `2026-04-28`
- Outcome: `keep`
- Title: `Action-first block prompting with banter preservation on case02`
- Root layer: `draft_block_action_first_and_light_banter_preservation`
- Files changed: `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `tests/test_prompt_rendering.py`
- Success snapshot:
  - action-first rule added: rules/clues/danger must show through consequence before brief interpretation
  - light-banter preservation added so anti-repeat edits do not flatten `light_adventure_banter`
  - `case02` comparison accepted the change: `pairwise_preferred_side = candidate`, `core_metric_delta = +0.22`, `guard_metric_delta = +0.12`
  - score deltas: `romance_tension 8.2 -> 8.7`, `relationship_progression 7.8 -> 8.5`, `hook 9.0 -> 9.25`, `redundancy 7.42 -> 7.78`
  - cost improved: `llm_calls 18 -> 17`, `duration_seconds 1639.99 -> 1308.28`
- Next step: run one cross-tone confirmation case (`case01` or `case03`) and then tune recurring `红痕 / 刻痕 / 发烫` imagery plus residual inner paraphrase without losing chemistry
- Report ref: `report.md` / `Iteration 25`

## Iteration 26

- Date: `2026-04-28`
- Outcome: `reject`
- Title: `Cross-tone validation rejects the action-first / banter candidate as branch default`
- Root layer: `cross_tone_draft_block_generalization_failure`
- Files changed: `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `tests/test_prompt_rendering.py` (experiment only; reverted after validation)
- Success snapshot:
  - `case02` positive signal remained valuable as isolated evidence
  - `case01_high_impact_once` repaired the worst redundancy collapse from `5.92 -> 7.20`, and lifted `emotional_resonance 8.0 -> 9.0`, `hook 9.0 -> 9.5` versus the first failed `case01_action_first_guard`
  - but cross-tone comparison still rejected rollout: `pairwise_preferred_side = baseline`, `relationship_progression 9.0 -> 8.0`, `continuity 9.0 -> 8.0`, `redundancy 7.82 -> 7.20`
- Next step: split future fixes by tone family instead of forcing one broad prompt rule across `light_adventure_banter` and `restrained_angst`; likely add intrigue-specific clue-lifecycle control rather than another global anti-repeat line
- Report ref: `report.md` / `Iteration 26`

## Iteration 27

- Date: `2026-04-28`
- Outcome: `keep`
- Title: `Split style variance into one dedicated style-card layer while keeping the shared writer path unified`
- Root layer: `style_only_control_surface`
- Files changed: `src/novel_flow/services/style_cards.py`, `src/novel_flow/services/novel_context.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `tests/test_schema_and_context.py`
- Success snapshot:
  - removed the old one-size-fits-all fixed `style_card_text`
  - writer context now emits dynamic style cards by story direction
  - block prompts explicitly use `style_rules` as the isolated style layer while leaving other block inputs stable
  - tests confirm historical and xianxia contexts now receive different style cards and that style focus survives into block runtime payloads
- Next step: migrate the proven `case02` banter tactics and the preferred `case01` court-pressure tactics into this new style layer, then rerun one representative case per direction
- Report ref: `report.md` / `Iteration 27`

## Iteration 28

- Date: `2026-04-28`
- Outcome: `keep`
- Title: `Add mainstream romance category selection and backend-owned style matching for new-novel creation`
- Root layer: `style_category_entrypoint_and_ui_mapping`
- Files changed: `src/novel_flow/services/style_cards.py`, `src/novel_flow/server.py`, `tests/test_schema_and_context.py`, `tests/test_style_cards.py`
- Success snapshot:
  - added a unified romance category registry based on mainstream women-fiction site taxonomies
  - new-novel modal now exposes `小说类型` with automatic helper text and style placeholder updates
  - backend now persists `novel_type / novel_type_label / style_direction / effective_style_request`
  - style cards are now clean Chinese-maintainable text instead of mixed English + corrupted strings
  - local browser check confirmed the dropdown renders and updates correctly on selection
- Next step: move proven `case01` intrigue cues and `case02` banter cues into the new direction cards, then run representative direction-specific evals
- Report ref: `report.md` / `Iteration 28`

## Iteration 29

- Date: `2026-04-28`
- Outcome: `keep`
- Title: `Reorganize romance report artifacts into time / model / case archive paths`
- Root layer: `artifact_naming_and_archive_hygiene`
- Files changed: `tools/organize_romance_reports.py`, `evals/romance/reports/index.md`, `evals/romance/reports/catalog.json`, `evals/romance/README.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`, plus path rewrites inside moved report artifacts
- Success snapshot:
  - moved 18 cluttered root report directories into `reports/runs/YYYYMMDD/provider__model/case_bucket/label/`
  - moved `sample_iteration` into `reports/templates/sample_iteration/`
  - added machine-readable `catalog.json` and human-readable `index.md`
  - rerunning the organizer script now returns `moved_count = 0`, so the migration is idempotent
- Next step: optionally wire the same archive convention into future eval runners so fresh runs land in the structured tree directly
- Report ref: `report.md` / `Iteration 29`

## Iteration 30

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Archive live cross-tone summary snapshots into the structured runs tree`
- Root layer: `live_summary_snapshot_hygiene`
- Files changed: `tools/organize_romance_reports.py`, `evals/romance/reports/runs/20260428/chapter_eval_rollup/mixed__doubao-plus-deepseek/multi_case__3cases/cross_tone_smoke_prompt_beat_slim_mixed_provider/summary.json`, `evals/romance/reports/runs/20260428/chapter_eval_rollup/mixed__doubao-plus-deepseek/multi_case__3cases/cross_tone_smoke_prompt_beat_slim_mixed_provider/summary.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - removed the remaining cross-tone prompt/beat slim summary pair from `self_improve_live/`
  - archived them under `runs/20260428/mixed__doubao-plus-deepseek/multi_case__3cases/...`
  - upgraded the organizer script so future `*_summary.json` live snapshots with case bundles are auto-moved and companion markdown is renamed to `summary.md`
  - rerunning the organizer now returns `live_summary_move_count = 0`
- Next step: if more ad-hoc `implementation_summary` or `iteration_report` files accumulate under `self_improve_live`, decide whether they should stay as operator notes or get their own archive bucket
- Report ref: `report.md` / `Iteration 30`

## Iteration 31

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Move one-off operator summaries out of the live root into self_improve_live/notes`
- Root layer: `live_note_bucket_cleanup`
- Files changed: `evals/romance/reports/self_improve_live/notes/20260428_implementation_summary.md`, `evals/romance/reports/self_improve_live/notes/20260428_iteration_report.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - moved the two ad-hoc explanation files out of the live root
  - kept `self_improve_live/` root focused on the canonical live pair: `report.md` and `iteration_log.md`
  - preserved the note content without misclassifying it as a run artifact
- Next step: send any future one-off operator notes under `self_improve_live/notes/` by default
- Report ref: `report.md` / `Iteration 31`

## Iteration 32

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Promote Step8 into a contract layer and rename the active writer path around chapter contracts and beats`
- Root layer: `chapter_contract_and_beat_semantics`
- Files changed: `src/novel_flow/models/schemas.py`, `src/novel_flow/models/__init__.py`, `src/novel_flow/tools/plan_content_blocks.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/services/novel_context.py`, `src/novel_flow/services/review_aggregator.py`, `src/novel_flow/agents/writer.py`, `src/novel_flow/agents/writing_chapter_agent.py`, `prompts/writer/step_8_chapter_briefs.txt`, `prompts/writer/plan_content_blocks.txt`, `prompts/writer/draft_content_block.txt`, `prompts/writer/review_block_quality.txt`, `prompts/writer/context_sanitization.txt`, `prompts/writer/review_chapter_engine.txt`, `prompts/writer/plan_review_tools.txt`, `prompts/writer/review_instruction_compliance.txt`, `prompts/writer/review_structure_and_continuity.txt`, `prompts/writer/rewrite_by_plan.txt`, `prompts/writer/make_scene_plan.txt`, `prompts/writer/summarize_actual_chapter.txt`, `prompts/critic/check_chapter_engine.txt`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`, `tests/test_romance_eval_harness.py`, `tests/test_eval_case_exporter.py`
- Success snapshot:
  - Step8 now carries explicit contract fields: `cost_of_progress / hook_kind / pace_curve / must_not_repeat`
  - the active planning and drafting path now speaks in `chapter contract / chapter beat` language instead of mixing new semantics with old labels
  - contract alias properties let downstream layers share one meaning without breaking stored `chapter_briefs` / `content_blocks` payload shapes
  - prompt encoding check passed and both the targeted writer tests and AGENTS minimum verification passed
- Next step: replay one requirement case on top of the new contract/beat chain and measure whether the sharper Step8 contract reduces repeated beat purpose and improves prose discipline
- Report ref: `report.md` / `Iteration 32`

## Iteration 33

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Add a planner-only beat-plan eval so Step8 and plan_content_blocks can be judged before prose generation`
- Root layer: `upstream_planner_observability`
- Files changed: `evals/romance/beat_plan_eval.py`, `evals/romance/runners/beat_plan_eval.py`, `tests/test_beat_plan_eval.py`
- Success snapshot:
  - new low-cost runner builds real writer context, executes the real `plan_content_blocks`, and scores the resulting beat plan without drafting prose
  - beat-plan metrics now directly surface overlap, weak contract coverage, and muddy progression before full chapter cost
  - overlap alerts identify the exact beat pairs and fields that collide
- Next step: run this planner-only eval on the current contract/beat chain first whenever the target is Step8 or planner quality, then only escalate to prose replay if the beat plan clears
- Report ref: `report.md` / `Iteration 33`

## Iteration 34

- Date: `2026-04-29`
- Outcome: `reject_for_default_promotion`
- Title: `Run the full Step8 -> beat plan -> prose validation on case01 for the new contract chain`
- Root layer: `contract_to_prose_validation`
- Files changed: `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - static Step8 eval on `romance_case_01_court_return` returned `warn` with `average_score = 6.97`
  - new beat-plan eval on the same case returned `pass` with `average_score = 9.14`
  - full prose replay landed at `evals/romance/reports/runs/20260428/chapter_eval/deepseek__deepseek-v4-pro/romance_case_01_court_return/step8_contract_case01_prose/summary.json`
  - compared with `sequential_beat_case01_deepseek`, prose regressed on the main romance metrics:
    - `romance_tension_score 9.2 -> 6.5`
    - `relationship_progression_score 9.0 -> 8.0`
    - `emotional_resonance_score 9.1 -> 8.5`
    - `character_attraction_score 9.18 -> 8.25`
    - `hook_score 9.65 -> 9.25`
    - `redundancy_score 8.62 -> 7.42`
    - `continuity_score` held at `9.0`
- Next step: keep the contract/beat observability foundation, but optimize the `draft_block` execution layer so the sharper contract does not collapse into clue-procedure and investigation prose at the expense of romance tension
- Report ref: `report.md` / `Iteration 34`

## Iteration 35

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Lock in the chapter-length interpretation after the case01 prose replay`
- Root layer: `evaluation_interpretation_guardrail`
- Files changed: `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - recorded that the `~5.6k` candidate chapter length is closer to the intended steady-state target than the old `~12.1k` baseline
  - explicitly documented that the regression is about budget allocation, not insufficient total length
  - set the next-pass rule to keep chapter length roughly in the `4.5k - 6k` range while shifting budget from clue procedure into romance pressure
- Next step: optimize `draft_block` under the shorter target length instead of letting future iterations expand chapter size to recover lost scores
- Report ref: `report.md` / `Iteration 35`

## Iteration 36

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Research five current hot ancient-romance chapter ones and benchmark our case01 prose against them`
- Root layer: `external_market_research_and_prose_diagnosis`
- Files changed: `evals/romance/reports/market_research/20260429_hot_ancient_openings_vs_case01.md`, `evals/romance/reports/market_research/20260429_hot_ancient_openings_vs_case01.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - verified that the user complaint about excessive `他……` / `她……` openings is correct
  - measured `pronoun_sentence_open_ratio = 25.69%` on the latest candidate vs `5.70%` sample average across five hot ancient-romance openings
  - confirmed the issue already existed in the old baseline (`26.05%`), so the root belongs to the shared `draft_block` prose execution layer
  - confirmed that the current eval verdict is directionally reasonable: the prose is strong on hook and pressure, but weak on relationship heat and heroine voice compared with the market samples
- Next step: optimize `draft_block` around sentence-open variation, action-first revelation, and stricter procedure-budget control instead of reworking Step8 first
- Report ref: `report.md` / `Iteration 36`

## Iteration 37

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Create a reusable positive-example corpus folder instead of leaving market research as one-off reports`
- Root layer: `reference_corpus_infrastructure`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/positive_examples/ancient_openings/*/notes.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - created a stable positive-example corpus root under `evals/romance/positive_examples/`
  - recorded five hot ancient-romance opening cards with links, short excerpts, tags, opening patterns, and what-to-learn notes
  - explicitly kept full copyrighted chapter text out of the repo while preserving reusable analytical value
- Next step: use the positive-example corpus directly when tuning `draft_block` for sentence openings, heroine voice, and action-carried revelation
- Report ref: `report.md` / `Iteration 37`

## Iteration 38

- Date: `2026-04-29`
- Outcome: `keep`
- Title: `Add authorized-fulltext slots to the positive-example corpus without storing scraped commercial full chapters`
- Root layer: `reference_corpus_fulltext_boundary`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/licensed_texts/README.md`, `evals/romance/positive_examples/licensed_texts/*/README.md`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - created a stable `licensed_texts/` subtree for future high-fidelity comparison
  - recorded the per-sample `authorized_text_slot` in each positive-example card
  - kept the repo ready for word-level analysis without committing scraped full commercial chapters
- Next step: if the user provides authorized full text, place it in the prepared slot and use it for finer-grained wording analysis
- Report ref: `report.md` / `Iteration 38`

## Iteration 39

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Remove the empty licensed_texts subtree and collapse the positive-example corpus back to sample cards only`
- Root layer: `reference_corpus_simplification`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - deleted the unused `licensed_texts/` subtree
  - removed the per-sample `authorized_text_slot` references
  - kept the positive-example corpus lean and focused on reusable sample cards only
- Next step: keep using the sample-card corpus until there is a concrete, content-backed need for a separate fulltext ingestion flow
- Report ref: `report.md` / `Iteration 39`

## Iteration 40

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Analyze five high-visibility Fanqie ancient-romance chapter ones and extract opening-level writing lessons`
- Root layer: `market_opening_reference_expansion`
- Files changed: `evals/romance/reports/market_research/20260430_fanqie_hot5_openings_deep_dive.md`, `evals/romance/reports/market_research/20260430_fanqie_hot5_openings_deep_dive.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - documented the opening shape, hook type, and reusable techniques for five current high-visibility Fanqie ancient-romance samples
  - confirmed again that hot openings rely on fast cut-ins, heroine voice, and concrete situation hooks more than on mechanism-heavy exposition
  - strengthened the diagnosis that our next prose gains should come from `draft_block`, not more Step8 complexity
- Next step: use the Fanqie opening analysis together with the earlier positive-example corpus when tightening first-beat heroine voice and hook delivery
- Report ref: `report.md` / `Iteration 40`

## Iteration 41

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Promote the Fanqie hot-opening research into reusable per-novel positive-example cards`
- Root layer: `reference_corpus_structuring`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/fanqie_openings/*/entry.json`, `evals/romance/positive_examples/fanqie_openings/*/notes.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - added a second positive-example collection for five high-visibility Fanqie ancient-romance chapter ones
  - expanded each sample into its own folder with detailed hook / technique / lesson notes
  - kept the corpus within the non-fulltext policy while making it much easier to reuse during future prose optimization
- Next step: use these per-novel cards when tightening heroine voice, first-beat cut-ins, and anti-explanation rules in `draft_block`
- Report ref: `report.md` / `Iteration 41`

## Iteration 42

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Deepen all ten positive-example cards with chapter-one story summaries and narrative-rhythm analysis`
- Root layer: `reference_corpus_depth_upgrade`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/positive_examples/ancient_openings/*/notes.md`, `evals/romance/positive_examples/fanqie_openings/*/entry.json`, `evals/romance/positive_examples/fanqie_openings/*/notes.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - added chapter-one story summaries, opening-flow beats, narrative-rhythm notes, retention mechanics, and strong-point analysis to all ten reference samples
  - upgraded the corpus from light sample cards into reusable opening-study references
  - made it much easier to compare our first-beat and first-chapter prose choices against concrete market examples
- Next step: use the new rhythm / retention fields when rewriting `draft_block`, especially for heroine-first cut-ins and anti-explanation pacing
- Report ref: `report.md` / `Iteration 42`

## Iteration 43

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Merge the two ancient-romance positive-example folders into one unified corpus directory`
- Root layer: `reference_corpus_consolidation`
- Files changed: `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - moved the five Fanqie samples under the same `ancient_openings/` directory as the five existing Xiaoxiang samples
  - simplified the corpus so all ten ancient-romance opening references now live in one folder
  - removed the need to remember two sibling directories for the same subject area
- Next step: let the user paste any legally usable text directly into the unified ancient-opening corpus without worrying about platform split
- Report ref: `report.md` / `Iteration 43`

## Iteration 44

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Replace the old ancient-opening cards with a local fulltext ten-book EPUB corpus`
- Root layer: `reference_corpus_rebuild`
- Files changed: `tools/rebuild_local_ancient_openings.py`, `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/ancient_openings/*/chapter1.txt`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/positive_examples/ancient_openings/*/notes.md`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - replaced the previous public-link-based reference cards with ten local EPUB-based ancient-romance chapter-one samples
  - stored `chapter1.txt` for all ten samples, alongside structured metadata and much deeper first-chapter analysis
  - established a reusable rebuild script so the corpus can be regenerated from future local EPUB sets without manual folder-by-folder editing
- Next step: derive reusable opening-rhythm templates and anti-`他/她...` heuristics from this fulltext corpus before the next `draft_block` iteration
- Report ref: `report.md` / `Iteration 44`

## Iteration 45

- Date: `2026-04-30`
- Outcome: `keep`
- Title: `Replace the ten-book EPUB corpus with a curated five-book local TXT three-chapter corpus`
- Root layer: `reference_corpus_rebuild`
- Files changed: `tools/rebuild_local_ancient_openings.py`, `evals/romance/positive_examples/README.md`, `evals/romance/positive_examples/index.json`, `evals/romance/positive_examples/ancient_openings/*/chapter1.txt`, `evals/romance/positive_examples/ancient_openings/*/chapter2.txt`, `evals/romance/positive_examples/ancient_openings/*/chapter3.txt`, `evals/romance/positive_examples/ancient_openings/*/entry.json`, `evals/romance/positive_examples/ancient_openings/*/notes.md`, `evals/romance/reports/market_research/20260430_local_selected_ancient_three_chapters_deep_dive.md`, `evals/romance/reports/market_research/20260430_local_selected_ancient_three_chapters_deep_dive.json`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - removed the prior ten active sample folders and rebuilt `ancient_openings/` from the user’s higher-quality `我的筛选` TXT set
  - expanded preservation from one chapter to three chapters per sample, so each reference now stores `chapter1-3.txt`
  - upgraded every sample card into a detailed three-chapter拆书分析，covering per-chapter story summaries, progression, rhythm, retention, information-release, and standout lines
  - added a fresh aggregate report specifically for these five curated samples
- Next step: convert this corpus into reusable templates for chapter-one pressure choice, chapter-two conflict locking, and chapter-three escalation before the next prose iteration
- Report ref: `report.md` / `Iteration 45`

## Iteration 46

- Date: `2026-04-30`
- Outcome: `partial_keep`
- Title: `Add beat-boundary execution guards and fast-patch structural stop to stabilize the contract+beat prose path`
- Root layer: `draft_execution_layer`
- Files changed: `src/novel_flow/agents/writing_chapter_agent.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/tools/draft_block.py`, `src/novel_flow/tools/revise_block.py`, `prompts/writer/draft_content_block.txt`, `prompts/writer/revise_content_block.txt`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - fixed the immediate structural failure mode in the current `contract + beat` chain by adding:
    - explicit future-beat boundary context
    - a local beat trim pass when a draft overruns its target ceiling
    - a fast-mode stop when the patch plan requests unsupported beat deletion or reordering
  - improved the broken `case01` contract run from:
    - `romance_tension 6.5`
    - `continuity 3.5`
    - `redundancy 2.0`
    - `mind_state_consistency 6.5`
    to:
    - `romance_tension 7.8`
    - `continuity 8.5`
    - `redundancy 8.44`
    - `mind_state_consistency 9.0`
  - confirmed that the repaired run is still below the strongest earlier `sequential_beat_case01_deepseek` prose baseline, so this is an execution keep but not a new best-default prose keep
- Next step: keep the new execution guards, then continue in `draft_execution_layer` by restoring hotter body-detail tension and relationship electricity inside the same `4.5k-6k` budget
- Report ref: `report.md` / `Iteration 46`

## Iteration 47

- Date: `2026-04-30`
- Outcome: `partial_keep`
- Title: `Cut low-ROI deep prose steps, parallelize beat candidates, and add layered validation`
- Root layer: `draft_execution_layer`
- Files changed: `src/novel_flow/agents/writing_chapter_agent.py`, `evals/romance/runners/layered_validation_eval.py`, `tests/test_writing_chapter_agent.py`, `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`
- Success snapshot:
  - confirmed the six-upgrades deep replay had mixed effect instead of a clean default win:
    - upstream / planner signal was real
    - `case02` passed
    - but `case01` remained blocked and `case03` failed before prose with `Invalid argument`
  - identified the main cost sink from the existing deep replay:
    - `draft_block=8`
    - `revise_block_if_needed=8`
    - `review_block_quality=4`
    - `review_character_integrity=4`
    - `review_reveal_leak=4`
    - `review_time_consistency=4`
  - kept the useful parts:
    - multi-candidate drafting
    - prose-surface selection
    - revision brief
  - removed / reduced the weak-ROI parts:
    - deep block reviews now collapse to `review_block_quality` only
    - block review runs only when surface signals are weak enough to justify it
    - surface-triggered revise is now stricter instead of defaulting too often
  - added safe generation parallelism:
    - same-beat candidate drafts now run in parallel, which is the highest-value parallel unit that does not break sequential beat dependency
  - added a new layered validation runner:
    - `step static -> beat plan -> bounded fast prose -> bounded deep prose`
    - fast/deep escalation now defaults to a tiny bounded subset instead of all-case deep replay first
- Next step: use the leaner deep path to rerun a bounded prose validation, then decide whether the remaining gap is mainly “voice/temperature” or still “relationship-cost execution”
- Report ref: `report.md` / `Iteration 47`
