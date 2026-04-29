# Romance Eval Diff: case02_compact_payload_drama vs cross_tone_smoke_prompt_beat_slim_case02_deepseek

- compared_at: `2026-04-28T13:28:01.383340+00:00`

## Average Delta

| metric | baseline | candidate | delta |
| --- | ---: | ---: | ---: |
| romance_tension_score | 8.20 | 8.00 | -0.20 |
| relationship_progression_score | 7.80 | 8.50 | +0.70 |
| emotional_resonance_score | 8.40 | 7.50 | -0.90 |
| character_attraction_score | 8.67 | 8.05 | -0.62 |
| hook_score | 9.00 | 8.25 | -0.75 |
| continuity_score | 9.00 | 9.00 | +0.00 |
| redundancy_score | 7.42 | 7.82 | +0.40 |
| mind_state_consistency_score | 9.00 | 9.00 | +0.00 |
| genre_fit_score | 9.20 | 8.50 | -0.70 |

- improved_metrics: redundancy_score；relationship_progression_score
- declined_metrics: character_attraction_score；emotional_resonance_score；genre_fit_score；hook_score
- blocked_case_delta: +0
- new_blocker_case_ids: None
- resolved_blocker_case_ids: None

## romance_case_02_xianxia_rival_trial - 心声同生契的规则秘境

- verdict: `pass` -> `pass`
| metric | delta |
| --- | ---: |
| romance_tension_score | -0.20 |
| relationship_progression_score | +0.70 |
| emotional_resonance_score | -0.90 |
| character_attraction_score | -0.62 |
| hook_score | -0.75 |
| continuity_score | +0.00 |
| redundancy_score | +0.40 |
| mind_state_consistency_score | +0.00 |
| genre_fit_score | -0.70 |

- cost_deltas: llm_calls=+0.00；patch_rounds=+0.00；duration_seconds=+9.70
- improved_metrics: relationship_progression_score；redundancy_score
- declined_metrics: emotional_resonance_score；character_attraction_score；hook_score；genre_fit_score
