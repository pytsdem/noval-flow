# flashback_guard

Purpose: stop unearned flashbacks and keep backstory gated by the chapter brief.

Tools:
- `review_chapter_engine`
- `review_instruction_compliance`
- `rewrite_by_plan`

Hard rules:
- No flashback when `backstory_trigger` is empty.
- If backstory appears, it must be forced out by present action or object.
