# Comparison Report: case01_high_impact_once vs cross_tone_smoke_prompt_beat_slim_case01

- comparison_type: `romance_eval`

## Decision

- accept_change: `false`
- core_metric_delta: `-0.02`
- guard_metric_delta: `-0.54`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `baseline`
- pairwise_weighted_margin: `-6.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Core romance objectives did not improve on average., Continuity regressed beyond the safety threshold., Redundancy regressed beyond the safety threshold., Average duration increased too much., Pairwise case preference favored the baseline.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | +0.00 |
| relationship_progression_score | -1.00 |
| emotional_resonance_score | +0.50 |
| character_attraction_score | -0.02 |
| hook_score | +0.40 |
| continuity_score | -1.00 |
| redundancy_score | -0.62 |
| mind_state_consistency_score | +0.00 |
| genre_fit_score | +0.00 |

## Pairwise Preference

- overall_preferred_side: `baseline`
- candidate_case_wins: `0`
- baseline_case_wins: `1`
- tied_case_count: `0`
- weighted_margin: `-6.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_01_court_return | baseline | -6.00 | emotional_resonance_score, hook_score | relationship_progression_score, continuity_score, redundancy_score | continuity_score, redundancy_score | duration_seconds>+20 |
