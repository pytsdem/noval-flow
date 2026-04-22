---
name: chinese-output-guard
description: Use when the user wants Chinese text to display correctly, when tasks involve Chinese prompts/UI/database/log output, or when shell/browser output shows mojibake such as `???`, `锟斤拷`, `鈥`, `鍙`, or similar corruption. Prefer UTF-8-safe reads, Python `-X utf8 -`, `ensure_ascii=False`, and a final Chinese-display sanity pass before replying.
---

# Chinese Output Guard

Use this skill whenever:
- the user complains about 中文显示、乱码、编码问题、mojibake
- you need to read, quote, summarize, or inspect Chinese from shell output, SQLite, logs, JSON, HTML, or prompts
- you are about to send a Chinese-heavy answer based on tool output

Rules:
1. Do not trust raw PowerShell-rendered Chinese for user-facing text if it looks suspicious.
2. Prefer Python-based UTF-8 reads for Chinese content:
   - `python -X utf8 -`
   - `Path(...).read_text(encoding='utf-8')`
   - SQLite via Python, then `json.dumps(..., ensure_ascii=False)`
3. If output shows `???`, `锟斤拷`, `鈥`, `鍙`, `æ`, or similar mojibake, stop quoting it and rerun with a UTF-8-safe path.
4. When you need to inspect hidden escapes, print with `unicode_escape`; when you need user-facing Chinese, print normal UTF-8 text.
5. Never copy garbled tool output into the final answer. Regenerate or paraphrase from a verified UTF-8 source.
6. In mixed Chinese/code responses, keep code blocks ASCII when possible and keep Chinese explanations outside the code block.
7. Before sending the final answer, do a quick self-check for corruption markers and rewrite any broken Chinese.
8. If the renderer corrupts already-correct Chinese after generation, state that limitation clearly instead of pretending the source text is wrong.

Workflow:
1. Gather Chinese text from files, databases, logs, or HTML with Python `-X utf8 -` or another verified UTF-8 reader.
2. For JSON output, use `ensure_ascii=False`.
3. If terminal output is suspicious, re-read the source and compare normal text with `unicode_escape` when needed.
4. Draft the final answer in clean Chinese; do not paste raw mojibake.
5. If the task also edits Chinese files in this repo, use `prompt-encoding-guard` together with this skill.

Common safe patterns:

```powershell
@'
from pathlib import Path
print(Path('some_file.txt').read_text(encoding='utf-8'))
'@ | python -X utf8 -
```

```powershell
@'
import json
import sqlite3

conn = sqlite3.connect('data/novel_flow.db')
rows = conn.execute('SELECT title FROM books').fetchall()
print(json.dumps(rows, ensure_ascii=False))
'@ | python -X utf8 -
```
