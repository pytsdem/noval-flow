# Romance Eval Report: cross_tone_smoke_prompt_beat_slim_case01

- mode: `fast`
- provider: `doubao`
- model: `ep-m-20260319020545-gzfvt`
- generated_at: `2026-04-28T06:50:39.903525+00:00`
- cases: `1`
- verdict_counts: pass=1
- blocked_case_ids: None
- top_optimization_targets: None

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.50 |
| relationship_progression_score | 9.00 |
| emotional_resonance_score | 8.50 |
| character_attraction_score | 8.67 |
| hook_score | 9.10 |
| continuity_score | 9.00 |
| redundancy_score | 7.82 |
| mind_state_consistency_score | 9.00 |
| genre_fit_score | 9.00 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 男女主之间的拉扯、试探与克制性压迫成立，以旧恨为底色，藏着未明的在意与隐秘的依赖，符合「克制虐恋」的情绪设定。没有直白暧昧，但通过动作细节传递出错位的情绪张力。 |
| relationship_progression_score | 9.00 | 关系发生了明确且关键的变化：从朝堂上的仇人证人关系，转为名义上的未婚夫妻，且从「谢临川单方面报复」变为「两人绑定成危机共同体」，推进逻辑清晰。 |
| emotional_resonance_score | 8.50 | 情绪通过动作细节落地，而非直白抒情，有余波留存，能钩住读者对角色处境的共情。克制的情绪表达符合「restrained_angst」的要求。 |
| character_attraction_score | 8.67 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.10 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 9.00 | 情节、情绪、人设承接自然，没有突兀跳变，旧伤、暗痕等设定前后统一，逻辑闭环完整。 |
| redundancy_score | 7.82 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 角色行为、话语符合当前心智状态，高自控人物的失控有合理触发点，没有逻辑失真。 |
| genre_fit_score | 9.00 | 完全符合「historical_romance_intrigue」（古风权谋言情）与「restrained_angst」（克制虐恋）的设定，兑现了「隐忍误会、权谋绑定、爱而不能言」的读者承诺。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 8.50 |
| rule_redundancy_score | 8.20 |
| rule_anti_slop_score | 5.10 |
| hybrid_redundancy_score | 7.82 |

- strengths: 拉扯感通过具象动作落地，克制中藏着强烈情绪张力，符合克制虐恋的核心要求；关系推进明确，从仇人到危机共同体的转变逻辑清晰，有实质变化；开头结尾钩子强劲，悬念密集，具备强追读性；人设立体，男女主均非标签化角色，行动逻辑自洽
- weaknesses: 部分朝堂权谋描写占比略高，挤压了男女主互动的篇幅，言情张力可更聚焦；女主的主动性体现不足，多为被动自保，缺乏主动推动关系或剧情的细节；双人同场的直接互动较少，多为单向压迫，双向试探的细节不够；存在直白心理解释信号
- improvement_hints: 压缩非核心权谋描写，增加男女主私下的错位互动细节（如隔空观察、隐晦传递信息），强化双向拉扯；给女主增加主动试探的动作，比如故意留下旧案线索给谢临川，或利用婚约主动获取信息；把权谋线索（如灭口指令、旧案证据）更紧密地绑定到男女主关系上，让权谋成为推动言情的工具而非独立线；先清掉“她知道/他意识到/这让她更明白”类句式，再把篇幅换成新动作、新误读和新关系代价。
- cost: llm_calls=17, judge_llm_calls=1, review_calls=3, patch_rounds=1, used_full_rewrite=false, duration_seconds=1182.64
