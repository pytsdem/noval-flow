# Romance Eval Report: candidate_agency_microaction_case01

- mode: `fast`
- provider: `doubao`
- model: `doubao-seed-1-8-251228`
- generated_at: `2026-04-27T13:15:03.408260+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 7.50 |
| relationship_progression_score | 7.80 |
| emotional_resonance_score | 8.00 |
| character_attraction_score | 7.87 |
| hook_score | 8.30 |
| continuity_score | 8.30 |
| redundancy_score | 7.20 |
| mind_state_consistency_score | 8.40 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 7.50 | 男女主之间的拉扯、试探、回避成立，但更多依托旧案压力驱动，言情层面的暧昧、旧情余绪的张力偏弱，以权力场的对峙感为主。 |
| relationship_progression_score | 7.80 | 关系发生了有效变化，从朝堂上的纯粹敌对，转向谢临川对沈知微立场产生怀疑的复杂对峙，不再是单一的恨意。 |
| emotional_resonance_score | 8.00 | 情绪通过具体动作、细节传递，有真实感和余波，能钩住读者对两人隐秘情绪的好奇。 |
| character_attraction_score | 7.87 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.30 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.30 | 情节、情绪、关系承接自然，从朝堂奏请到内库查档再到结尾危机，逻辑链条顺畅，人设情绪连贯。 |
| redundancy_score | 7.20 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 8.40 | 男女主的行为、话语符合高自控的心智状态，没有突兀失控，人设稳定。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 7.20 |
| rule_redundancy_score | 8.60 |
| rule_anti_slop_score | 8.20 |
| hybrid_redundancy_score | 7.20 |

- strengths: 细节承载情绪能力强，旧疤、雪水、抖墨等具象细节让情绪真实可感；关系推进明确，从纯粹敌对到复杂对峙的转变清晰落地；首尾钩子设计有效，开头快速建立冲突，结尾抛出双重悬念；人设保持稳定，男女主的克制、隐忍符合身份与性格逻辑
- weaknesses: 言情张力偏弱，更多依托旧案权力压迫，男女主的情感余绪交锋不足；存在细节解释冗余，直白的心理总结削弱了含蓄感；女主主动性不足，多为被动应对，缺乏体现目的性的主动选择；双人同场的化学反应偏隐晦，缺乏直接的情绪碰撞点
- improvement_hints: 强化双人私人情绪交锋，增加细微的眼神、肢体互动，提升言情张力；删除重复的解释性文本，用动作、细节替代直白的心理总结；给女主增加主动行为，比如主动请缨监看谢临川，体现她的隐秘目的性；在结尾处具象化谢临川的疑问，用动作暗示他的下一步行动，强化尾钩的引导性
- cost: llm_calls=20, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=1381.82
