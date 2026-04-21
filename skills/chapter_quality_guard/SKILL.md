# chapter_quality_guard

Purpose: protect the chapter brief, continuity, and chapter-engine execution.

Tools:
- `review_instruction_compliance`
- `review_continuity`
- `review_hook_appearance`
- `review_chapter_engine`
- `final_judge`

Recommended order:
1. Check instruction compliance.
2. Check continuity.
3. Check whether the opening hook, ending pull, appearance timing, and unsupported exact time claims are working.
4. Check chapter-engine execution.
5. Let final judge decide whether the chapter can pass.

Failure handling:
- If any hard gate fails, rewrite by plan before judging again.
