# Comparison Report: case02_action_first_banter vs cross_tone_smoke_prompt_beat_slim_case02_deepseek

- comparison_type: `romance_eval`

## Decision

- accept_change: `true`
- core_metric_delta: `0.22`
- guard_metric_delta: `0.12`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `candidate`
- pairwise_weighted_margin: `+8.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Candidate improved core romance objectives without violating continuity, mind-state, or cost guards.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | +0.50 |
| relationship_progression_score | +0.70 |
| emotional_resonance_score | -0.40 |
| character_attraction_score | +0.06 |
| hook_score | +0.25 |
| continuity_score | +0.00 |
| redundancy_score | +0.36 |
| mind_state_consistency_score | +0.00 |
| genre_fit_score | -0.20 |

## Pairwise Preference

- overall_preferred_side: `candidate`
- candidate_case_wins: `1`
- baseline_case_wins: `0`
- tied_case_count: `0`
- weighted_margin: `+8.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_02_xianxia_rival_trial | candidate | +8.00 | romance_tension_score, relationship_progression_score, hook_score, redundancy_score | emotional_resonance_score, genre_fit_score | None | None |
