# Romance Eval Harness

`evals/romance` 提供一套面向“中文言情小说章节生成”的专项评测框架，重点观察关系拉扯、情绪余波、章节钩子、角色魅力、连贯性、重复铺陈和角色心智一致性。

## 运行

```bash
python -m evals.romance.run_romance_evals --label baseline
```

常用参数：

- `--mode fast|deep`：切换 `WritingChapterAgent` 模式
- `--cases romance_case_01_court_return romance_case_02_sickbed_truce`：只跑指定 case
- `--reports-root evals/romance/reports`：指定报告输出目录
- `--compare-to evals/romance/reports/baseline/summary.json`：与已有 baseline 生成 diff

## 报告结构

每次运行都会在 `evals/romance/reports/<label>/` 下生成：

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
