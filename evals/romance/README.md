# Romance Eval Harness

`evals/romance` 提供一套面向“中文言情小说章节生成”的专项评测框架，重点观察关系拉扯、情绪余波、章节钩子、角色魅力、连贯性、重复铺陈和角色心智一致性。

## 运行

```bash
python -m evals.romance.runners.chapter_quality_eval --label baseline
```

常用参数：

- `--mode fast|deep`：切换 `WritingChapterAgent` 模式
- `--cases romance_case_01_court_return`：只跑指定 case
- `--suite evals/romance/suites/romance_cross_tone_smoke.yml`：跑 01 历史锚点 + 新 02/03 泛化 smoke suite
- `--reports-root evals/romance/reports`：指定报告输出目录
- `--compare-to evals/romance/reports/runs/20260422/codex__gpt-5.2/multi_case__3cases/baseline/summary.json`：与已有 baseline 生成 diff

## 报告结构

历史归档后的产物统一放在 `evals/romance/reports/runs/YYYYMMDD/provider__model/case_bucket/<label>/` 下。旧产物如果需要重新整理，可运行：

```powershell
python -X utf8 tools/organize_romance_reports.py
```

新的评测运行如果暂时还没有接入结构化路径 helper，仍可能先落在 `evals/romance/reports/<label>/`；整理脚本会把它们迁入统一归档结构。

单次运行目录内会生成：

- `summary.json`：聚合结果与每个 case 的专项分数
- `report.md`：便于人工查看的 markdown 报告
- `<case_id>/case_input.json`：固定 case 输入
- `<case_id>/writer_context.json`：写作前上下文包
- `<case_id>/chapter_execution.json`：章节执行结果，包含中间产物
- `<case_id>/stage_log.json`：阶段日志
- `<case_id>/final_text.txt`：最终正文
- `<case_id>/judge.json`：romance judge 原始结果
- `<case_id>/result.json`：该 case 的汇总评测结果

如果带 `--compare-to`，同目录还会生成：

- `diff_vs_<baseline>.json`
- `diff_vs_<baseline>.md`

## 新增 Case

1. 在 `evals/romance/cases/` 下新增一个 UTF-8 JSON 文件。
2. 结构使用 `RomanceEvalCase`：
   - `premise`
   - `chapter_brief`
   - `twist_designs`
   - `story_lines`
   - `character_cards`
   - `actual_chapter_summaries`
   - `prior_character_mindsets`（可选）
   - `goals`
   - `context_overrides`（可选）
3. `goals` 里至少写清：
   - `chapter_goal`
   - `emotional_goal`
   - `relationship_goal`
4. 如果该 case 需要更稳定的章节输入，可以在 `context_overrides` 里显式锁定：
   - `previous_chapter_full_text`
   - `writing_requirements`
   - `scene_character_context_text`
   - `relationship_state_text`

## Active Cases

- `evals/romance/cases/romance_case_01_court_return.json`：历史锚点 requirement case，可 seed 到 `test_self_improve_court_return`。
- `evals/romance/cases/romance_case_02_xianxia_rival_trial.json`：仙侠奇幻 + 轻松冒险 smoke case。
- `evals/romance/cases/romance_case_03_urban_reunion_comedy.json`：都市现代 + 旧情复燃 smoke case。
- 旧 02/03 requirement cases 已移到 `evals/romance/cases_legacy/`，默认 active eval 不再加载。

## Step1-8 Static Eval

用于评估离线 Step1-8 规划资产是否足够支撑后续正文生成：premise、story_engine、characters、timeline、milestones、twists、story_lines、chapter_briefs。

本仓也提供 3 个 active case 的离线 Step1-8 fixture：

- `evals/romance/cases/romance_case_01_court_return/steps.json`
- `evals/romance/cases/romance_case_02_xianxia_rival_trial/steps.json`
- `evals/romance/cases/romance_case_03_urban_reunion_comedy/steps.json`

这些 fixture 不是 LLM 任务生成结果，而是静态基准材料：Step8 可读取 `step_1` 到 `step_7` 作为上下文、读取 `step_8.chapter_briefs` 作为候选输出；Step6 可读取 `step_1` 到 `step_5` 作为上下文、读取 `step_6.twist_designs` 作为候选输出。

目录约定：`evals/romance/cases/*.json` 是现有 eval 会加载的 case 配置；`evals/romance/cases/<case_id>/steps.json` 是同一 case 的 Step1-8 离线资产，不会被 requirement case loader 误加载。

```bash
PYTHONPATH=src python3 -m evals.romance.runners.step_plan_static_eval \
  --cases-dir evals/romance/cases \
  --label step_plan_cross_tone_smoke
```

也可以只跑指定 case：

```bash
PYTHONPATH=src python3 -m evals.romance.runners.step_plan_static_eval \
  --cases-dir evals/romance/cases \
  --case-ids romance_case_01_court_return \
  --label step_plan_case01
```

## Long Arc Step8 Eval

用于评估几十章 `chapter_briefs` 是否像一条高级连载故事线，而不是只看前三章是否有钩子。它不评正文，只评 Step8 章节链：主旨对齐、类型/情绪稳定、上章尾钩到下章承接、升级曲线、角色发展线、反转埋线兑现、明暗线交织、追读检查点、信息预算和重复平台期。

只评已有 fixture：

```bash
PYTHONPATH=src python3 -m evals.romance.runners.long_arc_step8_eval \
  --cases-dir evals/romance/cases \
  --label long_arc_step8_static
```

用 step1-7 连续生成 30 章 Step8，再评长线质量：

```bash
PYTHONPATH=src python3 -m evals.romance.runners.long_arc_step8_eval \
  --cases-dir evals/romance/cases \
  --case-ids romance_case_01_court_return \
  --label long_arc_step8_case01_30ch \
  --generate \
  --target-chapters 30 \
  --batch-size 2 \
  --llm-provider deepseek
```

## 如何据此继续优化框架

建议看这几层：

1. 先看 `summary.json` 的平均分变化，确定主升降项。
2. 再看 `report.md` 和各 case `judge.json`，确认问题是否集中在：
   - `hook_score`
   - `relationship_progression_score`
   - `romance_tension_score`
   - `redundancy_score`
3. 如果分数下降但成本变低，去看 `stage_log.json` 与 `tool_calls_by_name`，确认是不是 review/patch 太弱。
4. 如果 `mind_state_consistency_score` 低，先查：
   - `build_character_mindset`
   - `write_chapter_full`
   - `rewrite_blocks_by_plan`
5. 如果 `hook_score` 或 `relationship_progression_score` 低，优先改：
   - `plan_content_blocks`
   - 章节级 review prompt
   - patch planner / patch writer
