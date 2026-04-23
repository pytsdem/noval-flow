# Novel Self-Improve Live Report

## 当前状态

- 启动时间：2026-04-23
- 执行模式：持续自优化，单轮只处理一个主假设
- 当前可用评测 provider：`doubao`
- 当前终端里的 `codex exec` 会返回 `Access denied`，因此后续评测与诊断命令应显式使用 `LLM_PROVIDER=doubao`
- 参考基线：`evals/romance/reports/baseline/summary.json`
- 当前可运行 smoke：`evals/romance/reports/smoke_doubao_case01/summary.json`

## 迭代记录规范

每次迭代必须补全以下信息：

- 主假设：本轮只优化一个根因层
- 改动文件：明确列出真实变更文件
- 验证：记录运行过的命令、报告路径和是否通过
- 收益：写清楚分数变化、覆盖率变化、成本变化或可观测性收益
- 结论：`keep` / `reject`
- 下一步：如果拒绝，写下下一个假设；如果保留，写下下一轮目标

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
