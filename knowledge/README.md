# Knowledge Cards

将你的情节设计资料、优秀片段分析、反例总结整理成 `*.json` 卡片，放在 `knowledge/cards/` 目录下。

如果你想在 IDE 里一键生成卡片：

1. 把原始资料粘到 `knowledge/_inbox.txt`
2. 打开 `knowledge/generate_cards.py`
3. 修改顶部的 `SOURCE_NAME`
4. 直接点运行

生成出来的卡片默认会写到 `knowledge/cards/`。

建议把卡片组织成“小簇”，而不是孤立散卡。

每个主题簇最好包含：

1. 1 张 `需求层` 或 `机制层` 卡：解释这个主题为什么会这样写
2. 1 张 `写法层` 反模式卡：描述常见写歪的桥段
3. 1 张 `正向` 卡：告诉 Writer 正确写法依靠什么

字段建议固定成这类结构：

1. `domain`：主题域，例如 `爱情线`、`大女主成长`
2. `layer`：`需求层` / `机制层` / `写法层` / `结构层`
3. `polarity`：`正向` / `反向`
4. `cluster_id`：同一主题簇共享的稳定 ID
5. `tags`：1 个大类标签 + 1 个结构/维度标签 + 2 到 3 个问题标签

不要把 `tags` 写成完整判断句，也不要只堆泛词。更具体的情节场景放在 `scene_types`，更强的判断放在 `summary` 和 `warning_signs`。

建议字段：

```json
{
  "card_id": "plot_wedding_faceoff_001",
  "kind": "plot_pattern",
  "title": "婚礼公开对峙的蓄压方式",
  "summary": "先制造旁观者误判，再让主角延迟反击，公开场合的压力越大，反杀越成立。",
  "domain": "对峙戏",
  "layer": "写法层",
  "polarity": "正向",
  "cluster_id": "public_faceoff_pressure",
  "tags": ["对峙戏", "公开场合", "误判压力", "延迟反击"],
  "applicable_stages": ["planning", "writing"],
  "scene_types": ["豪门对峙", "身份误认"],
  "emotions": ["屈辱", "期待翻盘"],
  "warning_signs": ["女主反击前没有任何主动铺垫", "围观者没有形成误判压力"],
  "techniques": ["先压后扬", "围观者站队", "延迟反击"],
  "dos": ["让群像参与站队", "反击前保留底牌"],
  "donts": ["直接照搬原文句式", "过早解释背景"],
  "source": "你的读书笔记"
}
```

运行时会优先按 `cluster_id` 和 `layer` 组织召回：如果一个主题簇命中得分高，系统会优先带出同簇里不同层级的卡，而不是只返回零散的 top N。

运行时默认优先读取 `knowledge/cards/` 下的 `.json` 文件，文件名以下划线 `_` 开头的会被忽略。
兼容旧路径：`knowledge/` 根目录下已有的 `.json` 也仍然会被读取。
