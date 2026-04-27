# Romance Eval Report: deepseek_v4_pro_case01_candidate

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-27T14:48:10.080659+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.00 |
| relationship_progression_score | 7.50 |
| emotional_resonance_score | 7.00 |
| character_attraction_score | 7.50 |
| hook_score | 9.25 |
| continuity_score | 8.00 |
| redundancy_score | 7.83 |
| mind_state_consistency_score | 9.00 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.00 | 朝堂重逢中的拉扯感成立：沈知微的抬眼与迅速垂落、改称‘谢世子’的疏远、本能避开旧伤，谢临川的注视、攥拳与转而冷静试探，均构成高压下的克制角力。 |
| relationship_progression_score | 7.50 | 关系从单向的‘叛徒’恨意，进阶为‘怀疑她藏着恐惧’的互相试探，谢临川的定位成功转化为以冷静逼迫她的对手，但变化仍偏内化。 |
| emotional_resonance_score | 7.00 | 情绪具体，依托身体感受（雪水、膝盖旧痛、攥拳）和细微动作（睫毛颤、指节发白）传达，有余波，但部分段落偏重权谋对答，情感节奏稍被稀释。 |
| character_attraction_score | 7.50 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.25 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.00 | 情节、情绪、人设承接上一章自然，雪水未干与归京次日天气一致，谢临川的情绪转折在修补后已更平滑。 |
| redundancy_score | 7.83 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 谢临川高自控但允许在退殿时因接近她而轻微失控（低声刺探），符合其‘越受压越冷，但极限处有攻击性’的心智状态；沈知微全程以礼制压真实情绪，只留细微生理反应，人格稳定。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 8.00 |
| rule_redundancy_score | 8.40 |
| rule_anti_slop_score | 7.15 |
| hybrid_redundancy_score | 7.83 |

- strengths: 身体细节（雪水、旧伤、袖口褶皱）扎实，使情绪可感且避免空泛抒情；高压朝堂下的潜台词（称呼、避视、退礼）构成有效拉扯与误读张力；结尾书吏之死强力拉起悬疑，与旧案、双人关系紧密勾连；男主从报复到冷静试探的转变具有策略性，人设稳定且有魅力
- weaknesses: 言情拉扯以男主观察和内心为主，女主多为被动回避，双向互动不足；关系推进虽有变化，但停留在试探与在意层面，缺少更具体的代价或依赖升级；中段朝堂辩论篇幅略长，稀释了言情节奏和情绪浓度
- improvement_hints: 在礼制缝隙中让女主做出一次只有男主能意会的主动保护或破防；压缩技术性对白，将更多笔墨分配给二人极近距离的呼吸、停顿、视线交锋；利用书吏之死让男主瞬间将女主的挡回重新解读为‘保护’，深化关系定价；后续同场戏增加一次意外触碰或被迫对视，将内化的拉扯外化为显性电流
- cost: llm_calls=15, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1303.51
