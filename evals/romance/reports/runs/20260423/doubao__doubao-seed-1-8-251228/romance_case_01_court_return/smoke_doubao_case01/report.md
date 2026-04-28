# Romance Eval Report: smoke_doubao_case01

- mode: `fast`
- provider: `doubao`
- model: `doubao-seed-1-8-251228`
- generated_at: `2026-04-23T03:03:37.148710+00:00`
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
| hook_score | 8.30 |
| continuity_score | 8.80 |
| redundancy_score | 9.00 |
| mind_state_consistency_score | 8.70 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 男女主之间的拉扯、试探、回避、压迫均成立，旧情残留与恨意交织，所有张力都围绕两人的私人关系展开，而非单纯权谋对峙。女主刻意用疏远称呼、回避旧伤构建防线，男主在礼制约束下的试探暗藏对旧情的执念，形成了克制又尖锐的情感拉扯。 |
| relationship_progression_score | 8.00 | 本章关系发生了明确的有效变化：从开篇男主对女主的“绝对背叛认定”，转向结尾的“怀疑与牵制”；从朝堂上的公开敌对，变成皇帝下令后的被迫近距离共处，关系从“对立”升级为“高危绑定”。 |
| emotional_resonance_score | 8.20 | 情绪通过身体细节传递，具体且有余波，能精准钩住读者的共情。没有直白抒情，所有情绪都藏在动作、体感和环境联动中，比如男主的湿靴冷意对应他的屈辱处境，虎口疤的发烫对应旧情残留。 |
| character_attraction_score | 8.25 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.30 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.80 | 情节、情绪、关系承接自然顺畅，没有突兀跳变。男主的怀疑、关系的转变都有细节铺垫，逻辑链完整。 |
| redundancy_score | 9.00 | 以 romance judge 为主分，规则检测只用于向下修正，不再允许规则层把坏重复救高。 |
| mind_state_consistency_score | 8.70 | 角色行为、话语符合当前心智状态，没有突兀失控。男主的隐忍、女主的克制都贯穿始终，符合两人的身份与处境。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 9.00 |
| rule_redundancy_score | 9.10 |
| hybrid_redundancy_score | 9.00 |

- strengths: 用身体细节传递情绪，避免直白抒情，让情感真实可感，比如男主的湿靴冷意、虎口疤发烫，女主的笔锋停顿、墨痕等细节；男女主的拉扯充满潜台词，旧情与恨意交织，张力十足，所有互动都围绕私人关系展开，而非单纯权谋；情节推进与关系转变同步，每一个权谋动作都推动关系升级，比如提查档导致两人被迫近距离共处；结尾钩子强，多重悬念叠加，直接推动下一章阅读欲望
- weaknesses: 女主的主动性不足，大部分是被动应对，缺少体现她立场的主动行为；男主的怀疑虽有铺垫，但不够具象，逻辑链可更清晰；双人同场的电流感可进一步强化，缺少更细腻的肢体或气息互动；开头钩子可更直接，切入核心关系的速度有待提升
- improvement_hints: 增加女主的主动行为，比如她主动提出陪同查档的规矩细节，体现她的立场与保护欲；让男主的怀疑更具象，比如关联女主袖口皱痕与昨夜的细节，强化怀疑的逻辑支撑；增加双人同场的细微互动，比如递档册时指尖的擦肩而过、女主听到证词时的呼吸微滞；开头直接切入旧关系回忆，更快锚定“旧情恩怨”的核心，提升钩子的抓力
- cost: llm_calls=18, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1178.18
