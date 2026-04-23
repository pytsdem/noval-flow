# Novel Self-Improve Live Report

## 当前状态

- 启动时间：2026-04-23
- 执行模式：持续自优化，单轮只处理一个主假设
- 评测策略：单点评测优先，仅在单点证据足够强时才做完整端到端
- 当前可用评测 provider：`doubao`
- 当前终端里的 `codex exec` 会返回 `Access denied`，因此后续评测与诊断命令应显式使用 `LLM_PROVIDER=doubao`
- 参考基线：`evals/romance/reports/baseline/summary.json`
- 当前可运行 smoke：`evals/romance/reports/smoke_doubao_case01/summary.json`

## 迭代记录规范

每次迭代必须补全以下信息：

- 主假设：本轮只优化一个根因层
- 改动文件：明确列出真实变更文件
- 验证：优先记录单点评测命令、报告路径和是否通过；只有必要时才追加完整端到端
- 收益：写清楚分数变化、覆盖率变化、成本变化或可观测性收益
- 结论：`keep` / `reject`
- 下一步：如果拒绝，写下下一个假设；如果保留，写下下一轮目标

## 执行策略调整

- 默认不跑完整 `run_romance_evals` 全案回放，除非：
  - 单点评测已经明确指向某个根因层
  - 该改动必须通过章节生成结果才能验证
  - 或准备做最终 keep / reject 判定
- 默认优先使用这些单点评测：
  - `python -m evals.romance.run_step_evals`
  - `python -m evals.romance.run_workflow_diagnostics`
  - 单 case artifact 检查：`writer_context.json` / `chapter_execution.json` / `stage_log.json`
  - 相关单测与小范围 prompt / tool 级验证
- 若必须跑端到端，只跑：
  - 单个 case
  - 单个标签
  - 单个验证目标
  - 并在报告中写清楚为什么这一轮必须端到端

## Iteration 0 - 基础链路打通

- 主假设：当前自优化循环先被 provider 执行链路卡住；如果不先修通 LLM 调用与错误可见性，后面的评测与迭代会持续空转
- 改动文件：
  - `src/novel_flow/llm/codex_cli.py`
  - `tests/test_codex_cli_client.py`
- 已做改动：
  - 把 `codex exec` 的最后消息输出文件改为落在仓库 `data/` 下，避免系统临时目录不可见导致的问题
  - 为 `Broken pipe` / 空输出补充 stderr 透传，避免只看到模糊的 `[Errno 32] Broken pipe`
  - 增加对调试预览输出的容错，避免 Windows 控制台编码异常把错误进一步吞掉
  - 新增回归测试，覆盖 `Broken pipe` 错误透传和“非零退出但有输出文件”的读取路径
- 验证：
  - `python -m py_compile src/novel_flow/llm/codex_cli.py tests/test_codex_cli_client.py`
  - `python -m unittest tests.test_codex_cli_client tests.test_novel_self_improve_skill`
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_01_court_return --label smoke_doubao_case01`
- 收益：
  - 之前的评测失败只暴露 `Broken pipe`，现在能明确看到 `codex exec returned empty output. stderr: ... Access denied`
  - 在显式切换到 `doubao` 后，requirement case `romance_case_01_court_return` 已完整跑通生成、judge 和报告落盘
  - `smoke_doubao_case01` 当前均分：
    - `romance_tension_score`: 8.5
    - `relationship_progression_score`: 8.0
    - `emotional_resonance_score`: 8.2
    - `character_attraction_score`: 8.25
    - `hook_score`: 8.3
    - `continuity_score`: 8.8
    - `redundancy_score`: 9.0
    - `mind_state_consistency_score`: 8.7
- 结论：`keep`
- 剩余风险：
  - 当前终端环境下 `codex` provider 仍不可直接用，后续自动化必须固定 `doubao`
  - 目前只确认了 requirement case 01 的完整运行链路，case 02 / case 03 还需要继续跑
- 下一步：
  - 先补齐三个 requirement case 的可运行基线
  - 优先确认 `romance_case_03_betrothal_banquet` 的失败是否已因 provider 切换而消失
  - 如果三案都能跑，再按 `novel_self_improve` 流程选一个单一根因层进入第一轮质量优化

## Iteration 1 - requirement case 03 可运行性确认

- 主假设：`romance_case_03_betrothal_banquet` 之前的失败主要来自 provider 执行链路异常；在显式固定 `LLM_PROVIDER=doubao` 后，这个 case 应能完整跑通
- 改动文件：
  - 无新增代码改动，本轮只做验证与基线补齐
- 验证：
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_03_betrothal_banquet --label smoke_doubao_case03`
- 收益：
  - `romance_case_03_betrothal_banquet` 已完整跑通生成、judge 和报告落盘，不再出现此前 `baseline` 中的 `Invalid argument` / provider 级失败
  - 新报告：`evals/romance/reports/smoke_doubao_case03/summary.json`
  - 当前均分：
    - `romance_tension_score`: 8.2
    - `relationship_progression_score`: 8.5
    - `emotional_resonance_score`: 8.3
    - `character_attraction_score`: 8.66
    - `hook_score`: 8.9
    - `continuity_score`: 8.7
    - `redundancy_score`: 8.44
    - `mind_state_consistency_score`: 9.0
  - 相比旧 `baseline` 的直接收益是 requirement case 覆盖率提升：case03 从“整案失败、无 case_result”变为“完整可评测”
- 结论：`keep`
- 观察到的下一层问题：
  - case03 虽然可运行，但当前 weakness 仍集中在“言情张力过度依附权谋事件、纯双人互动细节不足、女主主动性更多停留在想法层”
  - 这更像质量层问题，不再是基础设施问题
- 下一步：
  - 跑通 `romance_case_02_sickbed_truce`，补齐三个 requirement cases 的可运行基线
  - 三案可运行后，优先选择一个单一质量根因层进入第一轮真实优化，候选方向优先考虑“纯双人互动密度/言情拉扯兑现度”

## Iteration 2 - 调整为单点评测优先

- 主假设：当前完整端到端 `run_romance_evals` 成本过高，且 `romance_case_02_sickbed_truce` 受长文本生成超时影响；继续默认整案长跑会放大等待成本，降低迭代速度
- 改动文件：
  - `src/novel_flow/llm/doubao.py`
  - `tests/test_doubao_client.py`
  - `evals/romance/reports/self_improve_live/report.md`
- 已做改动：
  - 为 `DoubaoLLMClient` 增加更宽松的流式读超时与一次 `ReadTimeout` 重试
  - 增加对应回归测试，覆盖“超时后重试成功”和“重试预算耗尽后报错”
  - 明确把自优化执行策略改为“单点评测优先”
- 验证：
  - `python -m py_compile src/novel_flow/llm/doubao.py tests/test_doubao_client.py`
  - `python -m unittest tests.test_doubao_client`
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_02_sickbed_truce --label smoke_doubao_case02`
- 收益：
  - 已确认 `case02` 的主要阻塞不是业务逻辑，而是 `Doubao generation failed: The read operation timed out`
  - `smoke_doubao_case02` 当前可稳定落盘到 `writer_context.json`，说明阻塞点位于生成阶段而不是 case 解析或上下文构建阶段
  - 后续执行策略已切换为更适合当前项目节奏的单点评测优先，避免每轮都等待十几分钟以上
- 结论：`keep`
- 剩余风险：
  - `case02` 的真实端到端恢复还未完成，上一轮 retry 在用户中断前仍停留在生成阶段
  - 目前还没有做 `step_evals` / `workflow_diagnostics` 的小步验证补位
- 下一步：
  - 先对 requirement / historical case 跑 `run_step_evals` 与 `run_workflow_diagnostics`
  - 只在单点证据明确后，再选择一个最必要的单 case 端到端验证

## Iteration 3 - 修正历史回放 case 的状态与成本保真度

- 主假设：当前 historical exported cases 的主阻塞并不完全来自真实 writer 质量，而是 exporter 丢失了 `character_mind_states`，并把任何 `rewrite_iteration` 都误记成 `used_full_rewrite=true`；如果不先修正这些回放输入与成本标签，后续诊断会被假阻塞和假成本带偏。
- 改动文件：
  - `evals/romance/case_exporter.py`
  - `tests/test_eval_case_exporter.py`
- 已做改动：
  - 为历史 case exporter 增加保守回填：只有在真实持久化的 `character_mindsets` 缺失时，才从 `scene_character_context_text`、`relationship_state_text`、`step_3_character_packets_text`、角色卡与 chapter brief 中恢复最多 2 个 `character_mind_states`
  - 为推断得到的历史回放 mindset 增加 `export_note`，明确这不是原始 run 持久化结果，而是基于已保存上下文的兼容回填
  - 收紧回填字段质量，避免把 `fear/misbelief/surface_emotion` 之类字段回填成过于生硬的占位文本
  - 修正 `used_full_rewrite` 的判断口径：只有看到明确 `rewrite_by_plan` / full-rewrite 证据时才标记为 `true`，不再把所有 `rewrite_iteration_*` 都当成整章全量重写
  - 补充 exporter 回归测试，覆盖“缺失 persisted mindset 时的上下文回填”和“存在 rewrite iteration 但无 full-rewrite 证据时不误报”
- 验证：
  - `python -m py_compile evals/romance/case_exporter.py tests/test_eval_case_exporter.py`
  - `python -m unittest tests.test_eval_case_exporter`
  - `python -X utf8 -m tools.export_eval_cases --db data/novel_flow.db --output-dir evals/romance/exported_cases/latest --limit 10 --sample-mode low_score`
  - `python -X utf8 -m evals.romance.run_step_evals --cases evals/romance/exported_cases/latest --label latest_step_eval_mindstate_backfill`
  - `python -X utf8 -m evals.romance.run_workflow_diagnostics --cases evals/romance/exported_cases/latest --label latest_diagnostics_mindstate_backfill`
  - `python -X utf8 - <<py` 方式逐文件 `py_compile` `evals/romance/*.py` 与 `tools/*.py`（共 19 个文件）
  - `python -m unittest tests.test_eval_case_exporter tests.test_workflow_diagnostics tests.test_step_evals tests.test_case_comparison tests.test_novel_self_improve_skill tests.test_requirement_cases`
- 收益：
  - 历史低分样本里 `inputs.character_mind_states` 从 `0` 稳定恢复到 `2`
  - step gate 从 `pass=0 / warn=0 / blocked=10` 变为 `pass=0 / warn=10 / blocked=0`
  - 代表性 case `ch_001_run_5d719c523f` 的上游分数变化：
    - `relationship_state_quality_score`: `5.92 -> 7.06`
    - `mind_state_quality_score`: `5.54 -> 6.41`
  - historical diagnostics 的主根因迁移更接近真实业务问题：
    - `most_common_root_layers`: `state_modeling_layer -> draft_execution_layer`
    - `frequent_full_rewrite_cases`: `10 -> 0`
  - 成本口径收益：
    - 历史 exported cases 中误报的 `used_full_rewrite=true` 已清零，不再给后续 comparison / diagnostics 额外叠加虚假的 full-rewrite 成本惩罚
    - 本轮没有新增端到端 LLM 成本，全部收益来自本地导出、诊断和测试
- 结论：`keep`
- 剩余风险：
  - 当前 historical cases 虽然已不再被 state-modeling 假阻塞卡死，但 `mind_state_quality_score` 仍普遍停在 `warn`
  - 新的真实主根因已经收敛到 `draft_execution_layer`，低分项集中在 `relationship_progression_score`、`continuity_score`、`mind_state_consistency_score`
- 下一步：
  - 进入第一轮真正的 writer / rewrite 质量优化
  - 优先围绕 opening-pressure 类 case 的 `draft_execution_layer` 做单根因分析，聚焦 review 里反复出现的几类问题：重复 ending threat、线索预算溢出、chapter object 监控属性落地不足、relationship repricing 落不到具体动作

## Iteration 4 - reject：首稿+patch 宽约束 prompt 未换来稳定收益

- 主假设：
  - `draft_execution_layer` 的高频误伤来自“重复 ending threat、线索预算溢出、chapter object 落不到动作层、relationship repricing 落不到可观察行为”，如果把这些约束同时前置到首稿和 patch prompt，中高分 requirement case 也能进一步拉高 `emotional_resonance_score` 与 `hook_score`，且不会伤到连续性。
- 候选改动文件（已回退，不保留）：
  - `prompts/writer/write_chapter_full.txt`
  - `prompts/writer/rewrite_blocks_by_plan.txt`
  - `tests/test_prompt_rendering.py`
- 候选改动内容：
  - 给 `write_chapter_full` 增加“章节引擎硬约束”，显式限制 `ending_pull`、`allowed_clues`、`chapter_object`、`relationship_reprice`
  - 给 `rewrite_blocks_by_plan` 增加全章级约束，要求相邻 block 不重复 threat/clue beat，且把 chapter object / relationship reprice 落成可观察动作
  - 补充 prompt rendering 测试覆盖这些 guardrails
- 验证命令：
  - `python scripts/check_prompt_encoding.py`
  - `python -m unittest tests.test_prompt_rendering tests.test_writing_chapter_agent`
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_01_court_return --label candidate_prompt_guardrails_case01`
- 指标变化（对比 `smoke_doubao_case01`）：
  - `romance_tension_score`: `8.5 -> 8.2`
  - `relationship_progression_score`: `8.0 -> 8.0`
  - `emotional_resonance_score`: `8.2 -> 8.5`
  - `character_attraction_score`: `8.25 -> 8.17`
  - `hook_score`: `8.3 -> 8.5`
  - `continuity_score`: `8.8 -> 8.5`
  - `redundancy_score`: `9.0 -> 8.5`
  - `mind_state_consistency_score`: `8.7 -> 8.8`
- 成本变化：
  - 额外消耗 1 次 requirement case 真实端到端评测，`candidate_prompt_guardrails_case01` 用时约 `1244s`
  - 没有形成可保留收益，相关 throwaway report 目录将在收口时清理，不进入后续基线
- 结论：`reject`
- reject 原因：
  - 虽然 `emotional_resonance_score`、`hook_score`、`mind_state_consistency_score` 有小幅上升，但核心优先级更高的 `romance_tension_score`、`continuity_score`、`redundancy_score` 明显回撤
  - 问题说明这组 guardrail 过宽，连高分 baseline case 的首稿节奏也被一起压平了，不适合作为 repo 级默认行为
- 下一步：
  - 不再碰首稿大 prompt
  - 仅在 patch-plan / patch-rewrite 的最小归一化层做更窄的约束，优先减少“为低优先级重复问题扩写太多 block”的过修补倾向

## Iteration 5 - reject：直接裁掉低优先级 patch block 会伤到关系张力块

- 主假设：
  - `draft_execution_layer` 里真正的问题不是“patch 轮数太少”，而是 `build_chapter_patch_plan` 对 review issue 过度照单全收，导致低优先级润色问题也会把整章 5 个 block 一起拖进 rewrite；如果只保留高严重度连续性/规则问题，应该能在不伤 romance 的前提下降低过修补。
- 候选改动文件（已回退，不保留）：
  - `src/novel_flow/tools/build_chapter_patch_plan.py`
  - `tests/test_build_chapter_patch_plan.py`
- 候选改动内容：
  - 为 `build_chapter_patch_plan` 增加 review issue 优先级归一化
  - 高严重度连续性 / 礼制 / 线索泄露问题优先保留，纯低优先级润色 block 优先被裁掉
  - 对真实 `smoke_doubao_case01` artifact 做离线回放，patch target 从 `5 -> 4`，被裁掉的是只承载 `flat_emotion/repetitive_imagery` 的 `ch_012.sc_001.b002`
- 验证命令：
  - `python -m unittest tests.test_build_chapter_patch_plan tests.test_writing_chapter_agent`
  - 离线 artifact 回放：复用 `smoke_doubao_case01/romance_case_01_court_return/stage_log.json` 的 `patch_plan` 与 `review_reports`
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_01_court_return --label candidate_patch_scope_case01`
- 离线证据：
  - `before_target_ids`: `b001,b002,b003,b004,b005`
  - `after_target_ids`: `b001,b003,b004,b005`
  - `unchanged_blocks`: `b002`
- 指标变化（对比 `smoke_doubao_case01`）：
  - `romance_tension_score`: `8.5 -> 7.5`
  - `relationship_progression_score`: `8.0 -> 8.0`
  - `emotional_resonance_score`: `8.2 -> 8.2`
  - `character_attraction_score`: `8.25 -> 7.77`
  - `hook_score`: `8.3 -> 8.75`
  - `continuity_score`: `8.8 -> 9.0`
  - `redundancy_score`: `9.0 -> 8.0`
  - `mind_state_consistency_score`: `8.7 -> 8.8`
- 成本变化：
  - 额外消耗 1 次 requirement case 真实端到端评测，`candidate_patch_scope_case01` 用时约 `1117s`
- 结论：`reject`
- reject 原因：
  - `continuity_score` 和 `hook_score` 虽有提升，但更高优先级的 `romance_tension_score` 与 `character_attraction_score` 明显下滑
  - 说明 `b002` 这种表面看像“润色”的 block，实际承担了关系切口和言情兑现，不能被简单当作可删 patch target
- 下一步：
  - 不再直接删“flat_emotion 类 relationship block”
  - 改为只裁掉 line-level 的低价值重复润色指令，保住关系块本身

## Iteration 6 - reject：只裁低价值 line-level 指令仍未形成净收益

- 主假设：
  - `Iteration 5` 失败说明 block 级裁剪太粗；如果保留关键关系 block，但把 `repetitive_imagery` 这类低价值 line-level replacement instruction 裁掉，应该能减少 patch 抖动，同时保住 romance tension。
- 候选改动文件（已回退，不保留）：
  - `src/novel_flow/tools/build_chapter_patch_plan.py`
  - `tests/test_build_chapter_patch_plan.py`
- 候选改动内容：
  - 保留 `b001~b005` 全部 patch target，不再删除 `relationship_cut/clue_shift/ending` 等关键 block
  - 只裁掉与 `repetitive_imagery / repetition` 对应的低价值 line-level instruction
  - 真实 `case01` artifact 离线回放里，instruction counts 从 `3/2/3/2/2` 收窄到 `2/1/2/2/1`
- 验证命令：
  - `python -m unittest tests.test_build_chapter_patch_plan tests.test_writing_chapter_agent`
  - 离线 artifact 回放：复用 `smoke_doubao_case01/romance_case_01_court_return/stage_log.json`
  - `LLM_PROVIDER=doubao python -X utf8 -m evals.romance.run_romance_evals --cases-dir evals/romance/cases --cases romance_case_01_court_return --label candidate_patch_scope_case01_v2`
- 离线证据：
  - `before_target_ids`: `b001,b002,b003,b004,b005`
  - `after_target_ids`: `b001,b002,b003,b004,b005`
  - `before_instruction_counts`: `3/2/3/2/2`
  - `after_instruction_counts`: `2/1/2/2/1`
- 指标变化（对比 `smoke_doubao_case01`）：
  - `romance_tension_score`: `8.5 -> 8.5`
  - `relationship_progression_score`: `8.0 -> 8.0`
  - `emotional_resonance_score`: `8.2 -> 8.2`
  - `character_attraction_score`: `8.25 -> 8.03`
  - `hook_score`: `8.3 -> 8.75`
  - `continuity_score`: `8.8 -> 8.5`
  - `redundancy_score`: `9.0 -> 8.8`
  - `mind_state_consistency_score`: `8.7 -> 8.5`
- 成本变化：
  - 再额外消耗 1 次 requirement case 真实端到端评测，`candidate_patch_scope_case01_v2` 用时约 `1153s`
- 结论：`reject`
- reject 原因：
  - 虽然把 `romance_tension_score` 拉回 baseline，且 `hook_score` 继续提升，但 `continuity_score`、`redundancy_score`、`mind_state_consistency_score` 与 `character_attraction_score` 仍发生回撤
  - 中间 patch judge 还暴露出 residual duplicate / direct-thought 问题，说明这种“按问题标签裁 instruction”的方法太脆，容易和 LLM 已生成的 replacement 句式产生错位
- 下一步：
  - 当前证据已表明：`build_chapter_patch_plan` 的 tool-level 归一化不适合继续硬裁
  - 下一轮更合理的主目标应切到 `final_polish` / `rewrite_blocks_by_plan` 的去重与关系落点保真，而不是继续在 patch-plan 里做删除策略

## Iteration 7 - keep：补上 case 级加权 pairwise 比较，避免均分掩盖坏优化

- 主假设：
  - 当前 `run_case_comparison` 主要依赖平均分和 blocker/guard 阈值；这对“1 个 case 大涨、2 个 case 小幅变差”的候选不够敏感，容易把真实阅读体验更差的方案误看成“总体提升”。如果引入按 case 的加权 pairwise 偏好，就能更早挡住这类坏优化。
- 改动文件：
  - `evals/romance/comparison.py`
  - `tests/test_case_comparison.py`
- 已做改动：
  - 在 romance eval comparison 中新增 `pairwise_preference`：
    - 按项目优先级对 `romance_tension`、`relationship_progression`、`emotional_resonance`、`character_attraction`、`hook`、`continuity`、`mind_state_consistency`、`redundancy` 做 case 级加权比较
    - 为每个 case 产出 `preferred_side`、`weighted_margin`、`candidate_wins`、`baseline_wins`、`guard_failures`、`cost_flags`
    - 聚合得到 `overall_preferred_side`、`candidate_case_wins`、`baseline_case_wins`
  - 把 pairwise 结果接入 `decision`：
    - 当候选在 case 级 pairwise 上总体输给 baseline 时，即使平均核心分仍为正，也会拒绝保留
  - 更新 comparison markdown：
    - 报告里直接展示 pairwise 总结和每个 case 的偏好来源，便于后续 self-improve 复盘
  - 补充回归测试：
    - 覆盖普通提升 case 仍会被接受
    - 覆盖“平均核心分仍上升，但 3 个 case 里有 2 个更差”时会被 pairwise 拒绝
- 验证：
  - `python -m py_compile evals/romance/comparison.py tests/test_case_comparison.py`
  - `python -m unittest tests.test_case_comparison`
  - `python -X utf8 - <<py` 逐文件编译 `evals/romance/*.py` 与 `tools/*.py`（共 `19` 个文件）
  - `python -m unittest tests.test_eval_case_exporter tests.test_workflow_diagnostics tests.test_step_evals tests.test_case_comparison tests.test_novel_self_improve_skill tests.test_requirement_cases`
- 收益：
  - comparison 现在不再只给“均分涨没涨”，而是会额外给出“哪个方案在更多 case 上更优”
  - 新增的 pairwise 回归样例里：
    - 候选的平均核心分仍有正向提升：`core_metric_delta = +0.17`
    - 但 case 级偏好为：`candidate_case_wins = 1`、`baseline_case_wins = 2`
    - 最终 `overall_preferred_side = baseline`，并触发 `Pairwise case preference favored the baseline.`
  - 这正好补上了前两轮 reject 暴露出来的问题：像 `case01` 这种高优先级 romance 体验被伤到时，不会再被局部均分或单项 hook 提升掩盖
  - 本轮没有新增 LLM 调用与端到端生成成本，全部收益来自评测基础件增强
- 结论：`keep`
- 下一步：
  - 后续进入 `final_polish` / `rewrite_blocks_by_plan` 的真实质量优化时，优先用这套 pairwise 结果做 keep / reject 辅助判断
  - 下一轮更值得做的是补一个低成本 anti-slop / direct-thought 诊断，让“去重但不压平关系落点”的目标能在单点评测里更快被验证

## Iteration 8 - keep：新增 anti-slop / direct-thought 单点诊断，补齐 final polish 的低成本观测

- 主假设：
  - 目前 repo 能看见“重复”，但还不够稳定地看见“直白心理解释 / 机械性总结句”；这会让 `final_polish` 和 `rewrite_blocks_by_plan` 的优化仍然缺少单点证据。如果补一个规则型 anti-slop 信号，并把它挂到 workflow diagnostics 与 eval breakdown，就能在不跑端到端的情况下更快判断“是否真的在去解释化”。
- 改动文件：
  - `evals/romance/judges/rule_metrics.py`
  - `evals/romance/judges/__init__.py`
  - `evals/romance/harness.py`
  - `evals/romance/reporting.py`
  - `evals/romance/workflow_diagnostics.py`
  - `evals/romance/history_models.py`
  - `tests/test_rule_metrics.py`
  - `tests/test_romance_eval_harness.py`
  - `tests/test_workflow_diagnostics.py`
- 已做改动：
  - 新增 `AntiSlopRuleAnalyzer`
    - 命中 `她知道 / 他意识到 / 这让她更明白 / 这让她更清楚` 这类直白心理标签与解释性总结句
    - 同时吸收 review 报告里 `direct_thought / on_the_nose / 直白 / 解释 / 总结` 等信号
  - 把 anti-slop 接入 romance eval harness：
    - 新增 `rule_anti_slop_score` breakdown
    - `redundancy_score` 的 hybrid 现在会同时参考 `rule_redundancy_score` 和 `rule_anti_slop_score`，避免 judge 高估时把“坏重复/坏解释”放过去
    - 当 anti-slop 过低时，自动把“存在直白心理解释信号”补进 diagnosis
  - 把 anti-slop 接入 workflow diagnostics：
    - 为每个 case 新增 `diagnostic_signals.anti_slop_score`
    - aggregate 新增 `slop_hotspot_cases`
    - `draft_execution_layer` / `revision_layer` 会显式吃到 anti-slop 信号，让 root cause 更容易指向 `final_polish` / `patch` 层
  - 更新 report 渲染：
    - romance eval markdown 会显示 `rule_anti_slop_score`
    - workflow diagnostics markdown 会显示 per-case diagnostic signals 和全局 `slop_hotspot_cases`
- 验证：
  - `python -m py_compile evals/romance/judges/rule_metrics.py evals/romance/harness.py evals/romance/workflow_diagnostics.py evals/romance/reporting.py evals/romance/history_models.py tests/test_rule_metrics.py tests/test_romance_eval_harness.py tests/test_workflow_diagnostics.py`
  - `python -m unittest tests.test_rule_metrics tests.test_romance_eval_harness tests.test_workflow_diagnostics`
  - `python -X utf8 - <<py` 逐文件编译 `evals/romance/*.py` 与 `tools/*.py`（共 `19` 个文件）
  - `python -m unittest tests.test_eval_case_exporter tests.test_workflow_diagnostics tests.test_step_evals tests.test_case_comparison tests.test_novel_self_improve_skill tests.test_requirement_cases tests.test_romance_eval_harness tests.test_rule_metrics`
- 收益：
  - repo 现在可以单点识别“直白心理标签”和“解释性总结句”，不再只靠 redundancy 的高相似段落检测
  - workflow diagnostics 现在能直接标出 `slop_hotspot_cases`，更适合后续把 `final_polish` 当成单根因层来打
  - harness breakdown 新增 `rule_anti_slop_score` 后，full eval 报告也能看见“judge 觉得还行，但规则层看见了直白解释”这种错位
  - 新增规则单测里：
    - 明显 direct-thought 文本会被打到 `< 7.0`
    - 动作/潜台词主导文本会保持 `>= 8.0`
  - 本轮没有新增 LLM 生成成本，全部收益来自本地规则评测与诊断能力增强
- 结论：`keep`
- 下一步：
  - 下一轮优先进入 `final_polish` / `rewrite_blocks_by_plan` 的最小生成改动
  - 目标不是继续硬删 patch target，而是专打 `rule_anti_slop_score` 暴露出来的句式：删掉“她知道 / 他意识到 / 这让她更明白”类解释句，同时保住关系切口和双人拉扯
