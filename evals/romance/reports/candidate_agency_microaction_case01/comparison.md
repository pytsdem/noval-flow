# Comparison Report: candidate_agency_microaction_case01 vs candidate_beat_card_case01_clean

- comparison_type: `romance_eval`

## Decision

- accept_change: `false`
- core_metric_delta: `-0.45`
- guard_metric_delta: `-0.81`
- blocked_case_delta: `+0`
- pairwise_preferred_side: `baseline`
- pairwise_weighted_margin: `-28.00`
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None
- reasons: Core romance objectives did not improve on average., Continuity regressed beyond the safety threshold., Mind-state consistency regressed beyond the safety threshold., Redundancy regressed beyond the safety threshold., Average duration increased too much., Pairwise case preference favored the baseline.

## Average Deltas

| metric | delta |
| --- | ---: |
| romance_tension_score | -1.00 |
| relationship_progression_score | -0.20 |
| emotional_resonance_score | -0.20 |
| character_attraction_score | -0.38 |
| hook_score | -0.45 |
| continuity_score | -0.50 |
| redundancy_score | -1.64 |
| mind_state_consistency_score | -0.30 |

## Pairwise Preference

- overall_preferred_side: `baseline`
- candidate_case_wins: `0`
- baseline_case_wins: `1`
- tied_case_count: `0`
- weighted_margin: `-28.00`
- delta_threshold: `0.20`

| case_id | preferred | margin | candidate wins | baseline wins | guard failures | cost flags |
| --- | --- | ---: | --- | --- | --- | --- |
| romance_case_01_court_return | baseline | -28.00 | None | romance_tension_score, relationship_progression_score, emotional_resonance_score, character_attraction_score, hook_score, continuity_score, mind_state_consistency_score, redundancy_score | continuity_score, mind_state_consistency_score, redundancy_score | duration_seconds>+20 |
