
let mode='formal',bookId='',pendingRunId='',runsCache=[],expandedRuns=new Set(),boxStates={},detailStates={},currentBook=null,pendingStepRevision=null;
let refreshPaused=false,refreshPauseReason='',refreshPauseTimer=null,isMouseSelecting=false;
const STAGES={research:'调研中',planning:'大纲中',writing:'写作中',critique:'评价中',patching:'修改中',complete:'已完成'};
const stageText=v=>STAGES[v]||v||'未开始',esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),shortTs=v=>v?String(v).replace('T',' ').slice(0,19):'';
async function api(path,opt){const r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json'}},opt||{}));return await r.json();}
function ensureOk(r){if(r&&r.ok===false){alert(r.error||'请求失败');return false;}return true;}
let stepDrafts={},stepDraftDirty={},stepReviewNotes={},stepDraftBookId='';
let stepDraftObjects={};
function deepClone(value){return JSON.parse(JSON.stringify(value??{}));}
function resetStepDraftCache(targetBookId=''){stepDraftBookId=targetBookId;stepDrafts={};stepDraftDirty={};stepReviewNotes={};stepDraftObjects={};}
function stepPayloadFromBook(book,stepKey){const storyBlueprint=book?.metadata?.story_blueprint||{};if(stepKey==='step_1')return{premise:book?.premise||{},story_engine:storyBlueprint.story_engine||{}};if(stepKey==='step_2')return{story_engine:storyBlueprint.story_engine||{}};if(stepKey==='step_3')return{characters:book?.characters||[],relationship_network:Array.isArray(storyBlueprint.relationship_network)?storyBlueprint.relationship_network:[]};if(stepKey==='step_4')return{event_timeline:Array.isArray(storyBlueprint.event_timeline)?storyBlueprint.event_timeline:[]};if(stepKey==='step_5')return{character_milestones:Array.isArray(book?.metadata?.character_milestones)?book.metadata.character_milestones:[]};if(stepKey==='step_6')return{twist_designs:Array.isArray(storyBlueprint.twist_designs)?storyBlueprint.twist_designs:[]};if(stepKey==='step_7')return{story_lines:Array.isArray(storyBlueprint.story_lines)?storyBlueprint.story_lines:[],chapter_briefs:Array.isArray(storyBlueprint.chapter_briefs)?storyBlueprint.chapter_briefs:[]};if(stepKey==='step_8')return{chapter_plans:Array.isArray(book?.metadata?.chapter_plans)?book.metadata.chapter_plans:[]};return{};}
function ensureStepDraft(stepKey,payloadObj){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const serialized=JSON.stringify(payloadObj??{},null,2);if(!(stepKey in stepDrafts)||!stepDraftDirty[stepKey]){stepDrafts[stepKey]=serialized;stepDraftObjects[stepKey]=deepClone(payloadObj??{});}return stepDrafts[stepKey];}
function ensureStepObject(stepKey,payloadObj){ensureStepDraft(stepKey,payloadObj);if(!(stepKey in stepDraftObjects))stepDraftObjects[stepKey]=deepClone(payloadObj??{});return stepDraftObjects[stepKey];}
function updateStepDraft(stepKey,value){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=value;stepDraftDirty[stepKey]=true;try{stepDraftObjects[stepKey]=JSON.parse(value);}catch{}}
function markStepDraftSaved(stepKey,payloadObj,notes){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=JSON.stringify(payloadObj??{},null,2);stepDraftObjects[stepKey]=deepClone(payloadObj??{});stepDraftDirty[stepKey]=false;stepReviewNotes[stepKey]=Array.isArray(notes)?notes:[];}
function applyStepRevisionDraft(result){if(!result||!result.step_key)return;const stepKey=result.step_key;const revisedText=result.draft_json||JSON.stringify(result.step_payload||{},null,2);stepDrafts[stepKey]=revisedText;try{stepDraftObjects[stepKey]=JSON.parse(revisedText);}catch{stepDraftObjects[stepKey]=deepClone(result.step_payload||{});}stepDraftDirty[stepKey]=true;stepReviewNotes[stepKey]=Array.isArray(result.review_notes)?result.review_notes:[];if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function latestOutputByType(runData,outputType){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){if(outs[i]?.output_type===outputType)return outs[i].payload||null;}return null;}
function stepFieldLabel(key){const labels={premise:'大纲主体',story_engine:'写作架构',characters:'角色卡',relationship_network:'关系网',event_timeline:'客观事件时间线',character_milestones:'角色发展线',twist_designs:'反转设计',story_lines:'故事线',chapter_briefs:'章节标题与摘要',chapter_plans:'章节规划',title:'标题',high_concept:'高概念',theme_statement:'立意',story_summary:'故事简介',genre:'题材',target_style:'风格',emotional_hook:'情绪钩子',central_conflict:'核心冲突',core_hook:'核心看点',escalation_path:'升级路径',twist_blueprint:'反转蓝图',ending_payoff:'结尾兑现',selling_points:'卖点',engine_sentence:'故事驱动句',narrative_mode:'叙事结构',viewpoint_strategy:'视角策略',reveal_strategy:'信息揭示策略',hook_strategy:'前三章留人策略',default_track:'默认轨道',world_rules:'世界规则',power_structure:'权力结构',world_map:'世界地图',structural_inertia:'结构惯性',rebound_mechanism:'反弹机制',story_trigger:'故事启动条件',objective_conditions:'客观条件与机会结构',name:'名称',line_type:'线类型',start_state:'起点状态',midpoint_shift:'中段变化',end_state:'终点状态',core_question:'核心问题',chapter_id:'章节编号',active_lines:'挂线',summary:'摘要',turn:'转折',cliffhanger:'悬念',chapter_type:'章型',core_question_left:'留给读者的问题',small_payoff:'小兑现',reader_hook:'读者钩子',new_information:'新信息',relationship_shift:'关系变化',ending_pull:'结尾牵引',objective:'本章任务',tension:'张力',phase:'阶段',story_function:'剧情功能',key_turn:'关键转折',payoff:'兑现',next_route_hint:'下一步提示',target_words:'目标字数',scene_density:'场景密度',scene_beats:'场景节拍',planned_scene_count:'场景数量',scene_id:'场景编号',conflict:'冲突',info_reveal:'信息释放',emotional_shift:'情绪变化'};return labels[key]||String(key).replaceAll('_',' ');}
function parseStepPath(pathText){return String(pathText||'').split('.').filter(Boolean).map(part=>/^[0-9]+$/.test(part)?Number(part):part);}
function setStepValueByPath(root,path,value){if(!path.length)return value;let cursor=root;for(let i=0;i<path.length-1;i+=1){const key=path[i],nextKey=path[i+1];if(Array.isArray(cursor)&&typeof key==='number'){while(cursor.length<=key)cursor.push(typeof nextKey==='number'?[]:{});if(cursor[key]===null||cursor[key]===undefined)cursor[key]=typeof nextKey==='number'?[]:{};cursor=cursor[key];continue;}if(cursor[key]===undefined||cursor[key]===null){cursor[key]=typeof nextKey==='number'?[]:{};}cursor=cursor[key];}const finalKey=path[path.length-1];if(Array.isArray(cursor)&&typeof finalKey==='number'){while(cursor.length<finalKey)cursor.push({});while(cursor.length<=finalKey)cursor.push('');cursor[finalKey]=value;return root;}cursor[finalKey]=value;return root;}
function updateStepEditorValue(stepKey,pathText,kind,rawValue){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const state=ensureStepObject(stepKey,{});const path=parseStepPath(pathText);let value=rawValue;if(kind==='string_array'){value=normalizeMultiline(rawValue).split('\\n').map(item=>item.trim()).filter(Boolean);}else if(kind==='number'){const trimmed=String(rawValue??'').trim();value=trimmed===''?'':Number(trimmed);}else if(kind==='boolean'){value=!!rawValue;}setStepValueByPath(state,path,value);stepDrafts[stepKey]=JSON.stringify(state,null,2);stepDraftDirty[stepKey]=true;}
function renderStepEditorField(stepKey,path,value){const pathText=path.join('.');if(Array.isArray(value)){if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;const primitiveArray=value.every(item=>item===null||['string','number','boolean'].includes(typeof item));if(primitiveArray){return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string_array', this.value)">${esc(value.map(item=>String(item??'')).join('\\n'))}</textarea>`;}return `<div class='step-inline-stack'>${value.map((item,index)=>`<details class='step-inline-card'><summary class='step-inline-card-title'>${esc(stepFieldLabel(String(path[path.length-1]||'item')))} ${index+1}</summary>${renderStepEditorField(stepKey,[...path,index],item)}</details>`).join('')}</div>`;}if(value&&typeof value==='object'){const entries=Object.entries(value);if(!entries.length)return `<div class='step-inline-empty'>当前为空。</div>`;return `<div class='step-inline-root'>${entries.map(([key,val])=>`<div class='step-inline-field'><label>${esc(stepFieldLabel(key))}</label>${renderStepEditorField(stepKey,[...path,key],val)}</div>`).join('')}</div>`;}if(typeof value==='number'){return `<input class='step-inline-input' type='number' value='${esc(value)}' oninput="updateStepEditorValue('${stepKey}','${pathText}','number', this.value)" />`;}if(typeof value==='boolean'){return `<label class='row'><input type='checkbox' ${value?'checked':''} onchange="updateStepEditorValue('${stepKey}','${pathText}','boolean', this.checked)" /> ${value?'是':'否'}</label>`;}return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string', this.value)">${esc(value??'')}</textarea>`;}
function renderStepEditor(stepKey,stepTitle,payloadObj){const notes=Array.isArray(stepReviewNotes[stepKey])?stepReviewNotes[stepKey]:[];const state=ensureStepObject(stepKey,payloadObj);return `<div class='step-editor'><div class='step-editor-toolbar'><div class='step-editor-title'>${esc(stepTitle)} 直接编辑</div><div class='step-editor-actions'><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button></div></div><div class='step-editor-body'>${notes.length?`<ul class='step-editor-notes'>${notes.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:`<div class='step-editor-empty'>可以直接在这个模块里改内容；按 Enter 会换行，点右上角“保存修改”才会真正写回。</div>`}${renderStepEditorField(stepKey,[],state)}<div class='step-editor-hint'>这里是当前步骤的结构化编辑区。质检修改和指令修改会先生成建议稿并回填到这里，确认后再保存。</div></div></div>`;}
function getStepPayloadText(stepKey,payloadObj){const state=ensureStepObject(stepKey,payloadObj);return JSON.stringify(state??{},null,2);}
async function saveStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));const result=await api('/api/novels/save_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text})});if(!ensureOk(result))return;currentBook=result.book;markStepDraftSaved(stepKey,result.step_payload||stepPayloadFromBook(result.book,stepKey),stepReviewNotes[stepKey]||[]);renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();alert('当前步骤修改已保存。');}
async function reviseStepDraft(stepKey,revisionMode){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));let guidance='';if(revisionMode==='instruction'){guidance=prompt('描述你希望这一步结果怎么改：');if(!guidance)return;}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text,revision_mode:revisionMode,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:stepKey,revision_mode:revisionMode,payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:revisionMode==='review'?'步骤质检修改已启动。':'步骤指令修改已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function regenerateRelationshipNetwork(index){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));let guidance;if(index!=null){const item=(currentBook?.blueprint?.relationship_network||[])[index];const label=item?`${item.line_name||''}（${item.subject||''}→${item.target||''}）`:`第 ${index+1} 条`;guidance=`保留当前角色卡 characters 不变，只重新生成 relationship_network 中的第 ${index+1} 条关系：${label}。保留其他条目不动，仅对该条目重新创作，输出完整 relationship_network 数组。不要改动 characters。`;}else{guidance='保留当前角色卡 characters 不变，只重新生成 relationship_network。基于现有角色卡、步骤一和步骤二结果，输出完整详细关系卡，不要改动 characters。';}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:index!=null?`关系网第 ${index+1} 条重新生成任务已启动。`:'关系网重新生成任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseRelationshipNetworkByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望关系网怎么改：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const guidance=`保留当前角色卡 characters 不变，只调整 relationship_network。必须基于现有角色卡展开，不要改动 characters。\n用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'关系网按指令调整任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addCharacterByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述新角色需求（身份、作用、和谁形成关系）：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const guidance=`仅在 characters 中新增 1 个角色，不要删除或重写现有角色；relationship_network 保持不变。新增角色要与现有核心角色形成明确关系，并能推动后续剧情。\n用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_3',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'新增角色任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleCharacterByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const r=await api('/api/novels/revise_single_character',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;applyStepRevisionDraft(r);alert('该角色的建议稿已生成，请点“保存修改”后生效。');}
function toggleButtons(){const t=mode==='test';btnNew.style.display=t?'none':'inline-block';btnStep1.style.display=t?'none':'inline-block';btnStep2.style.display=t?'none':'inline-block';btnStep3.style.display=t?'none':'inline-block';btnStep4.style.display=t?'none':'inline-block';btnStep5.style.display=t?'none':'inline-block';btnStep6.style.display=t?'none':'inline-block';btnStep7.style.display=t?'none':'inline-block';btnStep8.style.display=t?'none':'inline-block';btnBlueprintReview.style.display=t?'none':'inline-block';btnContinue.style.display=t?'none':'inline-block';btnBlueprint.style.display=t?'inline-block':'none';btnWrite.style.display=t?'inline-block':'none';btnCritique.style.display=t?'inline-block':'none';btnPatch.style.display=t?'inline-block':'none';}
function updateStopButton(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);btnStop.style.display=a?'inline-block':'none';}
async function loadNovels(){const novels=await api('/api/novels?mode='+mode);novelSel.innerHTML="<option value=''>选择小说</option>";novels.forEach(n=>{const o=document.createElement('option');o.value=n.book_id;o.textContent=n.title||n.book_id;novelSel.appendChild(o);});if(bookId)novelSel.value=bookId;}
async function loadRuns(){if(!bookId){runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];return renderRuns();}runsCache=await api(`/api/runs?mode=${mode}&book_id=${bookId}`);const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();}
function renderEmptyRightPanels(){document.getElementById('pnl-input').innerHTML="<div class='empty'>等待加载用户输入</div>";document.getElementById('pnl-blueprint').innerHTML="<div class='empty'>等待加载小说信息</div>";document.getElementById('pnl-text').innerHTML="<div class='empty'>等待加载小说正文</div>";document.getElementById('pnl-critic').innerHTML="<div class='empty'>等待加载评价结果</div>";showTab('input');}
async function changeMode(){mode=modeSel.value;bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();boxStates={};resetStepDraftCache('');evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';toggleButtons();updateStopButton();await loadNovels();}
async function selectNovel(id){bookId=id;currentBook=null;pendingRunId='';pendingStepRevision=null;expandedRuns=new Set();boxStates={};resetStepDraftCache(id||'');if(!bookId){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';updateStopButton();return;}await refreshNovel();}
async function refreshNovel(){if(!bookId)return;const d=await api(`/api/novel?mode=${mode}&book_id=${bookId}`);if(!d.book)return;if(stepDraftBookId!==d.book.id)resetStepDraftCache(d.book.id);const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);const scrollState=captureScrollState();currentBook=d.book;if(!editingInRight){renderInputPanel(d.book);renderBlueprint(d.book,d.blueprint_review);renderText(d.book);renderCritic(d.critic);}stagePill.textContent=stageText(d.latest_stage);runsCache=d.runs||[];const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();await loadNovels();restoreScrollState(scrollState);}
async function refreshPendingRun(){if(!pendingRunId)return;const trackedRunId=pendingRunId;const d=await api(`/api/run?mode=${mode}&run_id=${trackedRunId}`);stagePill.textContent=stageText(d.stage||'writing');const running=d.is_running!==false;if(running){runsCache=[{run_id:trackedRunId,is_running:true,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),pending_message:'运行中，等待模型返回更多内容。'},...runsCache.filter(x=>x.run_id!==trackedRunId)];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();return;}let revisionPayload=latestOutputByType(d,'step_revision_draft');const completedRevision=pendingStepRevision&&pendingStepRevision.run_id===trackedRunId?pendingStepRevision:null;pendingRunId='';pendingStepRevision=null;if(!revisionPayload&&completedRevision&&completedRevision.step_key&&completedRevision.payload_text){const fallback=await api('/api/novels/revise_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:completedRevision.step_key,payload_text:completedRevision.payload_text,revision_mode:completedRevision.revision_mode||'instruction',guidance:completedRevision.guidance||''})});if(ensureOk(fallback)){revisionPayload=fallback;}}if(revisionPayload)applyStepRevisionDraft(revisionPayload);if(d.current_book_id){bookId=d.current_book_id;novelSel.value=bookId;await refreshNovel();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}return;}runsCache=[{run_id:trackedRunId,is_running:false,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),pending_message:'运行已结束，查看下方最新事件。'}];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}}
function boxHtml(key,title,payloadHtml,isOpen){return `<details class='box' ${isOpen?'open':''} ontoggle="toggleBox('${key}', this.open)"><summary><span class='title'>${title}</span></summary><div class='payload'>${payloadHtml}</div></details>`}
function toggleBox(key,isOpen){boxStates[key]=isOpen;}
const toArray=v=>Array.isArray(v)?v.filter(Boolean):[];
const jsonHtml=v=>`<div class='pre json'>${esc(JSON.stringify(v??{},null,2))}</div>`;
const chipsHtml=v=>{const items=toArray(v);return items.length?`<div class='chips'>${items.map(item=>`<span class='chip'>${esc(item)}</span>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
const linesHtml=v=>{const items=toArray(v);return items.length?`<div class='mini-list'>${items.map(item=>`<div class='mini-item'>${esc(item)}</div>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
function infoRow(label,value){if(value===undefined||value===null||value==='')return '';return `<div class='kv'><div class='k'>${esc(label)}</div><div>${esc(value)}</div></div>`}
function sectionHtml(label,body){return `<div class='subsec'>${esc(label)}</div>${body}`}
function renderDirectorDecision(payload){
  const infoGaps=toArray(payload&&payload.info_gaps);
  const toolInput=payload&&typeof payload.tool_input==='object'&&payload.tool_input?payload.tool_input:{};
  const query=toolInput.query||'';
  const stage=toolInput.stage||'';
  const focus=toArray(toolInput.focus);
  const tags=toArray(toolInput.tags);
  const extras=Object.entries(toolInput).filter(([key])=>!['query','stage','focus','tags'].includes(key));
  let html="<div class='agent-view'>";
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('理由', payload&&payload.reasoning||'');
  if(stage)html+=infoRow('阶段', stage);
  if(query)html+=infoRow('查询', query);
  if(focus.length)html+=sectionHtml('焦点', chipsHtml(focus));
  if(tags.length)html+=sectionHtml('标签', chipsHtml(tags));
  if(infoGaps.length)html+=sectionHtml('信息缺口', linesHtml(infoGaps));
  if(extras.length)html+=sectionHtml('其他', jsonHtml(Object.fromEntries(extras)));
  html+="</div>";
  return html;
}
function renderReferenceCards(payload){
  const cards=toArray(payload&&payload.cards);
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('查询', payload&&payload.query||'');
  const focus=toArray(payload&&payload.focus);
  const tags=toArray(payload&&payload.tags);
  if(focus.length)html+=sectionHtml('关注点', chipsHtml(focus));
  if(tags.length)html+=sectionHtml('筛选标签', chipsHtml(tags));
  if(cards.length){
    html+=sectionHtml('参考卡片', `<div class='mini-list'>${cards.map(card=>`<div class='mini-item'><div class='mini-title'>${esc(card.title||card.card_id||'未命名')}</div><div class='muted'>${esc(card.summary||'')}</div>${toArray(card.tags).length?`<div style='margin-top:6px'>${chipsHtml(card.tags.slice(0,5))}</div>`:''}</div>`).join('')}</div>`);
  }else{
    html+=sectionHtml('参考卡片', "<div class='muted'>暂无卡片</div>");
  }
  if(payload&&payload.reference_pack)html+=sectionHtml('参考 Prompt 包', `<div class='subbox pre'>${esc(payload.reference_pack)}</div>`);
  html+="</div>";
  return html;
}
function renderToolObservation(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('工具', payload&&payload.tool_name||'');
  html+=infoRow('摘要', payload&&payload.summary||'');
  if(payload&&payload.payload&&Object.keys(payload.payload).length)html+=sectionHtml('详情', jsonHtml(payload.payload));
  html+="</div>";
  return html;
}
function renderStageEvent(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('原因', payload&&payload.reason||'');
  html+="</div>";
  return html;
}
function renderErrorEvent(payload){
  return `<div class='agent-view'>${infoRow('错误', payload&&payload.error||'未知错误')}</div>`;
}
function renderItemPayload(item){
  if(item.kind==='output'&&item.outputType==='director_decision')return renderDirectorDecision(item.rawPayload);
  if(item.kind==='output'&&item.outputType==='reference_cards')return renderReferenceCards(item.rawPayload);
  if(item.kind==='output'&&item.outputType==='tool_observation')return renderToolObservation(item.rawPayload);
  if(item.kind==='event'&&item.eventType==='stage')return renderStageEvent(item.rawPayload);
  if(item.kind==='event'&&item.eventType==='error')return renderErrorEvent(item.rawPayload);
  if(item.kind==='plain')return `<div class='pre'>${esc(item.text||'')}</div>`;
  return jsonHtml(item.rawPayload);
}
function setRefreshPaused(paused,reason=''){refreshPaused=paused;refreshPauseReason=paused?reason:'';if(refreshPauseTimer){clearTimeout(refreshPauseTimer);refreshPauseTimer=null;}}
function pauseRefreshFor(ms,reason=''){setRefreshPaused(true,reason);refreshPauseTimer=setTimeout(()=>{if(!isMouseSelecting)setRefreshPaused(false,'');},ms);}
function isEditingElement(el){return !!(el&&(el.tagName==='TEXTAREA'||el.tagName==='INPUT'||el.isContentEditable));}
function hasUserSelection(){const sel=window.getSelection&&window.getSelection();return !!(sel&&String(sel).trim().length);}
document.addEventListener('mousedown',()=>{isMouseSelecting=true;setRefreshPaused(true,'selecting');});
document.addEventListener('mouseup',()=>{isMouseSelecting=false;if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isEditingElement(document.activeElement))setRefreshPaused(false,'');});
document.addEventListener('selectionchange',()=>{if(hasUserSelection())pauseRefreshFor(4000,'selection');else if(!isMouseSelecting&&!isEditingElement(document.activeElement)&&refreshPauseReason==='selection')setRefreshPaused(false,'');});
document.addEventListener('focusin',event=>{if(isEditingElement(event.target))setRefreshPaused(true,'editing');});
document.addEventListener('focusout',event=>{if(isEditingElement(event.target)){setTimeout(()=>{if(!hasUserSelection()&&!isEditingElement(document.activeElement)&&!isMouseSelecting)setRefreshPaused(false,'');},0);}});
function buildStreamItems(runId,evts){const groups=[],byId={};let active=null,seq=0;function ensureGroup(callId,ts,agent){const key=callId||`legacy_${++seq}`;if(byId[key]){if(agent&&!byId[key].agent)byId[key].agent=agent;return byId[key];}const group={key,text:'',reply:'',sortTs:ts||'',done:false,agent:agent||''};byId[key]=group;groups.push(group);return group;}evts.forEach(e=>{const payload=e.payload||{},callId=payload.call_id||'';if(e.event_type==='llm_prompt'){active=ensureGroup(callId||`prompt_${e.id||++seq}`,e.ts,e.agent);active.prompt=payload.preview||'';}else if(e.event_type==='llm_stream'){const group=callId?ensureGroup(callId,e.ts,e.agent):(active&&!active.done?active:ensureGroup(`stream_${e.id||++seq}`,e.ts,e.agent));group.text+=payload.preview||'';group.sortTs=e.ts||group.sortTs;if(e.agent&&!group.agent)group.agent=e.agent;}else if(e.event_type==='llm_reply'){const group=callId?ensureGroup(callId,e.ts,e.agent):active;if(group){group.reply=payload.preview||'';group.done=true;group.sortTs=e.ts||group.sortTs;if(e.agent&&!group.agent)group.agent=e.agent;}}});return groups.filter(group=>group.text||group.reply).map((group,index)=>({key:`${runId}:stream:${group.key}`,title:`${group.agent||'LLM'} · 流式输出 #${index+1}`,kind:'plain',text:group.text||group.reply||'',sortTs:group.sortTs||''}));}
async function renderRuns(pref){const scrollState=captureLeftScrollState();if(!runsCache.length){evs.innerHTML="<div class='empty'>??????</div>";restoreLeftScrollState(scrollState);return;}const cache=pref||{};for(const r of runsCache){if(expandedRuns.has(r.run_id)&&!cache[r.run_id])cache[r.run_id]=await api(`/api/run?mode=${mode}&run_id=${r.run_id}`);}let html='';runsCache.forEach(r=>{const ex=expandedRuns.has(r.run_id),d=cache[r.run_id],outs=(d&&d.outputs)||[],evts=(d&&d.events)||[];const streamItems=buildStreamItems(r.run_id,evts);const normalEvents=evts.filter(e=>!['llm_stream','llm_prompt','llm_reply'].includes(e.event_type));const items=[];if(r.pending_message)items.push({key:`${r.run_id}:pending`,title:'???',kind:'plain',text:r.pending_message,sortTs:r.updated_at||''});streamItems.forEach(item=>items.push(item));outs.forEach(o=>items.push({key:`${r.run_id}:out:${o.id}`,title:`${esc(o.agent)} ? ${esc(o.title)}`,kind:'output',outputType:o.output_type,rawPayload:o.payload,sortTs:o.created_at||''}));normalEvents.forEach(e=>items.push({key:`${r.run_id}:evt:${e.id}`,title:`${esc(e.agent||'System')} ? ${esc(e.title||'')}`,kind:'event',eventType:e.event_type,rawPayload:e.payload,sortTs:e.ts||''}));items.sort((a,b)=>String(a.sortTs).localeCompare(String(b.sortTs)));html+=`<div class='run'><div class='head' onclick="toggleRun('${r.run_id}')"><span class='tag'>${esc(stageText(r.stage))}</span>${r.is_running?"<span class='tag live'>???</span>":''}${r.cancel_requested?"<span class='tag stop'>???</span>":''}<span>${esc(r.run_id)}</span><span class='ts'>${esc(shortTs(r.updated_at))}</span></div>`;if(ex){html+="<div class='body'>";if(r.is_running)html+=`<div style='margin-bottom:8px'><button class='ghost' onclick="event.stopPropagation();stopRun('${r.run_id}')">?????</button></div>`;if(!items.length)html+="<div class='payload'>??????</div>";items.forEach((item,index)=>{const isLatest=index===items.length-1;const isOpen=(item.key in boxStates)?boxStates[item.key]:isLatest;html+=boxHtml(item.key,item.title,renderItemPayload(item),isOpen);});html+='</div>';}html+='</div>';});evs.innerHTML=html;restoreLeftScrollState(scrollState);}
function toggleRun(id){expandedRuns.has(id)?expandedRuns.delete(id):expandedRuns.add(id);renderRuns();}
async function stopCurrentRun(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);if(!a)return alert('当前没有运行中的任务。');await stopRun(a.run_id);}
async function stopRun(id){if(!confirm('确认删除此运行记录？'))return;await api('/api/runs/stop',{method:'POST',body:JSON.stringify({mode,run_id:id})});expandedRuns.delete(id);if(pendingRunId===id){pendingRunId='';pendingStepRevision=null;}runsCache=runsCache.filter(x=>x.run_id!==id);bookId?await refreshNovel():renderRuns();updateStopButton();}
function summarizeBlock(text){const cleaned=String(text||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').split(' ').filter(Boolean).join(' ');return cleaned||'（空白内容）';}
function isDetailOpen(key,defaultOpen=true){return key in detailStates?detailStates[key]:defaultOpen;}
function toggleDetailState(key,isOpen){detailStates[key]=isOpen;}
function autoSizeTextareas(rootId){document.querySelectorAll(`#${rootId} textarea`).forEach(el=>{const resize=()=>{el.style.height='auto';el.style.height=`${el.scrollHeight}px`;el.style.overflow='hidden';};if(!el.dataset.autosizeBound){el.addEventListener('input',resize);el.dataset.autosizeBound='1';}resize();});}
function captureScrollState(){const activePanel=document.querySelector('.pnl.active');const tc=document.getElementById('tc');return{windowX:window.scrollX,windowY:window.scrollY,leftScrollTop:evs?evs.scrollTop:0,rightScrollTop:tc?tc.scrollTop:0,activePanelId:activePanel?activePanel.id:'',activePanelScrollTop:activePanel?activePanel.scrollTop:0};}
function captureLeftScrollState(){return{leftScrollTop:evs?evs.scrollTop:0};}
function restoreScrollState(state){if(!state)return;requestAnimationFrame(()=>{window.scrollTo(state.windowX||0,state.windowY||0);if(evs)evs.scrollTop=state.leftScrollTop||0;const tc=document.getElementById('tc');if(tc)tc.scrollTop=state.rightScrollTop||0;if(state.activePanelId){const panel=document.getElementById(state.activePanelId);if(panel)panel.scrollTop=state.activePanelScrollTop||0;}});}
function restoreLeftScrollState(state){if(!state)return;requestAnimationFrame(()=>{if(evs)evs.scrollTop=state.leftScrollTop||0;});}
function setAllInputBlocks(open){document.querySelectorAll('#pnl-input details.input-block').forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas('pnl-input');}
function setPanelSections(panelId,open){document.querySelectorAll(`#${panelId} details.section-card`).forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas(panelId);}
function normalizeMultiline(value){const cr=String.fromCharCode(13),lf=String.fromCharCode(10);return String(value??'').split(cr+lf).join(lf).split(cr).join(lf).trimEnd();}
function openNewNovelDialog(){newNovelModal.style.display='flex';newTitleInput.focus();}
function closeNewNovelDialog(){newNovelModal.style.display='none';}
async function startFormalFromDialog(){const title=newTitleInput.value.trim();const q=normalizeMultiline(newQueryInput.value);if(!q)return alert('请输入题材/需求。');const style=normalizeMultiline(newStyleInput.value);const r=await api('/api/novels/create',{method:'POST',body:JSON.stringify({mode,title,query:q,style_request:style})});if(!ensureOk(r))return;closeNewNovelDialog();bookId=r.book.id;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();currentBook=r.book;stagePill.textContent='未开始';await loadNovels();novelSel.value=bookId;await refreshNovel();updateStopButton();}
async function startPlanningRun(path,message){if(!bookId)return alert('请先选择一部小说。');const r=await api(path,{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:message},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function generateOutline(){await startPlanningRun('/api/novels/generate_outline','大纲+蓝图生成中');}
async function generateWorldbuilding(){await startPlanningRun('/api/novels/generate_worldbuilding','世界观+背景体系生成中');}
async function generateCharacters(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_characters',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'角色卡+关系网生成中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function generateMilestones(){await startPlanningRun('/api/novels/generate_milestones','角色发展线生成中');}
async function generateEventTimeline(){await startPlanningRun('/api/novels/generate_event_timeline','事件时间线生成中');}
async function generateTwistDesigns(){await startPlanningRun('/api/novels/generate_twist_designs','反转设计生成中');}
async function generateStoryLines(){await startPlanningRun('/api/novels/generate_story_lines','故事线+章节标题生成中');}
async function generateChapterPlans(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/generate_chapter_plans',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'章节规划+大纲生成中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviewBlueprint(){await startPlanningRun('/api/novels/review_blueprint','Blueprint Critic 评审中');}
async function continueFormal(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/novels/continue',{method:'POST',body:JSON.stringify({book_id:bookId})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'正在写下一章，请稍候...'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function deleteNovel(){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除此小说？该操作不可撤销。'))return;await api('/api/novels/delete',{method:'POST',body:JSON.stringify({mode,book_id:bookId})});bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();evs.innerHTML="<div class='empty'>????????????????</div>";renderEmptyRightPanels();stagePill.textContent='未开始';await loadNovels();updateStopButton();}
async function testBlueprint(){const q=prompt('输入题材需求（测试大纲）：');if(!q)return;const r=await api('/api/test/blueprint',{method:'POST',body:JSON.stringify({query:q})});pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'测试大纲运行中'}]:[];await renderRuns();updateStopButton();}
async function testWrite(){let r;if(bookId)r=await api('/api/test/write',{method:'POST',body:JSON.stringify({book_id:bookId})});else{const q=prompt('输入题材需求（测试写作）：');if(!q)return;r=await api('/api/test/write',{method:'POST',body:JSON.stringify({query:q})});}pendingRunId=r.run_id||'';expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'测试写作运行中'}]:[];await renderRuns();updateStopButton();}
async function testCritique(){if(!bookId)return alert('请先选择一部小说。');const r=await api('/api/test/critique',{method:'POST',body:JSON.stringify({book_id:bookId})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'critique',updated_at:new Date().toISOString(),pending_message:'测试评价运行中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function testPatch(){if(!bookId)return alert('请先选择一部小说。');const blockId=prompt('请输入 block_id：');if(!blockId)return;const operation=prompt('操作类型 replace / append / prepend','replace')||'replace';const patchContent=prompt('补丁内容：');if(!patchContent)return;const reason=prompt('修改原因：','manual test patch')||'manual test patch';const r=await api('/api/test/patch',{method:'POST',body:JSON.stringify({book_id:bookId,block_id:blockId,operation,patch_content:patchContent,reason})});pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'测试补丁运行中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseConcept(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你希望 AI 怎么修改概念：');if(!guidance)return;const r=await api('/api/novels/ai_update_concept',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),pending_message:'AI 修改中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function aiReviseText(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt(scope==='chapter'?'描述你希望 AI 怎么修改这章：':'描述你希望 AI 怎么修改这段：');if(!guidance)return;const r=await api('/api/novels/ai_update_text',{method:'POST',body:JSON.stringify({mode,book_id:bookId,scope,target_id:targetId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';expandedRuns.add(pendingRunId);runsCache=[{run_id:pendingRunId,is_running:true,stage:'patching',updated_at:new Date().toISOString(),pending_message:'AI 修改文本中'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}

async function resolveCharacterCandidate(candidateId,action){
  if(!bookId)return alert('请先选择一部小说。');
  const result=await api('/api/novels/resolve_character_candidate',{method:'POST',body:JSON.stringify({mode,book_id:bookId,candidate_id:candidateId,action})});
  if(!ensureOk(result))return;
  currentBook=result.book;
  renderInputPanel(currentBook);
  renderBlueprint(currentBook);
  renderText(currentBook);
  await loadNovels();
  alert(action==='add'?'角色已添加':'已设为仅本场景');
}

function renderInputPanel(book){
  const currentQuery=book?.metadata?.query||'';
  const userTopic=book?.metadata?.user_topic||'';
  const styleRequest=book?.metadata?.style_request||'';
  const totalWordTarget=book?.metadata?.total_word_target||'';
  const chapterCountTarget=book?.metadata?.chapter_count_target||'';
  const chapterWordTarget=book?.metadata?.chapter_word_target||'';
  const paceNotes=book?.metadata?.pace_notes||'';
  const block=(key,id,title,text,placeholder,help,defaultOpen)=>`<details class='input-block' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summarizeBlock(text))}</div></div><div class='summary-arrow'>展开 / 折叠</div></summary><div class='block-body'><textarea id='${id}' placeholder='${esc(placeholder)}'>${esc(text)}</textarea><div class='block-help'>${help}</div></div></details>`;
  const writingSummary=[
    totalWordTarget?`总字 ${totalWordTarget}`:'',
    chapterCountTarget?`章数 ${chapterCountTarget}`:'',
    chapterWordTarget?`每章 ${chapterWordTarget}`:'',
    paceNotes?`节奏 ${paceNotes}`:''
  ].filter(Boolean).join(' / ')||'暂无写作要求';
  const writingBlock=`<details class='input-block' data-detail-key='input-writing-requirements' ${isDetailOpen('input-writing-requirements',false)?'open':''} ontoggle="toggleDetailState('input-writing-requirements', this.open)"><summary><div class='summary-text'><div class='summary-title'>写作要求</div><div class='summary-desc'>${esc(writingSummary)}</div></div><div class='summary-arrow'>›</div></summary><div class='block-body'><div class='writing-req-grid'><div class='field'><label>总字数目标</label><input id='concept-total-word-target' value='${esc(totalWordTarget)}' placeholder='约80-100万字' /></div><div class='field'><label>章节数目标</label><input id='concept-chapter-count-target' value='${esc(chapterCountTarget)}' placeholder='约180-220章' /></div><div class='field'><label>章节字数</label><input id='concept-chapter-word-target' value='${esc(chapterWordTarget)}' placeholder='约2500-3500字' /></div></div><div class='writing-req-full'><label>节奏备注</label><textarea id='concept-pace-notes' placeholder='描述各阶段节奏安排'>${esc(paceNotes)}</textarea></div><div class='block-help'>写作要求会影响步骤 1-8 的生成结果</div></div></details>`;
  const heroSummary='在这里填写小说的基础信息，修改后记得点保存。';
  const html=`<div class='card'><div class='sec'>用户输入</div><div class='input-hero'><div class='input-hero-copy'><div class='input-hero-kicker'>小说基础设置</div><div class='input-hero-title-row'><h2 class='input-hero-title'>${esc(book?.title||'未命名小说')}</h2><span class='input-hero-badge'>写作控制台</span></div><div class='input-hero-desc'>${heroSummary}</div></div><div class='input-toolbar'><div class='actions'><button class='ghost' onclick='setAllInputBlocks(true)'>全部展开</button><button class='ghost' onclick='setAllInputBlocks(false)'>全部折叠</button><button onclick='saveConcept()'>保存所有修改</button></div></div></div><div class='title-field'><label>书名标题</label><input id='concept-title' value='${esc(book?.title||'')}' placeholder='输入小说书名' /></div><div class='input-blocks'>${block('input-query','concept-query','题材与需求',currentQuery,'支持 Markdown 详细描述题材','此内容影响步骤 1-8 的生成',true)}${block('input-topic','concept-user-topic','用户主题',userTopic,'可选填写用户关注的主题方向','仅在明确时填写',false)}${block('input-style','concept-style-request','风格要求',styleRequest,'留空则由系统判断风格','明确时填写，不填则自动决策',false)}${writingBlock}</div></div>`;
  document.getElementById('pnl-input').innerHTML=html;
  autoSizeTextareas('pnl-input');
}
function renderBlueprint(book, blueprintReview){
  const premise=book?.premise||{};
  const blueprint=book?.metadata?.story_blueprint||{};
  const storyEngine=blueprint.story_engine||{};
  const sectionCard=(key,title,summary,body,defaultOpen=true)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  const toolbarSection=(key,title,summary,actions,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-toolbar' onclick='event.stopPropagation()'>${actions}</div></summary><div class='section-body'>${body}</div></details>`;
  const listHtml=(items, emptyText='暂无内容')=>{const arr=toArray(items);return arr.length?`<div class='mini-list'>${arr.map(item=>`<div class='mini-item'>${esc(typeof item==='string'?item:JSON.stringify(item,null,2))}</div>`).join('')}</div>`:`<div class='relationship-empty'>${emptyText}</div>`;};
  const detailRowsHtml=(title,items,emptyText)=>{const arr=toArray(items);if(!arr.length)return `<div class='field-block'><div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(title)}：</span><span class='field-val'>${esc(emptyText)}</span></div></div>`;return `<div class='field-block'><div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(title)}：</span><span class='field-val'>共 ${arr.length} 条</span></div>${arr.map((item,index)=>`<div class='field-row'><span class='field-dot'>${index+1}.</span><span class='field-val'>${esc(typeof item==='string'?item:JSON.stringify(item,null,2))}</span></div>`).join('')}</div>`;};
  const stepSection=(stepKey,title,summary,body,defaultOpen=false)=>{const badge=stepDraftDirty[stepKey]?`<span class='dirty-dot'>●未保存</span>`:'';const acts=`${badge}<button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存</button>`;return toolbarSection(stepKey,title,summary,acts,body,defaultOpen);};
  const subStepEditor=(stepKey,subKey,label)=>{const s=ensureStepObject(stepKey,stepPayloadFromBook(book,stepKey));return `<div class='step-editor'><div class='step-editor-body'><div class='step-editor-empty'>可以直接在这个模块里改内容，点右上角"保存"才会真正写回。</div>${renderStepEditorField(stepKey,[subKey],s[subKey]??[])}</div></div>`;};
  const step3DraftObj=stepDraftDirty['step_3']?(stepDraftObjects['step_3']||{}):null;
  const rawStep3Chars=Array.isArray(step3DraftObj?.characters)?step3DraftObj.characters:(book?.characters||[]);
  const displayCharacters=rawStep3Chars.filter(item=>item&&typeof item==='object');
  if(step3DraftObj&&Array.isArray(step3DraftObj.characters)&&displayCharacters.length!==step3DraftObj.characters.length){step3DraftObj.characters=displayCharacters;stepDraftObjects['step_3']=step3DraftObj;stepDrafts['step_3']=JSON.stringify(step3DraftObj,null,2);}
  const step3Dirty=!!stepDraftDirty['step_3'];
  const dirtyBadge=step3Dirty?`<span class='dirty-dot' title='有未保存的修改'>●未保存</span>`:'';
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说信息概览</div><div class='panel-title'>步骤 1-8 详情</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-blueprint',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-blueprint',false)">全部折叠</button></div></div>`;
  html+=stepSection('step_1','1 大纲+蓝图',premise.story_summary||premise.high_concept||'暂无概念信息',subStepEditor('step_1','premise','大纲主体')+subStepEditor('step_1','story_engine','叙事架构'),false);
  html+=stepSection('step_2','2 背景体系+世界观',storyEngine.engine_sentence||'暂无引擎句',subStepEditor('step_2','story_engine','世界观'));
  const fieldRows=(pairs)=>pairs.filter(([,v])=>v).map(([k,v])=>`<div class='field-row'><span class='field-dot'>·</span><span class='field-label'>${esc(k)}：</span><span class='field-val'>${esc(v)}</span></div>`).join('')||"<div class='field-row'>（暂无信息）</div>";
  const charField=(idx,key,label,val)=>`<div class='step-inline-field'><label>${esc(label)}</label><textarea class='step-inline-textarea' oninput="updateStepEditorValue('step_3','characters.${idx}.${key}','string',this.value)">${esc(val||'')}</textarea></div>`;
  const characterCards=displayCharacters.map((item,index)=>{const title=item.name||item.role||`角色 ${index+1}`;const summary=[item.role,item.personality,item.occupation].filter(Boolean).join(' · ')||'暂无信息';const editFields=[charField(index,'name','名称',item.name),charField(index,'role','角色定位',item.role),charField(index,'occupation','职业',item.occupation),charField(index,'personality','性格',item.personality),charField(index,'social_background','社会背景',item.social_background),charField(index,'education_background','教育背景',item.education_background),charField(index,'career','事业',item.career),charField(index,'initial_state','初始状态',item.initial_state),charField(index,'motivation','动机',item.motivation),charField(index,'behavior_pattern','行为模式',item.behavior_pattern),charField(index,'arc','成长弧',item.arc),charField(index,'relationships','关系',item.relationships)].join('');const axes=toArray(item.development_axes||[]);const body=`<div class='step-inline-root'>${editFields}</div>${axes.length?`<div style='margin-top:8px'>${listHtml(axes,'')}</div>`:''}<div style='display:flex;justify-content:flex-end;gap:8px;margin-top:12px'><button class='ghost' onclick='reviseSingleCharacterByInstruction(${index})'>指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存修改</button></div>`;return sectionCard(`step3-character-${index}`,title,summary,body,false);}).join('')||"<div class='relationship-empty'>暂无角色</div>";
  const charActions=`${dirtyBadge}<button class='ghost' onclick="addCharacterByInstruction()">增加角色</button><button class='ghost' onclick="reviseStepDraft('step_3','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('step_3','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存</button>`;
  html+=toolbarSection('step3-characters','3 角色卡',`${displayCharacters.length} 个角色`,charActions,characterCards,false);
  html+=stepSection('step_4','4 客观事件时间线',`${(blueprint.event_timeline||[]).length} 条`,subStepEditor('step_4','event_timeline','事件时间线'));
  html+=stepSection('step_5','5 角色发展线',`${(book?.metadata?.character_milestones||[]).length} 条发展线`,subStepEditor('step_5','character_milestones','角色发展线'));
  html+=stepSection('step_6','6 反转设计',`${(blueprint.twist_designs||[]).length} 个反转`,subStepEditor('step_6','twist_designs','反转设计'));
  html+=stepSection('step_7','7 故事线+章节标题',`${(blueprint.story_lines||[]).length} 条故事线 / ${(blueprint.chapter_briefs||[]).length} 章`,subStepEditor('step_7','story_lines','故事线')+subStepEditor('step_7','chapter_briefs','章节标题'));
  html+=stepSection('step_8','8 章节规划+大纲',`${(book?.metadata?.chapter_plans||[]).length} 章`,subStepEditor('step_8','chapter_plans','章节规划'));
  if(blueprintReview){html+=sectionCard('blueprint-review','Critic Blueprint',blueprintReview.summary||'暂无评审结论',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', blueprintReview.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((blueprintReview.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}`),'暂无问题')}</div></div>`,false);}
  document.getElementById('pnl-blueprint').innerHTML=html;
  autoSizeTextareas('pnl-blueprint');
}
function renderText(book){
  const volumes=book?.volumes||[];
  const chapters=[];
  const candidates=Array.isArray(book?.metadata?.new_character_candidates)?book.metadata.new_character_candidates:[];
  volumes.forEach(volume=>(volume.chapters||[]).forEach(chapter=>chapters.push({volume,chapter})));
  const sectionCard=(key,title,summary,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  if(!chapters.length && !candidates.length){document.getElementById('pnl-text').innerHTML="<div class='empty'>暂无内容</div>";return;}
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说正文</div><div class='panel-title'>章节内容</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-text',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-text',false)">全部折叠</button></div></div>`;
  if(candidates.length){
    const cards=candidates.map((item,index)=>{
      const traits=Array.isArray(item?.provisional_traits)?item.provisional_traits.filter(Boolean):[];
      const links=Array.isArray(item?.links_to_existing_characters)?item.links_to_existing_characters.filter(link=>link&&typeof link==='object'):[];
      const linkLines=links.length?links.map(link=>`<div class='kv'><div class='k'>${esc(link.target||'未知角色')}</div><div>${esc(link.relation||'未知关系')}</div></div>`).join(''):"<div class='relationship-empty'>暂无关联角色</div>";
      return `<div class='relationship-card'><div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'><div><div class='subsec'>${esc(item?.name||`角色候选 ${index+1}`)}</div><div class='muted'>首登场：${esc(item?.first_appearance_chapter||'待定')}</div></div><div class='actions'><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','add')">确认添加</button><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','scene_only')">仅本场景</button></div></div>${infoRow('场景作用', item?.role_in_scene||'')}${infoRow('存在理由', item?.why_needed||'')}${traits.length?sectionHtml('特征', chipsHtml(traits)):''}${sectionHtml('与现有角色关联', linkLines)}</div>`;
    }).join('');
    html+=sectionCard('text-character-candidates','新角色候选',`共 ${candidates.length} 个候选角色`,`<div class='relationship-stack'>${cards}</div>`,true);
  }
  chapters.forEach(({volume,chapter},index)=>{
    const title=chapter.title||chapter.id||`第${index+1}章`;
    const summary=chapter.summary||'暂无摘要';
    const scenes=(chapter.scenes||[]).map((scene,sceneIndex)=>{
      const blocks=(scene.blocks||[]).map((block,blockIndex)=>`<div class='block' style='margin-top:8px'><div class='row'><strong>块 ${blockIndex+1}</strong>${block.purpose?` <span class='muted'>${esc(block.purpose)}</span>`:''}</div><div>${esc(block.text||'')}</div></div>`).join('')||"<div class='relationship-empty'>暂无段落内容</div>";
      return `<div class='relationship-card'><div class='subsec'>场景 ${sceneIndex+1}${scene.title?` · ${esc(scene.title)}`:''}</div>${infoRow('场景概述', scene.summary||'')}${blocks}</div>`;
    }).join('')||"<div class='relationship-empty'>暂无场景</div>";
    const body=`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>基础信息</div>${infoRow('卷名', volume.title||volume.id||'')}${infoRow('章节标题', title)}${infoRow('章节概述', summary)}</div><div class='relationship-card'><div class='subsec'>场景</div><div class='relationship-stack'>${scenes}</div></div></div>`;
    html+=sectionCard(`text-chapter-${chapter.id||index}`,title,summary,body,false);
  });
  document.getElementById('pnl-text').innerHTML=html;
}

function renderCritic(c){
  if(!c){document.getElementById('pnl-critic').innerHTML="<div class='empty'>暂无评价内容</div>";return;}
  const sectionCard=(key,title,summary,body,defaultOpen=true)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>评价结果</div><div class='panel-title'>评价详情</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-critic',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-critic',false)">全部折叠</button></div></div>`;
  html+=sectionCard('critic-summary','评价总结',c.summary||'暂无摘要',`${infoRow('摘要', c.summary||'')}${infoRow('问题数', (c.issues||[]).length)}`,true);
  (c.issues||[]).forEach((issue,index)=>{
    html+=sectionCard(`critic-issue-${index}`,`${issue.severity||'未知'} · ${issue.title||`Issue ${index+1}`}`,issue.evidence||issue.impact||'无详细描述',`<div class='issue'>${infoRow('位置', issue.location?.block_id||'')}${infoRow('证据', issue.evidence||'')}${infoRow('影响', issue.impact||'')}${infoRow('建议', issue.recommendation||'')}</div>`,false);
  });
  document.getElementById('pnl-critic').innerHTML=html;
}

function showTab(name){document.querySelectorAll('.tab').forEach((e,i)=>e.classList.toggle('active',['input','blueprint','text','critic'][i]===name));document.querySelectorAll('.pnl').forEach(e=>e.classList.remove('active'));document.getElementById('pnl-'+name).classList.add('active');}
const btnNew=document.getElementById('btnNew'),btnStep1=document.getElementById('btnStep1'),btnStep2=document.getElementById('btnStep2'),btnStep3=document.getElementById('btnStep3'),btnStep4=document.getElementById('btnStep4'),btnStep5=document.getElementById('btnStep5'),btnStep6=document.getElementById('btnStep6'),btnStep7=document.getElementById('btnStep7'),btnStep8=document.getElementById('btnStep8'),btnBlueprintReview=document.getElementById('btnBlueprintReview'),btnContinue=document.getElementById('btnContinue'),btnBlueprint=document.getElementById('btnBlueprint'),btnWrite=document.getElementById('btnWrite'),btnCritique=document.getElementById('btnCritique'),btnPatch=document.getElementById('btnPatch'),btnStop=document.getElementById('btnStop'),stagePill=document.getElementById('stage-pill'),bootPill=document.getElementById('boot-pill'),novelSel=document.getElementById('novelSel'),modeSel=document.getElementById('modeSel'),evs=document.getElementById('evs'),newNovelModal=document.getElementById('newNovelModal'),newTitleInput=document.getElementById('newTitleInput'),newQueryInput=document.getElementById('newQueryInput'),newStyleInput=document.getElementById('newStyleInput');
function showFrontendError(message){
  if(bootPill)bootPill.textContent=`前端失败：${String(message||'未知错误').slice(0,40)}`;
  if(evs){
    evs.innerHTML=`<div class='empty'>前端初始化失败：${esc(message||'未知错误')}</div>`;
  }
  console.error(message);
}
window.addEventListener('error',event=>{
  showFrontendError(event?.error?.message||event?.message||'脚本运行错误');
});
window.addEventListener('unhandledrejection',event=>{
  const reason=event?.reason;
  showFrontendError(reason?.message||String(reason||'未处理的异步错误'));
});
async function initApp(){
  try{
    if(bootPill)bootPill.textContent='前端初始化中';
    toggleButtons();
    await loadNovels();
    if(bootPill)bootPill.textContent=`前端已加载 ${Math.max((novelSel?.options?.length||1)-1,0)} 本`;
    updateStopButton();
    setInterval(async()=>{
      if(refreshPaused)return;
      if(bookId)await refreshNovel();
      if(pendingRunId)await refreshPendingRun();
    },1500);
  }catch(err){
    showFrontendError(err?.message||String(err));
  }
}
initApp();
