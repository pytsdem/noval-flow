# reveal_guard

Purpose: stop early truth leakage, sympathy leakage, and over-explained clues.

Tools:
- `review_reveal_leak`
- `rewrite_by_plan`
- `final_judge`

Recommended order:
1. Inspect reveal leakage.
2. Rewrite to preserve false belief and allowed-clue ambiguity.
3. Judge again.

Hard rules:
- Never expose hidden twist truth before `reveal_at`.
- Never explain why a hidden character acted that way.
