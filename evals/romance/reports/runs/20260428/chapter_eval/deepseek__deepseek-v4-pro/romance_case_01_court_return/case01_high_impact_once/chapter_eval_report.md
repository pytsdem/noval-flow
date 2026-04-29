# Romance Eval Report: case01_high_impact_once

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-28T15:05:16.259533+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.50 |
| relationship_progression_score | 8.00 |
| emotional_resonance_score | 9.00 |
| character_attraction_score | 8.65 |
| hook_score | 9.50 |
| continuity_score | 8.00 |
| redundancy_score | 7.20 |
| mind_state_consistency_score | 9.00 |
| genre_fit_score | 9.00 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 男女主拉扯明显，请婚包装成报复却暗含保护，沈知微的平静接旨刺中谢临川的旧怨与在意，形成‘越救越像恨’的误读张力。潜台词丰富，但部分烦躁独白略有重复。 |
| relationship_progression_score | 8.00 | 关系从纯粹仇敌向前推进为‘报复名义下的脆弱同盟’：赐婚落定、暗号泄露、谢临川得知杀机并暗中保护，沈知微意识到他无意中成了屏障。双方认知差距仍然存在，但连接已建立。 |
| emotional_resonance_score | 9.00 | 情绪克制但精准，通过动作、物象和沉默传递。余波强烈，如沈知微血流掌心、脉搏失控，谢临川最后勒住喉咙的窒息感，都让读者感受压迫而非解释。 |
| character_attraction_score | 8.65 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.50 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.00 | 承接第1章归京、密令，时间、人设、规则均一致。情绪流合理，从朝堂到内库到宫墙，空间移动推动情节。但部分场景转换略依赖巧合（谢临川恰好在内库出现），可稍加铺垫。 |
| redundancy_score | 7.20 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 高自控角色完美保持心智一致：谢临川在外人前冷硬，独处时才会泄露烦躁；沈知微极度克制，连失控也仅限指节泛白、血印。无突然崩盘或解释过度。 |
| genre_fit_score | 9.00 | 完美符合历史权谋言情与克制虐恋的双重承诺：权力压迫（赐婚、旧案、宫规）构成阻碍，情感克制而强烈，误读贯穿始终，暗线推进有力，结尾钩子沉重且意图虐心。没有甜宠或提前和解。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 7.50 |
| rule_redundancy_score | 6.70 |
| rule_anti_slop_score | 6.00 |
| hybrid_redundancy_score | 7.20 |

- strengths: 开场请婚冲击力极强，公共羞辱与私下保护的反差立即成立。；婚书暗号设计精妙，将灭口令、旧案线索、关系纽带集于一体，功能密集。；双主角心智高度自控，行为符合人设，情绪泄露精准且节制。；结尾双视角收束，悬念与情感同步升级，追读驱动力强。
- weaknesses: 谢临川‘你欠我’系列的威胁语意重复，削弱后续出现时的冲击力。；部分内心独白（如‘他并不知道自己替她拖住了第一刀’）略显直白，削弱了潜台词魅力。；场景转换时偶然性偶有显现（如突然出现在内库），可加强铺垫。
- improvement_hints: 将重复台词转化为独特的身体动作或物件处理，如他反复抚过婚书绢面代替说话。；削减沈知微的内心烛照式总结，依靠环境、他人反应或小动作透露她的认知。；通过增加谢临川线人在各节点汇报的形式，让他的突然出现具备“被引导”的合理性。
- cost: llm_calls=18, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1563.63
