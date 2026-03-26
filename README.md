# Novel Flow

一个基于 Python 3.11 的 4+1 多 Agent 小说生成项目骨架，面向“多 Agent 协作生成 10 万字知乎风格小说”。当前版本优先把协议、Pydantic schema、SQLite 存储、block 级 patch、版本记录和单 Agent 调试入口打稳。

## 架构

- `MasterAgent`：负责规划、调度、状态机推进
- `ResearchAgent`：负责热点采集接口与结构化调研报告
- `WriterAgent`：负责创作与局部修改，支持 `create`、`rewrite_unit`、`patch_block`、`expand`
- `CriticAgent`：负责审稿，只输出结构化 `IssueCard`
- `MemoryAgent`：负责 SQLite 持久化、检索和版本记录

## 文档结构

小说内容严格采用：

```text
book -> volumes -> chapters -> scenes -> blocks
```

每个 `block` 必须有稳定可定位 id，例如：

```text
ch_001.sc_002.b003
```

## 目录

```text
noval-flow/
├─ .env.example
├─ pyproject.toml
├─ README.md
├─ examples/
│  ├─ 01_storage_demo.py
│  ├─ 02_research_demo.py
│  ├─ 03_writer_demo.py
│  ├─ 04_critic_patch_demo.py
│  ├─ 05_master_demo.py
│  ├─ 06_debug_writer_agent.py
│  ├─ 07_debug_research_agent.py
│  ├─ 08_debug_critic_agent.py
│  └─ _example_support.py
├─ prompts/
│  └─ writer/
├─ io/
│  └─ examples/
└─ src/
   └─ novel_flow/
      ├─ agents/
      ├─ llm/
      ├─ models/
      ├─ prompting/
      ├─ services/
      └─ storage/
```

## 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

如果当前环境里 `pip install -e .` 受限，也可以先直接用：

```powershell
$env:PYTHONPATH='src'
```

如果 VS Code / Pylance 提示 `Import "novel_flow..." could not be resolved`，当前仓库已经包含：

- [.vscode/settings.json](C:/Users/19237/workspace/noval-flow/.vscode/settings.json)
- [pyrightconfig.json](C:/Users/19237/workspace/noval-flow/pyrightconfig.json)

它们会把 `src` 识别为源码根目录。若仍未生效，请执行：

```text
Ctrl + Shift + P
Python: Select Interpreter
Developer: Reload Window
```

## 豆包模型接入

项目已经接入豆包 OpenAI 兼容接口。建议统一用环境变量，不要把密钥写进代码：

```powershell
$env:DOUBAO_API_KEY='你的 API Key'
$env:DOUBAO_MODEL='ep-m-20260319020545-gzfvt'
$env:DOUBAO_BASE_URL='https://ark.cn-beijing.volces.com/api/v3'
```

说明：

- `DOUBAO_MODEL` 是你的 endpoint id
- 当前默认优先走真实豆包
- 只有在你显式加 `--mock-llm` 时，才使用 mock LLM

当前各 Agent 的模型接入状态：

- `ResearchAgent`
  - 仍然使用 mock crawler，不调用大模型
- `WriterAgent`
  - `build_blueprint`、`create`、`rewrite_unit`、`expand` 已接入大模型
  - `patch_block` 仍然是本地精准 patch，不调用大模型
- `CriticAgent`
  - `review_book` 和 `build_patch_instruction` 已接入大模型
  - 若模型输出无法解析，会回退到项目内置 mock 常量
- `MasterAgent`
  - 自身不直接调用模型，但会调度 `WriterAgent` 和 `CriticAgent`

## 调 Prompt 与协议

如果你要直接调提示词，去看：

- `prompts/README.md`
- `prompts/critic/system.txt`
- `prompts/critic/review.txt`
- `prompts/critic/patch_instruction.txt`
- `prompts/writer/system.txt`
- `prompts/writer/blueprint.txt`
- `prompts/writer/create_hook.txt`
- `prompts/writer/create_turn.txt`
- `prompts/writer/rewrite_unit.txt`
- `prompts/writer/expand.txt`

如果你要看各个功能的输入输出，去看：

- `io/README.md`
- `io/agent_capabilities.md`
- `io/writer_agent.md`
- `io/research_agent.md`
- `io/critic_agent.md`
- `io/master_agent.md`
- `io/schemas_index.md`
- `io/examples/*.json`

如果你要看当前保留的 mock 常量，去看：

- `src/novel_flow/constants/mock_data.py`

## 示例文件说明

### 基础验证

- `01_storage_demo.py`
  - 验证 `BookDocument` 能否存入 SQLite 并读回

- `02_research_demo.py`
  - 验证 `ResearchAgent` 和 mock crawler 的结构化输出

- `03_writer_demo.py`
  - 验证 `WriterAgent` 生成初始书稿结构
  - 默认走真实豆包，可加 `--mock-llm`

### 链路验证

- `04_critic_patch_demo.py`
  - 验证 `CriticAgent` 审稿并生成 patch，再由 `WriterAgent` 精准修改 block

- `05_master_demo.py`
  - 验证 `MasterAgent` 串起完整 mock pipeline

### 单 Agent 调试

- `06_debug_writer_agent.py`
  - 专门调试 `WriterAgent`
  - 支持 `create`、`rewrite_unit`、`patch_block`、`expand`

- `07_debug_research_agent.py`
  - 专门调试 `ResearchAgent`
  - 用来检查 query、素材采集和报告结构

- `08_debug_critic_agent.py`
  - 专门调试 `CriticAgent`
  - 用来检查 `IssueCard` 是否具体，patch 指令是否可执行

## 运行示例

### 1. 验证存储

```bash
python examples/01_storage_demo.py
```

### 2. 验证调研

```bash
python examples/02_research_demo.py
python examples/07_debug_research_agent.py --query "知乎体高热度都市情感反转"
```

### 3. 验证 Writer

```bash
python examples/03_writer_demo.py
python examples/06_debug_writer_agent.py --mode create
python examples/06_debug_writer_agent.py --mode rewrite_unit --block-id ch_001.sc_001.b001 --guidance "加强婚礼现场压迫感和替身羞辱感"
python examples/06_debug_writer_agent.py --mode expand --block-id ch_001.sc_001.b001 --expansion-goal "补充宾客视线和女主心理细节"
```

### 4. 验证 Critic + Patch

```bash
python examples/04_critic_patch_demo.py
python examples/08_debug_critic_agent.py --show-patch
```

### 5. 验证 Master

```bash
python examples/05_master_demo.py
```

### 6. CLI

```bash
novel-flow run-mock --db data/novel_flow.db
```

如果你只想本地跑结构，不访问模型：

```bash
novel-flow run-mock --db data/novel_flow.db --mock-llm
```

## Agent 与可调试能力

- `ResearchAgent`
  - 核心能力：`collect_report`
  - 调试入口：`02`、`07`

- `WriterAgent`
  - 核心模式：`create`、`rewrite_unit`、`patch_block`、`expand`
  - 调试入口：`03`、`06`

- `CriticAgent`
  - 核心能力：`review_book`、`build_patch_instruction`
  - 调试入口：`04`、`08`

- `MemoryAgent`
  - 核心能力：保存和读取结构化对象、保存 patch 版本
  - 调试入口：`01`

- `MasterAgent`
  - 核心能力：工作流编排
  - 调试入口：`05`

## 当前实现重点

- 使用 Python 3.11
- 使用 Pydantic 定义核心 schema
- 默认使用 SQLite 存储
- 所有 Agent 继承统一 `BaseAgent`
- 审稿输出结构化 `IssueCard`
- 支持 block 级精准修改和 patch 前后版本保存
- 爬虫部分是接口 + mock 实现，不依赖真实知乎/小红书 DOM

## 后续可继续补强

- 给 `CriticAgent` 增加 LLM 审稿模式
- 给 `ResearchAgent` 增加真实站点适配器
- 给 `WriterAgent` 增加外置 prompt 模板文件
- 增加测试和更细粒度 repository 层
