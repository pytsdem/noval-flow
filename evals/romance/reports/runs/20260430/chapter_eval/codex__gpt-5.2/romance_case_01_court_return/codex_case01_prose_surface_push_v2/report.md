# Romance Eval Report: codex_case01_prose_surface_push_v2

- mode: `deep`
- provider: `codex`
- model: `gpt-5.2`
- generated_at: `2026-04-30T07:21:49.544982+00:00`
- cases: `1`
- verdict_counts: blocked=1
- blocked_case_ids: romance_case_01_court_return
- top_optimization_targets: prompts/writer/write_chapter_full.txt(3)；evals/romance/judges/llm_judge.py(1)；evals/romance/prompts/romance_chapter_judge.txt(1)；prompts/writer/build_character_mindset.txt(1)；prompts/writer/plan_content_blocks.txt(1)

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 5.00 |
| relationship_progression_score | 5.00 |
| emotional_resonance_score | 5.00 |
| character_attraction_score | 5.00 |
| hook_score | 5.00 |
| continuity_score | 5.00 |
| redundancy_score | 8.20 |
| mind_state_consistency_score | 5.00 |
| genre_fit_score | 5.00 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `blocked`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| relationship_progression_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| emotional_resonance_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| character_attraction_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| hook_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| continuity_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| redundancy_score | 8.20 | LLM judge 失败，本项退化为规则型重复/anti-slop 检测。 |
| mind_state_consistency_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |
| genre_fit_score | 5.00 | LLM judge 失败，使用中性降级分数 5.0。此分数只用于保留报告结构，不建议据此做趋势判断。 |

| redundancy view | score |
| --- | ---: |
| rule_redundancy_score | 8.20 |
| rule_anti_slop_score | 8.20 |
| hybrid_redundancy_score | 8.20 |

| hard fail flag | severity | related_metrics |
| --- | --- | --- |
| continuity_break | high | continuity_score |
| hook_underpowered | high | hook_score |
| mind_state_break | high | mind_state_consistency_score |
| relationship_progression_break | high | relationship_progression_score |
| romance_pull_weak | high | romance_tension_score, emotional_resonance_score |

| target_module | issue_type | severity | confidence |
| --- | --- | --- | ---: |
| evals/romance/judges/llm_judge.py | judge_reliability | high | 0.92 |
| evals/romance/prompts/romance_chapter_judge.txt | judge_reliability | high | 0.92 |
| prompts/writer/plan_content_blocks.txt | continuity | high | 0.76 |
| prompts/writer/write_chapter_full.txt | continuity | high | 0.76 |
| prompts/writer/build_character_mindset.txt | mind_state_consistency | high | 0.76 |

- strengths: None
- weaknesses: LLM judge 未返回可用结果，本次使用降级分数。
- improvement_hints: 先修复 judge 输出，再重新跑评测以获取可靠趋势。
- cost: llm_calls=25, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=3278.66
- errors: romance_judge_failed: [WinError 32] 另一个程序正在使用此文件，进程无法访问。: 'C:\\Users\\19237\\workspace\\noval-flow\\data\\codex_cli_l1ub6czl.txt'
