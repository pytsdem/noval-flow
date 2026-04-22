from __future__ import annotations

import json
from pathlib import Path

from evals.romance.harness import RomanceEvalHarness
from evals.romance.judges import RedundancyRuleAnalyzer, RomanceChapterJudge
from evals.romance.models import (
    RomanceCaseContextOverrides,
    RomanceCaseGoals,
    RomanceEvalCase,
)
from novel_flow.config import Settings
from novel_flow.llm.doubao import DoubaoLLMClient
from novel_flow.models.schemas import ChapterBrief, StoryPremise


REPORT_ROOT = Path("data/manual_eval_reports")
REPORT_JSON = REPORT_ROOT / "user_case_calibration_after.json"
REPORT_MD = REPORT_ROOT / "user_case_calibration_after.md"


def build_writer_context(case: RomanceEvalCase) -> str:
    return json.dumps(
        {
            "chapter_id": case.chapter_brief.chapter_id,
            "selection_summary_text": case.description,
            "time_anchor_text": case.chapter_brief.incoming_hook,
            "chapter_visible_context_text": case.chapter_brief.summary,
            "completed_chapter_memory_text": "",
            "scene_character_context_text": "；".join(case.chapter_brief.character_focus),
            "relationship_state_text": case.chapter_brief.relationship_reprice,
        },
        ensure_ascii=False,
    )


def make_case(
    *,
    case_id: str,
    title: str,
    description: str,
    tags: list[str],
    premise: dict,
    chapter_brief: dict,
    goals: dict,
) -> RomanceEvalCase:
    return RomanceEvalCase(
        case_id=case_id,
        title=title,
        description=description,
        tags=tags,
        premise=StoryPremise.model_validate(premise),
        chapter_brief=ChapterBrief.model_validate(chapter_brief),
        goals=RomanceCaseGoals.model_validate(goals),
        context_overrides=RomanceCaseContextOverrides(),
    )


CALIBRATION_CASES = [
    {
        "label": "strong_accept_divorce_letter",
        "expected_verdict": "pass",
        "case": make_case(
            case_id="user_case_divorce_letter",
            title="一纸休书",
            description="被遗弃六年的妻子收到太子夫君的休书。重点看情绪钩子、人物抓力、后续追读动力，以及男女主关系是否具备强牵引。",
            tags=["historical", "separation", "betrayal", "return-hook"],
            premise={
                "title": "一纸休书",
                "high_concept": "六年前被一场大火抛下的妻子，六年后在街边饺子摊收到丈夫送来的休书，却得知他已成了高高在上的太子。",
                "theme_statement": "真正伤人的不是抛弃本身，而是让人白白相信与等待。",
                "story_summary": "季九儿苦寻丈夫与孩子六年，只等来一封休书；而轿中的太子明知她不会轻易垮掉，却仍用最冷的方式斩断过去。",
                "genre": "historical romance",
                "target_style": "狠、冷、钩子硬、人物情绪克制但有穿透力",
                "emotional_hook": "一封休书把六年的苦等、贫困与爱恨一次性掀开。",
                "central_conflict": "他已位极人臣，她仍困在被抛弃的六年里；两人都没有真正从过去里抽身。",
                "core_hook": "太子让人送来休书，自己却坐在暗处等她的反应。",
                "escalation_path": [
                    "街边收到休书",
                    "六年苦寻被瞬间打翻",
                    "太子暗中窥看她的反应",
                ],
                "twist_blueprint": [
                    "表面是绝情抛弃",
                    "暗里却显出太子对她反应的异常在意",
                ],
                "ending_payoff": "从“休书已送达”推进到“第二个不速之客到来”，自然勾向下一章。",
                "selling_points": ["高概念休书开局", "人物命运落差", "强追读钩子"],
            },
            chapter_brief={
                "chapter_id": "ch_001",
                "title": "休书送到",
                "chapter_type": "relationship_pressure",
                "active_lines": ["line_royal_return"],
                "active_twists": ["twist_hidden_observer"],
                "summary": "季九儿在街边饺子摊收到太子送来的休书，六年寻找被一纸否定；表面看是被打发离开，暗里却埋下太子本人就在附近观察她反应的钩子。",
                "incoming_hook": "六年前一场大火后，她带着哑巴妹妹苦寻丈夫与孩子整整六年。",
                "opening_hook": "“季姑娘，这是太子殿下要我交给你的休书，请你过目。”",
                "core_scene": "街边摊前，传话人递来休书，季九儿一点点确认自己被彻底抛下；而镜头切到街尾华轿里，太子正等着听她的反应。",
                "chapter_object": "休书",
                "reader_emotion": "让读者感到憋屈、刺痛、愤怒，并被人物命运反差狠狠钩住。",
                "reader_belief": "读者此刻应坚定相信男主极度绝情，但又隐约感觉他并非真的毫不在意。",
                "allowed_info": [
                    "太子已经另娶",
                    "季九儿苦寻六年",
                    "太子安排她回上阳城并给予钱财",
                ],
                "allowed_clues": [
                    "休书是成婚当日就写好的",
                    "太子本人就在附近却不露面",
                    "他第一句问的是她哭了没有",
                ],
                "forbidden": [
                    "不能解释太子为何当年抛下她",
                    "不能让太子露面安抚",
                    "不能提前洗白男主",
                ],
                "world_limit": "季九儿身份低微，面对太子权势没有正面讨回公道的现实条件。",
                "character_focus": ["季九儿", "太子"],
                "character_shift": "季九儿从苦找不放，第一次被迫承认这六年可能全是笑话。",
                "relationship_reprice": "这段关系从失散夫妻，被重新定价为位高者对位低者的冷酷抛弃，同时又透出更复杂的未断掌控。",
                "emotional_turn": "她没有崩溃大哭，反而越平静越显得伤得深；而太子口中的冷漠命令，露出不合逻辑的在意。",
                "backstory_trigger": "六年前的大火与苦寻经历。",
                "scene_engine": "relationship_collision",
                "clue_reveal_mechanism": {
                    "style": "subordinate_report",
                    "pressure_source": "传话人与轿中主子的问答",
                    "surface_trigger": "李书德回报她的反应",
                    "first_noticer": "太子",
                    "owner_reaction": "太子语气更阴冷，却不肯现身",
                },
                "character_reentry_focus": {
                    "季九儿": "用她的右手残疾、粗布头巾、清醒平静来立人物。",
                    "太子": "先不露面，用轿中问话与下属反应来立其阴冷压迫感。",
                },
                "human_pain_anchor": "她和妹妹六年里饱饭都吃不上一顿，只为了找一个根本不想让她找到的人。",
                "romance_seed": "太子明明不露面，却第一句先问她哭了没有。",
                "small_payoff": "季九儿终于得到丈夫下落与态度的明确答案。",
                "ending_pull": "太子轿子离去后，饺子摊又来了第二个不速之客。",
                "info_budget": "target=2500-4500; hook must be hard; character fate shock must land on page",
            },
            goals={
                "chapter_goal": "用一封休书完成高概念开局，并把女主六年苦寻的代价砸在读者脸上。",
                "emotional_goal": "让读者又疼又气，同时被人物命运牢牢勾住。",
                "relationship_goal": "把这段关系定成“表面彻底抛弃，暗里仍未断掌控”的危险结构。",
                "hook_goal": "结尾必须留下更强的不速之客钩子。",
                "continuation_drive": "让读者想立刻知道太子到底要做到多绝，以及第二个来的人是谁。",
            },
        ),
        "text": """“季姑娘，这是太子殿下要我交给你的休书，请你过目。”
春暖花开，西郡皇朝国泰民安，风调雨顺，京都子城一派欣欣向荣的景象，马鸣车过，茶过飘香。
天子脚下的人们穿着也尤其华贵，谈吐优雅有理，譬如眼前这个年轻的男子，一身绫罗绸缎在身坐在格格不入的路边饺子摊上，却依然彬彬有礼地将一份淡黄的书信递到她面前。
“休书？”
像是听不懂他说的似的，季九儿又喃喃地重复一遍。
才二十二岁的她梳着妇人的发髻，没有珠钗手饰，为了方便干活还包扎着一块粗布的头巾，纤瘦的脸上五官不扬，只有一双大眼黑白分明，过分的执着有神。
而视线落到桌上的休书时，唯一能看的眼也黯了下去。
原来他真得是当朝一手遮天的太子殿下，下毒毒死自己的母妃，在百官众目睽睽之下上演殿前斩兄，事后逼迫自己中庸的父皇写下封太子的诏书，培植党羽监国涉政。
他是一个可怕到令人发指的执权太子，不是上阳城那个只会逛青楼、进赌场的有钱公子哥……多么大的反差，纵然她早查觉他不会是一般人，却怎么都料不到他是高入云端的太子。
垂在身侧裙袍上的右手无声地动了动，不是一只好看的手，长着薄薄的一层茧不似女子的手，手指微弱地动了两下后终是无力垂下，季九儿终究放弃，伸出左手去接书信，想要拆开来一只手却是无能为力。
坐在桌对面的年轻男子见状连忙帮她拆了开来。
“多谢。”季九儿捏着薄薄的纸，休书两个字触目惊心，她惊讶自己还能这样平静地说话，也许是多年的生活早把她的性子磨没了。
“没事。”年轻男子看向她始终垂着的手显得有些局促，“季姑娘，你的手……”
“六年前家里起了大火，我想去救我的丈夫和儿子，被困在火中，右手就这样废了。”季九儿低眉，坦然地说完，没有过多的表情。
休书上的字的确是他的笔迹，一字一字冷漠无情。
男子震惊，他当然知道她口中的丈夫和儿子就是自己侍奉的太子和大世子，只是她沉默安静的神色让他太过意外，她说得好像不是自己的事一样。
“笔墨不是新的，公子策……太子殿下什么时候写下的？”季九儿又问，干净利落。
男子愣了下，忙回道，“哦，是同太子妃成亲那日写下的。”
同太子妃成亲……呵，又娶了啊。
休书一直写着，却到瞒不住的关头才拿出来打发她。

捏着纸的手指指尖微微战粟，季九儿咬着牙齿，死死地咬着，那她这六年来的寻找算什么，自欺欺人吗？
“季姑娘……”年轻男子担忧地注视着她。
“我不知道六年前那场火是他想摆脱我、摆脱过去的身份才放的。”没有落泪，没有故作逞强的微笑，季九儿只是很平静地叙述出事实，“其实他可以和我讲明白，那我不会平白浪费六年光阴去做些无谓的事，我和小妹走到哪都是身无分文，饱饭都没吃过一顿，就只是为了找他和孩子。”
这大概是她季九儿这辈子最憋屈的事，她为了找个根本不想让自己找到的人而放弃吃饱饭，都不像她季九儿了。
谈到钱，年轻男子才想起自己的使命，忙道，“季姑娘，我会派人一路护送你和令妹安全无虞地回到上阳城，至于钱方面不用担心，太子吩咐过要让季姑娘下半辈子足以富裕过活。”
连露个面都不肯，写了休书就要她走……还真像他会做的事，绝情利落。
也是，堂堂一国的太子殿下怎么会愿意有一个青楼贱籍出身的糟糠之妻。
“好，那麻烦爷了。”季九儿从容答应，没有一点拐弯抹角，左手抓着休书站了起来，脸上有着明显的送客之意，“爷要留下来吃碗饺子吗？”
年轻男子脸羞红一大半，摇着头窘迫地站起身，“我叫李书德，不是什么爷，只是个跟在太子身边做事的奴才而已。”
“李爷的谈吐不像。”季九儿淡淡地说道，把休书塞入袖子，眼神飘向饺子摊热气腾腾的锅前。
李书德顺着她的视线看过去，只见一个和她身线差不多纤瘦的少女站在锅前忙着下饺子，卷起的袖子下露出一小截白藕似的细臂，灵巧的脸被薰得满头大汗，不时拿帕子擦去。
“她是我妹妹。”季九儿见他看自己的妹妹便说道，又补一句，“是个哑巴。”
“季姑娘，要是还需要什么照顾请尽管说，太子一定会竭力尽最大的补偿。”李书德几乎是冲口而出，他也不知道自己是怎么了，也许是格外同情携妹六年寻夫的季姑娘。
季九儿深深地看了他一眼，嘴唇紧抿，半晌才一字一字道，“告诉他，他欠我季九儿的，他这辈子都还不起。”

李书德惊愕异常，还想说些什么，季九儿却已经走向锅前，摆明把他晾在这边，顿了顿，李书德摸摸鼻子离去。
“小末儿，我来。”季九儿走到锅前把小妹推开，只以左手翻着饺子，身旁的少女望了一眼离去的李书德，焦急地冲她指手画脚。
季九儿看懂她的疑问，滞了半晌道，“小末儿，咱们离开上阳城六年了，也该回去了。”
看着妹妹比手画脚叙述自己的意思，季九儿忽然很想掉眼泪，她浪费了整整六年，这六年她可以重入青楼，她可以接客，六年足以她挣到很多钱去治小妹的哑病，她却没有，就只是为了找他。
“不找了。”季九儿勉强笑笑，推过一个碗，麻利地盛起一碗饺子，“你今年都十六了，再不治拖了时间，嗓子一辈子都好不了怎么办。”
知道瞒不过去，往锅里盛了几勺水，季九儿缓慢地说道，“你姐夫把我休了，刚那人是他的奴才……小末儿，姐真是傻气，找了六年就等到一张休书。”

小末比划地飞快，看得季九儿眼花缭乱，最后她只好抬起左手阻止小末继续比划下去，“都六年了，没有这一封休书姐也撑不下去了，咱还能找一辈子吗？”
季九儿扯起嘴角无谓地笑起来，“今天早点收摊吧，那位李爷说他会给我们很多钱，等回到上阳城咱们就去治你的嗓子。”
连“你姐夫”三个字她都无法再说出来。
小末直直地盯着她，好像想看穿她心里想的，季九儿低下头假装忙碌地收摊，却不慎打翻一碗热汤，滚烫的汤水泼洒在手臂下，刺入心肺的痛疼得她龇牙咧嘴地大叫，“痛、痛，小末儿，湿帕子！”
小末被吓一跳，连忙卷起帕子绞湿再覆到她的手臂上，然后慢慢卷起她的袖子，湿掉的书纸被小末抽了出来。
“休书”两个硕大的字被水渍晕开，小末突然哭了出来，季九儿瞥了上面的字一眼，然后把头撇到一边，不再去看。

街尾停着一顶富贵华丽的八抬大轿，珍珠流苏沿着四角垂下在风中轻晃，刺目的尊贵金色轿身外，细细的白纱覆盖住整顶过大的轿子，不烈的日头下，几个轿夫表情木然地站立等待着，不远处，一小队禁卫军严阵以待。
李书德一路小跑到轿前，掀袍单膝跪下，“奴才叩见太子千岁。回主子，奴才已经把休书交给季姑娘了。”
“她哭了么？”轿里传出一个男子的声音，初夏微燥的空气里，他的嗓音阴鸷到蛊惑人心。
怎么会这么问？李书德愣了下，一五一十地回道，“回主子，季姑娘没有哭，她接受主子的安排。”
“就这样？”男子的声音透了几分阴霾。
“回主子，季姑娘说……”

“迟疑什么，说。”
“是。季姑娘说，主子欠她的，这辈子都还不起。”李书德冷汗漓淋地说完，揣测着主子阴晴不定心思，他只是传话应该不会受责罚吧，虽然这话并不好听。
还不起么……
“回宫。”男子再没有过多的言语，阴冷地落下话。
轿夫们立即打起精神，搓搓手抬起轿子往宫门的方向走去。
李书德想想，迈开步伐跟上轿子，鼓足勇气开口，“主子，恕奴才斗胆，奴才以为季姑娘很可怜。”
“你多嘴了。”轿里传出男子分外冷漠的声音，让人不禁生起一阵寒气。
“奴才该死。”
“她撑得住。”
她撑得住，所有人都会垮掉，唯有季九儿不会，连一纸休书都不能让她垮掉，季九儿还怎么能垮。
李书德诧异地张大嘴，刚刚是主子说话了？撑得住，那是什么意思？
饺子摊收到一半，这个从来都乏人问津的路边摊继李书德之后，迎来第二个不速之客。""",
    },
    {
        "label": "weak_reject_mother_son_pressure",
        "expected_verdict": "blocked",
        "case": make_case(
            case_id="user_case_non_romance_ceremony",
            title="归宗礼上的旧案威压",
            description="这是一段宫廷权力对峙文本，氛围和 prose 很强，但没有言情主轴。用它测试 romance eval 会不会被表层张力骗高分。",
            tags=["court", "political", "non-romance", "hard-negative"],
            premise={
                "title": "归宗礼上的旧案威压",
                "high_concept": "一场宗室归宗礼里，回京功臣与掌权王妃在百官注视下暗刺旧案。",
                "theme_statement": "权力和旧恨可以制造高压，不等于言情张力。",
                "story_summary": "文本核心是礼制、旧案与权力威压，缺乏男女主之间的浪漫关系推进。",
                "genre": "historical suspense",
                "target_style": "礼制压迫感强、氛围浓、细节密",
                "emotional_hook": "仪式表面的平静下藏着旧案威胁。",
                "central_conflict": "人物之间是权力与旧案纠缠，而非言情主线。",
                "core_hook": "所有人都知道仪式平静只是表象。",
                "escalation_path": ["仪式推进", "低声威胁", "旧案账目被重新翻起"],
                "twist_blueprint": ["紧张感主要来自政治关系", "不是 романтический 双人推进"],
                "ending_payoff": "文本应被 romance eval 严格识别为非强言情样本。",
                "selling_points": ["氛围强", "礼制细", "非言情负例"],
            },
            chapter_brief={
                "chapter_id": "ch_007",
                "title": "礼成之后",
                "chapter_type": "relationship_pressure",
                "active_lines": ["line_old_case"],
                "active_twists": ["twist_hidden_account"],
                "summary": "归宗礼上人物以旧案互刺，场面高压，但文本并未建立男女主言情关系的推进或追读浪漫张力。",
                "incoming_hook": "归宗礼开始前，百官都在等这场礼制会不会出事。",
                "opening_hook": "归宗礼本应庄严，却被一股说不清的旧案寒意压住。",
                "core_scene": "大礼流程中人物低声互刺旧案，百官围观。",
                "chapter_object": "归宗文书",
                "reader_emotion": "应以冷压与权谋感为主，而不是恋爱驱动力。",
                "reader_belief": "读者应感到这是强氛围权谋场，但不是有效 romance chapter。",
                "allowed_info": [
                    "礼制流程完整",
                    "旧案压力存在",
                    "人物彼此提防",
                ],
                "allowed_clues": [
                    "旧军牌",
                    "茶渍",
                    "御史台记事簿",
                ],
                "forbidden": [
                    "不能硬判成 romance pass",
                    "不能把非恋爱高压误当成双人化学反应",
                ],
                "world_limit": "文本主要冲突是政治亲属与旧案压力，不具备恋爱推进基础。",
                "character_focus": ["萧湛", "苏蘅"],
                "character_shift": "人物状态变化极小，更偏威压重复。",
                "relationship_reprice": "不是 romance relationship，而是旧案权力关系再度收紧。",
                "emotional_turn": "威压加深，但浪漫关系没有成立。",
                "backstory_trigger": "旧案与归宗礼。",
                "scene_engine": "court_pressure",
                "clue_reveal_mechanism": {
                    "style": "direct_pressure",
                    "pressure_source": "归宗礼与低声威胁",
                    "surface_trigger": "旧案发问",
                    "first_noticer": "双方当事人",
                    "owner_reaction": "继续维持礼制表面",
                },
                "character_reentry_focus": {
                    "萧湛": "突出军功与压迫感。",
                    "苏蘅": "突出主母姿态与隐忍。",
                },
                "human_pain_anchor": "表面礼成，内里全是旧案余烬。",
                "romance_seed": "",
                "small_payoff": "旧案威胁被再次提起。",
                "ending_pull": "文本应该让评审意识到：氛围强不等于 romance 成立。",
                "info_budget": "target=1500-3500; negative case for stricter romance standards",
            },
            goals={
                "chapter_goal": "测试 romance eval 会不会被非恋爱高压 prose 误判成好言情。",
                "emotional_goal": "区分政治威压和 romance 张力。",
                "relationship_goal": "若无有效 romance 关系推进，不应给高分。",
                "hook_goal": "就算 prose 强，也不能仅凭氛围通过 romance pass。",
                "continuation_drive": "这个 case 的价值在于防止 eval 被假张力骗过。",
            },
        ),
        "text": """宫门下的青石板被马蹄踩得微颤，萧湛翻身下马时，腰间悬着的军功令牌撞得叮当作响——那是边地风沙磨出来的沉实声响，与周遭百官衣袂窸窣的礼制声格格不入。他只淡淡颔首回应上前见礼的礼部官员，黑沉的目光径直越过攒动的官帽，落在王府仪仗最前方的苏蘅身上，下颌线绷紧成一道冷硬的弧线。躲在苏蘅身后的萧宁被这扫过的目光惊得缩了缩肩，指尖攥紧了母亲的衣摆。

苏蘅立在鎏金华盖下，一身石青色织金褙子衬得她面色愈发苍白。听见令牌相撞的声响时，她的肩背几不可察地绷紧，搭在鎏金茶盏边缘的指尖微微蜷起，茶液晃了晃，溅在暗纹袖口上也未察觉。百官只看见她端严的主母姿态，无人留意到她腕骨处因用力而泛起的青白。

萧湛抬脚迈步，靴底碾过青石板时，力道重得震得阶前铜炉里的香灰簌簌落了半寸。他的目光裹着淬冰的寒意，像根针似的钉在苏蘅身上。礼部侍郎跟在身侧，喉结滚了又滚，眼角瞥见远处御史台的官员已经掏出记事簿，笔尖悬在素纸上方，终究没敢出声。萧湛一步步走向归宗仪式的殿门，脚步稳得像踩在刀尖上。

殿门内的内侍捧着锦裹的归宗文书趋步上前，尖细的唱喏声在肃穆的殿廊下荡开：“萧湛接归宗文书——”锦缎封面上烫着明黄宗室纹，边角压着枢密院朱红大印，是他归京的合法凭据。阶下一位须发皆白的宗室老臣捋着银须颔首，目光里满是对礼法周全的赞许，全然未察觉萧湛垂在身侧的手指已骤然蜷起，指节绷得泛出青白。

苏蘅端着鎏金茶盏的手纹丝未动，只眼尾飞快扫过那封文书，又迅速落回案头摊开的宗谱上，肩背绷得像一张拉满的弓。萧湛上前一步，指尖触到锦缎的瞬间，指腹被朱印棱边硌得生疼。他攥紧文书，指节几乎要嵌进锦缎里，垂眼时下颌线绷得快要裂开，喉结滚了半圈却没发出一点声音，缓缓屈膝，准备行那套恪守礼制的母子跪拜礼。

萧湛膝盖磕在冰凉的金砖上，礼毕起身时借着俯身的势头骤然凑近，黑眸压得极低，只有两人能听见的声音像淬了冰：“母亲，卫朔的祭礼，您去了吗？”直起身时动作幅度稍大，袖口自然滑落，半块边缘磨得发白的旧军牌露了一瞬，他眼角余光扫到阶下御史台官员的笔尖动了动，指尖猛地收紧，飞快将军牌掩回袖中。

鎏金茶盏猛地晃了一下，碧色茶液溅在苏蘅暗纹袖口的折痕里，洇开一小片深褐。她指尖掐进掌心，指腹抵着茶盏的鎏金边缘，声线平稳得无一丝波澜：“按例已祭。”身后的萧宁被两人间的低气压惊得攥紧她的衣摆，轻轻拽了拽，她却连眼尾都没扫过去，萧宁指尖飞快松开，缩回袖笼，头埋得更低。

萧湛直起身退回原位，腰背挺得笔直，仿佛方才的低语从未发生，抬手接过内侍递来的归宗文书，继续恪守礼制的流程。苏蘅端着茶盏的手纹丝不动，袖口的茶渍像块隐秘的烙印，在百官赞许的目光里，她连呼吸都放得极缓。

内侍尖细的唱喏声落定：“归宗礼成——”

殿廊下的百官终于松了口气，低低的赞许声此起彼伏。几个年轻官员偷偷交换了释然的眼神，阶下的御史台官员也悄悄合上了摊开的记事簿。

萧湛理了理玄色锦袍的下摆，指尖不经意扫过袖中那半块磨损的旧军牌。他眼角余光扫过御史台方向，脚步顿了半瞬，抬眼时黑眸骤然收紧，寒意像冰棱似的扎向案后的苏蘅。

他转身迈步，擦肩而过时，只有苏蘅能听见他压得极低的声音：“母亲，旧案的账，我会慢慢算。”

苏蘅端坐在案后，鎏金茶盏稳稳搁在描金云纹案几上，袖口沾着一点淡褐色的茶渍。

她放在案下的指尖掐得更紧，肩背绷得愈发笔直，连眼尾都没动一下。只有茶盏上浮起的热气，被她极轻的呼吸搅得微微晃了晃。

身后的萧宁缩着身子，指尖揪着她的衣摆，她却连余光都没分给这个怯懦的次子。

萧湛转身迈步，玄色锦袍的下摆扫过冰凉的金砖，行至殿门口时忽然侧身，压低的嗓音混在百官低语里，只有苏蘅能听见：“母亲，旧案的账，我会慢慢算。”阶下御史台的官员忽然抬眼，笔尖悬在记事簿上顿了半瞬。

她的呼吸猛地一滞，随即又压得匀净，目光牢牢锁在殿门口的空茫里。案下的指节绷得泛出青白，袖口的茶渍在殿外天光下泛着冷光，脊背挺得笔直。眼角余光扫过身后缩成一团的萧宁，指尖无意识地收紧了几分。""",
    },
    {
        "label": "strong_reject_flat_summary",
        "expected_verdict": "blocked",
        "case": make_case(
            case_id="user_case_flat_summary",
            title="朝堂重逢劣质摘要",
            description="这个文本表面是古言重逢言情，但几乎只有摘要式复述与重复判断。用来测试 eval 是否能严厉拦住“像提纲扩写”的假正文。",
            tags=["historical", "flat", "summary-prose", "hard-negative"],
            premise={
                "title": "折雪入京",
                "high_concept": "被流放三年的世子回京，与曾在旧案中指证他的旧爱朝堂重逢。",
                "theme_statement": "再强的设定也救不了毫无场面的摘要式正文。",
                "story_summary": "朝堂重逢本应高压拉扯，但文本若只会说“她很冷，他也很冷”，就不应被 romance eval 放过。",
                "genre": "historical romance",
                "target_style": "高压、克制、潜台词强",
                "emotional_hook": "旧案重逢应当像刀锋擦过旧伤。",
                "central_conflict": "敌意、误解与旧情纠缠在一起。",
                "core_hook": "重逢与旧案一起压下来。",
                "escalation_path": ["朝堂重逢", "档册试探", "书吏之死"],
                "twist_blueprint": ["她像叛徒", "但她的破绽令人起疑"],
                "ending_payoff": "高质量正文应让旧案与关系同时推进。",
                "selling_points": ["朝堂试探", "误读拉扯", "硬尾钩"],
            },
            chapter_brief={
                "chapter_id": "ch_012",
                "title": "雪靴未干",
                "chapter_type": "relationship_pressure",
                "active_lines": ["line_old_case"],
                "active_twists": ["twist_false_testimony"],
                "summary": "谢临川在朝堂上借调档册试探旧案，却被沈知微以更冷的方式顶回去；两人的敌意第一次出现了无法忽视的停顿。",
                "incoming_hook": "昨夜他带着北地军功归京，今晨奉诏入殿。",
                "opening_hook": "圣旨刚念到旧案名目，沈知微就抬起了眼。",
                "core_scene": "男主必须在文武百官面前接住羞辱与机会，女主则要在众目睽睽之下继续扮演站在他对面的人。",
                "chapter_object": "三年前军粮转运的原始档册",
                "reader_emotion": "应感到寒意、怨恨和压不住的在意。",
                "reader_belief": "读者应开始怀疑她不是真的背叛。",
                "allowed_info": ["回京未平反", "旧案档册仍在", "女主对旧案有本能反应"],
                "allowed_clues": ["停顿一拍", "避开旧伤", "称呼更疏远"],
                "forbidden": ["不能提前坦白", "不能只写摘要", "不能关系原地踏步"],
                "world_limit": "殿前无人可以公开推翻先帝旧判。",
                "character_focus": ["谢临川", "沈知微"],
                "character_shift": "男主从报复欲转向更危险的试探。",
                "relationship_reprice": "她从叛徒变成仍能影响他呼吸的人。",
                "emotional_turn": "失控边缘的人先成了他自己。",
                "backstory_trigger": "",
                "scene_engine": "court_pressure",
                "clue_reveal_mechanism": {
                    "style": "natural_exposure",
                    "pressure_source": "殿前问答与旧案名目",
                    "surface_trigger": "内库档册被抬上殿时的称呼变化",
                    "first_noticer": "谢临川",
                    "owner_reaction": "沈知微立刻把情绪压回礼制里",
                },
                "character_reentry_focus": {
                    "沈知微": "用礼制、袖口、称呼和避视重新立她。",
                },
                "human_pain_anchor": "鞋底雪水未干，就要跪在曾判他死路的人面前接旨。",
                "romance_seed": "她改口叫他“谢世子”的那一刻，他先注意到的是她声音更冷。",
                "small_payoff": "他拿到查档口子。",
                "ending_pull": "刚出殿门，便得知誊抄旧档的书吏死了。",
                "info_budget": "target=2500-4200; relationship shift must land on page",
            },
            goals={
                "chapter_goal": "测试 eval 会不会拦住没有场面、只有摘要复述的弱文本。",
                "emotional_goal": "避免被设定层面的好卖点骗高分。",
                "relationship_goal": "如果关系没有在页上变化，应强力拦下。",
                "hook_goal": "若尾钩只是带过，也不应被放过。",
                "continuation_drive": "高概念题材也要靠真实场面兑现。",
            },
        ),
        "text": """谢临川回京以后，在朝堂上又见到了沈知微。他觉得她很冷，她也觉得他很冷。旧案让他们都很难受，所以气氛一直很压抑。

他想查档，她按规矩答应。她很冷，他也很冷。她很冷，他也很冷。两个人都想到从前，但谁也没有做出新的反应。

散朝以后，他还是觉得她很冷，她也还是觉得他很冷。后来有人告诉他书吏死了，他决定以后再查。""",
    },
]


def evaluate_case(sample: dict) -> dict:
    settings = Settings.from_env()
    llm = DoubaoLLMClient(
        api_key=settings.doubao_api_key,
        model=settings.doubao_model,
        base_url=settings.doubao_base_url,
    )
    case = sample["case"]
    text = sample["text"]
    judge = RomanceChapterJudge(llm).judge(
        case=case,
        writer_context_json=build_writer_context(case),
        chapter_execution_json=json.dumps(
            {
                "chapter_id": case.chapter_brief.chapter_id,
                "chapter_text": text,
                "stage_log": [],
                "review_reports": {},
                "content_blocks": [],
            },
            ensure_ascii=False,
        ),
        chapter_text=text,
    )
    rule = RedundancyRuleAnalyzer().analyze(
        chapter_text=text,
        stage_log=[],
        review_reports={},
    )
    metrics = RomanceEvalHarness._judge_metrics_to_core(
        judge=judge,
        rule_redundancy=rule,
    )
    verdict, flags, targets = RomanceEvalHarness._derive_actionability(
        metrics=metrics,
        breakdowns={
            "male_lead_attraction": judge.male_lead_attraction,
            "female_lead_attraction": judge.female_lead_attraction,
            "lead_pair_chemistry": judge.lead_pair_chemistry,
            "opening_hook_score": judge.opening_hook,
            "ending_hook_score": judge.ending_hook,
            "judge_redundancy_score": judge.redundancy,
            "rule_redundancy_score": rule,
        },
        diagnosis=judge.diagnosis,
        judge_errors=[],
    )
    return {
        "label": sample["label"],
        "expected_verdict": sample["expected_verdict"],
        "actual_verdict": verdict,
        "matched_expectation": verdict == sample["expected_verdict"],
        "title": case.title,
        "description": case.description,
        "text": text,
        "scores": {key: round(value.score, 2) for key, value in metrics.items()},
        "judge_payload": judge.model_dump(mode="json"),
        "rule_redundancy": rule.model_dump(mode="json"),
        "hard_fail_flags": [item.model_dump(mode="json") for item in flags],
        "top_targets": [item.model_dump(mode="json") for item in targets[:5]],
    }


def render_markdown(results: list[dict]) -> str:
    lines = [
        "# User Calibration Suite",
        "",
        f"- total_cases: {len(results)}",
        f"- matched_expectation: {sum(1 for item in results if item['matched_expectation'])}/{len(results)}",
        "",
    ]
    for item in results:
        lines.extend(
            [
                f"## {item['label']}",
                "",
                f"- title: {item['title']}",
                f"- expected_verdict: `{item['expected_verdict']}`",
                f"- actual_verdict: `{item['actual_verdict']}`",
                f"- matched_expectation: `{str(item['matched_expectation']).lower()}`",
                f"- hard_fail_flags: {', '.join(flag['flag_type'] for flag in item['hard_fail_flags']) or 'None'}",
                f"- top_targets: {', '.join(target['target_module'] for target in item['top_targets']) or 'None'}",
                "",
                "```text",
                item["text"],
                "```",
                "",
                "| metric | score |",
                "| --- | ---: |",
            ]
        )
        for key, value in item["scores"].items():
            lines.append(f"| {key} | {value:.2f} |")
        lines.extend(
            [
                "",
                f"- romance_tension_reason: {item['judge_payload']['romance_tension']['reason']}",
                f"- relationship_progression_reason: {item['judge_payload']['relationship_progression']['reason']}",
                f"- redundancy_reason: {item['judge_payload']['redundancy']['reason']}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    results = [evaluate_case(sample) for sample in CALIBRATION_CASES]
    payload = {
        "summary": {
            "total_cases": len(results),
            "matched_expectation": sum(1 for item in results if item["matched_expectation"]),
            "expected_verdicts": {item["label"]: item["expected_verdict"] for item in results},
            "actual_verdicts": {item["label"]: item["actual_verdict"] for item in results},
        },
        "results": results,
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(results), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
