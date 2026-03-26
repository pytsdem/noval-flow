# WriterAgent Inputs And Outputs

## create

- 输入
  - `BookBlueprint`
  - `source_query: str`
- 输出
  - `BookDocument`
- 是否调用大模型
  - 是
- 相关 prompt
  - `prompts/writer/blueprint.txt`
  - `prompts/writer/system.txt`
  - `prompts/writer/create_hook.txt`
  - `prompts/writer/create_turn.txt`

## rewrite_unit

- 输入
  - `book: BookDocument`
  - `block_id: str`
  - `guidance: str`
- 输出
  - `BookDocument`
- 是否调用大模型
  - 是
- 相关 prompt
  - `prompts/writer/system.txt`
  - `prompts/writer/rewrite_unit.txt`

## patch_block

- 输入
  - `book: BookDocument`
  - `instruction: PatchInstruction`
- 输出
  - `BookDocument`
  - `BlockPatchVersion`
- 是否调用大模型
  - 否
- 相关逻辑
  - `src/novel_flow/services/patcher.py`

## expand

- 输入
  - `book: BookDocument`
  - `block_id: str`
  - `expansion_goal: str`
- 输出
  - `BookDocument`
- 是否调用大模型
  - 是
- 相关 prompt
  - `prompts/writer/system.txt`
  - `prompts/writer/expand.txt`
