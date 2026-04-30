# 正例库说明

这个目录用于维护**可复用的小说正例样本卡**，服务于小说生成框架的分析、对照和优化。

## 当前策略

当前这套古言正例库，**允许保存前三章原文**，前提是文本来自用户本地提供的 `TXT` 资源，而不是从线上站点抓取。

这里保存的是：

- 前三章原文：
  - `chapter1.txt`
  - `chapter2.txt`
  - `chapter3.txt`
- 结构化样本卡：`entry.json`
- 深度分析：`notes.md`

## 目录结构

```text
positive_examples/
  README.md
  index.json
  ancient_openings/
    <example_id>/
      chapter1.txt
      chapter2.txt
      chapter3.txt
      entry.json
      notes.md
```

## 字段约定

`entry.json` 建议包含：

- `id`
- `title`
- `author`
- `platform`
- `source_type`
- `source_txt_filename`
- `chapters_preserved`
- `chapter_titles`
- `chapter_lengths_chars`
- `chapters_1_3_total_length_chars`
- `tags`
- `opening_pattern`
- `voice_signature`
- `pressure_source`
- `chapter_summaries`
- `chapters_one_to_three_story_summary`
- `story_opening_flow`
- `narrative_rhythm`
- `character_and_relationship_setup`
- `information_release_design`
- `retention_mechanics`
- `strong_points`
- `standout_lines`
- `techniques`
- `what_to_learn`
- `avoid_copying`
- `analysis_basis`
- `raw_text_status`

## 使用原则

1. 用它学习**前三章**是如何铺人物、立关系、埋主线、控节奏的。
2. 优先提炼“为什么能留住人”，而不是只摘抄“这一句写得真好”。
3. 如果引用样本里的句法或切入方式，先确认你学的是它的压力结构、信息顺序和留人机制，而不是只学表皮词汇。
4. 如果后续替换样本，请同步更新 `index.json` 与样本卡，不要留下过期条目。

## 当前内容

当前已收录：

- `古代言情前三章正例` 共 `5` 例
- 全部来自用户本地 `TXT` 资源（我的筛选）
- 每例均包含：
  - `chapter1.txt`
  - `chapter2.txt`
  - `chapter3.txt`
  - `entry.json`
  - `notes.md`
