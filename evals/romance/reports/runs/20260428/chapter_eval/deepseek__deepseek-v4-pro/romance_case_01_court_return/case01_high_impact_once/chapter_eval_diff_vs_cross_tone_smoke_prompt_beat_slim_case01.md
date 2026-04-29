# Romance Eval Diff: case01_high_impact_once vs cross_tone_smoke_prompt_beat_slim_case01

- compared_at: `2026-04-28T15:05:16.262532+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 8.50 | 8.50 | +0.00 |
| relationship_progression_score | 9.00 | 8.00 | -1.00 |
| emotional_resonance_score | 8.50 | 9.00 | +0.50 |
| character_attraction_score | 8.67 | 8.65 | -0.02 |
| hook_score | 9.10 | 9.50 | +0.40 |
| continuity_score | 9.00 | 8.00 | -1.00 |
| redundancy_score | 7.82 | 7.20 | -0.62 |
| mind_state_consistency_score | 9.00 | 9.00 | +0.00 |
| genre_fit_score | 9.00 | 9.00 | +0.00 |

- improved_metrics: emotional_resonance_score；hook_score
- declined_metrics: continuity_score；redundancy_score；relationship_progression_score
- blocked_case_delta: +0
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass` -> `pass`
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

- cost_deltas: llm_calls=+1.00；patch_rounds=+0.00；duration_seconds=+380.99
- improved_metrics: emotional_resonance_score；hook_score
- declined_metrics: relationship_progression_score；continuity_score；redundancy_score
