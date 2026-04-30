# Romance Eval Diff: prose_surface_case01_exec_guard vs step8_contract_case01_prose

- compared_at: `2026-04-29T19:22:22.983884+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 6.50 | 7.80 | +1.30 |
| relationship_progression_score | 8.00 | 8.50 | +0.50 |
| emotional_resonance_score | 8.50 | 8.00 | -0.50 |
| character_attraction_score | 8.25 | 8.09 | -0.16 |
| hook_score | 9.25 | 9.25 | +0.00 |
| continuity_score | 9.00 | 8.50 | -0.50 |
| redundancy_score | 7.42 | 8.44 | +1.02 |
| mind_state_consistency_score | 9.00 | 9.00 | +0.00 |
| genre_fit_score | 9.50 | 9.00 | -0.50 |

- improved_metrics: redundancy_score；relationship_progression_score；romance_tension_score
- declined_metrics: continuity_score；emotional_resonance_score；genre_fit_score
- blocked_case_delta: +0
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `needs_work` -> `pass`
| metric | delta |
| --- | ---: |
| romance_tension_score | +1.30 |
| relationship_progression_score | +0.50 |
| emotional_resonance_score | -0.50 |
| character_attraction_score | -0.16 |
| hook_score | +0.00 |
| continuity_score | -0.50 |
| redundancy_score | +1.02 |
| mind_state_consistency_score | +0.00 |
| genre_fit_score | -0.50 |

- cost_deltas: llm_calls=-2.00；patch_rounds=-1.00；duration_seconds=+11.11
- improved_metrics: romance_tension_score；relationship_progression_score；redundancy_score
- declined_metrics: emotional_resonance_score；continuity_score；genre_fit_score
