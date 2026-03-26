# Agent Capabilities

## ResearchAgent

- 功能：`collect_report`
- 输入：`query`
- 输出：`ResearchReport`
- 调试入口：`examples/02_research_demo.py`、`examples/07_debug_research_agent.py`
- 是否调用大模型：否

## WriterAgent

- 功能：`create`
- 功能：`rewrite_unit`
- 功能：`patch_block`
- 功能：`expand`
- 输入：`BookBlueprint`、`BookDocument`、`block_id`、`guidance`、`PatchInstruction`
- 输出：`BookDocument`、`BlockPatchVersion`
- 调试入口：`examples/03_writer_demo.py`、`examples/06_debug_writer_agent.py`
- 是否调用大模型：
  - `build_blueprint` / `create` / `rewrite_unit` / `expand`：是
  - `patch_block`：否

## CriticAgent

- 功能：`review_book`
- 功能：`build_patch_instruction`
- 输入：`BookDocument`
- 输出：`CriticReport`、`PatchInstruction`
- 调试入口：`examples/04_critic_patch_demo.py`、`examples/08_debug_critic_agent.py`
- 是否调用大模型：是

## MemoryAgent

- 功能：存储和读取 `BookDocument`、`ResearchReport`、`CriticReport`、`WorkflowState`、`BlockPatchVersion`
- 调试入口：`examples/01_storage_demo.py`

## MasterAgent

- 功能：`run_mock_pipeline`
- 输入：`query`
- 输出：全流程结构化结果
- 调试入口：`examples/05_master_demo.py`
- 是否调用大模型：自身不直接调用，但会调度 `WriterAgent` 和 `CriticAgent`
