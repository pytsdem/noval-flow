# Comparison Report: candidate_beat_card_case01_clean vs smoke_doubao_case01

- comparison_type: `romance_eval`

## Decision

- accept_change: `false`
- core_metric_delta: `0.09`
- guard_metric_delta: `-0.05`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `candidate`
- pairwise_weighted_margin: `+1.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Average duration increased too much.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | +0.00 |
| relationship_progression_score | +0.00 |
| emotional_resonance_score | +0.00 |
| character_attraction_score | +0.00 |
| hook_score | +0.45 |
| continuity_score | +0.00 |
| redundancy_score | -0.16 |
| mind_state_consistency_score | +0.00 |

## Pairwise Preference

- overall_preferred_side: `candidate`
- candidate_case_wins: `1`
- baseline_case_wins: `0`
- tied_case_count: `0`
- weighted_margin: `+1.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_01_court_return | candidate | +1.00 | hook_score | None | None | duration_seconds>+20 |
