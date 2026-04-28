# Novel Flow

Novel Flow 是一个面向中文长篇连载小说的多 Agent 写作工作台。它把“题材输入 -> 世界与人物规划 -> 单章正文 -> 评审修补 -> 记忆回写”拆成可编辑、可追踪、可复用的结构化流程。

核心目标：提升连载小说的张力、关系推进、情绪共鸣、开章钩子、角色吸引力与连续性，同时减少无意义全量重写和不可控成本。

## 系统总览

```text
                  local browser
                       |
                       v
              src/novel_flow/server.py
        Web UI + HTTP API + run orchestration
                       |
      +----------------+----------------+
      |                |                |
      v                v                v
 BlueprintAgent    WriterAgent      CriticAgent
  8-step plan     chapter prose    review / patch
      |                |                |
      +----------------+----------------+
                       |
                       v
              PromptLibrary + tools
        prompts/*, tool_registry, LLM clients
                       |
                       v
                 SQLiteStore
 books, runs, outputs, events, blocks, reports
```

主要边界：

- `src/novel_flow/agents/`：规划、写作、评审、记忆 Agent。
- `src/novel_flow/tools/`：章节写作循环中的工具调用，如内容块规划、评审、补丁、润色、摘要。
- `src/novel_flow/services/`：上下文筛选、提示词渲染、技能管理、参考资料、JSON 修复。
- `src/novel_flow/storage/`：SQLite 持久化。
- `src/novel_flow/server.py`：本地 Web 控制台、API、任务运行记录。
- `prompts/`：规划、写作、评审提示词模板。
- `evals/romance/`：言情质量评估、历史 case、对比报告。

## 小说生产主流程

```text
用户输入题材/风格/篇幅
        |
        v
[0] 新建小说壳
        |
        v
[1] 大纲+蓝图 -> [2] 背景体系+世界观 -> [3] 角色卡
        |                 |                   |
        +-----------------+-------------------+
                          v
[4] 客观事件时间线 -> [5] 角色发展线 -> [6] 反转设计
                          |
                          v
[7] 明线暗线发展线 -> [8] 章节摘要规划
                          |
                          v
                    写下一章循环
                          |
                          v
             章节正文 + 摘要 + 评审报告 + 记忆回写
```

## 规划流程输入输出

| 步骤 | 输入 | 输出 | 目标 |
| --- | --- | --- | --- |
| 0 新建小说壳 | 用户题材、风格、总字数、章节数、单章字数、节奏要求 | `BookDocument`、空 `story_blueprint`、运行元信息 | 建立可落库、可继续运行的项目容器 |
| 1 大纲+蓝图 | 用户输入、风格要求、参考资料、已有规划上下文 | `premise`、`story_engine`、`volume_titles` | 锁定故事承诺、核心冲突、情绪钩子、叙事引擎 |
| 2 背景体系+世界观 | 步骤 1、题材、参考资料 | `story_engine` 扩展、世界规则、权力结构、客观限制 | 让后续剧情有稳定规则和可施压的环境 |
| 3 角色卡 | 步骤 1-2、题材、参考资料 | `characters` | 建立主角、配角、动机、关系、吸引力与行为模式 |
| 4 客观事件时间线 | 步骤 1-3、世界规则、角色关系 | `event_timeline` | 固定客观发生顺序，避免后文因果和时间线漂移 |
| 5 角色发展线 | 步骤 1-4、角色卡、故事引擎 | `character_milestones` | 规划每个关键角色的阶段目标、心态变化、关系重估 |
| 6 反转设计 | 步骤 1-5、事件线、角色发展线 | `twist_designs` | 管控误导、真相、埋线、揭示章节和禁止提前泄露的信息 |
| 7 明线暗线发展线 | 步骤 1-6、反转设计、事件线 | `story_lines` | 把明线、暗线、误导线拆成可追踪的问题与推进规则 |
| 8 章节摘要规划 | 步骤 1-7、目标章节数、已有章节摘要 | `chapter_briefs` | 给每章生成可执行写作卡，包含钩子、场面、信息预算、关系推进 |

规划产物都写回 `BookDocument.metadata.story_blueprint` 或 `BookDocument` 本体，可在前端“小说信息”中单步生成、编辑、保存。

## 章节写作流程

```text
ChapterBrief + story_blueprint + BookDocument
        |
        v
选择写作上下文
        |
        v
生成本章角色心态卡
        |
        v
规划内容块 ContentBlock[]
        |
        v
逐 beat 起草正文 / 或整章起草
        |
        v
章节级评审 gate
        |
   pass +--------------------+
        |                    |
        v                    |
 构建定向补丁计划            |
        |                    |
        v                    |
 只重写命中内容块             |
        |                    |
        v                    |
 补丁后 judge ---------------+
        |
        v
最终润色 -> 格式调整 -> 实际章节摘要 -> 落库
```

| 子流程 | 输入 | 输出 | 目标 |
| --- | --- | --- | --- |
| 上下文筛选 | 当前 `ChapterBrief`、角色卡、发展线、反转、故事线、历史摘要、世界观 | `WriterContext` | 只带本章需要的信息，减少泄密、冗余和成本 |
| 角色心态卡 | 本章焦点角色、历史心态、发展线、当前剧情压力 | `CharacterMindset[]` | 明确角色在本章的欲望、误读、克制、关系姿态 |
| 内容块规划 | `ChapterBrief`、`WriterContext`、心态卡 | `ContentBlock[]` | 把章节拆成具有推进功能的块，便于增量预览和定向修补 |
| 正文起草 | 内容块、上下文、技能指令 | `chapter_text`、已提交内容块 | 写出连续场景，保证每个 beat 都有新信息或关系变化 |
| 章节评审 | 正文、内容块、上下文、章节摘要 | `review_reports`、`final_judge` | 检查结构连续性、人物可信度、文笔、人味、信息泄露 |
| 定向补丁 | 评审报告、内容块、正文 | `patch_plan`、局部重写后的正文 | 只改问题块，避免整章重写破坏已有有效内容 |
| 最终润色 | 当前最佳正文、格式规则 | `final_text` | 清理表达和段落格式，不改事实与情绪逻辑 |
| 摘要回写 | 最终正文、章节卡、上下文 | `ActualChapterSummary` | 把已发生事实、关系变化、伏笔状态写入后续记忆 |

章节完成后，系统会更新：

- `volumes[0].chapters[]`：最终章节正文、内容块、心态卡。
- `metadata.completed_chapter_ids`：已完成章节。
- `metadata.next_chapter_index`：下一章索引。
- `metadata.actual_chapter_summaries`：后续写作记忆。
- `metadata.critic_reports`：评审、补丁与最终判定。
- `run_outputs`、`chapter_blocks`、`pipeline_events`：前端运行记录与调试材料。

## Agent 与工具分工

| 组件 | 责任 | 关键文件 |
| --- | --- | --- |
| `BlueprintAgent` | 生成 8 步规划、单角色新增、单发展线新增、规划修订 | `src/novel_flow/agents/blueprint.py` |
| `WriterAgent` | 创建书壳、选择下一章、组织章节写作、回写 BookDocument | `src/novel_flow/agents/writer.py` |
| `WritingChapterAgent` | 执行章节内部循环：上下文、心态、内容块、评审、补丁、润色 | `src/novel_flow/agents/writing_chapter_agent.py` |
| `CriticAgent` | 评审蓝图或章节，生成问题卡与补丁指令 | `src/novel_flow/agents/critic.py` |
| `MemoryAgent` | 读写书籍、运行状态、输出、事件、评审报告 | `src/novel_flow/agents/memory.py` |
| `DirectorAgent` | 在通用任务中根据观察选择下一步动作 | `src/novel_flow/agents/director.py` |
| `ToolRegistry` | 注册章节写作工具，统一执行 LLM 工具调用 | `src/novel_flow/services/tool_registry.py` |

## 数据模型与持久化

```text
BookDocument
  premise
  characters
  volumes[].chapters[]
  metadata.story_blueprint
    story_engine
    event_timeline
    character_milestones
    twist_designs
    story_lines
    chapter_briefs

SQLite
  books                当前小说全文档
  workflow_states      运行中/已完成任务状态
  run_outputs          每次任务的结构化产物
  pipeline_events      Agent 事件流
  chapter_blocks       章节内容块与版本
  critic_reports       评审报告
  patch_versions       局部补丁版本
```

默认数据库：

- 正式模式：`data/novel_flow.db`
- 测试模式：`data/novel_flow_test.db`

数据库文件已被 `.gitignore` 忽略，正常 `git add .` 不会提交小说正文。

## 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
novel-flow run --db data/novel_flow.db --test-db data/novel_flow_test.db --port 8765 --no-browser
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
novel-flow run --db data/novel_flow.db --test-db data/novel_flow_test.db --port 8765 --no-browser
```

访问：

```text
http://127.0.0.1:8765/
```

## LLM 配置

`.env` 中选择一个 provider。

DeepSeek：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

豆包：

```env
LLM_PROVIDER=doubao
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=your_endpoint_id
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

OpenAI：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=your_openai_model
OPENAI_BASE_URL=https://api.openai.com/v1
```

Codex CLI：

```env
LLM_PROVIDER=codex
CODEX_EXE=codex
CODEX_MODEL=your_codex_model_optional
```

## 前端操作路径

- 新建小说：创建 `BookDocument` 壳，保存用户题材与篇幅要求。
- 步骤 1-8：单步生成规划产物，支持人工编辑后保存。
- 步骤 3/5/8 局部调整：支持单角色、单发展线、单章摘要的指令修改。
- 写下一章：按 `next_chapter_index` 选择下一条 `chapter_brief`，执行章节写作循环。
- 运行记录：查看每次任务的 stage、agent input、输出、内容块预览、评审报告。
- 测试模式：使用 `--test-db` 指定的独立数据库，避免污染正式小说。

## 评估与自优化

常用历史 case 导出：

```bash
python3 -m tools.export_eval_cases --db data/novel_flow.db --output-dir evals/romance/exported_cases/latest --limit 20 --sample-mode low_score
```

规划诊断：

```bash
python3 -m evals.romance.runners.historical_step_gate_eval --cases evals/romance/exported_cases/latest --label latest_step_eval
python3 -m evals.romance.runners.workflow_diagnostics_eval --cases evals/romance/exported_cases/latest --label latest_diagnostics
```

章节质量评估：

```bash
python3 -m evals.romance.runners.chapter_quality_eval --cases-dir evals/romance/cases --label fixture_baseline
python3 -m evals.romance.runners.chapter_quality_eval --cases-dir evals/romance/exported_cases/latest --label historical_baseline
```

对比基线与候选：

```bash
python3 -m evals.romance.runners.eval_run_comparison --baseline evals/romance/reports/historical_baseline/summary.json --candidate evals/romance/reports/historical_candidate/summary.json
```

## 开发规则

- 中文提示词、README、前端内嵌文案都保持 UTF-8。
- 改规划结构时同步检查 `prompts/writer/step_*.txt`、`src/novel_flow/agents/blueprint.py`、`src/novel_flow/models/schemas.py`、`src/novel_flow/server.py`。
- 改章节写作循环时同步检查 `src/novel_flow/agents/writing_chapter_agent.py`、`src/novel_flow/tools/`、`prompts/writer/*.txt`、相关测试。
- 改 `server.py` 或浏览器可见流程时，要实际检查前端路径。
- 临时调试文件放在 `data/` 下，完成后删除。

最小自检：

```bash
python3 -m py_compile src/novel_flow/server.py src/novel_flow/agents/blueprint.py src/novel_flow/agents/writer.py src/novel_flow/agents/writing_chapter_agent.py src/novel_flow/models/schemas.py
python3 -m unittest tests.test_eval_case_exporter tests.test_workflow_diagnostics tests.test_step_evals tests.test_case_comparison tests.test_novel_self_improve_skill tests.test_requirement_cases
```

章节写作相关改动额外运行：

```bash
python3 -m unittest tests.test_romance_eval_harness tests.test_writing_chapter_agent tests.test_schema_and_context
```

## 常见问题

### 小说数据会提交到 Git 吗？

默认不会。`data/*.db`、`data/*.sqlite`、`data/*.sqlite3` 已忽略，除非手动 `git add -f`。

### 指令修改为什么没有立即生效？

指令修改先生成草稿，点击“保存”后才写入 `BookDocument`。

### 前端按钮无响应怎么办？

- 确认服务：`http://127.0.0.1:8765/`
- 查看运行日志和终端输出。
- 如端口占用，换端口或停止旧服务。

### 什么时候需要重跑步骤 6-8？

当反转结构、故事线或章节摘要 schema 升级，或正文生成提示“数据结构已升级”时，先重跑步骤 6、7、8，再继续写正文。
