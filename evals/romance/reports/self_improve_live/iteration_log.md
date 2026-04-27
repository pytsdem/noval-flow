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
- Files changed: `evals/romance/reports/self_improve_live/report.md`, `evals/romance/reports/self_improve_live/iteration_log.md`, `evals/romance/reports/candidate_beat_card_case01_clean/*`
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
- Files changed: `prompts/writer/write_chapter_full.txt`, `tests/test_writing_chapter_agent.py`（实验后未保留），以及 `evals/romance/reports/candidate_agency_microaction_case01/*`
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
- Files changed: `src/novel_flow/config.py`, `src/novel_flow/llm/factory.py`, `.env.example`, `README.md`, `tests/test_llm_factory.py`（保留）；以及 `src/novel_flow/models/schemas.py`, `src/novel_flow/services/chapter_tool_payloads.py`, `src/novel_flow/tools/plan_content_blocks.py`, `prompts/writer/plan_content_blocks.txt`, `prompts/writer/write_chapter_full.txt`, `tests/test_schema_and_context.py`, `tests/test_writing_chapter_agent.py`（实验后未保留），并新增 `evals/romance/reports/candidate_beat_card_initiative_case01/*`
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
- Files changed: `src/novel_flow/config.py`, `src/novel_flow/llm/factory.py`, `src/novel_flow/server.py`, `evals/romance/harness.py`, `.env.example`, `README.md`, `tests/test_llm_factory.py`, plus `evals/romance/reports/deepseek_v4_pro_case01_candidate/*`
- Success snapshot:
  - repo defaults, `codex` fallback priority, UI model dropdown, and eval model naming all now point to `DeepSeek V4-Pro`
  - direct UI fetch confirmed the page now exposes `DeepSeek V4-Pro` as the default model option
  - current `DeepSeek V4-Pro` candidate improved `hook_score` to `9.25` and reduced `llm_calls` / `patch_rounds`, but still lost to the clean beat-card baseline on pairwise preference and core romance metrics
- Next step: keep the `DeepSeek` switch, but move the next optimization target to post-draft / pre-polish execution rather than adding more planner or full-chapter relationship guidance
- Report ref: `report.md` / `Iteration 18`
