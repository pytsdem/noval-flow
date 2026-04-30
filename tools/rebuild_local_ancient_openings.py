from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSITIVE_ROOT = REPO_ROOT / "evals" / "romance" / "positive_examples"
ANCIENT_OUT = POSITIVE_ROOT / "ancient_openings"
README_PATH = POSITIVE_ROOT / "README.md"
INDEX_PATH = POSITIVE_ROOT / "index.json"
MARKET_RESEARCH_DIR = REPO_ROOT / "evals" / "romance" / "reports" / "market_research"
REPORT_MD = MARKET_RESEARCH_DIR / "20260430_local_selected_ancient_three_chapters_deep_dive.md"
REPORT_JSON = MARKET_RESEARCH_DIR / "20260430_local_selected_ancient_three_chapters_deep_dive.json"


CHAPTER_MARK = "\u7b2c"  # 第
ZHANG_MARK = "\u7ae0"  # 章
HUI_MARK = "\u56de"  # 回
SPECIAL_OPENINGS = ("\u6954\u5b50", "\u5e8f\u7ae0", "\u5f15\u5b50", "\u2606\u3001")


def _normalize_line(text: str) -> str:
    return text.strip("\ufeff \t\u3000")


def _is_heading(line: str) -> bool:
    line = _normalize_line(line)
    if not line or len(line) > 60:
        return False
    if line.startswith(SPECIAL_OPENINGS):
        return True
    return line.startswith(CHAPTER_MARK) and (
        ZHANG_MARK in line or HUI_MARK in line
    )


def _detect_source_dir() -> Path:
    workspace = REPO_ROOT.parent
    known = {"bizhen", "makeprint", "mythought", "noval-flow", "video-tools"}
    user_text_root = next(
        item for item in workspace.iterdir() if item.is_dir() and item.name not in known
    )
    ancient_root = max(
        [item for item in user_text_root.iterdir() if item.is_dir()],
        key=lambda item: len([child for child in item.iterdir() if child.is_dir()]),
    )
    return next(
        item
        for item in ancient_root.iterdir()
        if item.is_dir()
        and len([child for child in item.iterdir() if child.is_file() and child.suffix == ".txt"]) >= 5
    )


@dataclass(frozen=True)
class ExampleSpec:
    slug: str
    title: str
    author: str
    filename_match: str
    tags: list[str]
    opening_pattern: str
    voice_signature: str
    pressure_source: str
    chapter_summaries: list[str]
    three_chapter_summary: str
    story_opening_flow: list[str]
    narrative_rhythm: list[str]
    character_and_relationship_setup: list[str]
    information_release_design: list[str]
    retention_mechanics: list[str]
    strong_points: list[str]
    standout_lines: list[str]
    techniques: list[str]
    what_to_learn: list[str]
    avoid_copying: list[str]
    current_gap: str


SPECS: list[ExampleSpec] = [
    ExampleSpec(
        slug="shizun_zai_xiu_wuqingdao",
        title="师尊在修无情道",
        author="水凼凼",
        filename_match="师尊在修无情道",
        tags=["古代言情", "仙侠言情", "师徒", "身份坠落", "反差同居", "女主声口强"],
        opening_pattern="仙门高处惊鸿一瞥 -> 山腰破屋与饥饿生存 -> 被忽视弟子真相 -> 师尊在大战中坠落 -> 破屋照料与尴尬同居",
        voice_signature="第三人称紧贴池榆，口吻现代、嘴贫、接地气，用吐槽和生存感硬生生撬开传统仙侠的冷飘感。",
        pressure_source="被宗门放养的边缘弟子、仙门等级压迫、尊者坠落后的生存羞耻、师徒身份差与空间强制贴近。",
        chapter_summaries=[
            "第一章先让池榆从山脚仰望一群御剑而过的金丹真人，晏泽宁以“最俊也最冷”的高空剪影亮相，随即镜头立刻砸回池榆的地面生活：她手拎土鸡、背背枯木、被周叶叶找茬、连一顿饭都吃不上。接着作者回补两年前的收徒分配，点明池榆虽被分到阙夜洞，却根本没有得到师尊接引，只能靠度支堂弟子叶季活下来。整章最关键的不是“她穿越了”，而是“她被扔在一个看起来很高贵、实际对她毫无照拂的仙门体系里”，于是首章的主发动机就成了生存落差与口吻反差。",
            "第二章把镜头从池榆的荒凉日常切到聚仙殿。晏泽宁在紫海之战中为救楚无期、斩海妖王而金丹尽毁、根基断绝、双目失明，掌门与峰主们一边做“渡修为”的公开姿态，一边算计舆论与善后。章内同时完成了三件事：一是把晏泽宁从高处摔下来；二是让读者知道宗门救治里夹杂了人心与门面；三是正式把“叫他的弟子来照顾”这件事推上舞台。于是首章里那个从未被师尊真正接住的徒弟，到了第二章尾声，被迫成了照顾失明废丹师尊的人。",
            "第三章真正把戏拉进“同居现场”。池榆带着失去灵力的晏泽宁回阙夜峰，却发现两人谁都进不了阙夜洞，只能栖身她住了两年的脏小屋。木屋臭味、吃剩的鸡汤、会动的小剑、失明高冷师尊、只能用左手热饭的窘迫，全都堆到一个空间里。章节一边写池榆的尴尬、晏泽宁的洁癖和高姿态，一边让饥饿与受伤迫使他吞下现实，最终落成“神坛白鹤跌进烟火破屋”的新叙事关系。前三章到这里，故事已经从远观仙门，稳稳过渡到可长期连载的高反差日常关系场。"
        ],
        three_chapter_summary="前三章不是单纯地“介绍设定”，而是精准地完成了一个巨大落差：第一章让女主像个被宗门遗忘的底层杂役，第二章再让读者知道她那位从未出现的师尊其实是仙门神坛上的顶级人物，第三章再把这位神坛人物彻底打下来，塞进女主发霉的小木屋里。也就是说，作者用三章时间先搭起高低落差，再把两个人扔进同一个空间，戏剧关系这才真正成立。",
        story_opening_flow=[
            "先用高空御剑画面做一记“仙门很大、池榆很小”的视觉开场，但不沉迷高光，立刻把镜头砸回池榆的土鸡、调料、饥饿和被欺负。",
            "再用穿越后分配弟子、无人来接、半山腰破屋等细节，把池榆在宗门中的真实位置钉牢。",
            "第二章突然放大镜头，切到聚仙殿大战余波与宗门议事，让读者意识到晏泽宁原本是顶层人物，而且跌落得极惨。",
            "再将“叫她来照顾”作为命运转轴，让师徒两条线从远距离设定正式并轨。",
            "第三章不给大叙事继续飞，而是立刻把人物推进小木屋，让所有抽象身份差、战损、美强惨、底层生存感在一个充满鸡汤味的房间里落地。"
        ],
        narrative_rhythm=[
            "第一章节奏是“惊鸿一瞥 -> 泥地求生 -> 过往解释 -> 再次落回饥饿现实”，高低交替非常明显。",
            "第二章像一记垂直下坠的重锤，直接把视角拔高到宗门中枢，再砸出晏泽宁金丹尽毁的结果，让读者短时间内吃到大量命运信息。",
            "第三章节奏明显放慢，但不是松，而是靠空间尴尬、生活细节和身体窘态来制造持续拉扯。",
            "前三章整体形成“先远观、再揭伤、后同居”的三段推进，每一章都在换压力形态，而不是重复同一层情绪。",
            "最可学的地方是：它知道什么时候该快刀切设定，什么时候该把一碗鸡汤和一张脏床写得比世界观更有戏。"
        ],
        character_and_relationship_setup=[
            "池榆不是靠标签立住，而是靠“饿、穷、嘴贫、能忍、还能在破事里找乐子”立住，读者第一章就知道她是什么活法。",
            "晏泽宁则先以高处剪影存在，再以战损废人现身，人物吸引力来自落差，而不是单纯的“高冷师尊”标签。",
            "真正的关系引爆点并不是师徒身份本身，而是“他以前不接她，现在却只能依赖她”。",
            "第三章里晏泽宁嫌弃她的小屋、她又被迫照顾他，这种嫌弃与照顾并存的状态，让两人关系一开始就带着刺，不会滑成平淡保姆戏。"
        ],
        information_release_design=[
            "作者不先介绍宗门制度，而是先让池榆作为边角人活一遍，读者自然知道规则如何伤人。",
            "有关紫海大战的宏观信息，被集中丢在第二章，用掌门、峰主、楚无期等人的反应做拼图，而不是一口气旁白讲完。",
            "第三章又把世界观缩回日常用品、气味、饥饿、伤口和屋内摆设，让抽象设定回到可感知层。",
            "信息释放顺序非常克制：先给结果，再给原因，再给后果。"
        ],
        retention_mechanics=[
            "第一章留下的问题是：一个被晾着两年的便宜弟子，到底怎么在仙门活下来的？",
            "第二章的强钩子是：原来那个冷到不来接徒弟的师尊，竟然已经跌得这么惨。",
            "第三章的追读点则变成：这两个气味、身份、生活方式完全不兼容的人，接下来要怎么在同一间小破屋里过下去？",
            "同时，池小剑、进不去的阙夜洞、晏泽宁受伤真相，也都在暗暗留线。"
        ],
        strong_points=[
            "仙侠题材却不端着仙气，反而用土鸡、鸡汤、臭木屋和小破剑把人一下子摁进生活里。",
            "前三章的落差设计非常准：先让人物高不可攀，再让他摔下来，比一开始就卖惨更有吸力。",
            "女主声口特别清晰，她的吐槽和生存逻辑天然带着阅读黏性。"
        ],
        standout_lines=[
            "“隔得天远，俊不俊池榆看不见，但气质是独一档，大概是冻死人的那种类型。”",
            "“原来是传音入密。池榆听了此话，狠狠咬了一口手里的鸡腿。不会吧，这么菜。”",
            "“神坛白鹤跌进烟火破屋”的感觉，在第三章几乎是整章都成立的。"
        ],
        techniques=["高低反差开局", "底层视角吃世界观", "战损坠落", "同空间强制关系", "口吻驱动人物"],
        what_to_learn=[
            "不要一上来把仙侠设定讲平，先让人物在设定里活一遍。",
            "强关系题材非常适合用“先远后近”的落差结构，先让读者仰头，再让两人挤进同一空间。",
            "生活细节可以比大设定更能留人，前提是细节本身带有羞耻、代价或反差。",
            "女主声口一旦清晰，哪怕剧情还没爆，读者也愿意跟。"
        ],
        avoid_copying=[
            "不要照搬“战损失明师尊 + 山腰破屋”的具体壳子。",
            "不要机械模仿池榆的现代吐槽词，而忽略她背后的生存逻辑。"
        ],
        current_gap="我们当前正文很容易把题材写成“任务流程 + 信息推进”，而这本书前三章证明：真正能黏住读者的，是高低落差被生活细节接住之后形成的关系场，而不是设定本身。"
    ),
    ExampleSpec(
        slug="liangchenmeijin",
        title="良陈美锦",
        author="沉香灰烬",
        filename_match="良陈美锦",
        tags=["古代言情", "重生", "宅门", "母女线", "悔悟流", "旧时回望"],
        opening_pattern="病榻将死 -> 一生悔悟回看 -> 少女旧宅重醒 -> 重返母亲病榻前",
        voice_signature="第三人称贴身跟顾锦朝，语气平静、克制、冷醒，像一个终于不再骗自己的中年女人回头审视一生。",
        pressure_source="临终悔悟、错爱带来的终身代价、母亲病重、宅门姨娘与庶妹暗害、重来一次却知道灾难已近。",
        chapter_summaries=[
            "第一章写的是顾锦朝临终前的冬日。她坐在陈家偏院的病榻边，看着院里的雪和梅花，身上穿着旧衣，容颜与精神都被多年抑郁磨损。丫鬟、戏曲、旧景，一点点引出她一生最大的错误：少女时迷恋陈玄青，后来甚至嫁给对方的父亲为续弦，只为了能日日看见他。此后她因为嫉妒苛待陈玄青的妻子，被人做局、被夺权、被囚偏院，儿子与她离心，祖母死后更彻底失了生气。第一章不是简单交代前史，而是把“她是怎么把自己毁掉的”完整、连贯、痛感十足地写出来，让重生的必要性先成立。",
            "第二章并不急着爽快翻盘，而是让她在顾家旧宅中醒来。屋子里的陈设、旧丫鬟白芸与采芙、院里收雪水的婆子，全是她前世失去之后再也见不到的东西。她一边确认自己真的回到了十五六岁，一边敏锐地重新打量当年未曾看穿的宅门细节：谁在说闲话，谁在遮掩，谁在敷衍。她开始意识到，自己前世不是天生蠢，而是太晚醒。第二章最重要的是把“重来一次”的情绪拉成一根很绷的线：欣喜、怀疑、痛悔、补救欲望同时存在。",
            "第三章把重心压到母亲身上。顾锦朝换下艳丽衣裳，去见病中的母亲，屋内的乳母、姨娘、四妹、丫鬟、汤药、被褥，全都把顾家的旧秩序重新摆在读者眼前。她在这里想起了宋姨娘、顾澜、后续扶正与家产侵吞，也第一次明确意识到前世母亲临终前早已提醒过她，而她没有听。第三章表面安静，实际是在重建顾锦朝此生最核心的情感债：她必须先护住母亲与幼弟，重生才不是空话。"
        ],
        three_chapter_summary="前三章以“死前悔悟 -> 少女重醒 -> 回到母亲病榻”组成一个极其稳的重生开端。它没有抢着把宅斗招数和打脸桥段全抛出来，而是先把顾锦朝最痛、最欠、最想挽回的三样东西钉死：她错付的一生、她回来的事实、她还来得及见到的母亲。于是重生不是机制，而是情感再分配的机会。",
        story_opening_flow=[
            "第一章先用暮年病榻把人物压到最低处，再通过回忆与当下交错，讲透她一生的错误选择与代价。",
            "第二章让她在顾家旧宅重醒，先用空间与旧人确认“真的回来了”，再带出她重新看人的眼光。",
            "第三章不急着对敌，而是先去见母亲，让“想补救什么”这件事在最重要的情感关系里落地。",
            "整套开场不是靠爆点叠加，而是靠价值顺序调整：先知痛，再得机会，再定要守住的人。"
        ],
        narrative_rhythm=[
            "第一章节奏很慢，却慢得有层次：景物冷清、丫鬟回话、旧情回望、过错展开、病榻闭眼，像一层层往下沉。",
            "第二章节奏明显提起来，因为读者会跟着她一一确认旧宅、旧人、旧事是否还在，但这种快依然建立在感受而非打脸动作上。",
            "第三章又缓下来，转成深情绪、高信息密度的母女戏，让读者知道这次重来的真正 stakes。",
            "前三章整体是“沉到谷底 -> 被抬回过去 -> 抓住真正要救的人”，节奏线清晰而稳定。"
        ],
        character_and_relationship_setup=[
            "顾锦朝的核心魅力不是少女明艳，而是“痛过以后终于会看”。",
            "陈玄青并未在前三章里大量出场，却因第一章的回望与余痛形成强大的逆向存在感。",
            "母亲、宋姨娘、顾澜、乳母、丫鬟们共同搭起了顾家的人情与权力网，让顾锦朝的后续选择都不是浮在空中的。",
            "她与母亲的关系一被重新点亮，重生的方向就从“重新争男人”改成了“重新站稳人生”。"
        ],
        information_release_design=[
            "第一章把大量前史藏在病榻自省里，信息虽多，但都是从她今日为何会死、为何无望自然生出来的。",
            "第二章以旧宅与旧人做信息确认，读者通过她的二次目光补全前史，而不是重新听一遍设定。",
            "第三章通过母女对话与她心内独白，把顾家未来爆炸的雷一颗颗埋回当下。",
            "信息释放重心始终围绕“她此刻最痛什么”，所以不会显得像设定说明书。"
        ],
        retention_mechanics=[
            "第一章最强的留人点是：这样一个女人到底是怎么一步步走到今天的？",
            "第二章则把问题改成：既然回来了，她会先救谁、先改什么？",
            "第三章把读者的情绪钉在母亲与幼弟身上，接下来她若出手，读者天然就知道她在为谁而战。",
            "整部开头留人的不是悬疑，而是深重的“来不来得及”。"
        ],
        strong_points=[
            "把重生写成情感债而不是外挂，这是这本书最强的地方。",
            "病榻旧景、旧宅重醒、病母在榻这三步都很稳，读者几乎不会掉线。",
            "人物自省有力度，但不空喊后悔，每一层悔都能对应到一段具体往事。"
        ],
        standout_lines=[
            "“她只是觉得，没有什么可眷恋的，一切她喜欢的都毁掉了，人没了盼头，活着也没有精神。”",
            "“母亲的手仿佛温和的绸缎，永远不会因为年华而褪色。”",
            "“她并不是笨，她只是看不穿而已。”"
        ],
        techniques=["病榻倒叙", "情感债开场", "旧宅重醒", "母女线立 stakes", "以自省承载前史"],
        what_to_learn=[
            "重生题材的前三章，不一定要急着爽，先把为什么值得重来写出来更重要。",
            "如果人物有漫长前史，最有效的讲法不是百科式回顾，而是从她此刻最痛的地方往回倒。",
            "宅门文的开头，不是先摆招数，而是先摆人情债和亲缘债。",
            "真正能留人的不是“她回来了”，而是“她终于知道自己该救谁了”。"
        ],
        avoid_copying=[
            "不要照搬“少女时爱错人后来嫁给对方父亲”的极端壳子。",
            "不要把这种厚重自省机械挪成一大段苦情独白，忽略场景与物件支撑。"
        ],
        current_gap="我们当前正文很少让人物先背着真正的情感债上场，所以看起来推进很快，却不够沉。相比之下，《良陈美锦》前三章几乎没有浪费字，每一步都在把“她为什么非改不可”钉得更深。"
    ),
    ExampleSpec(
        slug="zhongsheng_jiangmenduhou",
        title="重生之将门毒后",
        author="千山茶客",
        filename_match="重生之将门毒后",
        tags=["古代言情", "重生复仇", "将门", "宅斗", "宫斗余波", "女强"],
        opening_pattern="废后绝境 -> 血债摊牌 -> 少女重生醒来 -> 堂姐挑拨试探 -> 复仇齿轮开始转动",
        voice_signature="句子利、情绪直、恨意重，人物视角带着被权力碾过后的冷硬与清醒，读起来有一种锋面推进感。",
        pressure_source="皇权背叛、满门血债、堂亲算计、定王旧情陷阱、被刻意养废的将门嫡女处境。",
        chapter_summaries=[
            "第一章把沈妙直接放在废后的最后时刻。寝殿陈旧、白绫当前、太监催命，傅修宜、楣夫人、沈清、沈玥轮番出场，把她一生最大的骗局一层层撕开：沈家被利用后灭门，儿女俱亡，她爱了二十年的男人从未真心，堂姐们更早与傅修宜结盟，只等她入局。整章几乎没有旁枝，所有场面都围着“我到底是怎样被所有人联手害死的”这一个核心问题运转，最后落在“血债血偿”的毒誓上，复仇引擎在第一章就彻底点燃。",
            "第二章让她在十四岁的玉娇苑醒来。四个旧丫鬟、镜中尚且稚嫩的脸、明齐六十八年的时间节点，迅速帮助读者确认：她不是临死幻梦，而是真的回来了。接着作者只花很短篇幅就把“她是什么时候被推下水”、“她为什么会迷恋傅修宜”、“沈家内部是如何捧杀她”的前情重新压缩回当下，让读者既知道她以前有多蠢，也知道她现在已经不再是那个蠢人。",
            "第三章则用沈玥登门求情这件事做重生后的第一场小型试探战。表面上沈玥在为沈清说话，实际上是在挑动沈妙为了定王发怒、再次把自己送进“无知丢脸”的旧轨道。沈妙却第一次稳住了，没有如前世那般当场翻脸，而是含笑接话、反手看穿两姐妹都爱慕傅修宜的事实，并在心里立下新的报复路线。第三章的价值不在于她做了多大的事，而在于读者第一次看见：这次的沈妙，会忍，会算，会让别人自己走进她准备好的局。"
        ],
        three_chapter_summary="前三章的核心其实特别简单：第一章把血债摆满桌，第二章给你重来的时间点，第三章证明你这次真的会动脑子。它不拖泥带水，不拐弯抹角，也不怕情绪太烈，反而以足够高的恨值和足够快的认知切换，让读者迅速认定这趟重生值得追。对于复仇宅斗文来说，这种前三章的效率非常可怕。",
        story_opening_flow=[
            "第一章用废后行刑前的高压场景作为终局切口，让所有矛盾一次性上桌。",
            "第二章迅速切回十四岁，用旧丫鬟、旧院子和镜中少女确认重生事实。",
            "再借“是谁把她推下水”这件当下小事，把沈家内部两房的恶意与捧杀逻辑重新摆出来。",
            "第三章直接进入第一场不见刀光的交锋，证明女主已经不是前世那个会被一句话带着跑的人。"
        ],
        narrative_rhythm=[
            "第一章几乎是持续高压，没有缓冲，读者刚进来就被压在废后白绫与血债翻供里。",
            "第二章节奏稍放，但信息交代极高效，属于“短暂换气但绝不松劲”。",
            "第三章节奏转为试探型心理攻防，看似平静，实际上每一句话都在校正人物位置。",
            "前三章构成“极痛开场 -> 快速校时 -> 首次反手”，爽点和悬念配比很重。"
        ],
        character_and_relationship_setup=[
            "沈妙的魅力先来自惨，再来自醒。第一章让人替她怒，第三章开始让人想看她怎么杀回来。",
            "傅修宜不需要在重生后大量出现，第一章已经把他的伪善和冷酷写成了巨大阴影。",
            "沈清与沈玥一柔一利，既是家庭内部的近身敌人，也提前完成了“闺阁战场”的立场铺垫。",
            "四个丫鬟在第二章重新出现，为沈妙后续的行动线补上了可信的亲信基础。"
        ],
        information_release_design=[
            "第一章通过临终摊牌，把血债、背叛链、家族灭门一次性释放出来，读者不需要慢慢猜主矛盾是什么。",
            "第二章在确认重生后，不重新从零讲世界，而是只讲与当前选择直接相关的那部分。",
            "第三章让信息进入人物试探对话，不再靠回忆硬抛。"
        ],
        retention_mechanics=[
            "第一章最大的钩子是怒值：她遭的罪太重，读者天然会想看这口气怎么出。",
            "第二章的钩子是时间点：她回来得够早，足以一切重来。",
            "第三章的钩子则是能力验证：她已经开始忍、开始算，说明这趟复仇不是空口发狠。",
            "读者被留下，不是因为谜团，而是因为血账开得足够大、回报预期足够强。"
        ],
        strong_points=[
            "复仇文最难的是先把恨值抬够，这本第一章几乎做到了满格。",
            "重生后的认知切换很快，避免了很多同类文常见的“刚重生还在发懵”拖沓。",
            "小宅斗试探接得很稳，让巨大宫变血债顺利落回少女闺阁，不会飘。"
        ],
        standout_lines=[
            "“原先金碧辉煌的宫殿在暗云笼罩下暗沉下来，仿佛巨大的囚笼，将里头的人困得牢牢实实。”",
            "“是日何时丧，予与汝皆亡！”",
            "“苍天不负人，苍天不负她！她回来了！”"
        ],
        techniques=["终局倒切", "高恨值复仇引擎", "重生校时", "堂姐妹试探", "小局验证大女主转变"],
        what_to_learn=[
            "如果题材本身就是复仇，就别怕前三章情绪太重，先把读者的站队做出来。",
            "重生回归后，要尽快用一场小交锋证明人物确实变了，否则读者只会觉得重生是口号。",
            "大血债要尽快落回眼前的人和事，否则会漂成大词。"
        ],
        avoid_copying=[
            "不要机械照搬“废后白绫 -> 少女重生”的经典复仇模版。",
            "不要只学它喊狠话，而忽略第三章那种真正克制、真正会算的转变。"
        ],
        current_gap="我们当前正文经常把张力分散在很多流程点里，而《重生之将门毒后》前三章的好，是它敢把所有字都压在同一根复仇主轴上，因而句句都像在往前顶。"
    ),
    ExampleSpec(
        slug="hebutongzhoudu",
        title="何不同舟渡",
        author="羡鱼珂",
        filename_match="何不同舟渡",
        tags=["古代言情", "乱世谍战", "家国", "求生", "身份迷局", "悬疑张力"],
        opening_pattern="家国崩塌序章 -> 雪地追逃与暴力羞辱 -> 遇上危险陌生人 -> 偷到谍报卷入大局",
        voice_signature="镜头冷、动作狠、景物带刀，叙述不絮叨，靠雪、江、血、井、暗道这些硬物把乱世压到人脸上。",
        pressure_source="国破家亡的大局压顶、底层少女的生存困境、岐兵暴力、叛臣身份之谜、陵安王逃亡线的谍战危险。",
        chapter_summaries=[
            "第一章先用一个极短却极有力的序，交代永康二十八年旧都失陷、新帝南逃、沥都府成为决战之地，然后毫不耽搁地切到南衣被商贾追打、为了一只玉镯死命护着的现场。玉镯背后又引出她在乱世中苦等章月回、一路流落寻人的个人执念。紧接着岐兵出现，她几乎在被凌辱的边缘绝地反杀，狂奔到渡口，遇见看似冷漠钓鱼的谢却山。整章最厉害的地方在于，它把“国破”的宏大叙事，狠狠压成了一个雪地里浑身是伤的小姑娘求活的身体经验。",
            "第二章则把谢却山正式写成一个危险又难测的人。他不给南衣慈悲，甚至递刀让她自戕，可她跳江后，他又一句“渡我去虎跪山”把她拽上乌篷船。船上这段既冷又暧昧：风雪、烛灯、湿衣、手腕上的镯子、他若有若无的目光，全是细节张力。最关键的是章尾，南衣偷了谢却山荷包，以为只是得了一笔银子，却被明确点出——那是她“所有劫难的开始”。于是谢却山从冷面路人，一下子变成会持续反噬她命运的人。",
            "第三章把偷荷包的后果立即兑现。南衣投宿、谢却山天未亮便追来、她跳井藏身，又在井底撞见带伤的庞遇。庞遇点破谢却山的真实身份：他是投敌卖国、专门南下搜捕陵安王的岐方重臣；同时庞遇从荷包里翻出绢信，确认接应计划泄露。到这里，南衣已经从一个想去找心上人的流民少女，被硬生生卷进了王朝生死线和谍报线里。第三章最值钱的不是单纯信息量，而是每一个信息都在即时抬高南衣的危险级别。"
        ],
        three_chapter_summary="前三章走的是“先把你扔进雪地里挨打，再把你按进更大的棋局里”的路线。第一章让你为南衣活下去而紧张，第二章让你开始戒备谢却山，第三章则彻底把局面升级成家国谍战。也就是说，这本书的前三章不靠解释时代背景留人，而是靠层层兑现的危险：你的身体危险刚过去，身份危险就来了；身份危险刚冒头，家国危险就盖下来。",
        story_opening_flow=[
            "先用极短的乱世序言把历史钉稳，但不沉迷背景，而是迅速落到南衣被追打、被羞辱、被迫求生的身体现场。",
            "通过玉镯和章月回，把她的个人愿望写得很具体，于是后面的一切危险都不是抽象悬疑，而是在损耗她去找心上人的可能。",
            "第二章在乌篷船上制造谢却山的复杂性：冷、危险、克制、贵气、让人不敢靠近，却又把她暂时从地狱边缘拎出来。",
            "第三章用偷来的荷包把两条线扣死：谢却山的追踪线与陵安王谍报线，南衣正式失去“只是一个路上女孩”的资格。"
        ],
        narrative_rhythm=[
            "第一章节奏非常猛，从序言落到追打，几乎没有空档，读者只能被拖着跑。",
            "第二章放慢，但不是松，乌篷船上的静反而让危险更黏、更冷。",
            "第三章重新加速，客栈搜人、跳井、井底见伤者、绢信泄密、身份揭穿，几乎一步一翻面。",
            "前三章整体是“暴力追生 -> 冷船试探 -> 井底大局揭开”，节奏变化非常有设计感。"
        ],
        character_and_relationship_setup=[
            "南衣首先被写成一个会疼、会怕、会偷、会求活的具体少女，因此后来卷入大局时不会轻飘。",
            "谢却山真正吸引人的，不只是危险，而是他危险中还保留着一种极度克制的秩序感，让人天然想追他到底站在哪边。",
            "庞遇出场很快就承担起“把私人生存线引到家国线”的桥接功能。",
            "章月回虽然并未真正出场，但玉镯与承诺让南衣一直有一个柔软的去处，因此她的硬境更刺人。"
        ],
        information_release_design=[
            "宏大背景只交代必要最小量，真正的信息释放靠人物被什么追、手里拿着什么、身边的人到底是谁。",
            "作者很擅长先让读者感受到危险，再揭示危险名字，这样信息天然带压迫感。",
            "谢却山的身份、庞遇的身份、绢信的意义不是一口气交代，而是一层层逼出来。"
        ],
        retention_mechanics=[
            "第一章留人：南衣能不能活下来？那枚镯子和章月回又意味着什么？",
            "第二章留人：谢却山究竟是好人、恶人，还是更危险的第三种人？",
            "第三章留人：荷包里到底藏了什么，南衣还回不回得去原本那条找人的路？",
            "每一章都把问题升级，而不是只是换场景。"
        ],
        strong_points=[
            "乱世感不是靠大词，而是靠身体疼痛、雪、鞭子、江水、井壁这些硬质细节做出来的。",
            "谢却山的危险魅力铺得很稳，绝不是简单的“冷面男主”。",
            "前三章就让小人物被家国大局碾到身上，格局和代价感都很足。"
        ],
        standout_lines=[
            "“乱世里，人人都披着一张皮，揭开那张皮，成为那张皮。”",
            "“一座只有一个出口的城，一个几乎不可能完成的任务。”",
            "“她并不知道，这才是她一切劫难的开始。”"
        ],
        techniques=["家国冷序", "身体性求生开场", "危险男性登场", "物件带线", "私线卷入谍战大局"],
        what_to_learn=[
            "如果故事有大格局，最有效的开法不是先讲朝局，而是先讲一个人快死了。",
            "把危险具象到身体和环境里，读者会比抽象说“局势紧张”更快入戏。",
            "强男主第一次出场，不一定要立刻显得温柔，危险与复杂反而更留人。",
            "让一个小物件同时承载情感线和剧情线，效率极高。"
        ],
        avoid_copying=[
            "不要照搬“流民少女 + 叛臣 + 谍报绢信”的具体剧情组合。",
            "不要只学它的冷句子，而忘了句子背后都有即时动作和即时危险支撑。"
        ],
        current_gap="我们当前正文常把“案子”和“情感”拆着写，而《何不同舟渡》前三章几乎每条线索都在立刻改变人物危险级别，因而案子本身也有强烈情绪张力。"
    ),
    ExampleSpec(
        slug="bei_wuqingdao_xiaoshidi_daozhui",
        title="被无情道小师弟倒追了",
        author="风歌且行",
        filename_match="被无情道小师弟倒追了",
        tags=["古代言情", "仙侠言情", "轻喜剧", "女主声口强", "暗恋", "风险突转"],
        opening_pattern="偷吃灵果的闹剧 -> 天才小师弟万众登场 -> 日常暗恋发酵 -> 任务死讯骤然砸落",
        voice_signature="女主声口极强，宋小河一开口就带着贪吃、厚脸皮、鲜活和可笑可爱的生命力，读者会先喜欢这个人，再跟着她吃刀。",
        pressure_source="低阶外门出身的自卑与暗恋距离、师父嫌弃式管教、仙盟等级差、任务危险、天才小师弟的生死线。",
        chapter_summaries=[
            "第一章几乎是靠宋小河的声口立住的。她偷溜进师父书房找灵果，自我说服“我就是最得宠的徒弟”，偷吃、看师父年轻画像、被梁檀堵窗、还理直气壮狡辩，整章笑点全来自她的贪吃与嘴硬。与此同时，作者也悄悄把几层核心设定带了出来：她是梁檀唯一的徒弟，但资质不高；她偷偷喜欢沈溪山；仙盟世界与她的距离并不小。第一章真正的功能不是推进大事，而是让读者在最短时间内爱上这个蠢萌热闹、满脑子都是吃和小师弟的姑娘。",
            "第二章几乎完全围绕沈溪山的“登场价值”展开。人群让道，少年着雪白金纹长袍、眉心一点朱砂，和逢阳灵尊对峙时不卑不亢、风雷咒引天雷而下，直接把“少剑仙”的分量打满。更重要的是，这一切都穿过宋小河的眼睛被看见，她的喜欢不再是口头设定，而是通过仰望、偷看、脸红、觉得世间所有好词都不够夸他来兑现。第二章表面写的是沈溪山出场，实则是在给这段不对等暗恋蓄电。",
            "第三章先补了仙门弟子灵力失窃的长期案件背景，让世界不至于只有恋爱与搞笑；随后又落回宋小河的日常修炼、木剑、鸡腿、考核失败、去前山偷看热闹这些生活细节，把她“又菜又爱看”的气质写得更加稳。关键转折出现在后半：沈溪山出任务，宋小河先被师父安慰说只是做做样子，转头却传来“沈溪山陨落”的噩耗。于是前三章并不止于轻喜剧，而是在读者已经被宋小河的喜欢收服之后，狠狠干下一刀。"
        ],
        three_chapter_summary="前三章走的是“先用人把你拽住，再用人把你刀住”的路线。第一章让你被宋小河的生命力吸进去，第二章让你和她一起把沈溪山抬上神坛，第三章则把这种欢快暗恋骤然撞上死亡消息。它的高明之处在于，刀不是为了反转而反转，而是先让你对这两个人有感情，再砸下来。",
        story_opening_flow=[
            "第一章先不讲大事件，先让女主在偷吃与被师父追打中一秒立住。",
            "随后借她对沈溪山的惦记，把“小师弟”作为情绪引擎悄悄放进故事中央。",
            "第二章用万众瞩目的出场把男主价值抬足，而且通过宋小河视角把仰慕写得具体可感。",
            "第三章补上仙盟案件背景和宋小河的普通生活，再把沈溪山出任务、死亡消息接上，让轻松和刀口完成一次漂亮的翻转。"
        ],
        narrative_rhythm=[
            "第一章节奏松快，几乎全靠人物声口和互动笑点推进。",
            "第二章节奏转成公开场面的大亮相，视觉感和仰望感都很强。",
            "第三章前半段回归日常，像是给读者一口气，后半段却直接把那口气掐断。",
            "前三章整体像一个笑着往前跑的人，突然在转角撞上血的消息，情绪反差非常有效。"
        ],
        character_and_relationship_setup=[
            "宋小河的人物不是靠“活泼”二字，而是靠一整套具体行为：偷吃、耍赖、会被打、爱凑热闹、考核压线、暗地里把沈溪山叫小师弟。",
            "沈溪山一出场就承担起“远不可及的光”的作用，和宋小河形成非常明确的高低差。",
            "梁檀表面嫌弃、实则护短，也让宋小河的生活底色不至于苦到发涩。",
            "第三章死讯一来，这段单向暗恋立刻有了命运感。"
        ],
        information_release_design=[
            "世界观与案件背景不是先讲，而是等读者已经接受了宋小河这个人，再慢慢加上去。",
            "沈溪山的价值不是靠别人口播，而是靠公开对峙、风雷咒、宋小河仰望三者共同完成。",
            "第三章把“大案背景”和“小情绪”并排写，却不互相打架，因为前者始终通过宋小河能不能再见到他来显出重量。"
        ],
        retention_mechanics=[
            "第一章留人：宋小河太鲜活，读者会想继续看她还能闯什么祸。",
            "第二章留人：沈溪山这么亮，宋小河这么喜欢，这段关系到底怎么长出来？",
            "第三章留人：如果他真死了，宋小河会怎样；如果没死，又会如何回来？",
            "它用的是典型的“先甜先热闹，再突然给痛”的留人机制。"
        ],
        strong_points=[
            "人物声口极强，开头完全不怕没有大事，因为光是看宋小河胡闹就有趣。",
            "沈溪山的登场值很高，第二章就把“为什么值得暗恋”写清了。",
            "第三章死讯转换特别狠，让前三章有完整的小弧线。"
        ],
        standout_lines=[
            "“巧了不是？我不就是师父座下最为得宠的徒弟么？”",
            "“端的是谦谦君子，温润如玉。”",
            "“她只能跟其他弟子一样，隐藏在那些艳羡的，嫉妒的，崇拜的目光之中，化作万千双眼睛里的其中之一，在无人注意的角落偷偷盯着沈溪山。”"
        ],
        techniques=["人物声口先行", "轻喜开场", "男主公开亮相", "暗恋视角加权", "先甜后刀"],
        what_to_learn=[
            "如果女主声口足够鲜活，开头不一定要立刻塞大事。",
            "让读者先跟着女主喜欢上一个人，再给那个人危险，刀感会重得多。",
            "轻松与风险不是对立的，关键在于风险要砸在已经建立好的情绪关系上。"
        ],
        avoid_copying=[
            "不要只学宋小河的嘴贫表层，而忽略她对人对事的真感情。",
            "不要机械模仿“第三章传死讯”，这种刀之所以有效，是前两章已经把人拽住了。"
        ],
        current_gap="我们当前正文很少让女主先凭声口把读者留住，往往太着急讲任务和机制。《被无情道小师弟倒追了》前三章提醒我们：只要人物够活，读者愿意先跟着人走，再接受后续的大局。"
    ),
]


def _load_source_files(source_dir: Path) -> list[Path]:
    return sorted(
        [
            item
            for item in source_dir.iterdir()
            if item.is_file() and item.suffix == ".txt" and not item.name.startswith("~$")
        ],
        key=lambda item: item.name,
    )


def _find_source_file(source_files: list[Path], match: str) -> Path:
    return next(item for item in source_files if match in item.name)


def _extract_first_three_chapters(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        normalized = _normalize_line(line)
        if _is_heading(normalized):
            headings.append((index, normalized))
        if len(headings) >= 4:
            break
    if len(headings) < 3:
        raise ValueError("Could not find at least three chapter headings.")

    chapters: list[tuple[str, str]] = []
    for idx, (start, title) in enumerate(headings[:3]):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip() + "\n"
        chapters.append((title, body))
    return chapters


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _render_notes(spec: ExampleSpec, chapter_titles: list[str]) -> str:
    lines: list[str] = [
        f"# {spec.title}",
        "",
        "- 来源：用户本地 TXT 资源（我的筛选）",
        f"- 作品：`{spec.title}`",
        f"- 作者：`{spec.author}`",
        "- 原文状态：已保存前三章全文 `chapter1.txt` / `chapter2.txt` / `chapter3.txt`",
        "",
        "## 前三章标题",
        "",
    ]
    for idx, title in enumerate(chapter_titles, start=1):
        lines.append(f"- 第{idx}章：`{title}`")
    lines.extend(
        [
            "",
            "## 第一章完整讲了什么",
            "",
            spec.chapter_summaries[0],
            "",
            "## 第二章完整讲了什么",
            "",
            spec.chapter_summaries[1],
            "",
            "## 第三章完整讲了什么",
            "",
            spec.chapter_summaries[2],
            "",
            "## 前三章整体故事是如何开展的",
            "",
            spec.three_chapter_summary,
            "",
            "## 前三章是如何一步步铺开的",
            "",
        ]
    )
    for item in spec.story_opening_flow:
        lines.append(f"- {item}")
    lines.extend(["", "## 前三章叙事节奏", ""])
    for item in spec.narrative_rhythm:
        lines.append(f"- {item}")
    lines.extend(["", "## 人物与关系是如何立住的", ""])
    for item in spec.character_and_relationship_setup:
        lines.append(f"- {item}")
    lines.extend(["", "## 信息是如何释放的", ""])
    for item in spec.information_release_design:
        lines.append(f"- {item}")
    lines.extend(["", "## 读者是如何被留下的", ""])
    for item in spec.retention_mechanics:
        lines.append(f"- {item}")
    lines.extend(["", "## 哪里写得好", ""])
    for item in spec.strong_points:
        lines.append(f"- {item}")
    lines.extend(["", "## 有哪些句子或写法特别好", ""])
    for item in spec.standout_lines:
        lines.append(f"- {item}")
    lines.extend(["", "## 主要写作手法", ""])
    for item in spec.techniques:
        lines.append(f"- {item}")
    lines.extend(["", "## 对我们最值得借鉴的点", ""])
    for item in spec.what_to_learn:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 和我们当前正文的差距",
            "",
            spec.current_gap,
            "",
            "## 不要直接照抄的地方",
            "",
        ]
    )
    for item in spec.avoid_copying:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _entry_payload(
    spec: ExampleSpec,
    source_file: Path,
    chapter_titles: list[str],
    chapter_texts: list[str],
) -> dict[str, object]:
    chapter_lengths = [len(text.strip()) for text in chapter_texts]
    return {
        "id": spec.slug,
        "title": spec.title,
        "author": spec.author,
        "platform": "本地TXT资源",
        "source_type": "user_supplied_local_txt",
        "source_txt_filename": source_file.name,
        "chapters_preserved": [1, 2, 3],
        "chapter_titles": chapter_titles,
        "chapter_lengths_chars": chapter_lengths,
        "chapters_1_3_total_length_chars": sum(chapter_lengths),
        "tags": spec.tags,
        "opening_pattern": spec.opening_pattern,
        "voice_signature": spec.voice_signature,
        "pressure_source": spec.pressure_source,
        "chapter_summaries": {
            "chapter1": spec.chapter_summaries[0],
            "chapter2": spec.chapter_summaries[1],
            "chapter3": spec.chapter_summaries[2],
        },
        "chapters_one_to_three_story_summary": spec.three_chapter_summary,
        "story_opening_flow": spec.story_opening_flow,
        "narrative_rhythm": spec.narrative_rhythm,
        "character_and_relationship_setup": spec.character_and_relationship_setup,
        "information_release_design": spec.information_release_design,
        "retention_mechanics": spec.retention_mechanics,
        "strong_points": spec.strong_points,
        "standout_lines": spec.standout_lines,
        "techniques": spec.techniques,
        "what_to_learn": spec.what_to_learn,
        "avoid_copying": spec.avoid_copying,
        "analysis_basis": "local_fulltext_chapters_1_3_read",
        "raw_text_status": "stored_local_txt_extract_chapters_1_3",
    }


def _write_readme() -> None:
    readme = """# 正例库说明

这个目录用于维护**可复用的小说正例样本卡**，服务于小说生成框架的分析、对照和优化。

## 当前策略

当前这套古言正例库，**允许保存前三章原文**，前提是文本来自用户本地提供的 `TXT` 资源，而不是从线上站点抓取。

这里保存的是：

- 前三章原文：
  - `chapter1.txt`
  - `chapter2.txt`
  - `chapter3.txt`
- 结构化样本卡：`entry.json`
- 深度分析：`notes.md`

## 目录结构

```text
positive_examples/
  README.md
  index.json
  ancient_openings/
    <example_id>/
      chapter1.txt
      chapter2.txt
      chapter3.txt
      entry.json
      notes.md
```

## 字段约定

`entry.json` 建议包含：

- `id`
- `title`
- `author`
- `platform`
- `source_type`
- `source_txt_filename`
- `chapters_preserved`
- `chapter_titles`
- `chapter_lengths_chars`
- `chapters_1_3_total_length_chars`
- `tags`
- `opening_pattern`
- `voice_signature`
- `pressure_source`
- `chapter_summaries`
- `chapters_one_to_three_story_summary`
- `story_opening_flow`
- `narrative_rhythm`
- `character_and_relationship_setup`
- `information_release_design`
- `retention_mechanics`
- `strong_points`
- `standout_lines`
- `techniques`
- `what_to_learn`
- `avoid_copying`
- `analysis_basis`
- `raw_text_status`

## 使用原则

1. 用它学习**前三章**是如何铺人物、立关系、埋主线、控节奏的。
2. 优先提炼“为什么能留住人”，而不是只摘抄“这一句写得真好”。
3. 如果引用样本里的句法或切入方式，先确认你学的是它的压力结构、信息顺序和留人机制，而不是只学表皮词汇。
4. 如果后续替换样本，请同步更新 `index.json` 与样本卡，不要留下过期条目。

## 当前内容

当前已收录：

- `古代言情前三章正例` 共 `5` 例
- 全部来自用户本地 `TXT` 资源（我的筛选）
- 每例均包含：
  - `chapter1.txt`
  - `chapter2.txt`
  - `chapter3.txt`
  - `entry.json`
  - `notes.md`
"""
    _write_text(README_PATH, readme)


def _write_index(specs: list[ExampleSpec]) -> None:
    payload = {
        "version": 3,
        "updated_at": "2026-04-30",
        "policy": {
            "store_full_original_text": True,
            "scope": "user_supplied_local_txt_only",
            "note": "仅保存来自用户本地提供的 TXT 前三章全文，不从公开站点抓取整章版权文本。",
        },
        "collections": [
            {
                "id": "ancient_openings_local_txt_three_chapter_corpus",
                "label": "古代言情前三章正例库",
                "theme": "古代言情 / 前三章拆书 / 本地全文样本",
                "platforms": ["本地TXT资源（我的筛选）"],
                "sample_count": len(specs),
                "entries": [f"ancient_openings/{spec.slug}" for spec in specs],
            }
        ],
    }
    _write_text(INDEX_PATH, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_aggregate_report(specs: list[ExampleSpec]) -> None:
    MARKET_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    md_lines = [
        "# 本地精选古言前三章拆书总报告",
        "",
        "- 日期：`2026-04-30`",
        "- 语料来源：用户本地 `女频言情/古代言情/我的筛选`",
        "- 样本范围：`5` 本古代言情小说，各保留并分析前三章全文",
        "",
        "## 本次替换的五本样本",
        "",
    ]
    for spec in specs:
        md_lines.append(f"- `{spec.title}` / `{spec.author}`")
    md_lines.extend(
        [
            "",
            "## 总体观察",
            "",
            "- 这五本的前三章都不是“先铺设定，再等剧情开始”，而是第一章就已经选定了最强压力源：",
            "  - `师尊在修无情道` 选的是身份高低反差与强制同居",
            "  - `良陈美锦` 选的是临终悔悟与母女情感债",
            "  - `重生之将门毒后` 选的是满门血债与重生复仇",
            "  - `何不同舟渡` 选的是乱世求生与谍战卷入",
            "  - `被无情道小师弟倒追了` 选的是女主声口与暗恋突变",
            "- 它们都特别清楚：前三章不是把世界讲明白，而是把“读者为什么现在必须继续看”讲明白。",
            "- 这些样本普遍比我们当前正文更会控制篇幅分配：",
            "  - 重要的不是解释机制",
            "  - 而是让人物在一个能立刻出后果的场面里说话、失手、挨打、偷看、迟疑、回避或被逼选择",
            "",
            "## 跨样本共性",
            "",
            "- **先选压力发动机，再写细节。** 这五本没有一本是靠“先写漂亮景色”留人的，所有景物都在服务压力。",
            "- **前三章通常各司其职。**",
            "  - 第一章负责把人拖进局里",
            "  - 第二章负责把人物关系或主矛盾钉牢",
            "  - 第三章负责把故事从“好看”推到“停不下来”",
            "- **信息释放从不平均。** 它们宁愿某一章只干一件大事，也不愿每章均匀撒一点情节和一点设定。",
            "- **读者被留下，是因为人和局互相咬住。** 不是角色单独可爱，也不是世界观单独宏大，而是人物的愿望立刻被局势卡住。",
            "",
            "## 我们当前正文最该对照修的地方",
            "",
            "- 少解释人物判断，多让人物在场面里被迫反应。",
            "- 少把篇幅花在 clue / procedure 上，多把篇幅花在“这条线索立刻让谁更痛、更近、更危险”。",
            "- 明确前三个 beat 的职责，不要让第一章前半在解释、后半才真正起戏。",
            "- 压低“他……她……”句首重复，更多用动作、空间、对话、物件和他人反应起句。",
            "",
            "## 分书拆解",
            "",
        ]
    )

    for spec in specs:
        md_lines.extend(
            [
                f"### {spec.title}",
                "",
                "#### 前三章完整在讲什么",
                "",
                f"- 第一章：{spec.chapter_summaries[0]}",
                f"- 第二章：{spec.chapter_summaries[1]}",
                f"- 第三章：{spec.chapter_summaries[2]}",
                "",
                "#### 前三章整体故事是如何开展的",
                "",
                spec.three_chapter_summary,
                "",
                "#### 前三章叙事节奏",
                "",
            ]
        )
        for item in spec.narrative_rhythm:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "#### 读者是如何被留下的", ""])
        for item in spec.retention_mechanics:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "#### 写得好的地方", ""])
        for item in spec.strong_points:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "#### 特别值得抄底层逻辑的句子/写法", ""])
        for item in spec.standout_lines:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "#### 对我们最直接的启发", ""])
        for item in spec.what_to_learn:
            md_lines.append(f"- {item}")
        md_lines.extend(["", "#### 与我们当前正文的差距", "", spec.current_gap, ""])

    _write_text(REPORT_MD, "\n".join(md_lines) + "\n")

    payload = {
        "date": "2026-04-30",
        "label": "local_selected_ancient_three_chapters_deep_dive",
        "source_dir_policy": "user_local_txt_only",
        "sample_count": len(specs),
        "titles": [spec.title for spec in specs],
        "cross_sample_findings": [
            "前三章最重要的不是把设定讲明白，而是选对压力发动机。",
            "最强样本会把第一章、第二章、第三章各自的职责拉开，而不是平均分配信息。",
            "读者留下来的原因，往往不是谜面多，而是人物的愿望与危险立刻咬合。",
            "我们当前正文要提升，关键在于把篇幅从程序说明重新分回人物张力与代价兑现。 ",
        ],
        "samples": [
            {
                "id": spec.slug,
                "title": spec.title,
                "author": spec.author,
                "tags": spec.tags,
                "chapter_summaries": spec.chapter_summaries,
                "three_chapter_summary": spec.three_chapter_summary,
                "narrative_rhythm": spec.narrative_rhythm,
                "retention_mechanics": spec.retention_mechanics,
                "strong_points": spec.strong_points,
                "standout_lines": spec.standout_lines,
                "what_to_learn": spec.what_to_learn,
                "current_gap": spec.current_gap,
            }
            for spec in specs
        ],
    }
    _write_text(REPORT_JSON, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def rebuild(source_dir: Path | None = None) -> None:
    source_dir = source_dir or _detect_source_dir()
    source_files = _load_source_files(source_dir)

    if ANCIENT_OUT.exists():
        shutil.rmtree(ANCIENT_OUT)
    ANCIENT_OUT.mkdir(parents=True, exist_ok=True)

    for spec in SPECS:
        source_file = _find_source_file(source_files, spec.filename_match)
        chapter_pairs = _extract_first_three_chapters(source_file.read_text(encoding="utf-8"))
        chapter_titles = [title for title, _ in chapter_pairs]
        chapter_texts = [text for _, text in chapter_pairs]

        example_dir = ANCIENT_OUT / spec.slug
        example_dir.mkdir(parents=True, exist_ok=True)
        for index, (_, chapter_text) in enumerate(chapter_pairs, start=1):
            _write_text(example_dir / f"chapter{index}.txt", chapter_text)
        _write_text(
            example_dir / "entry.json",
            json.dumps(
                _entry_payload(spec, source_file, chapter_titles, chapter_texts),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        _write_text(example_dir / "notes.md", _render_notes(spec, chapter_titles))

    _write_readme()
    _write_index(SPECS)
    _write_aggregate_report(SPECS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the local ancient-romance positive-example corpus from the curated TXT folder."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional override for the user-local TXT directory.",
    )
    args = parser.parse_args()
    rebuild(args.source_dir)


if __name__ == "__main__":
    main()
