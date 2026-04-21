# time_consistency_guard

Purpose: use when chapter time, day-night rhythm, or carry-over state is unstable.

Tools:
- `review_time_consistency`
- `review_continuity`
- `rewrite_by_plan`

Recommended order:
1. Check time_anchor against the written chapter.
2. Check previous-chapter carry-over and object/body continuity.
3. Rewrite only the transitions, time labels, and carry-over state required to fix the issue.

Hard rules:
- Obey `time_anchor.absolute`, `relative_to_previous_chapter`, and `must_not_conflict`.
- Do not jump from one time-of-day to another without explicit transition.
- Preserve body state, object state, and unfinished business from the prior chapter.
