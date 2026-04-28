# Cross-Tone Smoke Prompt/Beat Slim Summary

- date: `2026-04-28`
- scope: three single-case chapter evals; case01 Doubao, case02/03 DeepSeek
- caveat: mixed providers, not a clean provider A/B

| case | provider | verdict | tension | progression | hook | redundancy | genre_fit | llm_calls | gen_prompt | duration | final_chars | blocks | patched |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| romance_case_01_court_return | doubao | pass | 8.50 | 9.00 | 9.10 | 7.82 | 9.00 | 17 | 202700 | 1182.64 | 3504 | 4 | 2 |
| romance_case_02_xianxia_rival_trial | deepseek | pass | 8.20 | 7.80 | 9.00 | 7.42 | 9.20 | 18 | 279843 | 1639.99 | 9680 | 4 | 2 |
| romance_case_03_urban_reunion_comedy | deepseek | pass | 8.20 | 8.40 | 8.90 | 8.17 | 9.20 | 16 | 240464 | 1185.57 | 6897 | 3 | 1 |

## Conclusion

- quality: all three cases passed; genre/tone generalization looks viable.
- cost: still heavy; `llm_calls` stayed at `16-18`, generation prompt chars stayed at `202k-280k` per case.
- main issue: length/beat overrun, especially case02 final `9680` chars and case03 repeated final block before patch.
- DeepSeek: case02/03 quality is strong but slow; no same-case A/B, so no claim that it is better than Doubao.
- next step: enforce target length and per-beat stop conditions; stop later beats from re-narrating delivered events.
