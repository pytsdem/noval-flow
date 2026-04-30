# Romance Eval Diff: codex_case01_prose_surface_push_v2 vs sequential_beat_case01_deepseek

- compared_at: `2026-04-30T07:21:49.551504+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 9.20 | 5.00 | -4.20 |
| relationship_progression_score | 9.00 | 5.00 | -4.00 |
| emotional_resonance_score | 9.10 | 5.00 | -4.10 |
| character_attraction_score | 9.18 | 5.00 | -4.18 |
| hook_score | 9.65 | 5.00 | -4.65 |
| continuity_score | 9.00 | 5.00 | -4.00 |
| redundancy_score | 8.62 | 8.20 | -0.42 |
| mind_state_consistency_score | 9.40 | 5.00 | -4.40 |
| genre_fit_score | 0.00 | 5.00 | +5.00 |

- improved_metrics: genre_fit_score
- declined_metrics: character_attraction_score；continuity_score；emotional_resonance_score；hook_score；mind_state_consistency_score；redundancy_score；relationship_progression_score；romance_tension_score
- blocked_case_delta: +1
- new_blocker_case_ids: romance_case_01_court_return
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass` -> `blocked`
| metric | delta |
| --- | ---: |
| romance_tension_score | -4.20 |
| relationship_progression_score | -4.00 |
| emotional_resonance_score | -4.10 |
| character_attraction_score | -4.18 |
| hook_score | -4.65 |
| continuity_score | -4.00 |
| redundancy_score | -0.42 |
| mind_state_consistency_score | -4.40 |
| genre_fit_score | +5.00 |

- cost_deltas: llm_calls=+5.00；patch_rounds=+0.00；duration_seconds=+1509.86
- improved_metrics: genre_fit_score
- declined_metrics: romance_tension_score；relationship_progression_score；emotional_resonance_score；character_attraction_score；hook_score；continuity_score；redundancy_score；mind_state_consistency_score
