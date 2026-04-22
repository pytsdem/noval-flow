# Romance Eval Post-upgrade Test Report

- backend_started: false
- project_code_modified_in_this_run: false
- live_smoke_total: 2
- live_smoke_input_misread_count: 0
- offline_suite_total: 9
- offline_suite_matched_expectation: 6/9
- offline_suite_mismatch_count: 3
- offline_weak_case_overblocked_count: 3
- offline_verdict_counts: {"pass": 3, "needs_work": 0, "blocked": 6}

## Headline

- live judge path misread count: 0/2
- offline actionability summary is based on synthetic judge scores plus real post-processing logic.
- the key questions here are whether `verdict / hard_fail_flags / top_targets` look sane, and whether weak samples are being over-blocked.

## Live Smoke Cases

### live_strong_smoke_01 | romance_case_01_court_return | 旧案重逢的朝堂试探

- note: 本地手写强样本，用来验证真实 judge 通路。
- verdict: `pass`
- looks_like_input_misread: `false`
- hard_fail_flags: None

```text
殿门被内侍推开时，谢临川靴底的雪水还没干，冰凉先顺着裤脚往上爬。先帝旧案四字落下来，满殿的呼吸像被谁按住，沈知微这才抬眼。

她只看了一瞬，便把目光重新收回礼数里，像什么都没发生。可谢临川偏偏看见她指尖在袖中收紧了一分，也看见她在“转运旧档”四字上停得极轻，轻得若不是他这些年被人一句话一句话逼着活过来，根本听不出来。

他照旨谢恩，膝骨磕在金砖上，声线却稳得发冷：“臣不敢翻旧判，只求调阅三年前军粮转运的原始档册，验一验内库抄本有无讹误。”

群臣里立刻有人嗤笑，说流放回来的人竟也配碰内库旧档。谢临川没有抬头，反倒把请旨的话说得更缓，像把刀一寸寸压进鞘里。高阶上终于有人问沈知微。她是当年旧案证人，如今又掌着内库文簿，人人都等她一句。

“按例，可查。”她答得极冷，连称呼都规整得过分，“请谢世子于偏库阅副册，不得擅动原卷。”

谢临川本该只记住那句“不得擅动”，偏先被“谢世子”三个字钉住。三年前她还会在灯下叫他名字，如今却把每一个字都磨成了最疏远的礼器。他抬眼看她，她已经垂下睫毛，像从未在“旧案”两个字上乱过半拍。

可他还是抓到了。散朝后档册被抬出内库，沈知微从他身侧让开时，目光掠过他虎口旧伤，又极快移开。那一下短得近乎错觉，却比殿上的冷言更像破绽。

谢临川接过调阅腰牌，低声道：“沈大人当年证词落笔也这么稳么？”

她背脊绷得笔直，没有回头：“谢世子若想翻案，就别把力气浪费在问旧人。”

话音未落，殿外风雪里就有人疾步来报，说昨夜替内库誊抄三年前旧档的第一名书吏，今晨被发现死在值房。谢临川攥紧腰牌，忽然意识到她方才那一眼，也许不是心虚，而是来不及。
```

- romance_tension_reason: 男女主在朝堂高压下的克制拉扯成立，试探、回避、压迫感均通过细节传递，潜台词充足。男主精准捕捉女主的微破绽，女主用极致礼数掩盖情绪，双向的在意与敌意都藏在规矩缝隙里，符合设定的“误读型拉扯”核心。
- relationship_progression_reason: 本章关系发生了有效变化，从前期的“单向敌对仇敌”推进到“带有怀疑的高危牵制”，男主对女主的认知出现松动，不再认定她只是心虚的叛徒。
- top_targets: None

### live_strong_smoke_02 | romance_case_02_sickbed_truce | 雨夜药庐的被迫共处

- note: 第二个 live smoke，用来排除单 case 偶发。
- verdict: `needs_work`
- looks_like_input_misread: `false`
- hard_fail_flags: continuity_break, relationship_progression_break

```text
雨声压着屋檐，药盏里的苦气一阵阵往上翻。顾砚伤得重，醒来第一眼先看见林晚坐在灯下，袖口还沾着没干的血。

她听见动静，只把药递过去：“命是我暂时留下的，不代表旧账就算了。”话说得冷，手却在碰到他腕骨时停了一瞬，像怕扯开他刚缝好的伤口。

顾砚接过药，没有立刻喝，反而看见他掌心那枚旧铜钱沾了血。林晚也看见了，眼神只乱了半拍，随即把纱布勒得更紧：“别误会，我不是为了它。”

窗外忽然传来急促的马蹄声，门外人低声禀报，说追杀他的人已经摸到了山道口。顾砚这才把药一口喝尽，抬眼看她：“你现在若把我推出去，我连怨你的力气都没有。”

林晚把灯芯拨亮半寸，终于看向他：“我若真想让你死，昨夜就不会亲手给你止血。”雨声更急，后门也在这时被人敲了三下，用的是她最不想在今夜听到的暗号。
```

- romance_tension_reason: 具备基本的口是心非拉扯与旧情试探，但层次单一，缺乏动作、呼吸等细节支撑，潜台词不够饱满，压迫感与回避感的刻画偏浅。
- relationship_progression_reason: 关系有初步推进（从互疑旧识到暂时达成“不推出去”的默契），但缺乏从“怀疑”到“依赖”的过渡细节，变化显得突兀，没有体现关系松动的过程。
- top_targets: prompts/writer/plan_content_blocks.txt, prompts/writer/write_chapter_full.txt, prompts/writer/step_8_chapter_briefs.txt, prompts/writer/write_chapter_full.txt, prompts/writer/plan_content_blocks.txt

## Offline Actionability Suite

### romance_case_01_court_return | strong

- expectation: `pass`
- actual_verdict: `pass`
- matched_expectation: `true`
- note: 应被视为成立的强样本。
- hard_fail_flags: None
- top_targets: None

```text
殿门被内侍推开时，谢临川靴底的雪水还没干，冰凉先顺着裤脚往上爬。先帝旧案四字落下来，满殿的呼吸像被谁按住，沈知微这才抬眼。

她只看了一瞬，便把目光重新收回礼数里，像什么都没发生。可谢临川偏偏看见她指尖在袖中收紧了一分，也看见她在“转运旧档”四字上停得极轻，轻得若不是他这些年被人一句话一句话逼着活过来，根本听不出来。

他照旨谢恩，膝骨磕在金砖上，声线却稳得发冷：“臣不敢翻旧判，只求调阅三年前军粮转运的原始档册，验一验内库抄本有无讹误。”

群臣里立刻有人嗤笑，说流放回来的人竟也配碰内库旧档。谢临川没有抬头，反倒把请旨的话说得更缓，像把刀一寸寸压进鞘里。高阶上终于有人问沈知微。她是当年旧案证人，如今又掌着内库文簿，人人都等她一句。

“按例，可查。”她答得极冷，连称呼都规整得过分，“请谢世子于偏库阅副册，不得擅动原卷。”

谢临川本该只记住那句“不得擅动”，偏先被“谢世子”三个字钉住。三年前她还会在灯下叫他名字，如今却把每一个字都磨成了最疏远的礼器。他抬眼看她，她已经垂下睫毛，像从未在“旧案”两个字上乱过半拍。

可他还是抓到了。散朝后档册被抬出内库，沈知微从他身侧让开时，目光掠过他虎口旧伤，又极快移开。那一下短得近乎错觉，却比殿上的冷言更像破绽。

谢临川接过调阅腰牌，低声道：“沈大人当年证词落笔也这么稳么？”

她背脊绷得笔直，没有回头：“谢世子若想翻案，就别把力气浪费在问旧人。”

话音未落，殿外风雪里就有人疾步来报，说昨夜替内库誊抄三年前旧档的第一名书吏，今晨被发现死在值房。谢临川攥紧腰牌，忽然意识到她方才那一眼，也许不是心虚，而是来不及。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 8.9 | 8.90 |
| relationship_progression_score | 8.2 | 8.20 |
| emotional_resonance_score | 8.4 | 8.40 |
| character_attraction_score | - | 8.43 |
| hook_score | - | 8.75 |
| continuity_score | 8.7 | 8.70 |
| redundancy_score | 8.1 | 8.10 |
| mind_state_consistency_score | 8.6 | 8.60 |
- rule_redundancy_score: 10.00

### romance_case_01_court_return | weak

- expectation: `needs_work`
- actual_verdict: `blocked`
- matched_expectation: `false`
- note: 应被判成弱样本，而不是 blocker。
- hard_fail_flags: relationship_progression_break, continuity_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/step_8_chapter_briefs.txt, prompts/writer/write_chapter_full.txt, prompts/writer/plan_content_blocks.txt

```text
谢临川回京以后，在朝堂上又见到了沈知微。他觉得她很冷，她也觉得他很冷。旧案让他们都很难受，所以气氛一直很压抑。

他想查档，她按规矩答应。她很冷，他也很冷。她很冷，他也很冷。两个人都想到从前，但谁也没有做出新的反应。

散朝以后，他还是觉得她很冷，她也还是觉得他很冷。后来有人告诉他书吏死了，他决定以后再查。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 3.9 | 3.90 |
| relationship_progression_score | 2.4 | 2.40 |
| emotional_resonance_score | 4.2 | 4.20 |
| character_attraction_score | - | 4.46 |
| hook_score | - | 4.15 |
| continuity_score | 6.4 | 6.40 |
| redundancy_score | 3.1 | 3.10 |
| mind_state_consistency_score | 6.8 | 6.80 |
- rule_redundancy_score: 10.00

### romance_case_01_court_return | break

- expectation: `blocked`
- actual_verdict: `blocked`
- matched_expectation: `true`
- note: 应被强力拦下。
- hard_fail_flags: continuity_break, mind_state_break, relationship_progression_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/plan_content_blocks.txt, prompts/writer/write_chapter_full.txt, prompts/writer/build_character_mindset.txt

```text
圣旨刚念到旧案，沈知微就当众扑通跪下，哭着说当年作证全是为了保谢临川。满殿哗然，皇帝也当场改口，说先帝旧判或有误会。

谢临川上前一把扶住她，众目睽睽之下问她是不是这些年一直在等他回来。沈知微点头，说自己从未变心，只是不得不演戏。

群臣很快散去，旧案也立刻重审。谢临川握着她的手说以后再没人能逼她，他们决定一起查清所有真相。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 3.2 | 3.20 |
| relationship_progression_score | 1.6 | 1.60 |
| emotional_resonance_score | 3.7 | 3.70 |
| character_attraction_score | - | 3.20 |
| hook_score | - | 3.65 |
| continuity_score | 1.4 | 1.40 |
| redundancy_score | 4.8 | 4.80 |
| mind_state_consistency_score | 0.7 | 0.70 |
- rule_redundancy_score: 10.00

### romance_case_02_sickbed_truce | strong

- expectation: `pass`
- actual_verdict: `pass`
- matched_expectation: `true`
- note: 应被视为成立的强样本。
- hard_fail_flags: None
- top_targets: None

```text
雨声压着屋檐，药盏里的苦气一阵阵往上翻。顾砚伤得重，醒来第一眼先看见林晚坐在灯下，袖口还沾着没干的血。

她听见动静，只把药递过去：“命是我暂时留下的，不代表旧账就算了。”话说得冷，手却在碰到他腕骨时停了一瞬，像怕扯开他刚缝好的伤口。

顾砚接过药，没有立刻喝，反而看见他掌心那枚旧铜钱沾了血。林晚也看见了，眼神只乱了半拍，随即把纱布勒得更紧：“别误会，我不是为了它。”

窗外忽然传来急促的马蹄声，门外人低声禀报，说追杀他的人已经摸到了山道口。顾砚这才把药一口喝尽，抬眼看她：“你现在若把我推出去，我连怨你的力气都没有。”

林晚把灯芯拨亮半寸，终于看向他：“我若真想让你死，昨夜就不会亲手给你止血。”雨声更急，后门也在这时被人敲了三下，用的是她最不想在今夜听到的暗号。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 8.7 | 8.70 |
| relationship_progression_score | 8.1 | 8.10 |
| emotional_resonance_score | 8.6 | 8.60 |
| character_attraction_score | - | 8.50 |
| hook_score | - | 8.75 |
| continuity_score | 8.5 | 8.50 |
| redundancy_score | 8.2 | 8.20 |
| mind_state_consistency_score | 8.7 | 8.70 |
- rule_redundancy_score: 10.00

### romance_case_02_sickbed_truce | weak

- expectation: `needs_work`
- actual_verdict: `blocked`
- matched_expectation: `false`
- note: 应被判成弱样本。
- hard_fail_flags: relationship_progression_break, continuity_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/step_8_chapter_briefs.txt, prompts/writer/write_chapter_full.txt, prompts/writer/plan_content_blocks.txt

```text
雨夜里，顾砚在林晚的药庐养伤。林晚其实心软，但她不说。顾砚其实也在意她，但他不说。

她给他换药，他觉得她其实心软；她给他倒水，他还是觉得她其实心软。她其实心软，他其实在意，她其实心软，他其实在意。

两个人都没有再试探，也没有新的线索。雨还是很大，夜也很长。最后外面好像有人来，但也没有真正发生什么。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 4.1 | 4.10 |
| relationship_progression_score | 2.7 | 2.70 |
| emotional_resonance_score | 4.3 | 4.30 |
| character_attraction_score | - | 4.57 |
| hook_score | - | 4.30 |
| continuity_score | 6.5 | 6.50 |
| redundancy_score | 3.0 | 3.00 |
| mind_state_consistency_score | 6.6 | 6.60 |
- rule_redundancy_score: 10.00

### romance_case_02_sickbed_truce | break

- expectation: `blocked`
- actual_verdict: `blocked`
- matched_expectation: `true`
- note: 应被强力拦下。
- hard_fail_flags: continuity_break, mind_state_break, relationship_progression_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/plan_content_blocks.txt, prompts/writer/write_chapter_full.txt, prompts/writer/build_character_mindset.txt

```text
林晚刚替顾砚包好伤口，他就直接把税银去向和幕后名单全摊在桌上，说自己从一开始就完全相信她。

林晚也没有再回避，立刻承认自己这些年一直在替权贵做假账，只是为了等他回来。两个人很快把旧情说破，顾砚还抱住她，说以后什么都不用再瞒。

门外的人刚敲了一下，林晚便主动牵着他从后门离开，决定今夜就一起去端掉幕后主使。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 3.4 | 3.40 |
| relationship_progression_score | 1.9 | 1.90 |
| emotional_resonance_score | 3.6 | 3.60 |
| character_attraction_score | - | 3.27 |
| hook_score | - | 3.60 |
| continuity_score | 1.8 | 1.80 |
| redundancy_score | 5.1 | 5.10 |
| mind_state_consistency_score | 0.9 | 0.90 |
- rule_redundancy_score: 10.00

### romance_case_03_betrothal_banquet | strong

- expectation: `pass`
- actual_verdict: `pass`
- matched_expectation: `true`
- note: 应被视为成立的强样本。
- hard_fail_flags: None
- top_targets: None

```text
第一杯寿酒还没递到姜栀手里，国舅夫人就笑着问起她的婚事。满堂目光一齐压过来，姜栀指尖还扣着酒盏，先听见的是席间一阵压不住的附和。

她刚要按着规矩把话圆过去，裴砚便放下茶盏，语气比酒气还淡：“国舅夫人若真怜惜姜姑娘，就别在她生辰宴上替旁人下聘。”

一句话，先替她截断了最难接的台阶，也把所有视线都拽到了他身上。国舅夫人笑意微凝，反问他凭什么插手。裴砚没有看她，只把桌上一枚刚送来的玉佩推到姜栀面前：“既送到我手里，总该先问问我愿不愿意放。”

席间气息顿时变了。姜栀知道他是在替她挡刀，也知道这一挡会把她推得更近。她抬眼时没谢，只道：“裴大人这话说得太满，回头若收不住，可别怪我不认。”

裴砚这才看她，眸色像压住锋刃后的寒光：“姜姑娘既敢说，我就敢改日上门，亲自讨个说法。”满堂人都听见了，连姜父手里的酒都险些洒出来。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 8.8 | 8.80 |
| relationship_progression_score | 8.4 | 8.40 |
| emotional_resonance_score | 8.2 | 8.20 |
| character_attraction_score | - | 8.60 |
| hook_score | - | 8.85 |
| continuity_score | 8.4 | 8.40 |
| redundancy_score | 8.3 | 8.30 |
| mind_state_consistency_score | 8.5 | 8.50 |
- rule_redundancy_score: 10.00

### romance_case_03_betrothal_banquet | weak

- expectation: `needs_work`
- actual_verdict: `blocked`
- matched_expectation: `false`
- note: 应被判成弱样本。
- hard_fail_flags: relationship_progression_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/step_8_chapter_briefs.txt, prompts/writer/write_chapter_full.txt, prompts/writer/plan_content_blocks.txt

```text
生辰宴上，有人问起姜栀的婚事。姜栀觉得有压力，但她还是按规矩说了几句场面话。

裴砚也在场，他替她说了两句，却没有把话说得太重。大家于是继续喝酒，虽然气氛有些微妙，但也没有谁真的难堪。

姜栀觉得裴砚这个人很危险，也觉得他可能是在帮她。裴砚也觉得她很聪明。宴席结束前，他只说以后有机会再聊。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 4.4 | 4.40 |
| relationship_progression_score | 3.3 | 3.30 |
| emotional_resonance_score | 4.5 | 4.50 |
| character_attraction_score | - | 4.77 |
| hook_score | - | 4.45 |
| continuity_score | 6.9 | 6.90 |
| redundancy_score | 4.0 | 4.00 |
| mind_state_consistency_score | 7.1 | 7.10 |
- rule_redundancy_score: 10.00

### romance_case_03_betrothal_banquet | break

- expectation: `blocked`
- actual_verdict: `blocked`
- matched_expectation: `true`
- note: 应被强力拦下。
- hard_fail_flags: continuity_break, mind_state_break, relationship_progression_break, hook_underpowered, redundancy_drag, romance_pull_weak
- top_targets: prompts/writer/plan_content_blocks.txt, prompts/writer/write_chapter_full.txt, prompts/writer/build_character_mindset.txt

```text
国舅夫人才问完婚事，姜栀就当众起身，说自己早已心许裴砚，谁都不必再替她做主。裴砚随即握住她的手，直言自己今日就是来替她退掉所有婚约的。

满堂宾客还没反应过来，姜父便立刻同意，说姜家今后全听裴砚安排。裴砚也没有再遮掩，当众点出自己真正想借婚约去切国舅府的手。

姜栀当场跟着他离席，生辰宴就此散了。她一路上只顾着问他何时上门定亲，再不提家里的商路和后患。
```

| metric | synthetic_judge | hybrid_after_rules |
| --- | ---: | ---: |
| romance_tension_score | 3.0 | 3.00 |
| relationship_progression_score | 1.7 | 1.70 |
| emotional_resonance_score | 3.3 | 3.30 |
| character_attraction_score | - | 2.77 |
| hook_score | - | 3.65 |
| continuity_score | 1.2 | 1.20 |
| redundancy_score | 4.9 | 4.90 |
| mind_state_consistency_score | 0.6 | 0.60 |
- rule_redundancy_score: 10.00

## Conclusion

- 这份报告里的测试正文现在是 UTF-8 正常中文，不再是问号。
- live smoke 反映真实 judge 通路；offline suite 反映新加的 actionability/verdict 逻辑。
- 如果 live smoke 正常而 weak case 仍持续被打成 `blocked`，那就说明下一步该调 blocker 阈值，而不是继续怀疑中文输入链路。
