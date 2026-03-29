# Examples 命令行调试指南

这份指南说明 `examples/` 目录下几个调试脚本分别做什么、有哪些命令、该怎么用。

## 使用前准备

先进入项目根目录：

```powershell
cd c:\Users\19237\workspace\noval-flow
```

使用需要调用模型的脚本前，请先配置环境变量：

```powershell
$env:DOUBAO_API_KEY="你的 API Key"
$env:DOUBAO_MODEL="你的模型名"
```

大部分“写章节 / 评价 / 修改 / 主流程”脚本都会用到 SQLite 数据库。默认数据库路径是：

```text
data/example_master.db
```

## 脚本总览

- `03_writer_demo.py`
  用来调试“大纲生成”
- `06_debug_writer_agent.py`
  用来调试“按章节写小说”
- `08_debug_critic_agent.py`
  用来调试“评价小说章节”
- `04_critic_patch_demo.py`
  用来调试“修改小说章节”
- `05_master_demo.py`
  用来调试“主 Agent 全流程”

## 1. 调试大纲生成

脚本：

```powershell
python examples/03_writer_demo.py --query "都市情感反转"
```

作用：

- 调用 `WriterAgent.build_blueprint(...)`
- 生成并打印：
  - 书的设定 `premise`
  - 角色设定 `characters`
  - 卷标题 `volume_titles`
  - 章节规划 `chapter_plans`

适合调试：

- 小说标题是否合适
- 角色设定是否合理
- 章节规划是否清晰

示例：

```powershell
python examples/03_writer_demo.py --query "豪门婚恋反转"
```

## 2. 调试按章节写小说

脚本：

```powershell
python examples/06_debug_writer_agent.py start --db data/example_master.db --query "都市情感反转"
```

`start` 的作用：

- 先生成大纲
- 再创建一本“空书壳”
- 然后只写第一章
- 最后把结果存进 SQLite

输出里通常会有：

- `book_id`
- `book_title`
- `chapter`
- `next_chapter_index`
- `completed_chapter_ids`

继续写下一章：

```powershell
python examples/06_debug_writer_agent.py continue --db data/example_master.db --book-id book_xxxxx
```

`continue` 的作用：

- 从 SQLite 读取已有小说
- 找到下一章应该写哪一章
- 只写下一章
- 把更新后的书再存回 SQLite

示例流程：

```powershell
python examples/06_debug_writer_agent.py start --db data/example_master.db --query "先婚后爱豪门反转"
python examples/06_debug_writer_agent.py continue --db data/example_master.db --book-id book_ab12cd34ef
python examples/06_debug_writer_agent.py continue --db data/example_master.db --book-id book_ab12cd34ef
```

## 3. 调试评价小说章节

脚本：

```powershell
python examples/08_debug_critic_agent.py --db data/example_master.db --book-id book_xxxxx
```

作用：

- 从 SQLite 读取一本已有小说
- 调用 `CriticAgent.review_book(...)`
- 保存评价报告
- 在终端打印问题列表

如果你还想顺便看“第一条修改指令”：

```powershell
python examples/08_debug_critic_agent.py --db data/example_master.db --book-id book_xxxxx --show-patch
```

示例：

```powershell
python examples/08_debug_critic_agent.py --db data/example_master.db --book-id book_ab12cd34ef --show-patch
```

## 4. 调试修改小说章节

脚本：

```powershell
python examples/04_critic_patch_demo.py --db data/example_master.db --book-id book_xxxxx --block-id ch_001.sc_001.b001 --patch-content "新的段落内容"
```

作用：

- 从 SQLite 读取一本书
- 手动构造 `PatchInstruction`
- 对指定 `block` 执行修改
- 把修改后的书重新保存到 SQLite

支持的修改类型：

- `replace`
  直接替换整段内容
- `append`
  在原文后面追加
- `prepend`
  在原文前面插入

示例：

直接替换：

```powershell
python examples/04_critic_patch_demo.py --db data/example_master.db --book-id book_ab12cd34ef --block-id ch_001.sc_001.b001 --operation replace --patch-content "婚礼现场的羞辱感要更强。"
```

追加内容：

```powershell
python examples/04_critic_patch_demo.py --db data/example_master.db --book-id book_ab12cd34ef --block-id ch_001.sc_001.b001 --operation append --patch-content "我抬头看向满堂宾客，终于决定不再退让。"
```

前置插入：

```powershell
python examples/04_critic_patch_demo.py --db data/example_master.db --book-id book_ab12cd34ef --block-id ch_001.sc_001.b001 --operation prepend --patch-content "婚礼开始前十分钟，我就知道一切不对劲。"
```

## 5. 调试 MasterAgent 主流程

先查看当前数据库里有哪些小说：

```powershell
python examples/05_master_demo.py --db data/example_master.db list
```

新建一本小说并写第一章：

```powershell
python examples/05_master_demo.py --db data/example_master.db start --query "都市情感反转"
```

`start` 的作用：

- research
- 生成大纲
- 创建书壳
- 写第一章
- 评价
- 如果有需要则生成 patch 并修改
- 最后通过 `MemoryAgent` 保存

继续写一本已有小说，按 `book_id`：

```powershell
python examples/05_master_demo.py --db data/example_master.db continue --book-id book_xxxxx
```

继续写一本已有小说，按标题关键字：

```powershell
python examples/05_master_demo.py --db data/example_master.db continue --title "反转"
```

`continue` 的作用：

- 从 `MemoryAgent` 读取当前小说
- 写下一章
- 再次评价
- 如果有问题就继续 patch
- 最后把新状态写回 SQLite

完整示例：

```powershell
python examples/05_master_demo.py --db data/example_master.db start --query "先婚后爱豪门反转"
python examples/05_master_demo.py --db data/example_master.db list
python examples/05_master_demo.py --db data/example_master.db continue --title "先婚后爱"
```

## 推荐调试顺序

如果你想一步一步调提示词和流程，建议按这个顺序：

1. `03_writer_demo.py`
   先看大纲、角色、章节规划对不对
2. `06_debug_writer_agent.py`
   再看章节正文生成效果
3. `08_debug_critic_agent.py`
   再看评价结果是否合理
4. `04_critic_patch_demo.py`
   再看 patch 行为是否符合预期
5. `05_master_demo.py`
   最后再看完整多 Agent 流程

## 常见说明

- `03_writer_demo.py` 不会写数据库
- `06_debug_writer_agent.py`、`08_debug_critic_agent.py`、`04_critic_patch_demo.py`、`05_master_demo.py` 都会用到 SQLite
- `06_debug_writer_agent.py start` 是只调 Writer 的流程
- `05_master_demo.py start` 是完整主流程

如果你想查看某个脚本支持哪些参数，可以直接运行：

```powershell
python examples/06_debug_writer_agent.py --help
python examples/05_master_demo.py --help
python examples/08_debug_critic_agent.py --help
```

## 你最常用的几条命令

生成大纲：

```powershell
python examples/03_writer_demo.py --query "豪门婚恋反转"
```

开始写一本新小说：

```powershell
python examples/06_debug_writer_agent.py start --db data/example_master.db --query "豪门婚恋反转"
```

继续写下一章：

```powershell
python examples/06_debug_writer_agent.py continue --db data/example_master.db --book-id book_ab12cd34ef
```

列出当前维护的小说：

```powershell
python examples/05_master_demo.py --db data/example_master.db list
```

让主 Agent 继续写一本小说：

```powershell
python examples/05_master_demo.py --db data/example_master.db continue --title "豪门"
```
