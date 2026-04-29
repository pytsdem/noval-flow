# Romance Eval Report: candidate_beat_card_initiative_case01

- mode: `fast`
- provider: `doubao`
- model: `doubao-seed-1-8-251228`
- generated_at: `2026-04-27T13:56:18.975213+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 7.50 |
| relationship_progression_score | 8.00 |
| emotional_resonance_score | 8.00 |
| character_attraction_score | 7.45 |
| hook_score | 8.50 |
| continuity_score | 9.00 |
| redundancy_score | 8.84 |
| mind_state_consistency_score | 9.00 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 7.50 | 男女主之间的拉扯以旧案阴影下的戒备试探为主，通过回避动作、称呼变化传递克制的情绪博弈，但言情层面的暧昧张力偏弱，更多是权力与旧怨的压迫，而非恋爱对象间的欲望或旧情拉扯。 |
| relationship_progression_score | 8.00 | 本章关系发生了明确的动态变化，从谢临川单方面认定沈知微是“叛徒”的固化恨意，转变为他察觉沈知微的异常后，产生“她在怕什么”的怀疑，关系从单向敌对进入双向猜忌的博弈状态。 |
| emotional_resonance_score | 8.00 | 情绪通过具体的身体细节传递，冷硬压抑的氛围扎实，结尾书吏死亡的疑云留下明确的情绪余波，但言情层面的共情稍弱，更多是权谋压迫感。 |
| character_attraction_score | 7.45 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.50 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 9.00 | 情节承接顺滑，情绪与关系转变自然，人设保持统一，没有突兀的跳变或断裂。 |
| redundancy_score | 8.84 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 角色行为、话语均符合当前心智状态，高自控的人设没有出现过早失控的情况，情绪表达克制且合理。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 9.00 |
| rule_redundancy_score | 9.10 |
| rule_anti_slop_score | 8.20 |
| hybrid_redundancy_score | 8.84 |

- strengths: 细节扎实，用身体感受（冻僵的脚踝、腕间旧疤）传递情绪，代入感强；关系推进明确，从单向恨意转向双向猜忌，避免原地踏步；悬念设置有效，开头旧案悬念、结尾书吏死亡的新线索，钩子清晰；人设统一，男女主的冷硬与克制符合设定，无OOC行为
- weaknesses: 言情张力偏弱，更多是权力与旧案压迫，男女主的暧昧拉扯不足；女主主动性不足，以被动防守为主，主体性体现不够充分；情绪互动性弱，多为男主单向观察，缺乏女主对男主的情绪投射；部分环境描写稍显重复，可进一步凝练
- improvement_hints: 增加男女主私人化互动细节（如眼神交汇、指尖微颤），强化旧情残留的暧昧张力；给女主添加主动操控的小动作，体现她在旧案中的隐秘主导性；压缩重复环境描写，替换为双向情绪投射的细节；呼应上一章伏笔，强化前后章节的关联性
- cost: llm_calls=16, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1195.92
