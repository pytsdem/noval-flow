from __future__ import annotations

import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from novel_flow.config import Settings
from novel_flow.server import AppStores, NovelApp
from novel_flow.services.style_cards import (
    get_novel_type_option,
    infer_style_direction,
    list_novel_type_options,
    render_style_card,
    resolve_style_profile,
)
from novel_flow.storage.sqlite_store import SQLiteStore


class TestStyleCards(unittest.TestCase):
    def test_style_card_prompt_files_exist(self) -> None:
        root = Path(__file__).resolve().parents[1] / "prompts" / "style_cards"
        self.assertTrue((root / "shared_base.txt").exists())
        self.assertTrue((root / "general.txt").exists())
        self.assertTrue((root / "historical_intrigue.txt").exists())
        self.assertTrue((root / "light_adventure_banter.txt").exists())

    def test_list_novel_type_options_contains_mainstream_romance_categories(self) -> None:
        options = list_novel_type_options()
        values = {item["value"] for item in options}
        labels = {item["label"] for item in options}
        self.assertIn("auto", values)
        self.assertIn("historical_palace", values)
        self.assertIn("modern_romance", values)
        self.assertIn("xianxia_romance", values)
        self.assertIn("suspense_romance", values)
        self.assertIn("快穿系统", labels)

    def test_resolve_style_profile_applies_selected_type_defaults(self) -> None:
        profile = resolve_style_profile(novel_type="historical_palace", style_request="")
        self.assertEqual(profile["genre_label"], "古代言情·宫廷权谋")
        self.assertEqual(profile["style_direction"], "historical_intrigue")
        self.assertIn("古风权谋言情", profile["effective_style_request"])

    def test_explicit_style_request_can_override_type_default(self) -> None:
        profile = resolve_style_profile(novel_type="modern_romance", style_request="冷幽默都市复仇")
        self.assertEqual(profile["genre_label"], "现代言情")
        self.assertEqual(profile["effective_style_request"], "冷幽默都市复仇")

    def test_direction_can_be_inferred_from_genre_label(self) -> None:
        premise = type("Premise", (), {"genre": "悬疑言情", "target_style": "", "emotional_hook": "", "story_summary": ""})()
        chapter_brief = type("ChapterBrief", (), {"chapter_type": "", "scene_engine": "", "summary": ""})()
        self.assertEqual(infer_style_direction(premise=premise, chapter_brief=chapter_brief), "suspense_pull")
        self.assertIn("悬疑言情 / 拉扯推理", render_style_card(premise=premise, chapter_brief=chapter_brief))

    def test_get_novel_type_option_accepts_label_alias(self) -> None:
        option = get_novel_type_option("豪门总裁")
        self.assertIsNotNone(option)
        self.assertEqual(option["value"], "wealthy_ceo")


class TestNovelShellCreation(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        settings = Settings(database_path=self.root / "formal.db")
        self.app = NovelApp(
            AppStores(
                formal=SQLiteStore(self.root / "formal.db"),
                test=SQLiteStore(self.root / "test.db"),
                settings=settings,
            )
        )

    def tearDown(self) -> None:
        del self.app
        gc.collect()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_create_novel_shell_persists_selected_type_and_effective_style(self) -> None:
        book = self.app.create_novel_shell(
            "formal",
            title="春台误",
            query="宫廷权谋下的错位婚约与旧案重逢。",
            novel_type="historical_palace",
        )
        self.assertEqual(book["premise"]["genre"], "古代言情·宫廷权谋")
        self.assertIn("古风权谋言情", book["premise"]["target_style"])
        self.assertEqual(book["metadata"]["novel_type"], "historical_palace")
        self.assertEqual(book["metadata"]["novel_type_label"], "古代言情·宫廷权谋")
        self.assertEqual(book["metadata"]["style_direction"], "historical_intrigue")

    def test_create_novel_shell_keeps_custom_style_request(self) -> None:
        book = self.app.create_novel_shell(
            "formal",
            title="热搜之后",
            query="娱乐圈双向误解后复合。",
            novel_type="entertainment_romance",
            style_request="要有高密度舆论场对话和冷调复合拉扯",
        )
        self.assertEqual(book["premise"]["genre"], "现代言情·娱乐圈")
        self.assertEqual(book["premise"]["target_style"], "要有高密度舆论场对话和冷调复合拉扯")
        self.assertEqual(book["metadata"]["style_request"], "要有高密度舆论场对话和冷调复合拉扯")
        self.assertEqual(book["metadata"]["effective_style_request"], "要有高密度舆论场对话和冷调复合拉扯")


if __name__ == "__main__":
    unittest.main()
