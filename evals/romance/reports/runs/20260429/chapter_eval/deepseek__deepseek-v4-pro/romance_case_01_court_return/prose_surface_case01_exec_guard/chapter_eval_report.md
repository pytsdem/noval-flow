# Romance Eval Report: prose_surface_case01_exec_guard

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-29T19:22:22.978778+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 7.80 |
| relationship_progression_score | 8.50 |
| emotional_resonance_score | 8.00 |
| character_attraction_score | 8.09 |
| hook_score | 9.25 |
| continuity_score | 8.50 |
| redundancy_score | 8.44 |
| mind_state_consistency_score | 9.00 |
| genre_fit_score | 9.00 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 7.80 | 男女主之间的试探、回避和潜台词成立，尤其是在朝堂上那几句简短对话和拇指按婚书的动作中，恨意与保护欲交织，克制而有力。但缺少合约要求的腕伤回避、禁军扫视等高张力细节，使部分拉扯未能完全落地。 |
| relationship_progression_score | 8.50 | 本章将关系从仇敌悬置直接推进为公开婚约，且暗地里完成了从“背叛者-受害者”到“控制者-被护者”的重新定价，关系变化明确且代价高昂。 |
| emotional_resonance_score | 8.00 | 情绪推进紧凑，从开场压迫、赐婚冲击到结尾“杀新妇”的倒计时钩子，都留下了清晰的余波，尤其是婚书上浮出的死期令读者瞬间绷紧。 |
| character_attraction_score | 8.09 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.25 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.50 | 承接上章归京前夜的密令和旧案压力，本章在同日早朝自然展开，情绪和情节都顺滑延续，无突兀跳跃。 |
| redundancy_score | 8.44 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 高自控人设保持稳定：谢临川即便被沈知微的平静刺到，也只体现在观察的锐利和后续行动加速，未失控；沈知微全程用礼数掩护恐惧，无破绽。 |
| genre_fit_score | 9.00 | 文本完全契合古风权谋言情与克制虐恋的读者承诺：克制的情感张力、权力逼迫、误读与旧怨、暗线推进、结尾强钩子，且避免甜宠、直白和解。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 8.50 |
| rule_redundancy_score | 9.30 |
| rule_anti_slop_score | 8.20 |
| hybrid_redundancy_score | 8.44 |

- strengths: 开局钩子极其精准，反预期请旨迅速钉住读者注意力。；双人潜台词战场扎实，恭顺与冷语间的压差持续制造燃点。；结尾倒计时钩子刚猛，将赐婚从报复假象翻转成生死命题，追读力极强。；男主压迫感和女主克制自保的形象鲜明，同场戏有化学。
- weaknesses: 遗漏合约要求的腕上旧伤回避和接旨前注视禁军两个关键身体线索，削弱了部分拉力和女主的警觉层次。；人性痛感锚点“雪水未干”未在正文出现，开场身体质感稍显不足。；女主在中段的主动性较弱，多在应对而非暗中布局，导致辨识度略逊。
- improvement_hints: 在赐婚段落前插入沈知微扫视殿外禁军和谢临川目光避开她腕伤的微小动作，以补实线索和张力。；在开场加入鞋底雪水渗入的触感或袍摆潮湿的细节，将身体负担变为可见压力。；让沈知微在接旨后利用赐婚规则暗记旧配殿路径或观察禁军换防，给她一个无声的主动筹划行为，强化女主主体性。；确保所有新增内容保持有限视角和不解释的纪律，以免破坏克制虐恋的潜台词氛围。
- cost: llm_calls=17, judge_llm_calls=1, review_calls=2, patch_rounds=0, used_full_rewrite=false, duration_seconds=1223.56
