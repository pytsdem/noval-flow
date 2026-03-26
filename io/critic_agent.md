# CriticAgent Inputs And Outputs

## review_book

- 输入
  - `book: BookDocument`
- 输出
  - `CriticReport`
  - 内部包含 `IssueCard[]`
- 当前实现方式
  - 大模型结构化审稿
  - 若输出解析失败，回退到 `src/novel_flow/constants/mock_data.py`

## build_patch_instruction

- 输入
  - `issue: IssueCard`
- 输出
  - `PatchInstruction`
- 当前实现方式
  - 大模型生成 patch 内容
  - 若输出解析失败，回退到 `src/novel_flow/constants/mock_data.py`

## 相关文件

- `src/novel_flow/agents/critic.py`
- `examples/08_debug_critic_agent.py`
