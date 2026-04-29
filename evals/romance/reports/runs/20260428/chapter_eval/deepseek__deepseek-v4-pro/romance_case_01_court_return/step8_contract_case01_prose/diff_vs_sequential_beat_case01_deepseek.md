# Romance Eval Diff: step8_contract_case01_prose vs sequential_beat_case01_deepseek

- compared_at: `2026-04-28T18:05:00.889945+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 9.20 | 6.50 | -2.70 |
| relationship_progression_score | 9.00 | 8.00 | -1.00 |
| emotional_resonance_score | 9.10 | 8.50 | -0.60 |
| character_attraction_score | 9.18 | 8.25 | -0.93 |
| hook_score | 9.65 | 9.25 | -0.40 |
| continuity_score | 9.00 | 9.00 | +0.00 |
| redundancy_score | 8.62 | 7.42 | -1.20 |
| mind_state_consistency_score | 9.40 | 9.00 | -0.40 |
| genre_fit_score | 0.00 | 9.50 | +9.50 |

- improved_metrics: genre_fit_score
- declined_metrics: character_attraction_score；emotional_resonance_score；hook_score；mind_state_consistency_score；redundancy_score；relationship_progression_score；romance_tension_score
- blocked_case_delta: +0
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass` -> `needs_work`
| metric | delta |
| --- | ---: |
| romance_tension_score | -2.70 |
| relationship_progression_score | -1.00 |
| emotional_resonance_score | -0.60 |
| character_attraction_score | -0.93 |
| hook_score | -0.40 |
| continuity_score | +0.00 |
| redundancy_score | -1.20 |
| mind_state_consistency_score | -0.40 |
| genre_fit_score | +9.50 |

- cost_deltas: llm_calls=-1.00；patch_rounds=+0.00；duration_seconds=-556.35
- improved_metrics: genre_fit_score
- declined_metrics: romance_tension_score；relationship_progression_score；emotional_resonance_score；character_attraction_score；hook_score；redundancy_score；mind_state_consistency_score
