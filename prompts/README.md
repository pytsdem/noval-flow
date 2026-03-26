# Prompt Templates

这个目录专门汇总项目里的提示词，方便直接修改和对比。

## 目录说明

- `writer/system.txt`
  - WriterAgent 的 system prompt
- `writer/create_hook.txt`
  - `WriterAgent.create` 在生成每个 scene 的第一个 block 时使用
- `writer/create_turn.txt`
  - `WriterAgent.create` 在生成每个 scene 的第二个 block 时使用
- `writer/rewrite_unit.txt`
  - `WriterAgent.rewrite_unit` 使用
- `writer/expand.txt`
  - `WriterAgent.expand` 使用

## 调试建议

1. 先改模板，不要先改业务逻辑。
2. 用 `examples/06_debug_writer_agent.py` 跑单环节。
3. 确认单环节效果后，再跑 `05_master_demo.py` 看整链路。
