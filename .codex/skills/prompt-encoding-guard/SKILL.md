---
name: prompt-encoding-guard
description: Use when editing Chinese text in this repo, especially files under `prompts/` and large embedded HTML/JS strings in `src/novel_flow/server.py`. Always preserve UTF-8 Chinese text, avoid terminal-written mojibake, prefer Unicode-safe writes, and run the repo checks that match the edited file type.
---

# Prompt Encoding Guard

Use this skill whenever you edit:
- files under `prompts/`
- large embedded Chinese UI strings or JS/HTML template strings, especially `_HTML_PAGE` inside `src/novel_flow/server.py`

Rules:
1. Never trust direct terminal-emitted Chinese text when writing prompt files.
2. Prefer Unicode-safe writes or verified UTF-8 file edits.
3. Treat repeated `?` in Chinese sentences, visible mojibake, broken HTML tags, or odd private-use Unicode glyphs as corruption signals.
4. Never assume "page still returns 200" means embedded JS is valid; syntax-check extracted script content when editing `server.py`.
5. Prefer replacing an entire broken function/string block over patching individual mojibake characters in place.

Workflow:
1. Edit the target file with UTF-8-safe writes.
2. If you edited `prompts/`, run:
   - `python scripts/check_prompt_encoding.py`
3. If you edited embedded JS/HTML in `src/novel_flow/server.py`, extract and validate the script:
   - use Python to write the `<script>` contents to `data/_page_script_live.js`
   - run a Node parse check with `vm.Script`
4. If terminal output is suspicious, inspect using Python with `encoding='utf-8'` and, when needed, print with `unicode_escape`.
5. Re-open a few changed sections and verify readable Chinese.
6. Only then report completion.

Repo-specific checks:
- Prompt files:
  - `python scripts/check_prompt_encoding.py`
- Embedded frontend in `server.py`:
  - extraction:
    ```powershell
    @'
    from pathlib import Path
    text = Path('src/novel_flow/server.py').read_text(encoding='utf-8')
    start = text.index('<script>') + len('<script>')
    end = text.index('</script></body></html>')
    Path('data/_page_script_live.js').write_text(text[start:end], encoding='utf-8')
    '@ | python -
    ```
  - syntax check:
    ```powershell
    @'
    const fs = require('fs');
    const vm = require('vm');
    const src = fs.readFileSync('data/_page_script_live.js', 'utf8');
    new vm.Script(src, { filename: 'data/_page_script_live.js' });
    console.log('OK');
    '@ | node -
    ```

Heuristics for `server.py`:
- If the browser shows empty dropdowns or buttons stop working, suspect early JS parse failure before assuming backend data is missing.
- Verify `/api/novels?mode=formal` first; if data exists, fix frontend script execution before touching storage.
- When a single mojibake line breaks quoting, replace the whole JS function block, then rerun the extraction + parse check.
