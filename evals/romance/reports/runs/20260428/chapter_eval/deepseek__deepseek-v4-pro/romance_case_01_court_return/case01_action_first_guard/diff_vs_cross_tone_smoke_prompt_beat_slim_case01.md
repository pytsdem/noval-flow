# Romance Eval Diff: case01_action_first_guard vs cross_tone_smoke_prompt_beat_slim_case01

- compared_at: `2026-04-28T14:35:59.411288+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 8.50 | 8.50 | +0.00 |
| relationship_progression_score | 9.00 | 8.00 | -1.00 |
| emotional_resonance_score | 8.50 | 8.00 | -0.50 |
| character_attraction_score | 8.67 | 8.35 | -0.32 |
| hook_score | 9.10 | 9.00 | -0.10 |
| continuity_score | 9.00 | 8.00 | -1.00 |
| redundancy_score | 7.82 | 5.92 | -1.90 |
| mind_state_consistency_score | 9.00 | 8.50 | -0.50 |
| genre_fit_score | 9.00 | 9.00 | +0.00 |

- improved_metrics: None
- declined_metrics: character_attraction_score；continuity_score；emotional_resonance_score；mind_state_consistency_score；redundancy_score；relationship_progression_score
- blocked_case_delta: +0
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass` -> `needs_work`
| metric | delta |
| --- | ---: |
| romance_tension_score | +0.00 |
| relationship_progression_score | -1.00 |
| emotional_resonance_score | -0.50 |
| character_attraction_score | -0.32 |
| hook_score | -0.10 |
| continuity_score | -1.00 |
| redundancy_score | -1.90 |
| mind_state_consistency_score | -0.50 |
| genre_fit_score | +0.00 |

- cost_deltas: llm_calls=+4.00；patch_rounds=+1.00；duration_seconds=+597.48
- improved_metrics: None
- declined_metrics: relationship_progression_score；emotional_resonance_score；character_attraction_score；continuity_score；redundancy_score；mind_state_consistency_score
