
let mode = 'formal';
let bookId = '';
let pendingRunId = '';
let runsCache = [];
let runDetailsCache = {};
let currentBook = null;
let refreshPaused = false;

const STAGES = {research:'调研中', planning:'规划中', writing:'写作中', critique:'评审中', patching:'修改中', complete:'已完成'};
const stageText = value => STAGES[value] || value || '未开始';
const esc = value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const shortTs = value => value ? String(value).replace('T', ' ').slice(0, 19) : '';
const safeId = value => String(value || '').replace(/[^a-zA-Z0-9_-]/g, '_');
const textToLines = value => String(value || '').split('\n').map(item => item.trim()).filter(Boolean);

async function api(path, options){
  const response = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}}, options || {}));
  return await response.json();
}

function ensureOk(result){
  if(result && result.ok === false){
    alert(result.error || '请求失败');
    return false;
  }
  return true;
}

function updateStopButton(){
  const active = runsCache.find(item => item.is_running) || (pendingRunId ? {run_id: pendingRunId} : null);
  document.getElementById('btnStop').style.display = active ? 'inline-block' : 'none';
}

async function loadNovels(){
  const novels = await api('/api/novels?mode=' + mode);
  const select = document.getElementById('novelSel');
  select.innerHTML = "<option value=''>选择小说</option>";
  novels.forEach(item => {
    const option = document.createElement('option');
    option.value = item.book_id;
    option.textContent = `${item.title} (${item.book_id})`;
    select.appendChild(option);
  });
  if(bookId){
    select.value = bookId;
  }
}

async function selectNovel(id){
  bookId = id;
  pendingRunId = '';
  runDetailsCache = {};
  if(!bookId){
    currentBook = null;
    document.getElementById('pnl-blueprint').innerHTML = "<div class='empty'>请选择一部小说。</div>";
    document.getElementById('pnl-text').innerHTML = "<div class='empty'>请选择一部小说。</div>";
    document.getElementById('pnl-critic').innerHTML = "<div class='empty'>请选择一部小说。</div>";
    document.getElementById('runsPanel').innerHTML = "选择小说后可查看流程记录。";
    document.getElementById('stage-pill').textContent = '未开始';
    updateStopButton();
    return;
  }
  await refreshNovel();
}

async function refreshNovel(){
  if(!bookId){ return; }
  const data = await api(`/api/novel?mode=${mode}&book_id=${bookId}`);
  if(!data.book){ return; }
  currentBook = data.book;
  runsCache = data.runs || [];
  renderBlueprint(data.book, data.blueprint_review || data.book.metadata?.blueprint_review || null);
  renderText(data.book);
  renderCritic(data.critic);
  renderRuns();
  document.getElementById('stage-pill').textContent = stageText(data.latest_stage);
  await loadNovels();
  updateStopButton();
}

async function refreshPendingRun(){
  if(!pendingRunId){ return; }
  const detail = await api(`/api/run?mode=${mode}&run_id=${pendingRunId}`);
  runDetailsCache[pendingRunId] = detail;
  document.getElementById('stage-pill').textContent = stageText(detail.stage);
  if(detail.current_book_id){
    bookId = detail.current_book_id;
    pendingRunId = '';
    document.getElementById('novelSel').value = bookId;
    await refreshNovel();
    return;
  }
  runsCache = [{
    run_id: detail.run_id,
    stage: detail.stage,
    is_running: detail.is_running,
    cancel_requested: detail.cancel_requested,
    updated_at: detail.updated_at,
  }];
  renderRuns();
  updateStopButton();
}

function renderRuns(){
  const panel = document.getElementById('runsPanel');
  if(!runsCache.length){
    panel.innerHTML = '当前还没有运行记录。';
    return;
  }
  let html = '';
  runsCache.forEach(run => {
    const detail = runDetailsCache[run.run_id];
    html += `<div class='run'><div class='run-head'><div><span class='tag'>${esc(stageText(run.stage))}</span> ${run.is_running ? "<span class='tag live'>运行中</span>" : ''}${run.cancel_requested ? "<span class='tag stop'>停止中</span>" : ''}</div><div class='muted'>${esc(shortTs(run.updated_at))}</div></div><div style='margin-top:8px'><strong>${esc(run.run_id)}</strong></div>`;
    if(detail){
      const outputs = detail.outputs || [];
      const events = detail.events || [];
      if(outputs.length){
        html += `<details open><summary>输出 ${outputs.length}</summary><div class='pre'>${esc(outputs.map(item => `${item.agent} | ${item.title}`).join('\n'))}</div></details>`;
      }
      if(events.length){
        html += `<details><summary>事件 ${events.length}</summary><div class='pre'>${esc(events.map(item => `${item.agent} | ${item.title}`).join('\n'))}</div></details>`;
      }
    }
    html += `</div>`;
  });
  panel.innerHTML = html;
}

function openNewNovelDialog(){
  document.getElementById('newNovelModal').classList.add('open');
  document.getElementById('newQueryInput').focus();
}

function closeNewNovelDialog(){
  document.getElementById('newNovelModal').classList.remove('open');
}

async function createNovelFromDialog(){
  const query = document.getElementById('newQueryInput').value.trim();
  if(!query){ alert('请输入题材/需求。'); return; }
  const style = document.getElementById('newStyleInput').value.trim();
  const result = await api('/api/novels/create', {method:'POST', body:JSON.stringify({mode, query, style_request: style})});
  if(!ensureOk(result)){ return; }
  closeNewNovelDialog();
  bookId = result.book.id;
  currentBook = result.book;
  document.getElementById('newQueryInput').value = '';
  document.getElementById('newStyleInput').value = '';
  await loadNovels();
  document.getElementById('novelSel').value = bookId;
  await refreshNovel();
}

async function startRun(path, body, stage){
  if(!bookId){ alert('请先选择一部小说。'); return; }
  const result = await api(path, {method:'POST', body:JSON.stringify(body)});
  if(!ensureOk(result)){ return; }
  pendingRunId = result.run_id || '';
  runDetailsCache = {};
  runsCache = [{
    run_id: pendingRunId,
    stage,
    is_running: true,
    updated_at: new Date().toISOString(),
  }];
  document.getElementById('stage-pill').textContent = stageText(stage);
  renderRuns();
  updateStopButton();
}

async function generateOutline(){ await startRun('/api/novels/generate_outline', {book_id: bookId}, 'planning'); }
async function generateWorldbuilding(){ await startRun('/api/novels/generate_worldbuilding', {book_id: bookId}, 'planning'); }
async function generateCharacters(){ await startRun('/api/novels/generate_characters', {book_id: bookId}, 'planning'); }
async function generateEventTimeline(){ await startRun('/api/novels/generate_event_timeline', {book_id: bookId}, 'planning'); }
async function generateTwistDesigns(){ await startRun('/api/novels/generate_twist_designs', {book_id: bookId}, 'planning'); }
async function generateStoryLines(){ await startRun('/api/novels/generate_story_lines', {book_id: bookId}, 'planning'); }
async function generateChapterPlans(){ await startRun('/api/novels/generate_chapter_plans', {book_id: bookId}, 'planning'); }
async function generateMilestones(){ await startRun('/api/novels/generate_milestones', {book_id: bookId}, 'planning'); }
async function reviewBlueprint(){ await startRun('/api/novels/review_blueprint', {book_id: bookId}, 'critique'); }
async function continueFormal(){ await startRun('/api/novels/continue', {book_id: bookId}, 'writing'); }

async function addAiCharacter(){
  if(!bookId){ alert('请先选择一部小说。'); return; }
  const guidance = prompt('描述你想新增什么角色：');
  if(!guidance){ return; }
  await startRun('/api/novels/add_character', {book_id: bookId, guidance}, 'planning');
}

async function stopCurrentRun(){
  const active = runsCache.find(item => item.is_running) || (pendingRunId ? {run_id: pendingRunId} : null);
  if(!active){ alert('当前没有运行中的任务。'); return; }
  if(!confirm('确认停止并删除这次运行记录吗？')){ return; }
  await api('/api/runs/stop', {method:'POST', body:JSON.stringify({mode, run_id: active.run_id})});
  if(pendingRunId === active.run_id){ pendingRunId = ''; }
  runsCache = runsCache.filter(item => item.run_id !== active.run_id);
  renderRuns();
  updateStopButton();
}

async function deleteNovel(){
  if(!bookId){ alert('请先选择一部小说。'); return; }
  if(!confirm('确认删除这部小说吗？此操作不可撤销。')){ return; }
  await api('/api/novels/delete', {method:'POST', body:JSON.stringify({mode, book_id: bookId})});
  bookId = '';
  currentBook = null;
  pendingRunId = '';
  runsCache = [];
  runDetailsCache = {};
  await loadNovels();
  document.getElementById('pnl-blueprint').innerHTML = "<div class='empty'>请选择一部小说。</div>";
  document.getElementById('pnl-text').innerHTML = "<div class='empty'>请选择一部小说。</div>";
  document.getElementById('pnl-critic').innerHTML = "<div class='empty'>请选择一部小说。</div>";
  document.getElementById('runsPanel').innerHTML = '选择小说后可查看流程记录。';
  document.getElementById('stage-pill').textContent = '未开始';
  updateStopButton();
}

async function aiReviseConcept(scope, targetId){
  if(!bookId){ alert('请先选择一部小说。'); return; }
  const guidance = prompt('描述你想怎么修改：');
  if(!guidance){ return; }
  await startRun('/api/novels/ai_update_concept', {mode, book_id: bookId, scope, target_id: targetId, guidance}, 'planning');
}

async function aiReviseCharacter(index){
  const item = currentBook?.characters?.[index];
  if(!item){ return; }
  await aiReviseConcept('character', item.name || '');
}

async function aiRevisePlan(index){
  const item = currentBook?.metadata?.chapter_plans?.[index];
  if(!item){ return; }
  await aiReviseConcept('chapter_plan', item.chapter_id || '');
}

async function aiReviseText(scope, targetId){
  if(!bookId){ alert('请先选择一部小说。'); return; }
  const guidance = prompt(scope === 'chapter' ? '描述你想怎么修改这一章：' : '描述你想怎么修改这一段：');
  if(!guidance){ return; }
  await startRun('/api/novels/ai_update_text', {mode, book_id: bookId, scope, target_id: targetId, guidance}, 'patching');
}

async function saveOutline(){
  if(!currentBook){ return; }
  const premise = {
    ...currentBook.premise,
    title: document.getElementById('outline-title').value.trim(),
    genre: document.getElementById('outline-genre').value.trim(),
    target_style: document.getElementById('outline-style').value.trim(),
    high_concept: document.getElementById('outline-high-concept').value.trim(),
    story_summary: document.getElementById('outline-story-summary').value.trim(),
    emotional_hook: document.getElementById('outline-emotional-hook').value.trim(),
    central_conflict: document.getElementById('outline-central-conflict').value.trim(),
    core_hook: document.getElementById('outline-core-hook').value.trim(),
    ending_payoff: document.getElementById('outline-ending-payoff').value.trim(),
    selling_points: textToLines(document.getElementById('outline-selling-points').value),
  };
  const result = await api('/api/novels/update_concept', {
    method:'POST',
    body:JSON.stringify({
      mode,
      book_id: bookId,
      title: premise.title,
      premise,
      characters: currentBook.characters || [],
      chapter_plans: currentBook.metadata?.chapter_plans || [],
    })
  });
  if(!ensureOk(result)){ return; }
  currentBook = result.book;
  renderBlueprint(currentBook, currentBook.metadata?.blueprint_review || null);
  await loadNovels();
  alert('大纲已保存');
}

async function saveCharacter(index){
  if(!currentBook){ return; }
  const characters = [...(currentBook.characters || [])];
  characters[index] = {
    ...characters[index],
    name: document.getElementById(`char-name-${index}`).value.trim(),
    role: document.getElementById(`char-role-${index}`).value.trim(),
    background: document.getElementById(`char-background-${index}`).value.trim(),
    family_background: document.getElementById(`char-family-${index}`).value.trim(),
    social_identity: document.getElementById(`char-social-identity-${index}`).value.trim(),
    initial_state: document.getElementById(`char-initial-${index}`).value.trim(),
    motivation: document.getElementById(`char-motivation-${index}`).value.trim(),
    behavior_pattern: document.getElementById(`char-pattern-${index}`).value.trim(),
    arc: document.getElementById(`char-arc-${index}`).value.trim(),
    relationships: document.getElementById(`char-relationships-${index}`).value.trim(),
    theme_function: document.getElementById(`char-theme-${index}`).value.trim(),
    social_relations: textToLines(document.getElementById(`char-social-relations-${index}`).value),
    development_axes: textToLines(document.getElementById(`char-axes-${index}`).value),
    structural_constraints: textToLines(document.getElementById(`char-constraints-${index}`).value),
    structural_advantages: textToLines(document.getElementById(`char-advantages-${index}`).value),
    opportunity_window: document.getElementById(`char-opportunity-${index}`).value.trim(),
    risk_pressure: document.getElementById(`char-risk-${index}`).value.trim(),
    resource_dependency: textToLines(document.getElementById(`char-resources-${index}`).value),
    mobility_path: document.getElementById(`char-mobility-${index}`).value.trim(),
    external_turning_points: textToLines(document.getElementById(`char-turning-${index}`).value),
  };
  const result = await api('/api/novels/update_concept', {
    method:'POST',
    body:JSON.stringify({mode, book_id: bookId, title: currentBook.title, premise: currentBook.premise, characters, chapter_plans: currentBook.metadata?.chapter_plans || []})
  });
  if(!ensureOk(result)){ return; }
  currentBook = result.book;
  renderBlueprint(currentBook, currentBook.metadata?.blueprint_review || null);
  alert('?????');
}

async function addBlankCharacter(){
  if(!currentBook){ return; }
  const characters = [...(currentBook.characters || []), {name:'?????', role:'', background:'', family_background:'', social_identity:'', initial_state:'', motivation:'', behavior_pattern:'', arc:'', relationships:'', theme_function:'', social_relations:[], development_axes:[], structural_constraints:[], structural_advantages:[], opportunity_window:'', risk_pressure:'', resource_dependency:[], mobility_path:'', external_turning_points:[]}];
  const result = await api('/api/novels/update_concept', {
    method:'POST',
    body:JSON.stringify({mode, book_id: bookId, title: currentBook.title, premise: currentBook.premise, characters, chapter_plans: currentBook.metadata?.chapter_plans || []})
  });
  if(!ensureOk(result)){ return; }
  currentBook = result.book;
  renderBlueprint(currentBook, currentBook.metadata?.blueprint_review || null);
}

async function savePlan(index){
  if(!currentBook){ return; }
  const plans = [...(currentBook.metadata?.chapter_plans || [])];
  plans[index] = {
    ...plans[index],
    chapter_id: document.getElementById(`plan-id-${index}`).value.trim(),
    title: document.getElementById(`plan-title-${index}`).value.trim(),
    phase: document.getElementById(`plan-phase-${index}`).value.trim(),
    objective: document.getElementById(`plan-objective-${index}`).value.trim(),
    story_function: document.getElementById(`plan-function-${index}`).value.trim(),
    key_turn: document.getElementById(`plan-turn-${index}`).value.trim(),
    payoff: document.getElementById(`plan-payoff-${index}`).value.trim(),
    tension: document.getElementById(`plan-tension-${index}`).value.trim(),
    cliffhanger: document.getElementById(`plan-cliffhanger-${index}`).value.trim(),
    next_route_hint: document.getElementById(`plan-route-${index}`).value.trim(),
    planned_scene_count: Number(document.getElementById(`plan-scenes-${index}`).value || 2),
  };
  const result = await api('/api/novels/update_concept', {
    method:'POST',
    body:JSON.stringify({mode, book_id: bookId, title: currentBook.title, premise: currentBook.premise, characters: currentBook.characters || [], chapter_plans: plans})
  });
  if(!ensureOk(result)){ return; }
  currentBook = result.book;
  renderBlueprint(currentBook, currentBook.metadata?.blueprint_review || null);
  alert('章节规划已保存');
}

async function saveBlock(blockId){
  const value = document.getElementById(`block-${safeId(blockId)}`).value;
  const result = await api('/api/novels/update_text', {method:'POST', body:JSON.stringify({mode, book_id: bookId, block_id: blockId, block_text: value})});
  if(!ensureOk(result)){ return; }
  currentBook = result.book;
  renderText(currentBook);
  alert('段落已保存');
}

async function saveChapter(chapterId){
  try{
    const payload = JSON.parse(document.getElementById(`chapter-${safeId(chapterId)}`).value);
    const result = await api('/api/novels/update_text', {method:'POST', body:JSON.stringify({mode, book_id: bookId, chapter_id: chapterId, chapter: payload})});
    if(!ensureOk(result)){ return; }
    currentBook = result.book;
    renderText(currentBook);
    alert('本章已保存');
  }catch(error){
    alert('章节 JSON 解析失败：' + error.message);
  }
}

function renderBlueprint(book, blueprintReview){
  const premise = book.premise || {};
  const plans = book.metadata?.chapter_plans || [];
  const milestones = book.metadata?.character_milestones || [];
  const fullBlueprint = book.metadata?.story_blueprint || {};
  const twistDesigns = fullBlueprint.twist_designs || [];
  const storyLines = fullBlueprint.story_lines || [];
  const chapterBriefs = fullBlueprint.chapter_briefs || [];
  const step1Blueprint = {
    positioning: fullBlueprint.positioning || {},
    core_theme: fullBlueprint.core_theme || {},
    writing_constraints: fullBlueprint.writing_constraints || [],
  };
  let html = '';
  html += `<div class='card'><div class='section-title'><h3>创建信息</h3></div><div class='row'><div>原始题材需求</div><div class='pre'>${esc(book.metadata?.original_query || book.metadata?.query || '')}</div></div><div class='row'><div>风格要求</div><div>${esc(book.metadata?.style_request || '未填写')}</div></div><div class='row'><div>当前阶段</div><div>${esc(book.metadata?.planning_phase || 'created')}</div></div><div class='row'><div>已完成章节</div><div>${esc((book.metadata?.completed_chapter_ids || []).length)}</div></div></div>`;
  if(Object.keys(fullBlueprint).length){
    html += `<div class='card'><div class='section-title'><h3>??1??</h3></div><div class='pre'>${esc(JSON.stringify(step1Blueprint, null, 2))}</div></div>`;
  }
  html += `<div class='card'><div class='section-title'><h3>角色</h3><div class='mini-actions'><button onclick='addAiCharacter()'>AI 新增角色</button><button onclick='addBlankCharacter()'>手动新增空角色</button></div></div>`;
  if((book.characters || []).length){
    (book.characters || []).forEach((item, index) => {
      html += `<div class='card' style='margin-bottom:12px;background:#101722'><div class='section-title'><h4>${esc(item.name || '?????')}</h4><div class='mini-actions'><button onclick='aiReviseCharacter(${index})'>AI ????</button><button onclick='saveCharacter(${index})'>????</button></div></div><div class='grid3'><div><label>??</label><input id='char-name-${index}' value='${esc(item.name || '')}' /></div><div><label>????</label><input id='char-role-${index}' value='${esc(item.role || '')}' /></div><div><label>????</label><input id='char-social-identity-${index}' value='${esc(item.social_identity || '')}' /></div><div><label>????</label><input id='char-initial-${index}' value='${esc(item.initial_state || '')}' /></div><div><label>????</label><input id='char-motivation-${index}' value='${esc(item.motivation || '')}' /></div><div><label>????</label><input id='char-opportunity-${index}' value='${esc(item.opportunity_window || '')}' /></div></div><div class='row'><label>????</label><textarea id='char-background-${index}'>${esc(item.background || '')}</textarea></div><div class='row'><label>????</label><textarea id='char-family-${index}'>${esc(item.family_background || '')}</textarea></div><div class='row'><label>????</label><textarea id='char-pattern-${index}'>${esc(item.behavior_pattern || '')}</textarea></div><div class='row'><label>????</label><textarea id='char-arc-${index}'>${esc(item.arc || '')}</textarea></div><div class='row'><label>????</label><textarea id='char-relationships-${index}'>${esc(item.relationships || '')}</textarea></div><div class='row'><label>????</label><textarea id='char-theme-${index}'>${esc(item.theme_function || '')}</textarea></div><div class='row'><label>??????</label><textarea id='char-risk-${index}'>${esc(item.risk_pressure || '')}</textarea></div><div class='row'><label>??/????</label><textarea id='char-mobility-${index}'>${esc(item.mobility_path || '')}</textarea></div><div class='row'><label>??????????</label><textarea id='char-social-relations-${index}'>${esc((item.social_relations || []).join('\n'))}</textarea></div><div class='row'><label>??????????</label><textarea id='char-axes-${index}'>${esc((item.development_axes || []).join('\n'))}</textarea></div><div class='row'><label>??????????</label><textarea id='char-constraints-${index}'>${esc((item.structural_constraints || []).join('\n'))}</textarea></div><div class='row'><label>??????????</label><textarea id='char-advantages-${index}'>${esc((item.structural_advantages || []).join('\n'))}</textarea></div><div class='row'><label>??????????</label><textarea id='char-resources-${index}'>${esc((item.resource_dependency || []).join('\n'))}</textarea></div><div class='row'><label>???????????</label><textarea id='char-turning-${index}'>${esc((item.external_turning_points || []).join('\n'))}</textarea></div></div>`;
    });
  } else {
    html += "<div class='empty'>当前还没有角色。先点“生成角色”，或手动新增一个空角色。</div>";
  }
  html += `</div>`;
  html += `<div class='card'><div class='section-title'><h3>?????</h3></div>${milestones.length ? `<div class='pre'>${esc(JSON.stringify(milestones, null, 2))}</div>` : "<div class='empty'>??????????????????????4 ???????</div>"}</div>`;
  html += `<div class='card'><div class='section-title'><h3>????</h3></div>${twistDesigns.length ? `<div class='pre'>${esc(JSON.stringify(twistDesigns, null, 2))}</div>` : "<div class='empty'>??????????????5 ??????</div>"}</div>`;
  html += `<div class='card'><div class='section-title'><h3>???</h3></div>${storyLines.length ? `<div class='pre'>${esc(JSON.stringify(storyLines, null, 2))}</div>` : "<div class='empty'>?????????????6 ???+?????</div>"}</div>`;
  html += `<div class='card'><div class='section-title'><h3>????</h3></div>${chapterBriefs.length ? `<div class='pre'>${esc(JSON.stringify(chapterBriefs, null, 2))}</div>` : "<div class='empty'>??????????????7 ????+????</div>"}</div>`;
  html += `<div class='card'><div class='section-title'><h3>章节规划</h3></div>`;
  if(plans.length){
    plans.forEach((item, index) => {
      html += `<div class='card' style='margin-bottom:12px;background:#101722'><div class='section-title'><h4>${esc(item.title || item.chapter_id || '未命名章节')}</h4><div class='mini-actions'><button onclick='aiRevisePlan(${index})'>AI 修改章节规划</button><button onclick='savePlan(${index})'>保存章节规划</button></div></div><div class='grid3'><div><label>chapter_id</label><input id='plan-id-${index}' value='${esc(item.chapter_id || '')}' /></div><div><label>标题</label><input id='plan-title-${index}' value='${esc(item.title || '')}' /></div><div><label>阶段</label><input id='plan-phase-${index}' value='${esc(item.phase || '')}' /></div><div><label>本章任务</label><input id='plan-objective-${index}' value='${esc(item.objective || '')}' /></div><div><label>功能</label><input id='plan-function-${index}' value='${esc(item.story_function || '')}' /></div><div><label>关键转折</label><input id='plan-turn-${index}' value='${esc(item.key_turn || '')}' /></div><div><label>兑现</label><input id='plan-payoff-${index}' value='${esc(item.payoff || '')}' /></div><div><label>张力</label><input id='plan-tension-${index}' value='${esc(item.tension || '')}' /></div><div><label>悬念</label><input id='plan-cliffhanger-${index}' value='${esc(item.cliffhanger || '')}' /></div><div><label>续写路线</label><input id='plan-route-${index}' value='${esc(item.next_route_hint || '')}' /></div><div><label>场景数</label><input id='plan-scenes-${index}' type='number' min='1' value='${esc(item.planned_scene_count || 2)}' /></div></div></div>`;
    });
  } else {
    html += "<div class='empty'>当前还没有章节规划。请先点击“生成章节规划”。</div>";
  }
  html += `</div>`;
  html += `<div class='card'><div class='section-title'><h3>Character Milestones</h3></div>${milestones.length ? `<div class='pre'>${esc(JSON.stringify(milestones, null, 2))}</div>` : "<div class='empty'>当前还没有 milestones。请在角色和章节规划准备好后点击“生成 Milestone”。</div>"}</div>`;
  html += `<div class='card'><div class='section-title'><h3>Blueprint Critic</h3></div>`;
  if(blueprintReview){
    html += `<div class='row'><div>总结</div><div>${esc(blueprintReview.summary || '')}</div></div>`;
    const issues = blueprintReview.issues || [];
    html += issues.length ? issues.map(item => `<div class='issue'><div><strong>${esc(item.title || '问题')}</strong></div><div class='muted'>${esc(item.problem_type || '')}</div><div style='margin-top:6px'>证据：${esc(item.evidence || '')}</div><div style='margin-top:6px'>影响：${esc(item.impact || '')}</div><div style='margin-top:6px'>建议：${esc(item.recommendation || '')}</div></div>`).join('') : "<div class='empty'>当前没有 blueprint 问题。</div>";
  } else {
    html += "<div class='empty'>当前还没有 blueprint critic 结果。请点击“Critic Blueprint”。</div>";
  }
  html += `</div>`;
  document.getElementById('pnl-blueprint').innerHTML = html;
}

function renderText(book){
  let html = '';
  const volumes = book.volumes || [];
  volumes.forEach(volume => {
    html += `<div class='card'><div class='section-title'><h3>${esc(volume.title || volume.id)}</h3></div>`;
    if(!(volume.chapters || []).length){
      html += "<div class='empty'>这一卷还没有正文。点击“写第一/下一章”开始生成。</div>";
    }
    (volume.chapters || []).forEach(chapter => {
      html += `<div class='card' style='margin-bottom:12px;background:#101722'><div class='section-title'><h4>${esc(chapter.title || chapter.id)}</h4><div class='mini-actions'><button onclick="aiReviseText('chapter','${esc(chapter.id || '')}')">AI 修改整章</button><button onclick="saveChapter('${esc(chapter.id || '')}')">保存章节 JSON</button></div></div><div class='hint'>你可以直接改下面的段落，也可以改整章 JSON 后保存。</div><details><summary>整章 JSON</summary><textarea id='chapter-${safeId(chapter.id)}' style='min-height:260px'>${esc(JSON.stringify(chapter, null, 2))}</textarea></details>`;
      (chapter.scenes || []).forEach(scene => {
        html += `<div class='card' style='margin-top:10px;background:#0f1521'><h4>${esc(scene.title || scene.id)}</h4><div class='hint'>${esc(scene.summary || '')}</div>`;
        (scene.blocks || []).forEach(block => {
          html += `<div class='card' style='margin-top:10px;background:#0d121c'><div class='section-title'><strong>${esc(block.id)}</strong><div class='mini-actions'><button onclick="aiReviseText('block','${esc(block.id)}')">AI 修改段落</button><button onclick="saveBlock('${esc(block.id)}')">保存段落</button></div></div><div class='hint'>${esc(block.purpose || '')}</div><textarea id='block-${safeId(block.id)}' style='min-height:140px'>${esc(block.text || '')}</textarea></div>`;
        });
        html += `</div>`;
      });
      html += `</div>`;
    });
    html += `</div>`;
  });
  document.getElementById('pnl-text').innerHTML = html || "<div class='empty'>当前还没有正文。</div>";
}

function renderCritic(critic){
  if(!critic){
    document.getElementById('pnl-critic').innerHTML = "<div class='empty'>当前还没有正文评价结果。</div>";
    return;
  }
  let html = `<div class='card'><div class='section-title'><h3>正文评价</h3></div><div class='row'><div>摘要</div><div>${esc(critic.summary || '')}</div></div><div class='row'><div>问题数</div><div>${esc((critic.issues || []).length)}</div></div></div>`;
  (critic.issues || []).forEach(item => {
    html += `<div class='issue'><div><strong>${esc(item.severity || '')} | ${esc(item.title || '')}</strong></div><div style='margin-top:6px'>位置：${esc(item.location?.block_id || '')}</div><div style='margin-top:6px'>证据：${esc(item.evidence || '')}</div><div style='margin-top:6px'>影响：${esc(item.impact || '')}</div><div style='margin-top:6px'>建议：${esc(item.recommendation || '')}</div></div>`;
  });
  document.getElementById('pnl-critic').innerHTML = html;
}

function showTab(name){
  const names = ['blueprint', 'text', 'critic'];
  document.querySelectorAll('.tab').forEach((item, index) => item.classList.toggle('active', names[index] === name));
  document.querySelectorAll('.pnl').forEach(item => item.classList.remove('active'));
  document.getElementById('pnl-' + name).classList.add('active');
}

document.addEventListener('focusin', event => {
  if(event.target.tagName === 'TEXTAREA' || event.target.tagName === 'INPUT'){
    refreshPaused = true;
  }
});

document.addEventListener('focusout', event => {
  if(event.target.tagName === 'TEXTAREA' || event.target.tagName === 'INPUT'){
    setTimeout(() => {
      const active = document.activeElement;
      if(!active || (active.tagName !== 'TEXTAREA' && active.tagName !== 'INPUT')){
        refreshPaused = false;
      }
    }, 0);
  }
});

loadNovels();
updateStopButton();
setInterval(async () => {
  if(refreshPaused){ return; }
  if(pendingRunId){
    await refreshPendingRun();
    return;
  }
  if(bookId){
    await refreshNovel();
  }
}, 1500);
