# Romance Eval Report: case01_action_first_guard

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-28T14:35:59.409284+00:00`
- cases: `1`
- verdict_counts: needs_work=1
- blocked_case_ids: None
- top_optimization_targets: prompts/writer/plan_content_blocks.txt(1)；prompts/writer/write_chapter_full.txt(1)

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.50 |
| relationship_progression_score | 8.00 |
| emotional_resonance_score | 8.00 |
| character_attraction_score | 8.35 |
| hook_score | 9.00 |
| continuity_score | 8.00 |
| redundancy_score | 5.92 |
| mind_state_consistency_score | 8.50 |
| genre_fit_score | 9.00 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `needs_work`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 男女主在朝堂、偏殿两场同场戏中，通过质问、回避、称呼变化和身体细节实现了高强度潜台词拉扯。谢临川的报复性逼问与沈知微的疏离回应形成双向压迫，而婚书背后共同的灭口危机让这场拉扯从个人恩怨升级为生死共担，完全符合 restrained_angst 的要求。 |
| relationship_progression_score | 8.00 | 关系从朝堂上众人眼中的报复婚约，经婚书暗号揭示，到偏殿中‘无意生路’的给出，最后在谢临川看到杀令后主动下令保护，完成了从对立到高危同盟的实质性转变。每一步都有新的代价和新的依赖。 |
| emotional_resonance_score | 8.00 | 情绪完全通过动作、停顿、环境和物件传递，如靴底雪水、金砖血滴、婚书纸边割手、偏殿水印和脚步声，克制而具体。结尾‘先活过子时’留下很强的余波，让读者在压迫感中感受到一种未说出口的保护欲。 |
| character_attraction_score | 8.35 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.00 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.00 | 从朝堂到偏殿到内库到营帐再回住所，时间线一气呵成，情绪承接自然，事件环环相扣。旧伤、称呼、禁军观察等元素被复现但每次都带来新的意义，没有断裂感。 |
| redundancy_score | 5.92 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 8.50 | 两个角色心智高度一致：谢临川始终保持冷硬外壳，只在袖中、喉结、视线失控等机械性细节中微量泄漏；沈知微自始至终以过度平静包裹恐惧，她的观察、忍耐和快速计算都未突破生存本能的边界。 |
| genre_fit_score | 9.00 | 文本精准兑现了 historical_romance_intrigue 和 restrained_angst 的双重承诺：权力场中的婚约压迫、旧案暗线、误读与试探，情感表达极度克制，所有起伏都发生在礼制之下和潜台词之中，毫无甜宠或直白煽情。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 6.50 |
| rule_redundancy_score | 5.60 |
| rule_anti_slop_score | 3.60 |
| hybrid_redundancy_score | 5.92 |

| hard fail flag | severity | related_metrics |
| --- | --- | --- |
| redundancy_drag | high | redundancy_score |

| target_module | issue_type | severity | confidence |
| --- | --- | --- | ---: |
| prompts/writer/plan_content_blocks.txt | redundancy | high | 0.77 |
| prompts/writer/write_chapter_full.txt | redundancy | high | 0.77 |

- strengths: 公开请婚与婚书暗号双钩子强力拉动追读，节奏紧凑。；男女主双人同场戏通过简短对话和回避动作产生极高潜台词张力。；情绪完全由身体、物件和空间细节承载，无直白煽情却余波强烈。；结尾多线倒计时（灭口、脚步声、召见）形成不可抗拒的下一章牵引。
- weaknesses: 婚书背面的‘今夜子时，杀新妇’信息被重复揭示多次，冗余削弱了初次冲击。；沈知微在独自场景中的内心活动偶尔偏向概述（如‘她得想办法活过今夜’），削弱了沉浸感。；偏殿对话中‘你可愿意’的二次出现与殿前那次虽功能不同，但仍产生轻微重复感。；存在直白心理解释信号
- improvement_hints: 合并或删减婚书暗号的重复展示，确保该信息只被关键视角发现一次。；将沈知微的内心决断转化为更具体的动作选择或记忆闪回，避免概述句。；在偏殿问答处，可替换一种不同性质的逼问（如直接问‘你怕什么’），避免与殿前问题形式雷同。；先清掉“她知道/他意识到/这让她更明白”类句式，再把篇幅换成新动作、新误读和新关系代价。
- cost: llm_calls=21, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=1780.12
