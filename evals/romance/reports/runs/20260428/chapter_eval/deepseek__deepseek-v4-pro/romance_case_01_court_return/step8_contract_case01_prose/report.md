# Romance Eval Report: step8_contract_case01_prose

- mode: `fast`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-28T18:04:29.750069+00:00`
- cases: `1`
- verdict_counts: needs_work=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 6.50 |
| relationship_progression_score | 8.00 |
| emotional_resonance_score | 8.50 |
| character_attraction_score | 8.25 |
| hook_score | 9.25 |
| continuity_score | 9.00 |
| redundancy_score | 7.42 |
| mind_state_consistency_score | 9.00 |
| genre_fit_score | 9.50 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `needs_work`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 6.50 | 男主公开请婚的报复姿态与女主被迫接旨的平静形成拉扯，但紧张更多来自外部灭口压力和旧案暗号，两人间的直接情感试探和暧昧较弱。主要体现为男主对女主冷静的失控感，却缺少欲望、旧情或误读的深层火花。 |
| relationship_progression_score | 8.00 | 关系从朝堂赐婚的公开羞辱成功推进到夹道私下的程序交锋，男主从单纯报复者转向开始疑心婚书被动过的人，女主从被动接旨转为主动追问试探。两人地位、信息差和危险绑定均有明确变化。 |
| emotional_resonance_score | 8.50 | 情绪通过身体反应、环境细节和克制动作传递，余波强烈。读者能感受到灭口倒计时的窒息感、女主不敢暴露的恐惧和男主被平静刺伤的憋闷。 |
| character_attraction_score | 8.25 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.25 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 9.00 | 情节、情绪、关系承接自然：从前夜密令到朝堂赐婚，再到夹道追问和旧书阁验证，时间地点一致，人物行为逻辑连贯，没有突兀跳变。 |
| redundancy_score | 7.42 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 男女主的高自控状态稳定：谢临川虽被女主平静刺到，但从未失控暴躁；沈知微在灭口威胁下仍保持精准的礼法和程序反击，没有过早泄露恐惧或真实动机。 |
| genre_fit_score | 9.50 | 完美贴合古风权谋言情+克制虐恋：婚约、旧案、礼制压力、灭口暗号构成权谋背景；情感隐忍，所有保护都伪装成报复；潜台词强，没有直白告白或过早和解；意象如旧伤、墨香、叙旧有功能不堆砌。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 8.00 |
| rule_redundancy_score | 7.50 |
| rule_anti_slop_score | 5.10 |
| hybrid_redundancy_score | 7.42 |

- strengths: 强钩子：公开请婚和灭口暗号双重悬念开场，结尾杀新妇倒计时推拉强。；人物辨识度高：谢临川的北地风雪磨出来的冷硬与墨香回忆，沈知微的程序记忆与精准反击。；关系推进有层次：从表面羞辱转向程序交锋，暗线已在彼此试探中打开。；情绪落地扎实：全部用工整动作和环境细节承载压迫感和余波。
- weaknesses: 男女主直接的情感拉扯稍弱，外部危机抢占过多注意力，导致化学反应偏冷。；沈知微的过度平静可能让部分读者感到距离感，缺少一两个能瞬间打动人心的脆弱泄露。；部分心理独白或解释性句子可以进一步压减，让动作和停顿完全主导。
- improvement_hints: 在夹道对峙中增加一个双方同时被旧物触发（如墨香、旧疤）的瞬间沉默或呼吸变化，加热双人化学反应。；让沈知微在独自场景有一次极短暂的失态（如扶墙一下）再迅速恢复，平衡冷静中的脆弱。；尾部谢临川追原档前加一句与他初衷矛盾的自问，强化他无意的保护转折。
- cost: llm_calls=19, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1212.45
