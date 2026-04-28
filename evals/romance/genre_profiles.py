from __future__ import annotations

import json
from typing import Any


GENRE_PROFILES: dict[str, dict[str, str]] = {
    "general_web_fiction": {
        "display_name": "通用网文",
        "reader_promise": "Fast serialized readability, clear scene pressure, memorable characters, and a reason to continue.",
        "style_preference": "Readable, concrete, emotionally legible prose without ornate over-explanation.",
        "avoid_overreward": "Do not overreward genre-specific ritual, palace intrigue, taboo tension, or literary polish unless it creates page-level pull.",
        "motif_policy": "Repeated motifs are useful only when they create new plot function, reader expectation, escalation, or payoff.",
    },
    "historical_romance_intrigue": {
        "display_name": "古风权谋言情",
        "reader_promise": "克制但强烈的情感张力；身份与权力造成关系阻碍；误读、旧怨、试探与动摇；暗线推进与结尾钩子。",
        "style_preference": "古风但不堆辞藻；情绪含蓄，有潜台词；意象复现要有新功能。",
        "avoid_overreward": "只写权谋不推进感情；大段解释真实心意；过早和解；无功能重复旧伤、称呼、袖口等意象。",
        "motif_policy": "旧伤、称呼、袖口、礼制、寒意等意象可复现，但每次必须带来新代价、误读、线索推进或关系变化。",
    },
    "xianxia_fantasy_romance": {
        "display_name": "仙侠奇幻言情",
        "reader_promise": "奇幻设定服务情感张力；历险、试炼、契约、宿命推动关系变化；修炼规则、师门压力、资源竞争制造感情阻碍；救与被救、共感、误会带来亲密压力；结尾有更大危机或宿命钩子。",
        "style_preference": "有奇幻画面感；设定必须落到人物选择和情绪代价；战斗/试炼不能只炫技，要改变关系。",
        "avoid_overreward": "只写升级打怪不写感情；大段解释修炼体系；男女主互动太少；设定很大但不影响关系选择。",
        "motif_policy": "契约、灵力、法器、试炼危机等 motif 只有在改变互动、选择、误会、救护或亲密压力时才加分。",
    },
    "urban_modern_romance": {
        "display_name": "都市现代言情",
        "reader_promise": "现实压力下的情感拉扯；自然、有潜台词的现代对白；旧情、误会、边界感与暧昧张力；人物选择同时影响事业和关系；每章有新的信息差或情绪钩子。",
        "style_preference": "语言现代、克制、真实；对白推进关系；少空泛抒情，多动作和潜台词。",
        "avoid_overreward": "古风化表达；霸总模板化台词；只有情绪没有现实事件；大段解释心理而没有互动。",
        "motif_policy": "工作流程、会议、彩排、消息、旧物、玩笑等重复出现时，必须带来新的现实事件、边界变化、旧情回响或信息差。",
    },
}

TONE_PROFILES: dict[str, dict[str, str]] = {
    "restrained_angst": {
        "display_name": "克制虐恋",
        "emotional_promise": "克制；隐忍；误会压迫；爱而不能言；情感代价。",
        "style_preference": "少解释真实心意；用动作、选择、沉默和回避表现情绪；结尾保留未解的痛点。",
        "avoid_overreward": "过早和解；直白表白；把误会解释清楚；为虐而虐。",
    },
    "light_adventure_banter": {
        "display_name": "轻松冒险 / 欢喜冤家",
        "emotional_promise": "轻松冒险；斗嘴互动；危机中的甜；意外亲密；甜中带一点危险。",
        "style_preference": "节奏轻快；对白有反差；危机不要压得太沉；甜点来自行动而非表白。",
        "avoid_overreward": "沉重宿命感过强；大段设定解释；男女主互动太少；只打怪不暧昧。",
    },
    "light_witty_reunion": {
        "display_name": "轻松愉悦 / 旧情复燃",
        "emotional_promise": "轻松愉悦；互怼暧昧；甜中带酸；旧情未了；现实压力下的心动回潮。",
        "style_preference": "对白有节奏；小动作制造暧昧；情绪真实但不要过度沉重；轻松氛围中保留旧伤。",
        "avoid_overreward": "苦大仇深；大段伤痛独白；过度狗血；古风化表达；霸总模板化台词。",
    },
}


def resolve_genre_profile(profile_id: str | None) -> tuple[str, dict[str, str]]:
    key = str(profile_id or "").strip() or "historical_romance_intrigue"
    if key not in GENRE_PROFILES:
        key = "general_web_fiction"
    return key, GENRE_PROFILES[key]


def genre_profile_json(profile_id: str | None) -> str:
    key, profile = resolve_genre_profile(profile_id)
    payload: dict[str, Any] = {"profile_id": key, **profile}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def resolve_tone_profile(profile_id: str | None) -> tuple[str, dict[str, str]]:
    key = str(profile_id or "").strip() or "restrained_angst"
    if key not in TONE_PROFILES:
        key = "restrained_angst"
    return key, TONE_PROFILES[key]


def tone_profile_json(profile_id: str | None) -> str:
    key, profile = resolve_tone_profile(profile_id)
    payload: dict[str, Any] = {"profile_id": key, **profile}
    return json.dumps(payload, ensure_ascii=False, indent=2)
