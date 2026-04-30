# Comparison Report: prose_surface_case01_exec_guard vs sequential_beat_case01_deepseek

- comparison_type: `romance_eval`

## Decision

- accept_change: `false`
- core_metric_delta: `-0.90`
- guard_metric_delta: `-0.36`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `baseline`
- pairwise_weighted_margin: `-23.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Core romance objectives did not improve on average., Continuity regressed beyond the safety threshold., Mind-state consistency regressed beyond the safety threshold., Pairwise case preference favored the baseline.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | -1.40 |
| relationship_progression_score | -0.50 |
| emotional_resonance_score | -1.10 |
| character_attraction_score | -1.09 |
| hook_score | -0.40 |
| continuity_score | -0.50 |
| redundancy_score | -0.18 |
| mind_state_consistency_score | -0.40 |
| genre_fit_score | +9.00 |

## Pairwise Preference

- overall_preferred_side: `baseline`
- candidate_case_wins: `0`
- baseline_case_wins: `1`
- tied_case_count: `0`
- weighted_margin: `-23.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_01_court_return | baseline | -23.00 | genre_fit_score | romance_tension_score, relationship_progression_score, emotional_resonance_score, character_attraction_score, hook_score, continuity_score, mind_state_consistency_score | continuity_score, mind_state_consistency_score | None |
