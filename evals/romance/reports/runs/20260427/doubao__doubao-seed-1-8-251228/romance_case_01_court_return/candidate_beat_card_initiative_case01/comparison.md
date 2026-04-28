# Comparison Report: candidate_beat_card_initiative_case01 vs candidate_beat_card_case01_clean

- comparison_type: `romance_eval`

## Decision

- accept_change: `false`
- core_metric_delta: `-0.45`
- guard_metric_delta: `0.17`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `baseline`
- pairwise_weighted_margin: `-5.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Core romance objectives did not improve on average., Pairwise case preference favored the baseline.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | -1.00 |
| relationship_progression_score | +0.00 |
| emotional_resonance_score | -0.20 |
| character_attraction_score | -0.80 |
| hook_score | -0.25 |
| continuity_score | +0.20 |
| redundancy_score | +0.00 |
| mind_state_consistency_score | +0.30 |

## Pairwise Preference

- overall_preferred_side: `baseline`
- candidate_case_wins: `0`
- baseline_case_wins: `1`
- tied_case_count: `0`
- weighted_margin: `-5.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_01_court_return | baseline | -5.00 | continuity_score, mind_state_consistency_score | romance_tension_score, emotional_resonance_score, character_attraction_score, hook_score | None | None |
