# Romance Eval Report: prose_surface_case01

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-29T18:52:07.282681+00:00`
- cases: `1`
- verdict_counts: blocked=1
- blocked_case_ids: romance_case_01_court_return
- top_optimization_targets: prompts/writer/write_chapter_full.txt(3)；prompts/writer/plan_content_blocks.txt(2)；prompts/writer/build_character_mindset.txt(1)

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 6.50 |
| relationship_progression_score | 7.80 |
| emotional_resonance_score | 7.20 |
| character_attraction_score | 8.04 |
| hook_score | 8.40 |
| continuity_score | 3.50 |
| redundancy_score | 2.00 |
| mind_state_consistency_score | 6.50 |
| genre_fit_score | 6.80 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `blocked`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 6.50 | 主线拉扯分明：朝堂羞辱与轿前对峙都有强潜台词，但接旨—羞辱节拍被完整复刻，导致张力稀释放缓，削弱沉浸感。 |
| relationship_progression_score | 7.80 | 关系从公开报复推进到他无意中挡刀的认知颠覆，变化显著，但重审美化导致进展被拖慢。 |
| emotional_resonance_score | 7.20 | 克制动作与物件细节有效承载情绪，但重复接旨破坏余波。 |
| character_attraction_score | 8.04 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.40 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 3.50 | 时间线严重断裂：散朝后对话后再重复殿内接旨羞辱，事件先后顺序错乱，严重影响阅读沉浸。 |
| redundancy_score | 2.00 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 6.50 | 高自控人物在重复场景下行为毫无变化，显得僵化，但单次场景中的控制与裂痕均贴合设定。 |
| genre_fit_score | 6.80 | 文本质地符合‘历史权谋言情’的礼制压迫和‘克制虐恋’的压抑失误，但结构性重复损害了该类型应有的精密节奏。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 2.00 |
| rule_redundancy_score | 9.10 |
| rule_anti_slop_score | 9.35 |
| hybrid_redundancy_score | 2.00 |

| hard fail flag | severity | related_metrics |
| --- | --- | --- |
| continuity_break | blocker | continuity_score |
| mind_state_break | high | mind_state_consistency_score |
| redundancy_drag | high | redundancy_score |

| target_module | issue_type | severity | confidence |
| --- | --- | --- | ---: |
| prompts/writer/plan_content_blocks.txt | continuity | blocker | 0.90 |
| prompts/writer/write_chapter_full.txt | continuity | blocker | 0.90 |
| prompts/writer/plan_content_blocks.txt | redundancy | high | 0.95 |
| prompts/writer/write_chapter_full.txt | redundancy | high | 0.95 |
| prompts/writer/build_character_mindset.txt | mind_state_consistency | high | 0.76 |

- strengths: 开场用‘请旨赐婚’打破预期，张力立即拉满；沈知微接旨时的极度克制与随后点破杀局的冷感，形成高辨识度女主形象；谢临川避开腕伤、称呼转换等细节精准承载了未言明的情绪；轿前‘接旨比抗旨多活几个时辰’一语完成关系反转，埋下强钩子
- weaknesses: 接旨与羞辱段落重复出现，严重拖垮节奏和沉浸感；散朝后与殿内戏时间线错乱，导致连续断裂，读者易弃读；核心尾钩‘杀新妇’在正文中提前泄露，削弱了结尾危机感；重复段内人物行为无变化，让高自控显得僵滞而非有层次
- improvement_hints: 按线性时间重排：请婚→接旨+一次羞辱→散朝查副册→轿前对质，彻底删除重复段；保留唯一一次殿内对峙，集中所有有效对话与动作，不再闪回；确保‘杀新妇’七字仅在结尾或接近结尾处首次完整出现，前期只留疑笔；微调重复被删后，在保留段落中增加一次极小的身体细节升级，确保情绪递进感
- cost: llm_calls=21, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=1701.81
