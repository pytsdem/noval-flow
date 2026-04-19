# Novel Flow

Novel Flow 是一个面向中文长篇小说创作的多 Agent 工作台。  
它把“从题材输入到章节正文”的流程拆成可编辑、可回溯、可复用的 8 个步骤，并提供本地 Web 控制台。

## 项目目标

- 把小说规划流程结构化，而不是一次性生成整本。
- 每一步都可单独运行、人工改写、再保存。
- 运行过程可追踪，支持任务记录与结果回填。
- 数据默认本地保存，方便私有创作与版本控制隔离。

## 核心流程（正式模式）

1. 大纲+蓝图  
2. 背景体系+世界观  
3. 角色卡+关系网  
4. 客观事件时间线  
5. 角色发展线  
6. 反转设计  
7. 故事线+章节标题  
8. 章节规划+大纲

每一步结果都可在前端“小说信息”中查看、展开、编辑、保存。

## 技术结构

- 后端：Python 3.11+
- Web：内置在 Python 服务中（无独立前端工程）
- 存储：SQLite
- Schema：Pydantic
- 代码目录：`src/novel_flow`

主要模块：

- `agents/`：Blueprint、Writer、Critic、Master、Research、Memory
- `llm/`：`codex_cli`、`doubao`、`openai`、`factory`
- `storage/`：SQLite 持久化
- `prompting/` 与 `prompts/`：提示词模板与渲染
- `server.py`：Web API + 控制台页面

## 安装

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -e .
```

## 环境变量

先复制：

```bash
cp .env.example .env
```

### 方案 A：豆包

```env
LLM_PROVIDER=doubao
DOUBAO_API_KEY=your_api_key
DOUBAO_MODEL=your_endpoint_id
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 方案 B：OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=your_openai_model
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 方案 C：Codex CLI

```env
LLM_PROVIDER=codex
CODEX_EXE=codex
CODEX_MODEL=your_codex_model_optional
```

说明：

- `codex` 模式支持回退：若配置了豆包或 OpenAI，会在 CodexCLI 失败时自动 fallback。
- 目前 `.env.example` 未列出 `CODEX_EXE/CODEX_MODEL`，可手动添加。

## 启动服务

```bash
novel-flow run --db data/novel_flow.db --test-db data/novel_flow_test.db --port 8765 --no-browser
```

打开浏览器：

```text
http://127.0.0.1:8765/
```

参数说明：

- `--db`：正式模式数据库
- `--test-db`：测试模式数据库
- `--port`：服务端口
- `--no-browser`：不自动打开浏览器

## 数据存储与 Git

默认数据存储在项目内：

- `data/novel_flow.db`
- `data/novel_flow_test.db`

仓库 `.gitignore` 已忽略数据库：

- `data/*.db`
- `data/*.sqlite`
- `data/*.sqlite3`

因此正常 `git add .` 不会提交你的小说数据。

## 前端使用说明（高频操作）

- 新建小说：只创建项目壳与输入层，不强制自动跑完整流程。
- 步骤按钮：按需运行单步，产物写回“小说信息”。
- 指令修改：生成建议稿，需点击“保存”才真正落库。
- 增加角色：走“只新增一个角色”的专用任务，不会重算整个步骤 3。
- 运行记录：左侧显示任务标签（如“步骤3 单角色指令修改”）。

## 常见问题

### 1) 我的小说会不会被推到 Git？

不会，数据库文件已被 `.gitignore` 忽略。除非你手动 `git add -f`。

### 2) 前端点按钮没反应怎么办？

- 先确认服务在跑：`http://127.0.0.1:8765/`
- 看日志：`data/manual_server_stderr.log`
- 如有端口占用，先停旧进程再启动。

### 3) 为什么“指令修改”后没立即写入？

这是设计行为。指令修改先生成草稿，只有你点“保存”才写库。

### 4) 数据误操作了怎么恢复？

先停止写入，再从 `data/` 下数据库备份恢复。建议定期备份 `data/novel_flow.db`。

## 开发提示

- 项目内含大量中文提示词，编辑时请保持 UTF-8 编码。
- 前端脚本嵌入在 `src/novel_flow/server.py`，改动后建议先 `py_compile`。
- 需要新增或调整生成逻辑时，优先同步更新：
  - `prompts/writer/*.txt`
  - `agents/blueprint.py`
  - `models/schemas.py`
  - `server.py`（渲染与保存链路）

## 最小自检命令

```bash
python -m py_compile src/novel_flow/server.py src/novel_flow/agents/blueprint.py src/novel_flow/models/schemas.py
```

如需查看当前命令行参数定义，可看：

- `src/novel_flow/cli.py`

