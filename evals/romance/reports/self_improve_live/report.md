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
