"""Fix garbled ? labels in _HTML_PAGE JavaScript strings."""
with open('src/novel_flow/server.py', 'r', encoding='utf-8-sig') as f:
    code = f.read()

replacements = [
    # renderDirectorDecision
    ("infoRow('??', payload&&payload.action||'')", "infoRow('动作', payload&&payload.action||'')"),
    ("infoRow('??', payload&&payload.reasoning||'')", "infoRow('理由', payload&&payload.reasoning||'')"),
    ("if(stage)html+=infoRow('??', stage)", "if(stage)html+=infoRow('阶段', stage)"),
    ("if(query)html+=infoRow('???', query)", "if(query)html+=infoRow('查询', query)"),
    ("html+=sectionHtml('???', chipsHtml(focus))", "html+=sectionHtml('焦点', chipsHtml(focus))"),
    ("html+=sectionHtml('??', chipsHtml(tags))", "html+=sectionHtml('标签', chipsHtml(tags))"),
    ("html+=sectionHtml('????', linesHtml(infoGaps))", "html+=sectionHtml('信息缺口', linesHtml(infoGaps))"),
    ("html+=sectionHtml('????', jsonHtml(Object.fromEntries(extras)))", "html+=sectionHtml('其他', jsonHtml(Object.fromEntries(extras)))"),
    # renderReferenceCards
    ("infoRow('??', payload&&payload.stage||'')", "infoRow('阶段', payload&&payload.stage||'')"),
    ("infoRow('???', payload&&payload.query||'')", "infoRow('查询', payload&&payload.query||'')"),
    ("html+=sectionHtml('?????', chipsHtml(focus))", "html+=sectionHtml('关注点', chipsHtml(focus))"),
    ("html+=sectionHtml('????', chipsHtml(tags))", "html+=sectionHtml('筛选标签', chipsHtml(tags))"),
    ("html+=sectionHtml('????', `<div class='mini-list'>", "html+=sectionHtml('参考卡片', `<div class='mini-list'>"),
    ("card.title||card.card_id||'?????'", "card.title||card.card_id||'未命名'"),
    ("html+=sectionHtml('????', \"<div class='muted'>???????</div>\")", "html+=sectionHtml('参考卡片', \"<div class='muted'>暂无卡片</div>\")"),
    ("html+=sectionHtml('?? Prompt ????',", "html+=sectionHtml('参考 Prompt 包',"),
    # renderToolObservation
    ("infoRow('??', payload&&payload.tool_name||'')", "infoRow('工具', payload&&payload.tool_name||'')"),
    ("infoRow('??', payload&&payload.summary||'')", "infoRow('摘要', payload&&payload.summary||'')"),
    ("html+=sectionHtml('????', jsonHtml(payload.payload))", "html+=sectionHtml('详情', jsonHtml(payload.payload))"),
    # renderStageEvent
    ("infoRow('??', payload&&payload.action||'')", "infoRow('动作', payload&&payload.action||'')"),
    ("infoRow('??', payload&&payload.reason||'')", "infoRow('原因', payload&&payload.reason||'')"),
    # renderErrorEvent
    ("infoRow('??', payload&&payload.error||'???????')", "infoRow('错误', payload&&payload.error||'未知错误')"),
    # renderRuns
    ("title:'????',kind:'plain'", "title:'待处理',kind:'plain'"),
    ("\"<span class='tag live'>???</span>\"", "\"<span class='tag live'>运行中</span>\""),
    ("\"<span class='tag stop'>???</span>\"", "\"<span class='tag stop'>取消中</span>\""),
    (">?????????</button>", ">停止此运行</button>"),
    ("\"<div class='empty'>??????????</div>\"", "\"<div class='empty'>暂无运行记录</div>\""),
    ("\"<div class='payload'>??????????</div>\"", "\"<div class='payload'>暂无输出内容</div>\""),
    ("title:`${group.agent||'LLM'} ? ???? #${index+1}`", "title:`${group.agent||'LLM'} · 流式输出 #${index+1}`"),
    # stopCurrentRun / stopRun
    ("if(!a)return alert('????????????')", "if(!a)return alert('当前没有运行中的任务。')"),
    ("if(!confirm('?????????????'))return", "if(!confirm('确认删除此运行记录？'))return"),
    ("return cleaned||'????????????????'", "return cleaned||'（空白内容）'"),
    # startFormalFromDialog
    ("if(!q)return alert('??????????/???')", "if(!q)return alert('请输入题材/需求。')"),
    ("stagePill.textContent='???';await loadNovels();novelSel.value=bookId;await refreshNovel()",
     "stagePill.textContent='未开始';await loadNovels();novelSel.value=bookId;await refreshNovel()"),
    # startPlanningRun
    ("if(!bookId)return alert('?????????');const r=await api(path,",
     "if(!bookId)return alert('请先选择一部小说。');const r=await api(path,"),
    # generate* pending messages
    ("'/api/novels/generate_outline','??+????????'", "'/api/novels/generate_outline','大纲+蓝图生成中'"),
    ("'/api/novels/generate_worldbuilding','???+?????????'", "'/api/novels/generate_worldbuilding','世界观+背景体系生成中'"),
    ("pending_message:'???+?????????'", "pending_message:'角色卡+关系网生成中'"),
    ("if(!bookId)return alert('?????????');const r=await api('/api/novels/generate_characters'",
     "if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_characters'"),
    ("'/api/novels/generate_milestones','???????????'", "'/api/novels/generate_milestones','角色发展线生成中'"),
    ("'/api/novels/generate_event_timeline','?????????????'", "'/api/novels/generate_event_timeline','事件时间线生成中'"),
    ("'/api/novels/generate_twist_designs','??????????'", "'/api/novels/generate_twist_designs','反转设计生成中'"),
    ("'/api/novels/generate_story_lines','???+??????????'", "'/api/novels/generate_story_lines','故事线+章节标题生成中'"),
    ("if(!bookId)return alert('?????????');const r=await api('/api/novels/generate_chapter_plans'",
     "if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_chapter_plans'"),
    ("pending_message:'????+????????'", "pending_message:'章节规划+大纲生成中'"),
    ("'Blueprint Critic ??????'", "'Blueprint Critic 评审中'"),
    # continueFormal
    ("if(!bookId)return alert('????????????');", "if(!bookId)return alert('请先选择一部小说。');"),
    ("pending_message:'?????????????????'", "pending_message:'正在写下一章，请稍候...'"),
    # deleteNovel
    ("if(!bookId)return alert('?????????');if(!confirm('??????????????????')",
     "if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除此小说？该操作不可撤销。')"),
    ("stagePill.textContent='???';await loadNovels();updateStopButton()",
     "stagePill.textContent='未开始';await loadNovels();updateStopButton()"),
    # testBlueprint
    ("const q=prompt('?????????????')", "const q=prompt('输入题材需求（测试大纲）：')"),
    # testWrite
    ("const q=prompt('???????????')", "const q=prompt('输入题材需求（测试写作）：')"),
    # testCritique
    ("if(!bookId)return alert('?????????');const r=await api('/api/test/critique'",
     "if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/test/critique'"),
    # testPatch
    ("if(!bookId)return alert('?????????');const blockId=prompt('?????? block_id?')",
     "if(!bookId)return alert('请先选择一部小说。');const blockId=prompt('请输入 block_id：')"),
    ("const patchContent=prompt('???????')", "const patchContent=prompt('补丁内容：')"),
    ("const reason=prompt('???????','manual test patch')", "const reason=prompt('修改原因：','manual test patch')"),
    # aiReviseConcept
    ("if(!bookId)return alert('?????????');const guidance=prompt('????? AI ?????????')",
     "if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你希望 AI 怎么修改概念：')"),
    # aiReviseText
    ("guidance=prompt(scope==='chapter'?'????? AI ????????':'????? AI ????????')",
     "guidance=prompt(scope==='chapter'?'描述你希望 AI 怎么修改这章：':'描述你希望 AI 怎么修改这段：')"),
    # pending messages for AI revise
    ("pending_message:'AI ??????????'", "pending_message:'AI 修改中'"),
    # renderInputPanel: summary-arrow (appears in both block and sectionCard)
    ("class='summary-arrow'>?? / ??</div>", "class='summary-arrow'>展开 / 折叠</div>"),
    # writingSummary
    ("totalWordTarget?`??? ${totalWordTarget}`", "totalWordTarget?`总字 ${totalWordTarget}`"),
    ("chapterCountTarget?`??? ${chapterCountTarget}`", "chapterCountTarget?`章数 ${chapterCountTarget}`"),
    ("chapterWordTarget?`?? ${chapterWordTarget}`", "chapterWordTarget?`每章 ${chapterWordTarget}`"),
    ("paceNotes?`?? ${paceNotes}`", "paceNotes?`节奏 ${paceNotes}`"),
    ("'????????????????????????'", "'暂无写作要求'"),
    # writingBlock title
    ("<div class='summary-title'>????</div><div class='summary-desc'>", "<div class='summary-title'>写作要求</div><div class='summary-desc'>"),
    ("<label>?????</label><input id='concept-total-word-target'", "<label>总字数目标</label><input id='concept-total-word-target'"),
    ("placeholder='???80-100? / 15???'", "placeholder='约80-100万字'"),
    ("<label>?????</label><input id='concept-chapter-count-target'", "<label>章节数目标</label><input id='concept-chapter-count-target'"),
    ("placeholder='???180-220? / 40???'", "placeholder='约180-220章'"),
    ("<label>????</label><input id='concept-chapter-word-target'", "<label>章节字数</label><input id='concept-chapter-word-target'"),
    ("placeholder='???2500-3500?'", "placeholder='约2500-3500字'"),
    ("<label>????</label><textarea id='concept-pace-notes'", "<label>节奏备注</label><textarea id='concept-pace-notes'"),
    ("placeholder='??????????????????????????'", "placeholder='描述各阶段节奏安排'"),
    ("<div class='block-help'>???????????????? 1-8 ??????</div>",
     "<div class='block-help'>写作要求会影响步骤 1-8 的生成结果</div>"),
    ("const heroSummary='?????????????????????????????????????'",
     "const heroSummary='在这里填写小说的基础信息，修改后记得点保存。'"),
    # hero area labels
    ("<div class='sec'>????</div>", "<div class='sec'>用户输入</div>"),
    ("<div class='input-hero-kicker'>?????</div>", "<div class='input-hero-kicker'>小说基础设置</div>"),
    ("<span class='input-hero-badge'>?????</span>", "<span class='input-hero-badge'>写作控制台</span>"),
    ("onclick='setAllInputBlocks(true)'>????</button>", "onclick='setAllInputBlocks(true)'>全部展开</button>"),
    ("onclick='setAllInputBlocks(false)'>????</button>", "onclick='setAllInputBlocks(false)'>全部折叠</button>"),
    ("onclick='saveConcept()'>???????</button>", "onclick='saveConcept()'>保存所有修改</button>"),
    ("<label>????</label><input id='concept-title'", "<label>书名标题</label><input id='concept-title'"),
    ("placeholder='??????????????????????????'", "placeholder='输入小说书名'"),
    # block call labels
    ("block('input-query','concept-query','????????????',currentQuery,",
     "block('input-query','concept-query','题材与需求',currentQuery,"),
    ("block('input-topic','concept-user-topic','????',userTopic,",
     "block('input-topic','concept-user-topic','用户主题',userTopic,"),
    ("block('input-style','concept-style-request','????',styleRequest,",
     "block('input-style','concept-style-request','风格要求',styleRequest,"),
    # block placeholder/help texts
    (",'?????????? Markdown ??????????','???? 1-8 ?????????????',true)",
     ",'支持 Markdown 详细描述题材','此内容影响步骤 1-8 的生成',true)"),
    (",'?????????????????????????','??????????????????????',false)",
     ",'可选填写用户关注的主题方向','仅在明确时填写',false)"),
    (",'????????????????????????????','??????????????????????',false)",
     ",'留空则由系统判断风格','明确时填写，不填则自动决策',false)"),
    # renderBlueprint panel meta
    ("<div class='panel-meta'>??????</div>", "<div class='panel-meta'>小说信息概览</div>"),
    ("<div class='panel-title'>? 1-8 ?????</div>", "<div class='panel-title'>步骤 1-8 详情</div>"),
    ("onclick=\"setPanelSections('pnl-blueprint',true)\">????</button>",
     "onclick=\"setPanelSections('pnl-blueprint',true)\">全部展开</button>"),
    ("onclick=\"setPanelSections('pnl-blueprint',false)\">????</button>",
     "onclick=\"setPanelSections('pnl-blueprint',false)\">全部折叠</button>"),
    # step_1
    ("stepSection('step_1','1 ??+??',", "stepSection('step_1','1 大纲+蓝图',"),
    ("premise.story_summary||premise.high_concept||'??????????',",
     "premise.story_summary||premise.high_concept||'暂无概念信息',"),
    ("<div class='subsec'>?????</div>${infoRow('??', premise.title",
     "<div class='subsec'>故事本体</div>${infoRow('标题', premise.title"),
    ("infoRow('??', premise.theme_statement||'')", "infoRow('主题', premise.theme_statement||'')"),
    ("infoRow('????', premise.story_summary||'')", "infoRow('故事简介', premise.story_summary||'')"),
    ("infoRow('???', premise.high_concept||'')", "infoRow('核心概念', premise.high_concept||'')"),
    ("infoRow('????', premise.emotional_hook||'')", "infoRow('情感钩子', premise.emotional_hook||'')"),
    ("infoRow('????', premise.central_conflict||'')", "infoRow('核心冲突', premise.central_conflict||'')"),
    ("infoRow('????', premise.core_hook||'')", "infoRow('核心钩子', premise.core_hook||'')"),
    ("infoRow('??', premise.target_style||'')", "infoRow('风格', premise.target_style||'')"),
    ("<div class='subsec'>?????</div>${listHtml(premise.selling_points",
     "<div class='subsec'>商业卖点</div>${listHtml(premise.selling_points"),
    ("listHtml(premise.selling_points,'????????')", "listHtml(premise.selling_points,'暂无卖点')"),
    ("listHtml(premise.escalation_path,'??????????')", "listHtml(premise.escalation_path,'暂无升级路径')"),
    ("<div class='subsec'>????</div>${infoRow('????', storyEngine.narrative_mode",
     "<div class='subsec'>叙事引擎</div>${infoRow('叙事模式', storyEngine.narrative_mode"),
    ("infoRow('????', storyEngine.viewpoint_strategy||'')", "infoRow('视角策略', storyEngine.viewpoint_strategy||'')"),
    ("infoRow('??????', storyEngine.reveal_strategy||'')", "infoRow('揭示策略', storyEngine.reveal_strategy||'')"),
    ("infoRow('???????', storyEngine.hook_strategy||'')", "infoRow('钩子策略', storyEngine.hook_strategy||'')"),
    # step_2
    ("stepSection('step_2','2 ???+???',", "stepSection('step_2','2 背景体系+世界观',"),
    ("storyEngine.engine_sentence||'??????????',", "storyEngine.engine_sentence||'暂无引擎句',"),
    ("<div class='subsec'>?????</div>${infoRow('?????', storyEngine.engine_sentence",
     "<div class='subsec'>世界引擎</div>${infoRow('引擎核心句', storyEngine.engine_sentence"),
    ("infoRow('????', storyEngine.default_track||'')", "infoRow('默认轨道', storyEngine.default_track||'')"),
    ("infoRow('????', storyEngine.world_rules||'')", "infoRow('世界法则', storyEngine.world_rules||'')"),
    ("infoRow('????', storyEngine.power_structure||'')", "infoRow('权力结构', storyEngine.power_structure||'')"),
    ("infoRow('????', storyEngine.world_map||'')", "infoRow('世界地图', storyEngine.world_map||'')"),
    ("infoRow('????', storyEngine.structural_inertia||'')", "infoRow('结构惯性', storyEngine.structural_inertia||'')"),
    ("infoRow('????', storyEngine.rebound_mechanism||'')", "infoRow('反弹机制', storyEngine.rebound_mechanism||'')"),
    ("infoRow('??????', storyEngine.story_trigger||'')", "infoRow('故事触发', storyEngine.story_trigger||'')"),
    ("infoRow('?????????', storyEngine.objective_conditions||'')", "infoRow('客观起点', storyEngine.objective_conditions||'')"),
    # step_3
    ("stepSection('step_3','3 ???+???',", "stepSection('step_3','3 角色卡+关系网',"),
    ("<div class='subsec'>???</div>${listHtml((book?.characters||[]).map",
     "<div class='subsec'>角色</div>${listHtml((book?.characters||[]).map"),
    ("item.name||item.role||'?????'),'?????????'", "item.name||item.role||'未命名角色'),'暂无角色'"),
    ("<div class='subsec'>???</div>${listHtml((blueprint.relationship_network",
     "<div class='subsec'>关系网</div>${listHtml((blueprint.relationship_network"),
    ("item.subject||'???'} -> ${item.target||'???'}", "item.subject||'未知'} -> ${item.target||'未知'}"),
    ("),'?????????')}<div style='margin-top:8px'", "),'暂无关系'}<div style='margin-top:8px'"),
    ("onclick='regenerateRelationshipNetwork()'>???????</button>",
     "onclick='regenerateRelationshipNetwork()'>重新生成关系网</button>"),
    ("onclick='reviseRelationshipNetworkByInstruction()'>????????</button>",
     "onclick='reviseRelationshipNetworkByInstruction()'>指令调整关系网</button>"),
    # step_4
    ("stepSection('step_4','4 ???????',", "stepSection('step_4','4 客观事件时间线',"),
    ("blueprint.event_timeline||[]).length} ???`", "blueprint.event_timeline||[]).length} 条`"),
    ("<div class='subsec'>????</div>${listHtml((blueprint.event_timeline",
     "<div class='subsec'>事件列表</div>${listHtml((blueprint.event_timeline"),
    ("item.title||item.event_id||'?????'),'???????????'", "item.title||item.event_id||'未命名事件'),'暂无事件'"),
    # step_5
    ("stepSection('step_5','5 ?????',", "stepSection('step_5','5 角色发展线',"),
    ("character_milestones||[]).length} ????`", "character_milestones||[]).length} 条发展线`"),
    ("<div class='subsec'>???</div>${listHtml((book?.metadata?.character_milestones",
     "<div class='subsec'>角色</div>${listHtml((book?.metadata?.character_milestones"),
    ("item.name||item.character||'??????'),'???????????'", "item.name||item.character||'未命名角色'),'暂无发展线'"),
    # step_6
    ("stepSection('step_6','6 ????',", "stepSection('step_6','6 反转设计',"),
    ("blueprint.twist_designs||[]).length} ???`", "blueprint.twist_designs||[]).length} 个反转`"),
    ("<div class='subsec'>????</div>${listHtml((blueprint.twist_designs",
     "<div class='subsec'>反转列表</div>${listHtml((blueprint.twist_designs"),
    ("item.title||item.twist_name||'?????'),'??????????'", "item.title||item.twist_name||'未命名反转'),'暂无反转设计'"),
    # step_7
    ("stepSection('step_7','7 ???+????',", "stepSection('step_7','7 故事线+章节标题',"),
    ("blueprint.story_lines||[]).length} ???? / ${(blueprint.chapter_briefs||[]).length} ???`",
     "blueprint.story_lines||[]).length} 条故事线 / ${(blueprint.chapter_briefs||[]).length} 章`"),
    ("<div class='subsec'>???</div>${listHtml((blueprint.story_lines",
     "<div class='subsec'>故事线</div>${listHtml((blueprint.story_lines"),
    ("item.name||'??????'),'?????????'", "item.name||'未命名故事线'),'暂无故事线'"),
    ("<div class='subsec'>????</div>${listHtml((blueprint.chapter_briefs",
     "<div class='subsec'>章节标题</div>${listHtml((blueprint.chapter_briefs"),
    ("item.title||item.chapter_id||'?????'),'?????????????'", "item.title||item.chapter_id||'未命名章节'),'暂无章节标题'"),
    # step_8
    ("stepSection('step_8','8 ????+??',", "stepSection('step_8','8 章节规划+大纲',"),
    ("book?.metadata?.chapter_plans||[]).length} ???`", "book?.metadata?.chapter_plans||[]).length} 章`"),
    ("<div class='subsec'>????</div>${listHtml((book?.metadata?.chapter_plans",
     "<div class='subsec'>章节规划</div>${listHtml((book?.metadata?.chapter_plans"),
    ("item.title||item.chapter_id||'???????'),'??????????'",
     "item.title||item.chapter_id||'未命名规划'),'暂无章节规划'"),
    # blueprint review
    ("blueprintReview.summary||'???????????',", "blueprintReview.summary||'暂无评审结论',"),
    ("<div class='subsec'>????</div>${infoRow('??', blueprintReview.summary",
     "<div class='subsec'>总结</div>${infoRow('摘要', blueprintReview.summary"),
    ("<div class='subsec'>????</div>${listHtml((blueprintReview.issues",
     "<div class='subsec'>问题列表</div>${listHtml((blueprintReview.issues"),
    ("item.severity||'??'}?${item.title||'?????'}", "item.severity||'未知'}·${item.title||'未命名问题'}"),
    ("}`),'?????????')}", "}`),'暂无问题')"),
    # listHtml default
    ("const listHtml=(items, emptyText='?????')=>{", "const listHtml=(items, emptyText='暂无内容')=>{"),
    # renderText
    ("chapter.summary||'?????????'", "chapter.summary||'暂无章节摘要'"),
    ("<div class='subsec'>????</div>${infoRow('???', volume.title||volume.id||'')}${infoRow('????', title)}${infoRow('??', summary)",
     "<div class='subsec'>目录</div>${infoRow('卷名', volume.title||volume.id||'')}${infoRow('章节标题', title)}${infoRow('摘要', summary)"),
    ("\"<div class='relationship-empty'>????????????</div>\"",
     "\"<div class='relationship-empty'>暂无场景内容</div>\""),
    # renderCritic
    ("sectionCard('critic-summary','????',c.summary||'????',",
     "sectionCard('critic-summary','评价总结',c.summary||'暂无摘要',"),
    ("${infoRow('??', c.summary||'')}${infoRow('???', (c.issues||[]).length)}",
     "${infoRow('摘要', c.summary||'')}${infoRow('问题数', (c.issues||[]).length)}"),
    ("issue.evidence||issue.impact||'????????',", "issue.evidence||issue.impact||'无详细描述',"),
    ("${infoRow('??', issue.location?.block_id||'')}${infoRow('??', issue.evidence||'')}${infoRow('??', issue.impact||'')}${infoRow('??', issue.recommendation||'')}",
     "${infoRow('位置', issue.location?.block_id||'')}${infoRow('证据', issue.evidence||'')}${infoRow('影响', issue.impact||'')}${infoRow('建议', issue.recommendation||'')}"),
    ("issue.severity||'??'} ? ${issue.title", "issue.severity||'未知'} · ${issue.title"),
    # empty panels (two different ones)
    ("innerHTML=\"<div class='empty'>??????????</div>\";return;}\n  const sectionCard",
     "innerHTML=\"<div class='empty'>暂无正文内容</div>\";return;}\n  const sectionCard"),
    ("innerHTML=\"<div class='empty'>??????????</div>\";return;}\n  const sectionCard=(key,title,summary,body,defaultOpen=true)",
     "innerHTML=\"<div class='empty'>暂无评价内容</div>\";return;}\n  const sectionCard=(key,title,summary,body,defaultOpen=true)"),
]

count = 0
not_found = []
for old, new in replacements:
    if old in code:
        code = code.replace(old, new, 1)
        count += 1
    else:
        not_found.append(old[:70])

# Fix the two empty panel messages differently since they're identical
# renderText empty panel
code = code.replace(
    "innerHTML=\"<div class='empty'>??????????</div>\";return;}",
    "innerHTML=\"<div class='empty'>暂无内容</div>\";return;}",
)

print(f"Applied {count} replacements")
if not_found:
    print(f"\nNOT FOUND ({len(not_found)}):")
    for s in not_found:
        print(f"  {s!r}")

with open('src/novel_flow/server.py', 'w', encoding='utf-8-sig') as f:
    f.write(code)
print("\nFile saved.")
