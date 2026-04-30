# Romance Eval Diff: prose_surface_case01 vs step8_contract_case01_prose

- compared_at: `2026-04-29T18:52:07.287499+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 6.50 | 6.50 | +0.00 |
| relationship_progression_score | 8.00 | 7.80 | -0.20 |
| emotional_resonance_score | 8.50 | 7.20 | -1.30 |
| character_attraction_score | 8.25 | 8.04 | -0.21 |
| hook_score | 9.25 | 8.40 | -0.85 |
| continuity_score | 9.00 | 3.50 | -5.50 |
| redundancy_score | 7.42 | 2.00 | -5.42 |
| mind_state_consistency_score | 9.00 | 6.50 | -2.50 |
| genre_fit_score | 9.50 | 6.80 | -2.70 |

- improved_metrics: None
- declined_metrics: continuity_score；emotional_resonance_score；genre_fit_score；hook_score；mind_state_consistency_score；redundancy_score
- blocked_case_delta: +1
- new_blocker_case_ids: romance_case_01_court_return
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `needs_work` -> `blocked`
| metric | delta |
| --- | ---: |
| romance_tension_score | +0.00 |
| relationship_progression_score | -0.20 |
| emotional_resonance_score | -1.30 |
| character_attraction_score | -0.21 |
| hook_score | -0.85 |
| continuity_score | -5.50 |
| redundancy_score | -5.42 |
| mind_state_consistency_score | -2.50 |
| genre_fit_score | -2.70 |

- cost_deltas: llm_calls=+2.00；patch_rounds=+1.00；duration_seconds=+489.36
- new_blockers: continuity_break
- improved_metrics: None
- declined_metrics: emotional_resonance_score；hook_score；continuity_score；redundancy_score；mind_state_consistency_score；genre_fit_score
