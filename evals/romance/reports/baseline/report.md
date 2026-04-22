# Romance Eval Report: baseline

- mode: `fast`
- provider: `codex`
- model: `gpt-5.2`
- generated_at: `2026-04-22T18:28:31.671874+00:00`
- cases: `2`

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 8.70 |
| relationship_progression_score | 8.10 |
| emotional_resonance_score | 8.35 |
| character_attraction_score | 8.34 |
| hook_score | 8.85 |
| continuity_score | 8.50 |
| redundancy_score | 8.21 |
| mind_state_consistency_score | 8.75 |

## romance_case_01_court_return - 旧案重逢的朝堂试探

| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.70 | 拉扯成立且高压：两人同场被礼制钉死，情绪只能从“称呼、停顿、目光落点、笔锋失手”里泄出来。男主把刀藏在规矩里去逼反应，女主用更冷的规矩回击并把破绽压回去，敌意与在意互相绞着走，读者能清楚感到“谁先动就输”。 |
| relationship_progression_score | 8.00 | 关系有有效变化：从“未正式碰面、只在想象里定罪”推进到“殿前公开对峙+形成新的互相牵制规则”。男主拿到查档口子，同时第一次被女主的称呼与身体反应刺到，态度从纯报复更明显转向冷静、危险的试探；女主则把两人关系重新定价为必须用礼制硬封的高危对象。 |
| emotional_resonance_score | 8.30 | 情绪推进具体且有余波：从入殿的冷痛与羞辱压迫，推进到称呼刺痛带来的失衡，再到“准查旧档”的短暂开口与随即更冷的危险回灌，结尾以死亡消息把寒意从情绪转成现实威胁，读者会想立刻看下一步怎么查、怎么活。 |
| character_attraction_score | 8.23 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.85 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.40 | 承接自然、规矩边界稳：紧接上章“次日入殿”，男主未平反的处境与殿前禁忌贯彻到他的措辞策略；女主不失态、只在细微处泄漏；皇帝裁示设限也符合世界规则，整体连贯可信。 |
| redundancy_score | 8.31 | 由 romance judge 与规则型重复检测混合得出。 |
| mind_state_consistency_score | 8.70 | 心智一致性强：两位高自控人物都没有无理由失控。男主被刺到但迅速压回并继续按规矩推进；女主出现停顿与笔锋失手，但立刻归位到礼制与例条，符合“越心乱越冷更守礼”的设定。 |

- strengths: 礼制高压下的潜台词拉扯很硬，称呼与笔锋细节能让读者自动起疑；男主“用规矩当刀”的推进方式有连载感：每一步都在为后续查案铺路；尾钩把“旧案危险”从氛围落到人命与封口，追读驱动力强
- weaknesses: 同类冷感与静默的表达略多，局部像在重复加压而非持续升级变化；女主的主体性目前主要是“顶回去”，主动改局面的动作还不够清晰；中段对“谢世子”刺痛的强调略重复，若不加新变化容易磨损锋利度
- improvement_hints: 下一章让女主以程序名义做一次主动布局（不解释动机），把她从“冷”升级为“能改路径的人”；把重复的氛围句子换成更具体的动作后果（监陪重排、档册流转、旁观者的微反应），用变化制造更强升级；让男主在得知书吏之死后立刻调整策略（仍合规），把魅力从“能忍”推到“能算、能狠、能活”
- cost: llm_calls=21, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=3694.14

## romance_case_02_sickbed_truce - 雨夜药庐的被迫共处

| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.70 | “救命”和“审问”同场推进得很紧：顾砚用冷命令与断句把求生伪装成上位试探，林晚用医嘱与规矩挡回去却不得不贴身处理伤口；旧铜钱、旧疤、残页让两人的停顿与回避都带潜台词，靠近是被逼的、拉开是硬撑的，拉扯成立且有压迫感。 |
| relationship_progression_score | 8.20 | 关系有清晰变化：从“互疑旧识”推进到“仍互疑但已出现实际依赖与同战壕动作”。顾砚伤到走不出巷口，林晚不止救治，还把他藏进内室、清痕、压声控光；他也开始替她预备说辞，说明他把她的风险算进去了，但信任并未建立，符合连载推进。 |
| emotional_resonance_score | 8.40 | 情绪落在身体与环境里，不靠抒情堆词：疼痛、热血烫指、控声控光的紧绷把“压着不说的心软”写得具体；结尾暗号敲门把读者情绪吊在门闩上，余波够强，能推下一章。 |
| character_attraction_score | 8.45 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.85 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 8.60 | 承接与约束整体自然：夜禁、不能惊动外人、伤势必须留宿都通过动作闭环落实；物件状态也跟得住（铜钱入袖、残页入柜），章节末的空间位置与风险都能无缝接下一章。 |
| redundancy_score | 8.12 | 由 romance judge 与规则型重复检测混合得出。 |
| mind_state_consistency_score | 8.80 | 两人的心智与行为一致性强：顾砚高自控、越痛越短越硬，试探藏在职责口吻里且不突然失控；林晚越害怕越沉，用规矩与动作挡情绪，不解释、不摊牌；暗号出现时她的选择链条也符合“先控住他、再面对外部风险”的生存逻辑。 |

- strengths: 救命与审问同场，张力持续不松；铜钱+残页把悬疑线与旧情残响绑得很紧，物件驱动有效；夜禁控声控光的细节让“藏人一夜”的压迫可信；结尾暗号敲门悬停够狠，强力推动追读
- weaknesses: 部分节拍与意象重复（压灯、雨声、侧耳确认），中段略规律化；关系推进主要落在“被迫留宿/共同藏匿”，还缺一次更硬的互相让步或站队回报；清理痕迹段落信息密但略接近动作清单，压迫感有轻微平台期
- improvement_hints: 补一处“互相保护/互相让步”的可验证小回报（不洗清怀疑），让关系重标价更明确；压缩重复的环境控制动作，用更独特的外部微讯号替换同类描写；让试探更多落在称呼、物件交换、误读对撞上，少靠点题式问句；为下一章“开门后的第一应对”埋一个可立刻启用的动作伏笔（不解释暗号身份）
- cost: llm_calls=18, judge_llm_calls=1, review_calls=4, patch_rounds=2, used_full_rewrite=false, duration_seconds=2977.48

## Run Errors

- romance_case_03_betrothal_banquet: [Errno 22] Invalid argument
