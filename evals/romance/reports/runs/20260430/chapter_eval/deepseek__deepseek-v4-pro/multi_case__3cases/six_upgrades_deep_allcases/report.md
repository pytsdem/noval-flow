# Romance Eval Report: six_upgrades_deep_allcases

- mode: `deep`
- provider: `deepseek`
- model: `deepseek-v4-pro`
- generated_at: `2026-04-30T05:07:36.992296+00:00`
- cases: `2`
- verdict_counts: blocked=1；pass=1
- blocked_case_ids: romance_case_01_court_return
- top_optimization_targets: prompts/writer/plan_content_blocks.txt(3)；prompts/writer/write_chapter_full.txt(3)

## Average Scores

| metric | score |
| --- | ---: |
| romance_tension_score | 7.50 |
| relationship_progression_score | 8.25 |
| emotional_resonance_score | 7.00 |
| character_attraction_score | 7.55 |
| hook_score | 8.88 |
| continuity_score | 5.00 |
| redundancy_score | 8.00 |
| mind_state_consistency_score | 8.50 |
| genre_fit_score | 8.50 |

## romance_case_01_court_return - 围宫请婚的旧案重逢

- verdict: `blocked`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 6.50 | 拉扯感成立但偏冷，主要靠恨意和权谋驱动，缺少暧昧、试探与情感电流。谢临川用旧案逼问，沈知微以礼数疏离，本质是躲闪而非真正的恋爱拉扯。尽管双方存在旧情残余的潜台词，但页上未兑现为有效的双向波动。 |
| relationship_progression_score | 8.00 | 关系发生了明确且多维的变化：从旧案仇敌变为“全京城眼中的报复未婚夫妻”，并且因婚书暗号而实际上打开了救命同盟的可能。关系定价被重新确立，且谢临川发现灭口威胁后，掌控意图出现裂痕，为下一章的进一步变化留足了空间。 |
| emotional_resonance_score | 6.00 | 情绪克制但解释性语句削弱了沉浸感，余波的拉力不足。谢临川的失控被概括为“像被捅到旧伤口的条件反射”，宣告了情绪种类却未留给读者咀嚼空间。沈知微全程近乎工具化的冷静，缺少能引发共情的内心波动。 |
| character_attraction_score | 6.55 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 8.75 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 3.00 | 存在严重的连续性断裂：婚书在第二块被沈知微收入袖口，第三块中她已带着婚书离开，第四块婚书却凭空出现在御案上让谢临川拿起，物品位置矛盾。此外，沈知微独自告退到被禁军依仪程送出宫之间缺少过渡。 |
| redundancy_score | 7.00 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 8.00 | 角色行为与预设心智状态高度契合。谢临川高自控下出现缝隙，但整体仍保持冷硬；沈知微在巨大恐惧中用过度平静维持礼数，崩溃点很小且立刻收回，符合其克制人设。 |
| genre_fit_score | 7.50 | 文本契合古风权谋言情的权力操作和克制虐恋的隐忍基调，朝堂、婚约、旧案、灭口等元素有效兑现。但言情浓度略低于预期，本章更偏重权谋设定和外部压力，男女主间的私人情感层次较薄，距离“克制但强烈的情感张力”的读者承诺仍有距离。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 7.00 |
| rule_redundancy_score | 10.00 |
| rule_anti_slop_score | 9.10 |
| hybrid_redundancy_score | 7.00 |

| hard fail flag | severity | related_metrics |
| --- | --- | --- |
| continuity_break | blocker | continuity_score |

| target_module | issue_type | severity | confidence |
| --- | --- | --- | ---: |
| prompts/writer/plan_content_blocks.txt | continuity | blocker | 0.94 |
| prompts/writer/write_chapter_full.txt | continuity | blocker | 0.94 |
| prompts/writer/plan_content_blocks.txt | redundancy | medium | 0.70 |
| prompts/writer/write_chapter_full.txt | redundancy | medium | 0.70 |

- strengths: 开场当众请婚的钩子精准而强劲，立即打破常规朝堂叙事，制造追读冲动。；婚书暗号与结尾灭口倒计时的双重悬念设置巧妙，使情节压力层层叠加。；男主从冷静操控到被冷静反刺的转折有情感真实感，人物弧光开始建立。；环境物件（雪水、旧伤、禁军甲片）成为情绪载体，增强了压抑氛围。
- weaknesses: 存在严重连续性断裂：婚书在沈知微带走后凭空出现在御案，逻辑错误破坏沉浸感。；双人同场戏缺乏化学反应，敌意与疏离虽有依据，但没有挤出残留旧情或私密磁场，导致言情拉力不足。；沈知微全程被动，主体性较弱，削弱了她作为言情女主的魅力和读者共情。；情感解释句（如“不是恐惧，而是条件反射”）过度命名，让关键时刻从沉浸滑向解说。
- improvement_hints: 立即修补婚书位置引起的连续性断裂，改由谢临川发现沈知微遗落在地的婚书，确保物品逻辑。；为双人同场增加一个只有两人能懂的私人细节（旧物、旧称、或旧日习惯性动作），让恨意中隐现在意。；削减解释性旁白，更多依靠动作顺序、呼吸变化、称呼切换、袖口收紧等外部细节传递情绪。；在散朝过渡处增加一句内侍引沈知微去备仪程的交代，使后续禁军接送不显突兀，并让女主在退场时露出一瞬警惕的眼神，暗示她在计算下一步。
- cost: llm_calls=47, judge_llm_calls=1, review_calls=18, patch_rounds=0, used_full_rewrite=false, duration_seconds=3345.66

## romance_case_02_xianxia_rival_trial - 心声同生契的规则秘境

- verdict: `pass`
| metric | score | note |
| --- | ---: | --- |
| romance_tension_score | 8.50 | 本章在符灯阵规则压迫下，男女主之间形成了持续的拉扯感：陆既白因听见心声而分心，只能靠冷面动作掩饰；云眠表面嘴硬吐槽，实际开始依赖他。两人通过共享痛感、互换贴身物、肢体接触（挡住金线、格开她的手）等持续推拉，潜台词丰富，张力始终在线。 |
| relationship_progression_score | 8.50 | 关系从互相嫌弃推进到了不得已守护的边界：陆既白由单纯嫌麻烦变为用行动兜底，云眠从想甩开他转为承认他会先护自己。互换随身物更是把距离推进到不好笑的亲密。 |
| emotional_resonance_score | 8.00 | 情绪推进有层次，从符灯压迫的紧张，到共享痛感的牢靠，再到互换物品的亲密和结尾惊惧，余波强烈。疼痛不是空写，而是落在行动选择上，让读者共情。 |
| character_attraction_score | 8.55 | 由男主吸引力、女主吸引力和双人化学反应加权合成。 |
| hook_score | 9.00 | 由开篇钩子与结尾钩子均值合成。 |
| continuity_score | 7.00 | 整体承接上一章腕印发烫、石门崩塌，顺畅；但内部一处连续性断裂：陆既白小臂上‘那道新的红’在之前未有伏笔，略显突兀。 |
| redundancy_score | 9.00 | 以 romance judge 为主分，并用重复/anti-slop 规则信号做向下修正，不再允许规则层把坏重复或直白心理解释救高。 |
| mind_state_consistency_score | 9.00 | 所有角色行为皆贴合当前心智状态：陆既白高自控，听到心声只能掩饰，从不失控透露；云眠嘴硬且怕死，但本能会在关键时选择信赖，没有不合时宜的勇气或软弱。 |
| genre_fit_score | 9.50 | 文本完美兑现轻快冒险 / 欢喜冤家的情绪承诺：仙侠奇幻服务了互动，试炼规则推动关系变化，大量斗嘴与危机甜感并存，结尾沉重但不越线。 |

| redundancy view | score |
| --- | ---: |
| judge_redundancy_score | 9.00 |
| rule_redundancy_score | 10.00 |
| rule_anti_slop_score | 9.35 |
| hybrid_redundancy_score | 9.00 |

| target_module | issue_type | severity | confidence |
| --- | --- | --- | ---: |
| prompts/writer/plan_content_blocks.txt | continuity | medium | 0.70 |
| prompts/writer/write_chapter_full.txt | continuity | medium | 0.70 |

- strengths: 心声与动作的错位带来强烈的轻喜感和暧昧张力，且不穿帮，信息差运用极佳。；同生契的痛感与触感共享让每一次身体反应都成为关系推进的杠杆，奇幻设定服务情感。；双人互动始终在冷话与热动作中推拉，化学反应强，结尾阴谋钩子收束有力。；女主嘴硬但心动通过细碎动作与念头自然流露，人设稳且讨喜。
- weaknesses: 总字数偏少，导致两处情感转折（云眠确认他会护她、交出铃铛的内心挣扎）展开略浅。；陆既白小臂红痕的连续性存在小断裂，需要提前一两句暗示以避免瞬间抽离。
- improvement_hints: 在b003中为陆既白小臂红痕埋一句短小伏笔，例如云眠瞥见他袖口下隐隐新痕。；将云眠跨线前的犹豫稍做延长，加入一句对铜铃的模糊触感回忆，增强情感韧性。；可在痛感分配的瞬间，让云眠闪过‘为什么他总是刚好挡在前面’的念头，深化她意识到他护她的转折。
- cost: llm_calls=49, judge_llm_calls=1, review_calls=18, patch_rounds=0, used_full_rewrite=false, duration_seconds=2660.85

## Run Errors

- romance_case_03_urban_reunion_comedy: [Errno 22] Invalid argument
