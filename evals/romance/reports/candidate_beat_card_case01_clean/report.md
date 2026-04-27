# Romance Eval Report: candidate_beat_card_case01_clean

- mode: `fast`
- provider: `doubao`
- model: `doubao-seed-1-8-251228`
- generated_at: `2026-04-26T18:37:07.122347+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.50 |
| relationship_progression_score | 8.00 |
| emotional_resonance_score | 8.20 |
| character_attraction_score | 8.25 |
| hook_score | 8.75 |
| continuity_score | 8.80 |
| redundancy_score | 8.84 |
| mind_state_consistency_score | 8.70 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 男女主之间的拉扯、试探、回避均成立，核心张力来自旧情余韵与隐秘在意，而非单纯朝堂权谋压迫。谢临川的刻意试探（提旧案、露旧伤）与沈知微的刻意冷淡（回避眼神、压下情绪）形成精准的情绪对抗，拉扯感扎实。 |
| relationship_progression_score | 8.00 | 本章关系发生明确有效变化：从谢临川单方面认定沈知微为“叛徒”的敌对状态，转向双向的困惑试探与互相牵制，关系定价明显更新。 |
| emotional_resonance_score | 8.20 | 情绪具体且有余波，全部落地在身体细节与场景感受上，无空泛抒情，能有效钩住读者的共情。 |
| character_attraction_score | 8.25 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.75 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.80 | 情节、情绪、关系与人设承接自然，无突兀跳变，逻辑闭环完整。 |
| redundancy_score | 8.84 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 8.70 | 角色行为、话语与回避方式完全符合当前心智状态，高克制人设没有过早失控，逻辑自洽。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 9.00 |
| rule_redundancy_score | 9.10 |
| rule_anti_slop_score | 8.20 |
| hybrid_redundancy_score | 8.84 |

- strengths: 旧情拉扯与权谋结合自然，言情张力未被权谋压制，核心冲突清晰；情绪全部落地在身体细节，无空泛抒情，共情力强；角色行为符合人设，心智状态一致，逻辑自洽；结尾钩子精准，直接关联核心矛盾，追读驱动力强
- weaknesses: 女主主动性稍弱，多为被动应对，缺乏主动布局的细节；双人互动的隐秘细节不足，电流感可进一步强化；男主的旧情动机支撑稍显单薄，缺乏碎片化回忆补充
- improvement_hints: 给女主增加主动布局的小动作，如刻意控制档册传递、暗中提醒风险，强化主体性；补充1-2处男女主的错位互动细节，如视线短暂纠缠、指尖擦过档册，增强化学反应；添加男主关于三年前的碎片化回忆，让他的“在意”更有依据，动机更立体；适当压缩朝堂流程描述，聚焦男女主的互动与情绪变化，提升节奏
- cost: llm_calls=18, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=1214.45
