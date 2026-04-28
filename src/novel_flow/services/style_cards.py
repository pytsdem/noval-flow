from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


_STYLE_CARD_DIR = Path(__file__).resolve().parents[3] / "prompts" / "style_cards"
_SHARED_STYLE_CARD_FILE = "shared_base.txt"
_DEFAULT_FOCUS_STYLE_CARD_FILE = "general.txt"


_NOVEL_TYPE_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "value": "auto",
        "label": "自动判断 / 通用言情",
        "group": "通用",
        "genre_label": "通用言情",
        "style_direction": "general",
        "direction_label": "通用连载",
        "default_style_request": "",
        "description": "不强行指定频道，系统按题材需求和额外风格要求自动匹配。",
        "aliases": ("auto", "自动判断", "通用言情"),
    },
    {
        "value": "ancient_romance",
        "label": "古代言情",
        "group": "古代言情",
        "genre_label": "古代言情",
        "style_direction": "historical_intrigue",
        "direction_label": "古风情感",
        "default_style_request": "古代言情，重礼法、关系拉扯和动作里的情绪，不要写成背景介绍。",
        "description": "对应起点女频、红袖、言情站常见主类目“古代言情”。",
        "aliases": ("ancient_romance", "古代言情"),
    },
    {
        "value": "historical_palace",
        "label": "古代言情·宫廷权谋",
        "group": "古代言情",
        "genre_label": "古代言情·宫廷权谋",
        "style_direction": "historical_intrigue",
        "direction_label": "权谋拉扯",
        "default_style_request": "古风权谋言情，讲究礼法压迫、称呼变化、旧案与关系错位，情绪优先落在动作和后果上。",
        "description": "适合朝堂、夺嫡、赐婚、旧案、身份压迫这类强戏剧场景。",
        "aliases": ("historical_palace", "宫廷权谋", "朝堂权谋", "古代言情·宫廷权谋"),
    },
    {
        "value": "historical_estate",
        "label": "古代言情·宅斗婚恋",
        "group": "古代言情",
        "genre_label": "古代言情·宅斗婚恋",
        "style_direction": "historical_intrigue",
        "direction_label": "宅斗婚恋",
        "default_style_request": "古代婚恋宅斗，重身份秩序、内宅博弈、婚约拉扯和日常细节里的情绪暗战。",
        "description": "适合侯门、家族博弈、先婚后爱、重生宅斗这类方向。",
        "aliases": ("historical_estate", "宅斗婚恋", "先婚后爱", "古代言情·宅斗婚恋"),
    },
    {
        "value": "modern_romance",
        "label": "现代言情",
        "group": "现代言情",
        "genre_label": "现代言情",
        "style_direction": "urban_witty",
        "direction_label": "都市情感",
        "default_style_request": "现代言情，重现实场景里的情感拉扯、社交压力和人物体面。",
        "description": "对应起点女频、红袖、番茄女频等常见主类目“现代言情”。",
        "aliases": ("modern_romance", "现代言情"),
    },
    {
        "value": "wealthy_ceo",
        "label": "现代言情·豪门总裁",
        "group": "现代言情",
        "genre_label": "现代言情·豪门总裁",
        "style_direction": "urban_witty",
        "direction_label": "豪门拉扯",
        "default_style_request": "豪门总裁言情，重身份差、资源差、公开场合的面子与暧昧博弈，避免空泛霸总腔。",
        "description": "对应番茄、红袖、起点女频常见高频子类“豪门总裁”。",
        "aliases": ("wealthy_ceo", "豪门总裁", "现代言情·豪门总裁"),
    },
    {
        "value": "workplace_marriage",
        "label": "现代言情·职场婚恋",
        "group": "现代言情",
        "genre_label": "现代言情·职场婚恋",
        "style_direction": "urban_witty",
        "direction_label": "职场婚恋",
        "default_style_request": "职场婚恋言情，重工作节奏、合作与冲突、身份边界和成年人的现实代价。",
        "description": "适合办公室、创业、契约婚姻、行业竞争等方向。",
        "aliases": ("workplace_marriage", "职场婚恋", "现代言情·职场婚恋"),
    },
    {
        "value": "entertainment_romance",
        "label": "现代言情·娱乐圈",
        "group": "现代言情",
        "genre_label": "现代言情·娱乐圈",
        "style_direction": "urban_witty",
        "direction_label": "娱乐圈情感",
        "default_style_request": "娱乐圈言情，重镜头内外反差、舆论、资源竞争和公开关系风险。",
        "description": "适合演员、歌手、经纪人、综艺、舆论场等题材。",
        "aliases": ("entertainment_romance", "娱乐圈", "现代言情·娱乐圈"),
    },
    {
        "value": "youth_campus",
        "label": "浪漫青春·校园甜宠",
        "group": "浪漫青春",
        "genre_label": "浪漫青春·校园甜宠",
        "style_direction": "youthful_sweet",
        "direction_label": "校园甜宠",
        "default_style_request": "校园甜宠，重面子、起哄、嘴硬、心动细节和轻微社死，不要写成成熟婚恋口吻。",
        "description": "对应晋江、起点女频、红袖常见“浪漫青春 / 校园甜宠”方向。",
        "aliases": ("youth_campus", "校园甜宠", "浪漫青春", "浪漫青春·校园甜宠"),
    },
    {
        "value": "xianxia_romance",
        "label": "仙侠言情",
        "group": "幻想仙侠",
        "genre_label": "仙侠言情",
        "style_direction": "light_adventure_banter",
        "direction_label": "仙侠欢喜冤家",
        "default_style_request": "仙侠言情，重规则与危险落地、并肩吃亏、欢喜冤家和任务中的关系升温。",
        "description": "对应起点女频、红袖常见主类目“仙侠奇缘 / 仙侠言情”。",
        "aliases": ("xianxia_romance", "仙侠言情", "仙侠奇缘"),
    },
    {
        "value": "fantasy_romance",
        "label": "幻想言情",
        "group": "幻想仙侠",
        "genre_label": "幻想言情",
        "style_direction": "light_adventure_banter",
        "direction_label": "幻想冒险",
        "default_style_request": "幻想言情，重设定和冒险压力中的情感推进，避免设定名词循环复读。",
        "description": "对应起点女频、红袖、番茄女频常见主类目“幻想言情 / 玄幻言情”。",
        "aliases": ("fantasy_romance", "幻想言情", "玄幻言情"),
    },
    {
        "value": "suspense_romance",
        "label": "悬疑言情",
        "group": "悬疑科幻",
        "genre_label": "悬疑言情",
        "style_direction": "suspense_pull",
        "direction_label": "悬疑拉扯",
        "default_style_request": "悬疑言情，重关系拉扯和信息迷雾并行推进，钩子要更窄更狠。",
        "description": "适合悬疑推理、微灵异、案件链、身份谜团里的言情推进。",
        "aliases": ("suspense_romance", "悬疑言情", "悬疑推理"),
    },
    {
        "value": "sci_fi_romance",
        "label": "科幻言情 / 科幻空间",
        "group": "悬疑科幻",
        "genre_label": "科幻言情 / 科幻空间",
        "style_direction": "future_adventure",
        "direction_label": "未来任务流",
        "default_style_request": "科幻言情，重任务指标、资源约束、系统规则和协作中的情感推进。",
        "description": "对应起点女频、红袖常见主类目“科幻空间”。",
        "aliases": ("sci_fi_romance", "科幻言情", "科幻空间"),
    },
    {
        "value": "quick_transmigration",
        "label": "快穿系统",
        "group": "悬疑科幻",
        "genre_label": "快穿系统",
        "style_direction": "future_adventure",
        "direction_label": "任务快穿",
        "default_style_request": "快穿系统言情，重任务目标、位面规则、身份限制和每次互动带来的关系变量。",
        "description": "番茄、晋江、女频站点常见高频玩法，适合系统、任务、位面切换。",
        "aliases": ("quick_transmigration", "快穿系统", "快穿"),
    },
    {
        "value": "era_romance",
        "label": "年代言情",
        "group": "现代言情",
        "genre_label": "年代言情",
        "style_direction": "urban_witty",
        "direction_label": "年代成长",
        "default_style_request": "年代言情，重生活质地、人情往来、家庭压力和时代环境里的关系推进。",
        "description": "适合年代、返城、知青、创业、养家成长等方向。",
        "aliases": ("era_romance", "年代言情", "年代文"),
    },
)


def _text(value: Any) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=None)
def _read_style_card_file(filename: str) -> str:
    path = _STYLE_CARD_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Style card file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _render_focus_style_card(direction: str) -> str:
    filename = f"{direction}.txt"
    path = _STYLE_CARD_DIR / filename
    if path.exists():
        return _read_style_card_file(filename)
    return _read_style_card_file(_DEFAULT_FOCUS_STYLE_CARD_FILE)


def list_novel_type_options() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for option in _NOVEL_TYPE_OPTIONS:
        items.append(
            {
                "value": str(option["value"]),
                "label": str(option["label"]),
                "group": str(option["group"]),
                "genre_label": str(option["genre_label"]),
                "style_direction": str(option["style_direction"]),
                "direction_label": str(option["direction_label"]),
                "default_style_request": str(option["default_style_request"]),
                "description": str(option["description"]),
            }
        )
    return items


def get_novel_type_option(value: Any | None) -> dict[str, Any] | None:
    key = _text(value).lower()
    if not key:
        return None
    for option in _NOVEL_TYPE_OPTIONS:
        aliases = {str(alias).strip().lower() for alias in option.get("aliases", ())}
        aliases.add(str(option["value"]).strip().lower())
        aliases.add(str(option["label"]).strip().lower())
        aliases.add(str(option["genre_label"]).strip().lower())
        if key in aliases:
            return option
    return None


def resolve_style_profile(*, novel_type: Any | None, style_request: Any | None) -> dict[str, str]:
    option = get_novel_type_option(novel_type) or _NOVEL_TYPE_OPTIONS[0]
    clean_style = _text(style_request)
    effective_style = clean_style or str(option["default_style_request"]).strip() or "TBD"
    return {
        "novel_type": str(option["value"]),
        "novel_type_label": str(option["label"]),
        "genre_label": str(option["genre_label"]),
        "style_direction": str(option["style_direction"]),
        "effective_style_request": effective_style,
        "custom_style_request": clean_style,
    }


def infer_style_direction(*, premise: Any | None, chapter_brief: Any | None) -> str:
    option = get_novel_type_option(_text(getattr(premise, "genre", "")))
    if option is not None:
        return str(option["style_direction"])

    premise_text = " ".join(
        [
            _text(getattr(premise, "genre", "")),
            _text(getattr(premise, "target_style", "")),
            _text(getattr(premise, "emotional_hook", "")),
            _text(getattr(premise, "story_summary", "")),
            _text(getattr(chapter_brief, "chapter_type", "")),
            _text(getattr(chapter_brief, "scene_engine", "")),
            _text(getattr(chapter_brief, "summary", "")),
        ]
    )
    premise_text_lower = premise_text.lower()

    if any(token in premise_text_lower for token in ("historical", "court", "intrigue")) or any(
        token in premise_text for token in ("古风", "古代", "权谋", "宫廷", "朝堂", "旧案", "赐婚", "宅斗")
    ):
        return "historical_intrigue"
    if any(token in premise_text_lower for token in ("xianxia", "fantasy", "banter", "light adventure")) or any(
        token in premise_text for token in ("仙侠", "欢喜冤家", "斗嘴", "试炼", "秘境", "幻想")
    ):
        return "light_adventure_banter"
    if any(token in premise_text_lower for token in ("campus", "youth", "school")) or any(
        token in premise_text for token in ("青春", "校园", "甜宠", "社死")
    ):
        return "youthful_sweet"
    if any(token in premise_text_lower for token in ("suspense", "mystery", "investigation")) or any(
        token in premise_text for token in ("悬疑", "推理", "案件", "谜团")
    ):
        return "suspense_pull"
    if any(token in premise_text_lower for token in ("scifi", "sci-fi", "system", "quick transmigration")) or any(
        token in premise_text for token in ("科幻", "系统", "快穿", "位面", "星际", "末世")
    ):
        return "future_adventure"
    if any(token in premise_text_lower for token in ("urban", "modern", "witty", "reunion")) or any(
        token in premise_text for token in ("现代", "都市", "职场", "豪门", "娱乐圈", "年代")
    ):
        return "urban_witty"
    return "general"


def render_style_card(*, premise: Any | None, chapter_brief: Any | None) -> str:
    direction = infer_style_direction(premise=premise, chapter_brief=chapter_brief)
    shared = _read_style_card_file(_SHARED_STYLE_CARD_FILE)
    focus = _render_focus_style_card(direction)
    return f"{shared}\n\n{focus}".strip()
