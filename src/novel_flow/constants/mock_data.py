MOCK_BLUEPRINT_SEED: dict[str, object] = {
    "premise": {
        "title": "婚礼弃我后，他小叔亲手把我捧上神坛",
        "high_concept": "婚礼当天被背叛的策展人女主，被迫与新郎权势深沉的小叔结盟，从替身羞辱局一路逆袭到名利场核心。",
        "genre": "都市言情",
        "target_style": "知乎高反转长篇",
        "emotional_hook": "从被当作替身的羞辱感，走到被坚定选择的价值确认。",
        "central_conflict": "女主要在家族权力斗争与自我成长中证明自己不是任何人的替代品。",
        "selling_points": ["婚礼开局爆点", "豪门资源战", "女主事业成长", "评论区型反转"],
    },
    "characters": [
        {
            "name": "沈知微",
            "role": "女主",
            "goal": "夺回事业主导权并摆脱被定义的人生",
            "flaw": "习惯隐忍，过度独立",
            "relationship_hooks": ["曾把未婚夫当作唯一退路", "与男主从互相利用到真正信任"],
        },
        {
            "name": "傅承砚",
            "role": "男主",
            "goal": "借家族洗牌机会重塑商业版图",
            "flaw": "表达克制，不轻易示弱",
            "relationship_hooks": ["是前未婚夫的小叔", "欣赏女主的判断力与韧性"],
        },
        {
            "name": "傅景行",
            "role": "前未婚夫",
            "goal": "维持体面并追回旧爱资源",
            "flaw": "自私虚荣",
            "relationship_hooks": ["把女主当作过渡选择", "在失去后反复纠缠"],
        },
    ],
    "volume_titles": ["替身婚礼卷"],
    "chapter_plans": [
        {
            "chapter_id": "ch_001",
            "title": "婚礼变局",
            "objective": "用婚礼事故立刻打出替身羞辱与权力关系。",
            "tension": "女主在众目睽睽下失去婚约与体面。",
            "cliffhanger": "男主提出合作婚约，条件是她必须站到自己这边。",
            "planned_scene_count": 2,
        },
        {
            "chapter_id": "ch_002",
            "title": "合作协议",
            "objective": "建立交易关系和短期共同目标。",
            "tension": "女主对男主不信任，但已经没有更优选择。",
            "cliffhanger": "她发现男主手里握着前未婚夫真正的把柄。",
            "planned_scene_count": 2,
        },
    ],
}

MOCK_CRITIC_ISSUE_SEED: dict[str, object] = {
    "summary": "发现影响首章抓力与核心卖点表达的问题。",
    "issue": {
        "severity": "medium",
        "title": "核心冲突露出不足",
        "problem_type": "missing_core_conflict",
        "evidence": "首章尚未足够明确地指出女主被当作替身，卖点表达偏弱。",
        "impact": "读者可能无法快速识别故事主钩子。",
        "recommendation": "直接点明替身身份羞辱，并把冲突放在公开婚礼场景中。",
        "acceptance_criteria": [
            "出现替身相关关键词或同义表达",
            "出现公开场合的羞辱氛围",
            "读者能理解女主为何决定反击",
        ],
    },
}

MOCK_PATCH_CONTENT: str = (
    "我站在婚礼通道尽头，终于听见休息室里那句压低的抱怨。"
    "“如果不是她和阿宁眉眼有三分像，景行怎么会把人带到今天？”"
    "那一瞬间，我连指尖都凉了，原来这场人人称羡的婚礼，不过是把我钉进替身位置的公开处刑。"
    "我抬眼时，满厅宾客的目光像刀一样落下来，而我第一次清楚地意识到，这一次我不能再忍。"
)
