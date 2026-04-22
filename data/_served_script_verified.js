
let mode='formal',llmProvider='doubao',bookId='',pendingRunId='',runsCache=[],expandedRuns=new Set(),boxStates={},detailStates={},currentBook=null,pendingStepRevision=null,lastRightRenderKey='',lastLivePreviewKey='',runActiveItemKeys={};
let refreshPaused=false,refreshPauseReason='',refreshPauseTimer=null,isMouseSelecting=false;
const LLM_PROVIDER_STORAGE_KEY='novel_flow_llm_provider';
const STAGES={research:'调研中',planning:'大纲中',writing:'写作中',critique:'评价中',patching:'修改中',complete:'已完成'};
const stageText=v=>STAGES[v]||v||'未开始',esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),shortTs=v=>v?String(v).replace('T',' ').slice(0,19):'';
async function api(path,opt){const r=await fetch(path,Object.assign({headers:{'Content-Type':'application/json'}},opt||{}));return await r.json();}
function ensureOk(r){if(r&&r.ok===false){alert(r.error||'请求失败');return false;}return true;}
const validLlmProvider=v=>['doubao','openai','codex'].includes(String(v||'').toLowerCase());
function currentLlmProvider(){return validLlmProvider(llmProvider)?llmProvider:'doubao';}
function withLlmProvider(payload){return Object.assign({},payload||{}, {llm_provider:currentLlmProvider()});}
function changeModel(){llmProvider=validLlmProvider(modelSel.value)?modelSel.value:'doubao';try{localStorage.setItem(LLM_PROVIDER_STORAGE_KEY,llmProvider);}catch{}}
let stepDrafts={},stepDraftDirty={},stepReviewNotes={},stepDraftBookId='';
let stepDraftObjects={};
function deepClone(value){return JSON.parse(JSON.stringify(value??{}));}
function resetStepDraftCache(targetBookId=''){stepDraftBookId=targetBookId;stepDrafts={};stepDraftDirty={};stepReviewNotes={};stepDraftObjects={};}
const STEP_STORY_BLUEPRINT_FIELDS={step_2:'story_engine',step_4:'event_timeline',step_6:'twist_designs',step_7:'story_lines',step_8:'chapter_briefs'};
const STEP_METADATA_FIELDS={step_5:'character_milestones'};
const STEP_RUN_CONFIGS={
  step_1:{path:'/api/novels/generate_outline',pendingMessage:'大纲+蓝图生成中',taskLabel:'步骤1 大纲+蓝图'},
  step_2:{path:'/api/novels/generate_worldbuilding',pendingMessage:'世界观+背景体系生成中',taskLabel:'步骤2 背景体系+世界观'},
  step_3:{path:'/api/novels/generate_characters',pendingMessage:'角色卡生成中',taskLabel:'步骤3 角色卡'},
  step_4:{path:'/api/novels/generate_event_timeline',pendingMessage:'事件时间线生成中',taskLabel:'步骤4 客观事件时间线'},
  step_5:{path:'/api/novels/generate_milestones',pendingMessage:'角色发展线生成中',taskLabel:'步骤5 角色发展线'},
  step_6:{path:'/api/novels/generate_twist_designs',pendingMessage:'反转设计生成中',taskLabel:'步骤6 反转设计'},
  step_7:{path:'/api/novels/generate_story_lines',pendingMessage:'明线暗线发展线生成中',taskLabel:'步骤7 明线暗线发展线'},
  step_8:{path:'/api/novels/generate_chapter_briefs_batch',pendingMessage:'步骤8 生成中（当前 1 章）',taskLabel:'步骤8 续写一章摘要',payload:{batch_size:1}},
  blueprint_review:{path:'/api/novels/review_blueprint',pendingMessage:'Blueprint Critic 评审中',taskLabel:'Critic Blueprint 评审'},
};
const STEP_SPECIAL_PAYLOAD_READERS={
  step_1:(book,storyBlueprint)=>({premise:book?.premise||{},story_engine:readStoryStepFieldValue(storyBlueprint,'story_engine')}),
  step_3:(book)=>({characters:Array.isArray(book?.characters)?book.characters:[]}),
};
const STEP_SPECIAL_EMPTY_PAYLOADS={step_1:{premise:{},story_engine:{}},step_3:{characters:[]}};
function readStoryStepFieldValue(storyBlueprint,field){
  if(field==='story_engine'){
    const value=storyBlueprint?.story_engine;
    return value&&typeof value==='object'&&!Array.isArray(value)?value:{};
  }
  const value=storyBlueprint?.[field];
  return Array.isArray(value)?value:[];
}
function emptyStepFieldValue(field){return field==='story_engine'?{}:[];}
function stepPayloadFromBook(book,stepKey){
  const storyBlueprint=book?.metadata?.story_blueprint||{};
  const specialReader=STEP_SPECIAL_PAYLOAD_READERS[stepKey];
  if(specialReader)return specialReader(book,storyBlueprint);
  const storyField=STEP_STORY_BLUEPRINT_FIELDS[stepKey];
  if(storyField){
    return{[storyField]:readStoryStepFieldValue(storyBlueprint,storyField)};
  }
  const metaField=STEP_METADATA_FIELDS[stepKey];
  if(metaField)return{[metaField]:Array.isArray(book?.metadata?.[metaField])?book.metadata[metaField]:[]};
  return{};
}
function emptyStepPayload(stepKey){
  const special=STEP_SPECIAL_EMPTY_PAYLOADS[stepKey];
  if(special)return deepClone(special);
  const storyField=STEP_STORY_BLUEPRINT_FIELDS[stepKey];
  if(storyField)return{[storyField]:emptyStepFieldValue(storyField)};
  const metaField=STEP_METADATA_FIELDS[stepKey];
  if(metaField)return{[metaField]:[]};
  return{};
}
function ensureStepDraft(stepKey,payloadObj){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const serialized=JSON.stringify(payloadObj??{},null,2);if(!(stepKey in stepDrafts)||!stepDraftDirty[stepKey]){stepDrafts[stepKey]=serialized;stepDraftObjects[stepKey]=deepClone(payloadObj??{});}return stepDrafts[stepKey];}
function ensureStepObject(stepKey,payloadObj){ensureStepDraft(stepKey,payloadObj);if(!(stepKey in stepDraftObjects))stepDraftObjects[stepKey]=deepClone(payloadObj??{});return stepDraftObjects[stepKey];}
function updateStepDraft(stepKey,value){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=value;stepDraftDirty[stepKey]=true;try{stepDraftObjects[stepKey]=JSON.parse(value);}catch{}}
function markStepDraftSaved(stepKey,payloadObj,notes){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);stepDrafts[stepKey]=JSON.stringify(payloadObj??{},null,2);stepDraftObjects[stepKey]=deepClone(payloadObj??{});stepDraftDirty[stepKey]=false;stepReviewNotes[stepKey]=Array.isArray(notes)?notes:[];}
function sanitizeCharactersDraft(chars){if(!Array.isArray(chars))return[];return chars.filter(item=>item&&typeof item==='object'&&Object.keys(item).length>0&&(String(item.name||'').trim()||String(item.role||'').trim()));}
function sanitizeStep3DraftObject(obj){if(!obj||typeof obj!=='object')return obj;const next=deepClone(obj);if(Array.isArray(next.characters))next.characters=sanitizeCharactersDraft(next.characters);return next;}
function applyStepRevisionDraft(result){if(!result||!result.step_key)return;const stepKey=result.step_key;const revisedText=result.draft_json||JSON.stringify(result.step_payload||{},null,2);stepDrafts[stepKey]=revisedText;try{stepDraftObjects[stepKey]=JSON.parse(revisedText);}catch{stepDraftObjects[stepKey]=deepClone(result.step_payload||{});}if(stepKey==='step_3'){stepDraftObjects[stepKey]=sanitizeStep3DraftObject(stepDraftObjects[stepKey]||{});stepDrafts[stepKey]=JSON.stringify(stepDraftObjects[stepKey]||{},null,2);}stepDraftDirty[stepKey]=true;stepReviewNotes[stepKey]=Array.isArray(result.review_notes)?result.review_notes:[];if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function latestOutputByType(runData,outputType){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){if(outs[i]?.output_type===outputType)return outs[i].payload||null;}return null;}
function latestChapterPreviewByMode(runData,previewMode){const outs=Array.isArray(runData?.outputs)?runData.outputs:[];for(let i=outs.length-1;i>=0;i-=1){const item=outs[i];if(item?.output_type!=='chapter_live_preview')continue;const payload=item?.payload||{};if(String(payload?.preview_mode||'')!==String(previewMode||''))continue;return{payload,createdAt:item?.created_at||''};}return null;}
function mergeChapterBlocksText(blocks,fallbackText=''){const arr=Array.isArray(blocks)?blocks:[];const merged=arr.map(block=>String(block?.text||'').trim()).filter(Boolean).join('\n\n').trim();return merged||String(fallbackText||'').trim();}
function parsePatchRound(stageName){const match=String(stageName||'').match(/patch_round_(\d+)_/);return match?Number(match[1]||0):0;}
function latestPatchedBlockIds(runData){const evts=Array.isArray(runData?.events)?runData.events:[];for(let i=evts.length-1;i>=0;i-=1){const payload=evts[i]?.payload||{};const stage=String(payload?.stage||'');if(!stage.includes('_rewrite_done'))continue;const patchedBlocks=Array.isArray(payload?.rewrite_result?.patched_blocks)?payload.rewrite_result.patched_blocks:[];const ids=patchedBlocks.map(item=>String(item?.block_id||'').trim()).filter(Boolean);if(ids.length)return ids;}return [];}
function collectChapterTaskOutputs(runData){
  const runId=String(runData?.run_id||'run');
  const chapterPreview=runData?.chapter_preview&&typeof runData.chapter_preview==='object'?runData.chapter_preview:{};
  const chapterId=String(chapterPreview?.chapter_id||'').trim();
  const stageEvents=(Array.isArray(runData?.events)?runData.events:[]).filter(event=>event?.event_type==='stage'&&event?.payload&&typeof event.payload==='object');
  const items=[];
  const draft=latestChapterPreviewByMode(runData,'chapter_draft');
  if(draft&&String(draft.payload?.final_text||'').trim()){
    items.push({
      key:`${runId}:task:draft`,
      title:'正文任务 · 整章手稿',
      kind:'output',
      outputType:'chapter_draft_task',
      rawPayload:{chapter_id:chapterId||String(draft.payload?.chapter_id||''),draft_preview:draft.payload},
      sortTs:draft.createdAt||'',
    });
  }
  const reviewEvents=stageEvents.filter(event=>String(event?.payload?.stage||'')==='review_iteration_1_tool_done'&&String(event?.payload?.tool_name||'').trim()&&event?.payload?.tool_result&&typeof event.payload.tool_result==='object');
  if(reviewEvents.length){
    items.push({
      key:`${runId}:task:review`,
      title:'正文任务 · 轻量 Review',
      kind:'output',
      outputType:'chapter_review_bundle',
      rawPayload:{
        chapter_id:chapterId,
        reviews:reviewEvents.map(event=>({tool_name:String(event?.payload?.tool_name||''),tool_result:event?.payload?.tool_result||{},stage:String(event?.payload?.stage||''),ts:event?.ts||''})),
      },
      sortTs:String(reviewEvents[reviewEvents.length-1]?.ts||''),
    });
  }
  stageEvents.forEach(event=>{
    const payload=event?.payload||{};
    const stageName=String(payload?.stage||'');
    const patchRound=parsePatchRound(stageName);
    if(stageName.endsWith('_plan_done')&&payload?.patch_plan&&typeof payload.patch_plan==='object'){
      items.push({
        key:`${runId}:task:plan:${patchRound||items.length}`,
        title:`正文任务 · Patch Plan${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_plan_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,patch_plan:payload.patch_plan},
        sortTs:String(event?.ts||''),
      });
    }
    if(stageName.endsWith('_rewrite_done')&&payload?.rewrite_result&&typeof payload.rewrite_result==='object'){
      items.push({
        key:`${runId}:task:rewrite:${patchRound||items.length}`,
        title:`正文任务 · 修改后的 Block${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_rewrite_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,rewrite_result:payload.rewrite_result},
        sortTs:String(event?.ts||''),
      });
    }
    if(stageName.endsWith('_judge')&&payload?.judge_result&&typeof payload.judge_result==='object'){
      items.push({
        key:`${runId}:task:judge:${patchRound||items.length}`,
        title:`正文任务 · Patch Judge${patchRound?` · 第 ${patchRound} 轮`:''}`,
        kind:'output',
        outputType:'chapter_patch_judge_task',
        rawPayload:{chapter_id:String(payload?.chapter_id||chapterId),patch_round:patchRound,judge_result:payload.judge_result,final_judge:payload?.final_judge||{}},
        sortTs:String(event?.ts||''),
      });
    }
  });
  return items;
}
function stepFieldLabel(key){const labels={premise:'大纲主体',story_engine:'写作架构',characters:'角色卡',event_timeline:'客观事件时间线',character_milestones:'角色发展线',twist_designs:'反转设计',story_lines:'故事线',chapter_briefs:'章节摘要',title:'标题',high_concept:'高概念',theme_statement:'立意',story_summary:'故事简介',genre:'题材',target_style:'风格',emotional_hook:'情绪钩子',central_conflict:'核心冲突',core_hook:'核心看点',escalation_path:'升级路径',twist_blueprint:'反转蓝图',ending_payoff:'结尾兑现',selling_points:'卖点',engine_sentence:'故事驱动句',narrative_mode:'叙事结构',viewpoint_strategy:'视角策略',reveal_strategy:'信息揭示策略',hook_strategy:'前三章留人策略',default_track:'默认轨道',world_rules:'世界规则',power_structure:'权力结构',world_map:'世界地图',structural_inertia:'结构惯性',rebound_mechanism:'反弹机制',story_trigger:'故事启动条件',objective_conditions:'客观条件与机会结构',twist_id:'反转编号',false_belief:'表层误导认知',truth:'真实真相',reader_alignment:'读者站位',seed_from:'埋线起点',reveal_at:'揭示章节',allowed_clues:'允许埋下的线索',forbidden_reveals:'禁止提前揭示',pov_lock:'视角锁',related_characters:'关联角色',payoff_effect:'兑现效果',line_id:'故事线编号',name:'名称',visibility:'明暗线',line_type:'线类型',reader_hook_mode:'读者钩子方式',line_rules:'线规则',carried_twists:'承载反转',line_goal:'线目标',key_progressions:'关键推进章节',plot:'关键情节',start_state:'起点状态',midpoint_shift:'中段变化',end_state:'终点状态',core_question:'核心问题',chapter_id:'章节编号',active_lines:'挂线',active_twists:'激活反转',summary:'章节摘要',chapter_type:'章型',incoming_hook:'承接钩子',opening_hook:'开篇钩子',core_scene:'核心场面',chapter_object:'章节目标物',reader_emotion:'读者情绪',reader_belief:'读者当前认知',allowed_info:'允许释放的信息',forbidden:'禁止出现',world_limit:'世界/规则限制',character_focus:'角色焦点',character_shift:'角色变化',relationship_reprice:'关系重估',emotional_turn:'情绪转折',backstory_trigger:'触发的前史',scene_engine:'场景引擎',clue_reveal_mechanism:'线索露出机制',character_reentry_focus:'人物再出场锚点',human_pain_anchor:'人味痛点锚',romance_seed:'言情危险种子',small_payoff:'小兑现',ending_pull:'结尾牵引',info_budget:'信息预算',objective:'章节摘要',tension:'张力',phase:'阶段',story_function:'剧情功能',key_turn:'关键转折',payoff:'兑现',next_route_hint:'下一步提示',target_words:'目标字数',scene_density:'场景密度',scene_id:'场景编号',conflict:'冲突',info_reveal:'信息释放',emotional_shift:'情绪变化',appearance:'外貌'};return labels[key]||String(key).replaceAll('_',' ');}
function orderedStepObjectEntries(stepKey,path,obj){
  const rawEntries=Object.entries(obj||{});
  const orderMap={
    step_6:['twist_id','title','false_belief','truth','reader_alignment','seed_from','reveal_at','allowed_clues','forbidden_reveals','pov_lock','related_characters','payoff_effect'],
    step_7:['line_id','name','line_type','visibility','core_question','reader_hook_mode','start_state','midpoint_shift','end_state','carried_twists','line_rules'],
    step_8:['chapter_id','title','chapter_type','active_lines','active_twists','summary','incoming_hook','opening_hook','core_scene','chapter_object','reader_emotion','reader_belief','allowed_info','allowed_clues','forbidden','world_limit','character_focus','character_shift','relationship_reprice','emotional_turn','backstory_trigger','scene_engine','clue_reveal_mechanism','character_reentry_focus','human_pain_anchor','romance_seed','small_payoff','ending_pull','info_budget']
  };
  const isStep6Item=stepKey==='step_6'&&path.length===2&&String(path[0])==='twist_designs'&&typeof path[1]==='number';
  const isStep7Item=stepKey==='step_7'&&path.length===2&&String(path[0])==='story_lines'&&typeof path[1]==='number';
  const isStep8Item=stepKey==='step_8'&&path.length===2&&String(path[0])==='chapter_briefs'&&typeof path[1]==='number';
  if(!isStep6Item&&!isStep7Item&&!isStep8Item)return rawEntries;
  const wanted=orderMap[stepKey]||[];
  if(!wanted.length)return rawEntries;
  const entryMap=new Map(rawEntries);
  const ordered=wanted.filter(key=>entryMap.has(key)).map(key=>[key,entryMap.get(key)]);
  rawEntries.forEach(([key,val])=>{if(!wanted.includes(key))ordered.push([key,val]);});
  return ordered;
}
function parseStepPath(pathText){return String(pathText||'').split('.').filter(Boolean).map(part=>/^[0-9]+$/.test(part)?Number(part):part);}
function setStepValueByPath(root,path,value){if(!path.length)return value;let cursor=root;for(let i=0;i<path.length-1;i+=1){const key=path[i],nextKey=path[i+1];if(Array.isArray(cursor)&&typeof key==='number'){while(cursor.length<=key)cursor.push(typeof nextKey==='number'?[]:{});if(cursor[key]===null||cursor[key]===undefined)cursor[key]=typeof nextKey==='number'?[]:{};cursor=cursor[key];continue;}if(cursor[key]===undefined||cursor[key]===null){cursor[key]=typeof nextKey==='number'?[]:{};}cursor=cursor[key];}const finalKey=path[path.length-1];if(Array.isArray(cursor)&&typeof finalKey==='number'){while(cursor.length<finalKey)cursor.push(null);while(cursor.length<=finalKey)cursor.push('');cursor[finalKey]=value;return root;}cursor[finalKey]=value;return root;}
function updateStepEditorValue(stepKey,pathText,kind,rawValue){if(stepDraftBookId!==bookId)resetStepDraftCache(bookId);const basePayload=stepPayloadFromBook(currentBook,stepKey);const state=ensureStepObject(stepKey,basePayload);const path=parseStepPath(pathText);let value=rawValue;if(kind==='string_array'){value=normalizeMultiline(rawValue).split('\n').map(item=>item.trim()).filter(Boolean);}else if(kind==='number'){const trimmed=String(rawValue??'').trim();value=trimmed===''?'':Number(trimmed);}else if(kind==='boolean'){value=!!rawValue;}setStepValueByPath(state,path,value);stepDrafts[stepKey]=JSON.stringify(state,null,2);stepDraftDirty[stepKey]=true;}
function characterKey(item,index){const name=String(item?.name||'').trim();if(name)return `name:${name}`;const role=String(item?.role||'').trim();if(role)return `role:${role}:${index}`;return `index:${index}`;}
function summarizeStep3Diff(oldChars,newChars){const safeOld=Array.isArray(oldChars)?oldChars.filter(x=>x&&typeof x==='object'):[];const safeNew=Array.isArray(newChars)?newChars.filter(x=>x&&typeof x==='object'):[];const oldMap=new Map();safeOld.forEach((item,index)=>oldMap.set(characterKey(item,index),item));const newMap=new Map();safeNew.forEach((item,index)=>newMap.set(characterKey(item,index),item));const removed=[];const added=[];let changed=0;for(const [k,v] of oldMap.entries()){if(!newMap.has(k)){removed.push(String(v?.name||v?.role||k));continue;}if(JSON.stringify(v)!==JSON.stringify(newMap.get(k)))changed+=1;}for(const [k,v] of newMap.entries()){if(!oldMap.has(k))added.push(String(v?.name||v?.role||k));}return{oldCount:safeOld.length,newCount:safeNew.length,removed,added,changed};}
function step3DiffConfirmMessage(diff){const cap=(arr)=>arr.slice(0,5).join('、');let msg=`即将保存角色卡\n原有：${diff.oldCount} 个\n当前：${diff.newCount} 个\n修改：${diff.changed} 个\n新增：${diff.added.length} 个\n删除：${diff.removed.length} 个`;if(diff.added.length)msg+=`\n新增示例：${cap(diff.added)}${diff.added.length>5?' …':''}`;if(diff.removed.length)msg+=`\n删除示例：${cap(diff.removed)}${diff.removed.length>5?' …':''}`;msg+='\n\n确认保存吗？';return msg;}
function stepArrayItemTitle(stepKey,path,item,index){
  const fallback=`${stepFieldLabel(String(path[path.length-1]||'item'))} ${index+1}`;
  if(!(item&&typeof item==='object'))return fallback;
  if(stepKey==='step_4'&&path.length===1&&String(path[0])==='event_timeline'){
    const timeLabel=String(item.time_label||'').trim()||'未标注时间';
    const title=String(item.title||'').trim()||'未命名事件';
    return `${timeLabel}：${title}`;
  }
  if(stepKey==='step_5'){
    const tail=String(path[path.length-1]||'');
    if(path.length===1&&String(path[0])==='character_milestones'){
      return String(item.character_name||'未命名角色').trim()||`角色 ${index+1}`;
    }
    if(tail==='axes'){
      return String(item.axis||'未命名线').trim()||`线 ${index+1}`;
    }
    if(tail==='phases'){
      const phaseNo=String(item.phase||'').trim();
      const label=String(item.label||'').trim();
      return `${phaseNo?`阶段${phaseNo}`:`阶段${index+1}`}${label?`：${label}`:''}`;
    }
  }
  if(stepKey==='step_6'&&path.length===1&&String(path[0])==='twist_designs'){
    return String(item.title||'').trim()||`反转设计 ${index+1}`;
  }
  if(stepKey==='step_7'&&path.length===1&&String(path[0])==='story_lines'){
    const name=String(item.name||'').trim();
    if(name)return name;
    const visibility=String(item.visibility||'').trim();
    return visibility?`${visibility} ${index+1}`:`明线暗线 ${index+1}`;
  }
  if(stepKey==='step_8'&&path.length===1&&String(path[0])==='chapter_briefs'){
    const chapterId=String(item.chapter_id||'').trim()||`ch_${String(index+1).padStart(3,'0')}`;
    const title=String(item.title||'').trim();
    return title?`${chapterId} · ${title}`:chapterId;
  }
  return fallback;
}
function renderStepEditorField(stepKey,path,value){
  const pathText=path.join('.');
  if(
    stepKey==='step_5' &&
    Array.isArray(value) &&
    String(path[path.length-1]||'')==='phases'
  ){
    if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    return `<div class='step-inline-stack'>${value.map((phase,phaseIndex)=>{
      const phaseNo=String(phase?.phase||'').trim();
      const phaseLabel=String(phase?.label||'').trim();
      const scenes=Array.isArray(phase?.scenes)?phase.scenes:[];
      const blockLines=[`${phaseNo?`阶段${phaseNo}`:`阶段${phaseIndex+1}`}${phaseLabel?`：${phaseLabel}`:''}`];
      scenes.forEach((scene)=>{
        const title=String(scene?.title||'未命名场景').trim();
        const trigger=String(scene?.trigger||'').trim();
        const psychology=String(scene?.psychology||'').trim();
        const outcome=String(scene?.outcome||'').trim();
        blockLines.push(`• ${title}`);
        if(trigger)blockLines.push(`  - 触发：${trigger}`);
        if(psychology)blockLines.push(`  - 心理：${psychology}`);
        if(outcome)blockLines.push(`  - 结果：${outcome}`);
      });
      return `<div class='step-inline-card'><div class='pre'>${esc(blockLines.join('\n'))}</div></div>`;
    }).join('')}</div>`;
  }
  if(Array.isArray(value)){
    if(!value.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    if(stepKey==='step_8'&&path.length===1&&String(path[0])==='chapter_briefs'){
      return `<div class='step-inline-stack'>${value.map((item,index)=>{
        const detailKey=`inline:${stepKey}:${[...path,index].join('.')}`;
        const title=stepArrayItemTitle(stepKey,path,item,index);
        const toolbar=`<div style='display:flex;justify-content:flex-end;gap:8px;padding:8px 0 0 0'><button class='ghost' onclick='event.stopPropagation();saveSingleChapterBrief(${index})'>保存</button><button class='ghost' onclick='event.stopPropagation();reviseSingleChapterBriefByInstruction(${index})'>指令调整</button><button class='ghost' onclick='event.stopPropagation();deleteSingleChapterBrief(${index})'>删除</button></div>`;
        return `<details class='step-inline-card' data-detail-key='${esc(detailKey)}' ${isDetailOpen(detailKey,false)?'open':''} ontoggle="toggleDetailState('${esc(detailKey)}', this.open)"><summary class='step-inline-card-title'>${esc(title)}</summary>${toolbar}${renderStepEditorField(stepKey,[...path,index],item)}</details>`;
      }).join('')}</div>`;
    }
    const primitiveArray=value.every(item=>item===null||['string','number','boolean'].includes(typeof item));
    if(primitiveArray){
      return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string_array', this.value)">${esc(value.map(item=>String(item??'')).join('\n'))}</textarea>`;
    }
    return `<div class='step-inline-stack'>${value.map((item,index)=>{
      const detailKey=`inline:${stepKey}:${[...path,index].join('.')}`;
      const defaultOpen = stepKey==='step_5';
      return `<details class='step-inline-card' data-detail-key='${esc(detailKey)}' ${isDetailOpen(detailKey,defaultOpen)?'open':''} ontoggle="toggleDetailState('${esc(detailKey)}', this.open)"><summary class='step-inline-card-title'>${esc(stepArrayItemTitle(stepKey,path,item,index))}</summary>${renderStepEditorField(stepKey,[...path,index],item)}</details>`;
    }).join('')}</div>`;
  }
  if(value&&typeof value==='object'){
    if(
      stepKey==='step_5' &&
      path.length===2 &&
      String(path[0])==='character_milestones' &&
      typeof path[1]==='number'
    ){
      const axesVal=Array.isArray(value.axes)?value.axes:[];
      return `<div class='step-inline-root'><div class='step-inline-field'><label>axes</label>${renderStepEditorField(stepKey,[...path,'axes'],axesVal)}</div></div>`;
    }
    if(
      stepKey==='step_5' &&
      path.length===4 &&
      String(path[0])==='character_milestones' &&
      String(path[2])==='axes' &&
      typeof path[1]==='number' &&
      typeof path[3]==='number'
    ){
      const phasesVal=Array.isArray(value.phases)?value.phases:[];
      return `<div class='step-inline-root'><div class='step-inline-field'><label>phases</label>${renderStepEditorField(stepKey,[...path,'phases'],phasesVal)}</div></div>`;
    }
    const entries=orderedStepObjectEntries(stepKey,path,value);
    if(!entries.length)return `<div class='step-inline-empty'>当前为空。</div>`;
    return `<div class='step-inline-root'>${entries.map(([key,val])=>`<div class='step-inline-field'><label>${esc(stepFieldLabel(key))}</label>${renderStepEditorField(stepKey,[...path,key],val)}</div>`).join('')}</div>`;
  }
  if(typeof value==='number'){
    return `<input class='step-inline-input' type='number' value='${esc(value)}' oninput="updateStepEditorValue('${stepKey}','${pathText}','number', this.value)" />`;
  }
  if(typeof value==='boolean'){
    return `<label class='row'><input type='checkbox' ${value?'checked':''} onchange="updateStepEditorValue('${stepKey}','${pathText}','boolean', this.checked)" /> ${value?'是':'否'}</label>`;
  }
  return `<textarea class='step-inline-textarea' oninput="updateStepEditorValue('${stepKey}','${pathText}','string', this.value)">${esc(value??'')}</textarea>`;
}
function renderStepEditor(stepKey,stepTitle,payloadObj){const notes=Array.isArray(stepReviewNotes[stepKey])?stepReviewNotes[stepKey]:[];const state=ensureStepObject(stepKey,payloadObj);return `<div class='step-editor'><div class='step-editor-toolbar'><div class='step-editor-title'>${esc(stepTitle)} 直接编辑</div><div class='step-editor-actions'><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button></div></div><div class='step-editor-body'>${notes.length?`<ul class='step-editor-notes'>${notes.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:`<div class='step-editor-empty'>可以直接在这个模块里改内容；按 Enter 会换行，点右上角“保存修改”才会真正写回。</div>`}${renderStepEditorField(stepKey,[],state)}<div class='step-editor-hint'>这里是当前步骤的结构化编辑区。质检修改和指令修改会先生成建议稿并回填到这里，确认后再保存。</div></div></div>`;}
function getStepPayloadText(stepKey,payloadObj){const state=ensureStepObject(stepKey,payloadObj);return JSON.stringify(state??{},null,2);}
async function saveConcept(){
  if(!bookId)return alert('请先选择一部小说。');
  const title=(document.getElementById('concept-title')?.value||'').trim();
  const query=normalizeMultiline(document.getElementById('concept-query')?.value||'');
  const user_topic=normalizeMultiline(document.getElementById('concept-user-topic')?.value||'');
  const style_request=normalizeMultiline(document.getElementById('concept-style-request')?.value||'');
  const assistant_persona_prompt=normalizeMultiline(document.getElementById('concept-assistant-persona')?.value||'');
  const total_word_target=(document.getElementById('concept-total-word-target')?.value||'').trim();
  const chapter_count_target=(document.getElementById('concept-chapter-count-target')?.value||'').trim();
  const chapter_word_target=(document.getElementById('concept-chapter-word-target')?.value||'').trim();
  const pace_notes=normalizeMultiline(document.getElementById('concept-pace-notes')?.value||'');
  const result=await api('/api/novels/update_concept',{
    method:'POST',
    body:JSON.stringify({
      mode,
      book_id:bookId,
      title,
      query,
      user_topic,
      style_request,
      assistant_persona_prompt,
      total_word_target,
      chapter_count_target,
      chapter_word_target,
      pace_notes
    })
  });
  if(!ensureOk(result))return;
  currentBook=result.book;
  renderInputPanel(currentBook);
  renderBlueprint(currentBook);
  renderText(currentBook);
  await loadNovels();
  alert('小说基础信息已保存。');
}
async function saveStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');if(stepKey==='step_3'){const draft=ensureStepObject('step_3',stepPayloadFromBook(currentBook,'step_3'));const sanitized=sanitizeStep3DraftObject(draft||{});stepDraftObjects['step_3']=sanitized||{};stepDrafts['step_3']=JSON.stringify(stepDraftObjects['step_3'],null,2);const oldChars=Array.isArray(currentBook?.characters)?currentBook.characters:[];const newChars=Array.isArray(stepDraftObjects['step_3']?.characters)?stepDraftObjects['step_3'].characters:[];const diff=summarizeStep3Diff(oldChars,newChars);if(diff.changed>0||diff.added.length>0||diff.removed.length>0||diff.oldCount!==diff.newCount){if(!confirm(step3DiffConfirmMessage(diff)))return;}}const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));const result=await api('/api/novels/save_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text})});if(!ensureOk(result))return;currentBook=result.book;markStepDraftSaved(stepKey,result.step_payload||stepPayloadFromBook(result.book,stepKey),stepReviewNotes[stepKey]||[]);renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();alert('当前步骤修改已保存。');}
function clearStepDraft(stepKey){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认清空当前步骤草稿？该操作不会立即写库，需点击保存才生效。'))return;const empty=emptyStepPayload(stepKey);stepDraftObjects[stepKey]=deepClone(empty);stepDrafts[stepKey]=JSON.stringify(empty,null,2);stepDraftDirty[stepKey]=true;if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
async function reviseStepDraft(stepKey,revisionMode){if(!bookId)return alert('请先选择一部小说。');const payload_text=getStepPayloadText(stepKey,stepPayloadFromBook(currentBook,stepKey));let guidance='';if(revisionMode==='instruction'){guidance=prompt('描述你希望这一步结果怎么改：');if(!guidance)return;}const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:stepKey,payload_text,revision_mode:revisionMode,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:stepKey,revision_mode:revisionMode,payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};const taskLabel=`${stepKey.toUpperCase()} ${revisionMode==='review'?'质检修改':'指令修改'}`;runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:taskLabel,pending_message:revisionMode==='review'?'步骤质检修改已启动。':'步骤指令修改已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addCharacterByInstruction(){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述新角色需求（身份、作用、和谁形成关系）：');if(!extra)return;const guidance=`仅新增 1 个角色，不要改写已有角色；新角色要与现有核心角色形成明确关系并推动后续剧情。
用户要求：${extra}`;const r=await api('/api/novels/add_character',{method:'POST',body:JSON.stringify({mode,book_id:bookId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision=null;expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:'步骤3 增加角色',pending_message:'新增角色任务已启动（仅追加新角色，不重算整包）。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function addMilestoneLine(){if(!bookId)return alert('请先选择一部小说。');const guidance=String(prompt('描述新增角色发展线需求（角色名、线名、阶段重点）：')||'').trim();if(!guidance)return;const r=await api('/api/novels/add_character_milestone',{method:'POST',body:JSON.stringify({mode,book_id:bookId,guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_5',revision_mode:'instruction',payload_text:'',guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:'步骤5 增加角色发展线',pending_message:'新增角色发展线任务已启动。'},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleCharacterByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_3',stepPayloadFromBook(currentBook,'step_3'));const r=await api('/api/novels/revise_single_character_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_3',revision_mode:'instruction',payload_text,guidance:extra};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤3 单角色指令修改（角色 ${index+1}）`,pending_message:`角色 ${index+1} 指令修改任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function reviseSingleMilestoneByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const extra=prompt('描述你希望这个角色发展线如何调整：');if(!extra)return;const payload_text=getStepPayloadText('step_5',stepPayloadFromBook(currentBook,'step_5'));const r=await api('/api/novels/revise_single_character_milestone_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,payload_text,character_index:index,guidance:extra})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_5',revision_mode:'instruction',payload_text,guidance:extra};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤5 单角色发展线指令调整（角色 ${index+1}）`,pending_message:`角色 ${index+1} 发展线指令调整任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
async function saveSingleChapterBrief(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];if(index<0||index>=plans.length)return alert('章节索引无效。');await saveStepDraft('step_8');}
async function reviseSingleChapterBriefByInstruction(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];const target=plans[index]||{};const chapterId=String(target?.chapter_id||'').trim()||`第${index+1}章`;const chapterTitle=String(target?.title||'').trim();const extra=prompt(`描述你希望如何调整 ${chapterTitle?`《${chapterTitle}》`:chapterId} 的章节摘要：`);if(!extra)return;const payload_text=getStepPayloadText('step_8',step8);const guidance=`只调整 chapter_briefs 中第 ${index+1} 条（chapter_id=${chapterId}${chapterTitle?`, title=${chapterTitle}`:''}），其他章节保持不变。
用户要求：${extra}`;const r=await api('/api/novels/revise_step_result_run',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:'step_8',payload_text,revision_mode:'instruction',guidance})});if(!ensureOk(r))return;pendingRunId=r.run_id||'';pendingStepRevision={run_id:pendingRunId,step_key:'step_8',revision_mode:'instruction',payload_text,guidance};expandedRuns.add(pendingRunId);boxStates={};runsCache=[{run_id:pendingRunId,is_running:true,stage:'planning',updated_at:new Date().toISOString(),task_label:`步骤8 单章指令调整（第 ${index+1} 章）`,pending_message:`第 ${index+1} 章指令调整任务已启动。`},...runsCache.filter(x=>x.run_id!==pendingRunId)];await renderRuns();updateStopButton();}
function deleteSingleChapterBrief(index){if(!bookId)return alert('请先选择一部小说。');const step8=stepPayloadFromBook(currentBook,'step_8');const plans=Array.isArray(step8?.chapter_briefs)?step8.chapter_briefs:[];if(index<0||index>=plans.length)return alert('章节索引无效。');const target=plans[index]||{};const label=String(target?.title||target?.chapter_id||`第${index+1}章`);if(!confirm(`确认删除章节摘要：${label}？`))return;const draft=ensureStepObject('step_8',step8);if(!Array.isArray(draft.chapter_briefs))draft.chapter_briefs=[];draft.chapter_briefs.splice(index,1);stepDraftObjects['step_8']=draft;stepDrafts['step_8']=JSON.stringify(draft,null,2);stepDraftDirty['step_8']=true;if(currentBook){renderBlueprint(currentBook);autoSizeTextareas('pnl-blueprint');}}
function toggleButtons(){const t=mode==='test';btnNew.style.display=t?'none':'inline-block';btnStep1.style.display=t?'none':'inline-block';btnStep2.style.display=t?'none':'inline-block';btnStep3.style.display=t?'none':'inline-block';btnStep4.style.display=t?'none':'inline-block';btnStep5.style.display=t?'none':'inline-block';btnStep6.style.display=t?'none':'inline-block';btnStep7.style.display=t?'none':'inline-block';btnStep8.style.display=t?'none':'inline-block';btnBlueprintReview.style.display=t?'none':'inline-block';btnContinue.style.display=t?'none':'inline-block';btnBlueprint.style.display=t?'inline-block':'none';btnWrite.style.display=t?'inline-block':'none';btnCritique.style.display=t?'inline-block':'none';btnPatch.style.display=t?'inline-block':'none';}
function updateStopButton(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);btnStop.style.display=a?'inline-block':'none';}
async function loadNovels(){const novels=await api('/api/novels?mode='+mode);novelSel.innerHTML="<option value=''>选择小说</option>";novels.forEach(n=>{const o=document.createElement('option');o.value=n.book_id;o.textContent=n.title||n.book_id;novelSel.appendChild(o);});if(bookId)novelSel.value=bookId;}
async function loadRuns(){if(!bookId){runsCache=pendingRunId?[{run_id:pendingRunId,is_running:true,stage:'writing',updated_at:new Date().toISOString(),pending_message:'运行已启动，正在准备请求模型。'}]:[];return renderRuns();}runsCache=await api(`/api/runs?mode=${mode}&book_id=${bookId}`);const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();}
function renderEmptyRightPanels(){document.getElementById('pnl-input').innerHTML="<div class='empty'>等待加载用户输入</div>";document.getElementById('pnl-blueprint').innerHTML="<div class='empty'>等待加载小说信息</div>";document.getElementById('pnl-text').innerHTML="<div class='empty'>等待加载小说正文</div>";document.getElementById('pnl-critic').innerHTML="<div class='empty'>等待加载评价结果</div>";showTab('input');}
async function changeMode(){mode=modeSel.value;bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();boxStates={};lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};resetStepDraftCache('');evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';toggleButtons();updateStopButton();await loadNovels();}
async function selectNovel(id){bookId=id;currentBook=null;pendingRunId='';pendingStepRevision=null;expandedRuns=new Set();boxStates={};lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};resetStepDraftCache(id||'');if(!bookId){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';updateStopButton();return;}await refreshNovel();}
async function refreshNovel(){if(!bookId)return;const d=await api(`/api/novel?mode=${mode}&book_id=${bookId}`);if(!d.book)return;if(stepDraftBookId!==d.book.id)resetStepDraftCache(d.book.id);const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);const scrollState=captureScrollState();currentBook=d.book;lastLivePreviewKey='';const rightRenderKey=[String(d.book?.id||''),String(d.book?.updated_at||''),String(d.latest_run_id||''),String(d.latest_stage||''),String(d.critic?.report_id||d.critic?.created_at||''),String(d.blueprint_review?.summary||'')].join('|');if(!editingInRight&&rightRenderKey!==lastRightRenderKey){snapshotPanelDetailStates('pnl-input');snapshotPanelDetailStates('pnl-blueprint');snapshotPanelDetailStates('pnl-text');snapshotPanelDetailStates('pnl-critic');renderInputPanel(d.book);renderBlueprint(d.book,d.blueprint_review);renderText(d.book,null);renderCritic(d.critic);lastRightRenderKey=rightRenderKey;}stagePill.textContent=stageText(d.latest_stage);runsCache=d.runs||[];const c=runsCache.find(x=>x.is_running)||runsCache[0];if(c)expandedRuns.add(c.run_id);await renderRuns();updateStopButton();await loadNovels();restoreScrollState(scrollState);}
async function refreshPendingRun(){if(!pendingRunId)return;const trackedRunId=pendingRunId;const prev=runsCache.find(x=>x.run_id===trackedRunId)||{};const d=await api(`/api/run?mode=${mode}&run_id=${trackedRunId}`);const scrollState=captureScrollState();const editingInRight=!!document.activeElement&&document.getElementById('right')?.contains(document.activeElement)&&isEditingElement(document.activeElement);stagePill.textContent=stageText(d.stage||'writing');const running=d.is_running!==false;if(running){runsCache=[{run_id:trackedRunId,is_running:true,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),task_label:prev.task_label||'',pending_message:'运行中，等待模型返回更多内容。'},...runsCache.filter(x=>x.run_id!==trackedRunId)];expandedRuns.add(trackedRunId);if(currentBook&&d.chapter_preview){const previewKey=JSON.stringify(d.chapter_preview||null);if(!editingInRight&&previewKey!==lastLivePreviewKey){snapshotPanelDetailStates('pnl-text');renderText(currentBook,d.chapter_preview,d);lastLivePreviewKey=previewKey;}}await renderRuns({[trackedRunId]:d});updateStopButton();restoreScrollState(scrollState);return;}let revisionPayload=latestOutputByType(d,'step_revision_draft');const completedRevision=pendingStepRevision&&pendingStepRevision.run_id===trackedRunId?pendingStepRevision:null;pendingRunId='';pendingStepRevision=null;lastLivePreviewKey='';delete runActiveItemKeys[trackedRunId];if(!revisionPayload&&completedRevision&&completedRevision.step_key&&completedRevision.payload_text){const fallback=await api('/api/novels/revise_step_result',{method:'POST',body:JSON.stringify({mode,book_id:bookId,step_key:completedRevision.step_key,payload_text:completedRevision.payload_text,revision_mode:completedRevision.revision_mode||'instruction',guidance:completedRevision.guidance||''})});if(ensureOk(fallback)){revisionPayload=fallback;}}if(revisionPayload)applyStepRevisionDraft(revisionPayload);if(d.current_book_id){bookId=d.current_book_id;novelSel.value=bookId;await refreshNovel();if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}return;}runsCache=[{run_id:trackedRunId,is_running:false,stage:d.stage,updated_at:d.updated_at||new Date().toISOString(),task_label:prev.task_label||'',pending_message:'运行已结束，查看下方最新事件。'}];expandedRuns.add(trackedRunId);await renderRuns({[trackedRunId]:d});updateStopButton();restoreScrollState(scrollState);if(completedRevision){if(revisionPayload)alert(completedRevision.revision_mode==='review'?'已生成质检后的建议稿，请确认后再点保存修改。':'已按你的指令生成建议稿，请确认后再点保存修改。');else alert('修改任务已结束，但没有返回建议稿，请查看左侧运行记录。');}}
function boxHtml(key,title,payloadHtml,isOpen,extraClass=''){const klass=['box',extraClass].filter(Boolean).join(' ');return `<details class='${klass}' ${isOpen?'open':''} ontoggle="toggleBox('${key}', this.open)"><summary><span class='title'>${title}</span></summary><div class='payload'>${payloadHtml}</div></details>`}
function toggleBox(key,isOpen){boxStates[key]=isOpen;}
const toArray=v=>Array.isArray(v)?v.filter(Boolean):[];
const jsonHtml=v=>`<div class='pre json'>${esc(JSON.stringify(v??{},null,2))}</div>`;
const chipsHtml=v=>{const items=toArray(v);return items.length?`<div class='chips'>${items.map(item=>`<span class='chip'>${esc(item)}</span>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
const linesHtml=v=>{const items=toArray(v);return items.length?`<div class='mini-list'>${items.map(item=>`<div class='mini-item'>${esc(item)}</div>`).join('')}</div>`:`<div class='muted'>鏆傛棤</div>`};
function infoRow(label,value){if(value===undefined||value===null||value==='')return '';return `<div class='kv'><div class='k'>${esc(label)}</div><div>${esc(value)}</div></div>`}
function sectionHtml(label,body){return `<div class='subsec'>${esc(label)}</div>${body}`}
function renderBlockCards(blocks,options={}){
  const arr=Array.isArray(blocks)?blocks:[];
  const label=String(options?.label||'内容块');
  const highlightSet=new Set((Array.isArray(options?.highlightIds)?options.highlightIds:[]).map(item=>String(item||'').trim()).filter(Boolean));
  return arr.map((block,index)=>{
    const purpose=String(block?.purpose||'').trim();
    const blockId=String(block?.block_id||block?.id||'').trim();
    const endState=String(block?.end_state||block?.metadata?.end_state||'').trim();
    const status=String(block?.status||block?.metadata?.status||'').trim();
    const version=Number(block?.version||block?.metadata?.version||1);
    const blockIndex=Number(block?.block_index||index+1);
    const isPatched=highlightSet.has(blockId);
    const metaBits=[purpose,blockId].filter(Boolean).join(' · ');
    const badges=[];
    if(isPatched)badges.push("<span class='block-badge patched'>本轮已更新</span>");
    if(status)badges.push(`<span class='block-badge status'>${esc(status)}</span>`);
    if(Number.isFinite(version))badges.push(`<span class='block-badge status'>v${Number(version)}</span>`);
    return `<div class='block ${isPatched?'patched':''}'><div class='row'><strong>${esc(label)} ${blockIndex}</strong>${metaBits?` <span class='muted'>${esc(metaBits)}</span>`:''}</div>${endState?`<div class='muted' style='margin-top:4px'>落点：${esc(endState)}</div>`:''}${badges.length?`<div class='block-badges'>${badges.join('')}</div>`:''}<div style='margin-top:6px'>${esc(block?.text||'')}</div></div>`;
  }).join('')||"<div class='relationship-empty'>暂无内容块</div>";
}
function renderCharacterMindsetsBlock(characterMindsets){
  const items=(Array.isArray(characterMindsets)?characterMindsets:[]).filter(item=>item&&typeof item==='object');
  if(!items.length)return '';
  const renderAttitudes=(attitudes)=>{
    const rows=Object.entries(attitudes&&typeof attitudes==='object'?attitudes:{}).filter(([key,value])=>String(key||'').trim()&&String(value||'').trim());
    return rows.length
      ? `<div class='mini-list'>${rows.map(([key,value])=>`<div class='mini-item'><strong>${esc(key)}</strong>：${esc(value)}</div>`).join('')}</div>`
      : "<div class='relationship-empty'>暂无关键他人态度</div>";
  };
  const cards=items.map((item,index)=>{
    const title=String(item?.character_name||item?.character_id||`角色 ${index+1}`).trim()||`角色 ${index+1}`;
    const emotionSummary=[String(item?.surface_emotion||'').trim(),String(item?.core_emotion||'').trim()].filter(Boolean).join(' / ')||'暂无情绪摘要';
    return `<div style='border:1px solid #2a3447;border-radius:12px;padding:12px;background:#0d1420'>
      <div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'>
        <div>
          <div class='subsec'>${esc(title)}</div>
          <div class='muted'>${esc(emotionSummary)}</div>
        </div>
        <span class='block-badge status'>${esc(item?.self_control_level||'medium')}</span>
      </div>
      ${infoRow('表层情绪', item?.surface_emotion||'')}
      ${infoRow('核心情绪', item?.core_emotion||'')}
      ${infoRow('主要目标', item?.primary_goal||'')}
      ${infoRow('隐藏需求', item?.hidden_need||'')}
      ${infoRow('恐惧', item?.fear||'')}
      ${infoRow('临界点提示', item?.breaking_point_hint||'')}
      ${infoRow('知道但未说', item?.known_but_unspoken||'')}
      ${infoRow('误判', item?.misbelief||'')}
      ${infoRow('本章变化提示', item?.chapter_change_hint||'')}
      <div class='subsec' style='margin-top:10px'>关键他人态度</div>
      ${renderAttitudes(item?.attitude_to_key_others)}
    </div>`;
  }).join('');
  return `<div class='relationship-card'><div class='subsec'>角色心智</div><div class='task-note'>仅维护本章前两个角色的章节心智，和章节本身绑定展示。</div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:12px'>${cards}</div></div>`;
}
function renderChapterDraftTask(payload){
  const preview=payload?.draft_preview&&typeof payload.draft_preview==='object'?payload.draft_preview:{};
  const finalText=String(preview?.final_text||'').trim();
  const contentBlocks=Array.isArray(preview?.content_blocks)?preview.content_blocks:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||preview?.chapter_id||'');
  html+=infoRow('阶段', '整章首稿');
  if(finalText)html+=sectionHtml('整章手稿', `<div class='subbox pre'>${esc(finalText)}</div>`);
  if(contentBlocks.length)html+=sectionHtml('首稿 block 视图', `<div class='mini-list'>${renderBlockCards(contentBlocks,{label:'内容块'})}</div>`);
  html+="</div>";
  return html;
}
function renderChapterReviewBundle(payload){
  const reviews=Array.isArray(payload?.reviews)?payload.reviews:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(!reviews.length){html+="<div class='muted'>暂无 review 输出</div></div>";return html;}
  html+=sectionHtml('Review 输出', `<div class='mini-list'>${reviews.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.tool_name||'review')}</div>${reviewReportSummaryHtml(String(item?.tool_name||'review'),item?.tool_result||{})}<div style='margin-top:8px'>${jsonHtml(item?.tool_result||{})}</div></div>`).join('')}</div>`);
  html+="</div>";
  return html;
}
function renderChapterPatchPlanTask(payload){
  const patchPlan=payload?.patch_plan&&typeof payload.patch_plan==='object'?payload.patch_plan:{};
  const patchTargets=Array.isArray(patchPlan?.patch_targets)?patchPlan.patch_targets:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=sectionHtml('Patch 目标', patchTargets.length?`<div class='mini-list'>${patchTargets.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.target_id||'未命中 block')}</div>${infoRow('问题类型', item?.problem_type||'')}${infoRow('修补目标', item?.goal||'')}${toArray(item?.instructions).length?sectionHtml('执行指令', linesHtml(item.instructions)):''}${toArray(item?.local_context_needed).length?sectionHtml('局部上下文', chipsHtml(item.local_context_needed)):''}</div>`).join('')}</div>`:"<div class='muted'>暂无 patch 目标</div>");
  if(toArray(patchPlan?.unchanged_blocks).length)html+=sectionHtml('保持不动的 block', chipsHtml(patchPlan.unchanged_blocks));
  if(toArray(patchPlan?.global_constraints).length)html+=sectionHtml('全局约束', linesHtml(patchPlan.global_constraints));
  html+="</div>";
  return html;
}
function renderChapterPatchRewriteTask(payload){
  const rewriteResult=payload?.rewrite_result&&typeof payload.rewrite_result==='object'?payload.rewrite_result:{};
  const patchedBlocks=Array.isArray(rewriteResult?.patched_blocks)?rewriteResult.patched_blocks:[];
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=sectionHtml('修改后的 block', patchedBlocks.length?`<div class='mini-list'>${patchedBlocks.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.block_id||'未命名 block')}</div>${item?.old_summary?infoRow('修改前摘要', item.old_summary):''}<div class='subbox pre'>${esc(item?.new_text||'')}</div></div>`).join('')}</div>`:"<div class='muted'>暂无 block 改写结果</div>");
  if(toArray(rewriteResult?.patch_report).length)html+=sectionHtml('Patch 报告', `<div class='mini-list'>${rewriteResult.patch_report.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.block_id||'未命名 block')}</div>${infoRow('是否应用', item?.applied?'是':'否')}${infoRow('说明', item?.notes||'')}</div>`).join('')}</div>`);
  if(String(rewriteResult?.merged_chapter_text||'').trim())html+=sectionHtml('当前拼接正文', `<div class='subbox pre'>${esc(rewriteResult.merged_chapter_text)}</div>`);
  html+="</div>";
  return html;
}
function renderChapterPatchJudgeTask(payload){
  const judgeResult=payload?.judge_result&&typeof payload.judge_result==='object'?payload.judge_result:{};
  const finalJudge=payload?.final_judge&&typeof payload.final_judge==='object'?payload.final_judge:{};
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload?.chapter_id||'');
  if(Number.isFinite(Number(payload?.patch_round))&&Number(payload.patch_round)>0)html+=infoRow('轮次', `第 ${Number(payload.patch_round)} 轮`);
  html+=infoRow('Judge 结论', judgeResult?.pass||judgeResult?.passed?'通过':'未通过');
  if(toArray(judgeResult?.remaining_issues).length)html+=sectionHtml('未修干净的问题', `<div class='mini-list'>${judgeResult.remaining_issues.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.problem_type||'问题')}</div>${toArray(item?.target_blocks).length?sectionHtml('命中 block', chipsHtml(item.target_blocks)):''}${infoRow('原因', item?.reason||'')}</div>`).join('')}</div>`);
  if(toArray(judgeResult?.newly_introduced_issues).length)html+=sectionHtml('新引入的问题', `<div class='mini-list'>${judgeResult.newly_introduced_issues.map(item=>`<div class='mini-item'><div class='mini-title'>${esc(item?.problem_type||'问题')}</div>${toArray(item?.target_blocks).length?sectionHtml('命中 block', chipsHtml(item.target_blocks)):''}${infoRow('原因', item?.reason||'')}</div>`).join('')}</div>`);
  if(judgeResult?.recommendation)html+=sectionHtml('建议', `<div class='task-note'>${esc(judgeResult.recommendation)}</div>`);
  if(finalJudge&&Object.keys(finalJudge).length)html+=sectionHtml('闭环判断', jsonHtml(finalJudge));
  html+="</div>";
  return html;
}
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
function reviewReportSummaryHtml(toolName,report){
  if(!report||typeof report!=='object')return "<div class='muted'>暂无结果</div>";
  const level=String(report.level||'').trim();
  const issues=toArray(report.issues);
  const metrics=[];
  if(typeof report.passed==='boolean')metrics.push(`passed=${report.passed?'yes':'no'}`);
  if(level)metrics.push(`level=${level}`);
  if(Number.isFinite(Number(report.prose_score)))metrics.push(`prose=${Number(report.prose_score)}`);
  if(Number.isFinite(Number(report.tension_score)))metrics.push(`tension=${Number(report.tension_score)}`);
  if(Number.isFinite(Number(report.exposition_score)))metrics.push(`exposition=${Number(report.exposition_score)}`);
  let html=`<div class='mini-item'><div class='mini-title'>${esc(toolName)}</div>`;
  if(metrics.length)html+=`<div class='muted'>${esc(metrics.join(' | '))}</div>`;
  if(issues.length)html+=`<div style='margin-top:6px'>${linesHtml(issues.slice(0,6))}</div>`;
  if(report.rewrite_guidance)html+=`<div class='subbox pre' style='margin-top:6px'>${esc(report.rewrite_guidance)}</div>`;
  html+='</div>';
  return html;
}
function renderActualChapterSummary(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('章节', payload&&payload.chapter_id||'');
  html+=sectionHtml('实际发生', linesHtml(payload&&payload.actual_events));
  html+=sectionHtml('读者现在知道', linesHtml(payload&&payload.reader_now_knows));
  html+=sectionHtml('读者现在相信', linesHtml(payload&&payload.reader_now_believes));
  html+=sectionHtml('未解问题', linesHtml(payload&&payload.open_questions));
  html+=sectionHtml('角色状态', linesHtml(payload&&payload.character_states));
  html+=sectionHtml('关系状态', linesHtml(payload&&payload.relationship_state));
  html+=sectionHtml('已埋线索', linesHtml(payload&&payload.seeded_clues));
  html+=sectionHtml('仍锁住的真相', linesHtml(payload&&payload.locked_truths));
  html+="</div>";
  return html;
}
function renderChapterStageLog(payload){
  const chapterId=String(payload&&payload.chapter_id||'').trim();
  const stages=toArray(payload&&payload.stage_log);
  let html="<div class='agent-view'>";
  if(chapterId)html+=infoRow('章节', chapterId);
  if(!stages.length){html+="<div class='muted'>暂无 stage log</div></div>";return html;}
  html+=sectionHtml('正文闭环', `<div class='mini-list'>${stages.map((entry,index)=>{
    const stageName=String(entry&&entry.stage||`stage_${index+1}`);
    const skills=toArray(entry&&entry.skill_ids);
    const toolCalls=toArray(entry&&entry.tool_calls).map(item=>typeof item==='string'?item:String(item&&item.tool_name||'').trim()).filter(Boolean);
    const reviewReports=(entry&&typeof entry.review_reports==='object'&&entry.review_reports)?entry.review_reports:{};
    const finalJudge=(entry&&typeof entry.final_judge==='object'&&entry.final_judge)?entry.final_judge:null;
    const revisionPlan=(entry&&typeof entry.revision_plan==='object'&&entry.revision_plan)?entry.revision_plan:null;
    let block=`<div class='mini-item'><div class='mini-title'>WritingChapterAgent · ${esc(stageName)}</div>`;
    if(skills.length)block+=`<div style='margin-top:6px'>${chipsHtml(skills)}</div>`;
    if(toolCalls.length)block+=sectionHtml('Tool 调用', chipsHtml(toolCalls));
    if(Number.isFinite(Number(entry&&entry.chapter_length)))block+=infoRow('正文长度', `${Number(entry.chapter_length)} 字符`);
    if(entry&&entry.current_chapter_draft_tail)block+=sectionHtml('当前草稿尾部', `<div class='subbox pre'>${esc(entry.current_chapter_draft_tail)}</div>`);
    const reportEntries=Object.entries(reviewReports);
    if(reportEntries.length)block+=sectionHtml('Tool 输出', `<div class='mini-list'>${reportEntries.map(([toolName,report])=>reviewReportSummaryHtml(toolName,report)).join('')}</div>`);
    if(revisionPlan){
      block+=sectionHtml('修订计划', `<div class='mini-list'>${[
        revisionPlan.summary?`<div class='mini-item'><div class='mini-title'>摘要</div><div class='muted'>${esc(revisionPlan.summary)}</div></div>`:'',
        toArray(revisionPlan.must_fix).length?`<div class='mini-item'><div class='mini-title'>必须修</div>${linesHtml(revisionPlan.must_fix)}</div>`:'',
        toArray(revisionPlan.should_fix).length?`<div class='mini-item'><div class='mini-title'>建议修</div>${linesHtml(revisionPlan.should_fix)}</div>`:'',
        toArray(revisionPlan.keep).length?`<div class='mini-item'><div class='mini-title'>保留</div>${linesHtml(revisionPlan.keep)}</div>`:'',
        toArray(revisionPlan.hard_constraints).length?`<div class='mini-item'><div class='mini-title'>硬约束</div>${linesHtml(revisionPlan.hard_constraints)}</div>`:''
      ].filter(Boolean).join('')}</div>`);
    }
    if(finalJudge){
      const reasons=toArray(finalJudge.blocking_reasons);
      const metrics=finalJudge.metrics&&typeof finalJudge.metrics==='object'?finalJudge.metrics:{};
      block+=sectionHtml('Final Judge', `<div class='mini-list'>${[
        `<div class='mini-item'><div class='mini-title'>结论</div><div class='muted'>${esc(finalJudge.passed?'通过':'未通过')}</div></div>`,
        reasons.length?`<div class='mini-item'><div class='mini-title'>阻塞原因</div>${linesHtml(reasons)}</div>`:'',
        Object.keys(metrics).length?`<div class='mini-item'><div class='mini-title'>指标</div>${jsonHtml(metrics)}</div>`:''
      ].filter(Boolean).join('')}</div>`);
    }
    block+='</div>';
    return block;
  }).join('')}</div>`);
  html+="</div>";
  return html;
}
function renderStageEvent(payload){
  let html="<div class='agent-view'>";
  html+=infoRow('阶段', payload&&payload.stage||'');
  html+=infoRow('动作', payload&&payload.action||'');
  html+=infoRow('原因', payload&&payload.reason||'');
  if(payload&&payload.chapter_id)html+=infoRow('章节', payload.chapter_id);
  if(Number.isFinite(Number(payload&&payload.iteration)))html+=infoRow('轮次', `第 ${Number(payload.iteration)} 轮`);
  const contextKeys=toArray(payload&&payload.context_keys);
  const skillIds=toArray(payload&&payload.skill_ids);
  const toolCalls=toArray(payload&&payload.tool_calls).map(item=>typeof item==='string'?item:String(item&&item.tool_name||'').trim()).filter(Boolean);
  if(contextKeys.length)html+=sectionHtml('固定信息包', chipsHtml(contextKeys));
  if(skillIds.length)html+=sectionHtml('已加载 Skills', chipsHtml(skillIds));
  if(toolCalls.length)html+=sectionHtml('计划调用 Tools', chipsHtml(toolCalls));
  if(payload&&payload.tool_name)html+=infoRow('当前 Tool', payload.tool_name);
  if(Number.isFinite(Number(payload&&payload.chapter_length)))html+=infoRow('正文长度', `${Number(payload.chapter_length)} 字符`);
  if(payload&&payload.current_chapter_draft_tail)html+=sectionHtml('当前草稿尾部', `<div class='subbox pre'>${esc(payload.current_chapter_draft_tail)}</div>`);
  const toolResult=payload&&payload.tool_result&&typeof payload.tool_result==='object'?payload.tool_result:null;
  if(toolResult){
    html+=sectionHtml('Tool 输出', reviewReportSummaryHtml(String(payload&&payload.tool_name||'tool'), toolResult));
    html+=sectionHtml('Tool 输出详情', jsonHtml(toolResult));
  }
  const reviewReports=payload&&payload.review_reports&&typeof payload.review_reports==='object'?payload.review_reports:null;
  if(reviewReports&&Object.keys(reviewReports).length){
    html+=sectionHtml('本轮 Review 汇总', `<div class='mini-list'>${Object.entries(reviewReports).map(([toolName,report])=>reviewReportSummaryHtml(toolName,report)).join('')}</div>`);
  }
  const revisionPlan=payload&&payload.revision_plan&&typeof payload.revision_plan==='object'?payload.revision_plan:null;
  if(revisionPlan){
    html+=sectionHtml('修订计划', `<div class='mini-list'>${[
      revisionPlan.summary?`<div class='mini-item'><div class='mini-title'>摘要</div><div class='muted'>${esc(revisionPlan.summary)}</div></div>`:'',
      toArray(revisionPlan.must_fix).length?`<div class='mini-item'><div class='mini-title'>必须修</div>${linesHtml(revisionPlan.must_fix)}</div>`:'',
      toArray(revisionPlan.should_fix).length?`<div class='mini-item'><div class='mini-title'>建议修</div>${linesHtml(revisionPlan.should_fix)}</div>`:'',
      toArray(revisionPlan.keep).length?`<div class='mini-item'><div class='mini-title'>保留</div>${linesHtml(revisionPlan.keep)}</div>`:'',
      toArray(revisionPlan.hard_constraints).length?`<div class='mini-item'><div class='mini-title'>硬约束</div>${linesHtml(revisionPlan.hard_constraints)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  const finalJudge=payload&&payload.final_judge&&typeof payload.final_judge==='object'?payload.final_judge:null;
  if(finalJudge){
    const reasons=toArray(finalJudge.blocking_reasons);
    const metrics=finalJudge.metrics&&typeof finalJudge.metrics==='object'?finalJudge.metrics:{};
    html+=sectionHtml('Final Judge', `<div class='mini-list'>${[
      `<div class='mini-item'><div class='mini-title'>结论</div><div class='muted'>${esc(finalJudge.passed?'通过':'未通过')}</div></div>`,
      reasons.length?`<div class='mini-item'><div class='mini-title'>阻塞原因</div>${linesHtml(reasons)}</div>`:'',
      Object.keys(metrics).length?`<div class='mini-item'><div class='mini-title'>指标</div>${jsonHtml(metrics)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  const summary=payload&&payload.summary&&typeof payload.summary==='object'?payload.summary:null;
  if(summary){
    html+=sectionHtml('Actual Summary', `<div class='mini-list'>${[
      toArray(summary.actual_events).length?`<div class='mini-item'><div class='mini-title'>实际发生</div>${linesHtml(summary.actual_events)}</div>`:'',
      toArray(summary.reader_now_knows).length?`<div class='mini-item'><div class='mini-title'>读者现在知道</div>${linesHtml(summary.reader_now_knows)}</div>`:'',
      toArray(summary.reader_now_believes).length?`<div class='mini-item'><div class='mini-title'>读者现在相信</div>${linesHtml(summary.reader_now_believes)}</div>`:'',
      toArray(summary.seeded_clues).length?`<div class='mini-item'><div class='mini-title'>已埋线索</div>${linesHtml(summary.seeded_clues)}</div>`:'',
      toArray(summary.locked_truths).length?`<div class='mini-item'><div class='mini-title'>仍锁住的真相</div>${linesHtml(summary.locked_truths)}</div>`:''
    ].filter(Boolean).join('')}</div>`);
  }
  html+="</div>";
  return html;
}
function renderErrorEvent(payload){
  return `<div class='agent-view'>${infoRow('错误', payload&&payload.error||'未知错误')}</div>`;
}
function clipDisplayText(text,maxChars){
  const raw=String(text||'');
  if(!raw)return '';
  if(raw.length<=maxChars)return raw;
  return `[内容较长，仅展示最近 ${maxChars} 字]\n${raw.slice(-maxChars)}`;
}
function mergeStreamText(current,incoming){
  const prev=String(current||''),next=String(incoming||'');
  if(!next)return prev;
  if(!prev)return next;
  if(next.startsWith(prev))return next;
  if(prev.endsWith(next))return prev;
  return prev+next;
}
function summarizeStreamPrompt(prompt){
  const cleaned=String(prompt||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').trim();
  if(!cleaned)return '';
  return cleaned.length>160?`${cleaned.slice(0,160)}…`:cleaned;
}
function renderEmbeddedStreams(streamGroups){
  const groups=Array.isArray(streamGroups)?streamGroups.filter(Boolean):[];
  if(!groups.length)return '';
  return `<div class='stream-shell'>${groups.map((group,index)=>{
    const streamTitle=esc(group.agent||`模型调用 ${index+1}`);
    const streamStatus=group.done?'已完成':'流式输出中';
    const promptSummary=summarizeStreamPrompt(group.prompt||'');
    const streamText=clipDisplayText(group.displayText||group.reply||group.text||'',18000);
    return `<div class='stream-card ${group.done?'':'live'}'><div class='stream-meta'><div class='stream-title'>${streamTitle}</div><div class='stream-status'>${esc(streamStatus)}</div></div>${promptSummary?`<div class='stream-prompt'>${esc(promptSummary)}</div>`:''}${streamText?`<div class='stream-text'>${esc(streamText)}</div>`:`<div class='muted'>流式输出暂未返回内容</div>`}</div>`;
  }).join('')}</div>`;
}
function renderItemPayload(item){
  const streamHtml=renderEmbeddedStreams(item.streamGroups);
  let body='';
  if(item.kind==='output'&&item.outputType==='chapter_draft_task')body=renderChapterDraftTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_review_bundle')body=renderChapterReviewBundle(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_plan_task')body=renderChapterPatchPlanTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_rewrite_task')body=renderChapterPatchRewriteTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_patch_judge_task')body=renderChapterPatchJudgeTask(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='director_decision')body=renderDirectorDecision(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='reference_cards')body=renderReferenceCards(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='tool_observation')body=renderToolObservation(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='actual_chapter_summary')body=renderActualChapterSummary(item.rawPayload);
  else if(item.kind==='output'&&item.outputType==='chapter_stage_log')body=renderChapterStageLog(item.rawPayload);
  else if(item.kind==='event'&&item.eventType==='stage')body=renderStageEvent(item.rawPayload);
  else if(item.kind==='event'&&item.eventType==='error')body=renderErrorEvent(item.rawPayload);
  else if(item.kind==='plain'&&item.text)body=`<div class='pre'>${esc(item.text||'')}</div>`;
  else if(item.streamOnly)body='';
  else body=jsonHtml(item.rawPayload);
  if(item.streamOnly)return streamHtml||"<div class='muted'>等待模型返回内容</div>";
  return `${streamHtml}${body}`;
}
function sortTimelineItems(items){
  return items.sort((a,b)=>{
    const ta=String(a?.sortTs||''),tb=String(b?.sortTs||'');
    if(ta===tb)return String(a?.key||'').localeCompare(String(b?.key||''));
    return ta.localeCompare(tb);
  });
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
function collectStreamGroups(evts){
  const groups=[],byId={};let activeKey='',seq=0;
  function ensureGroup(callId,ts,agent){
    const key=callId||`legacy_${++seq}`;
    if(byId[key]){if(agent&&!byId[key].agent)byId[key].agent=agent;return byId[key];}
    const group={groupKey:key,prompt:'',text:'',reply:'',displayText:'',sortTs:ts||'',done:false,agent:agent||''};
    byId[key]=group;groups.push(group);return group;
  }
  evts.forEach(e=>{
    const payload=e.payload||{};
    const callId=String(payload.call_id||'').trim();
    if(e.event_type==='llm_prompt'){
      const group=ensureGroup(callId||`prompt_${e.id||++seq}`,e.ts,e.agent);
      group.prompt=String(payload.preview||'');
      group.sortTs=e.ts||group.sortTs;
      if(e.agent&&!group.agent)group.agent=e.agent;
      activeKey=group.groupKey;
      return;
    }
    if(e.event_type==='llm_stream'){
      const group=callId?ensureGroup(callId,e.ts,e.agent):(activeKey&&byId[activeKey]&&!byId[activeKey].done?byId[activeKey]:ensureGroup(`stream_${e.id||++seq}`,e.ts,e.agent));
      group.text=mergeStreamText(group.text,payload.preview||'');
      group.displayText=group.text||group.displayText;
      group.sortTs=e.ts||group.sortTs;
      if(e.agent&&!group.agent)group.agent=e.agent;
      activeKey=group.groupKey;
      return;
    }
    if(e.event_type==='llm_reply'){
      const group=callId?ensureGroup(callId,e.ts,e.agent):(activeKey?byId[activeKey]:null);
      if(group){
        group.reply=mergeStreamText(group.reply,payload.preview||'');
        if(!group.text&&group.reply)group.displayText=group.reply;
        group.done=true;
        group.sortTs=e.ts||group.sortTs;
        if(e.agent&&!group.agent)group.agent=e.agent;
        if(activeKey===group.groupKey)activeKey='';
      }
    }
  });
  return groups.filter(group=>group.displayText||group.reply||group.prompt).map(group=>({
    ...group,
    prompt:String(group.prompt||'').slice(0,800),
    displayText:clipDisplayText(group.displayText||group.reply||'',24000),
  }));
}
function attachStreamGroupsToItems(runId,items,streamGroups,fallbackTitle=''){
  const bound=items.map(item=>({...item,streamGroups:Array.isArray(item.streamGroups)?item.streamGroups.slice():[]}));
  let index=0;
  bound.forEach(item=>{
    while(index<streamGroups.length){
      const group=streamGroups[index];
      if(String(group.sortTs||'')<=String(item.sortTs||'')){
        item.streamGroups.push(group);
        index+=1;
        continue;
      }
      break;
    }
  });
  while(index<streamGroups.length){
    const group=streamGroups[index];
    bound.push({
      key:`${runId}:stream:${group.groupKey}`,
      title:esc(fallbackTitle?`${fallbackTitle} · 流式输出`:(group.agent||'模型流式输出')),
      kind:'plain',
      text:'',
      sortTs:group.sortTs||'',
      streamGroups:[group],
      streamOnly:true,
    });
    index+=1;
  }
  return sortTimelineItems(bound);
}
function findActiveRunItemKey(items){
  for(let i=items.length-1;i>=0;i-=1){
    const groups=Array.isArray(items[i]?.streamGroups)?items[i].streamGroups:[];
    if(groups.some(group=>!group.done))return String(items[i].key||'');
  }
  return '';
}
function syncActiveRunCard(runId,activeKey){
  const prevKey=String(runActiveItemKeys[runId]||'');
  if(prevKey&&prevKey!==activeKey)boxStates[prevKey]=false;
  if(activeKey&&prevKey!==activeKey)boxStates[activeKey]=true;
  if(activeKey)runActiveItemKeys[runId]=activeKey;
  else delete runActiveItemKeys[runId];
}
function outputTaskLabel(out){const t=String(out?.output_type||'');if(t==='outline_blueprint')return'步骤1 大纲+蓝图';if(t==='worldbuilding')return'步骤2 背景体系+世界观';if(t==='character_bible')return'步骤3 角色卡';if(t==='character_added')return'步骤3 增加角色';if(t==='event_timeline')return'步骤4 客观事件时间线';if(t==='character_milestones')return'步骤5 角色发展线';if(t==='twist_designs')return'步骤6 反转设计';if(t==='story_lines')return'步骤7 明线暗线发展线';if(t==='chapter_briefs')return'步骤8 章节摘要规划';if(t==='step_revision_draft'){const p=out?.payload||{};const stepKey=String(p?.step_key||'');const idx=p?.character_index;if(stepKey==='step_3'&&Number.isInteger(idx))return`步骤3 单角色指令修改（角色 ${Number(idx)+1}）`;if(stepKey==='step_5'&&Number.isInteger(idx))return`步骤5 单角色发展线指令调整（角色 ${Number(idx)+1}）`;if(stepKey)return`${stepKey.toUpperCase()} 结果修订`;return'步骤结果修订';}if(t==='blueprint_review')return'Critic Blueprint 评审';if(t==='text_updated')return'正文AI修改';if(t==='chapter_blocks')return'正文 content blocks';if(t==='chapter_final_text')return'正文最终稿';if(t==='actual_chapter_summary')return'正文 actual summary';if(t==='chapter_stage_log')return'正文 agent 闭环';return'';}
function inferTaskLabel(run,detail){
  if(run?.task_label)return String(run.task_label);
  const ctx=detail?.context||{};
  const action=String(ctx?.action||'');
  const stepKey=String(ctx?.step_key||'');
  const revisionMode=String(ctx?.revision_mode||'');
  const idx=ctx?.character_index;
  const stepName=(key)=>({step_1:'步骤1 大纲+蓝图',step_2:'步骤2 背景体系+世界观',step_3:'步骤3 角色卡',step_4:'步骤4 客观事件时间线',step_5:'步骤5 角色发展线',step_6:'步骤6 反转设计',step_7:'步骤7 明线暗线发展线',step_8:'步骤8 章节摘要规划'}[key]||key.toUpperCase());
  if(action==='generate_outline')return'步骤1 大纲+蓝图';
  if(action==='generate_worldbuilding')return'步骤2 背景体系+世界观';
  if(action==='generate_characters')return'步骤3 角色卡';
  if(action==='generate_event_timeline')return'步骤4 客观事件时间线';
  if(action==='generate_milestones')return'步骤5 角色发展线';
  if(action==='generate_twist_designs')return'步骤6 反转设计';
  if(action==='generate_story_lines')return'步骤7 明线暗线发展线';
  if(action==='generate_chapter_briefs')return'步骤8 章节摘要规划';
  if(action==='generate_chapter_briefs_batch')return'步骤8 续生成章节摘要';
  if(action==='review_blueprint')return'Critic Blueprint 评审';
  if(action==='add_character')return'步骤3 增加角色';
  if(action==='add_character_milestone')return'步骤5 增加角色发展线';
  if(action==='continue_formal_novel' || action==='write_chapter')return'正文生成';
  if(action==='revise_single_character')return Number.isInteger(idx)?`步骤3 单角色指令修改（角色 ${Number(idx)+1}）`:'步骤3 单角色指令修改';
  if(action==='revise_single_character_milestone')return Number.isInteger(idx)?`步骤5 单角色发展线指令调整（角色 ${Number(idx)+1}）`:'步骤5 单角色发展线指令调整';
  if(action==='revise_step_result')return `${stepName(stepKey)} ${revisionMode==='review'?'质检修改':'指令修改'}`;
  if(action==='ai_update_concept')return'小说信息 AI 修改';
  if(action==='ai_update_text')return'正文 AI 修改';
  const outs=Array.isArray(detail?.outputs)?detail.outputs:[];
  for(let i=outs.length-1;i>=0;i-=1){const label=outputTaskLabel(outs[i]);if(label)return label;}
  const msg=String(run?.pending_message||'');
  if(msg.includes('大纲'))return'步骤1 大纲+蓝图';
  if(msg.includes('世界观')||msg.includes('背景'))return'步骤2 背景体系+世界观';
  if(msg.includes('角色卡')||msg.includes('关系网'))return'步骤3 角色卡';
  if(msg.includes('事件时间线'))return'步骤4 客观事件时间线';
  if(msg.includes('角色发展线'))return'步骤5 角色发展线';
  if(msg.includes('反转'))return'步骤6 反转设计';
  if(msg.includes('故事线')||msg.includes('明线')||msg.includes('暗线'))return'步骤7 明线暗线发展线';
  if(msg.includes('章节规划')||msg.includes('章节摘要'))return'步骤8 章节摘要规划';
  if(msg.includes('写下一章'))return'正文生成';
  if(String(run?.run_id||'').startsWith('edit_'))return'编辑任务';
  return'';
}
async function renderRuns(pref){
  const scrollState=captureLeftScrollState();
  if(!runsCache.length){evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";restoreLeftScrollState(scrollState);return;}
  const cache=pref||{};
  for(const r of runsCache){
    if((expandedRuns.has(r.run_id)||r.is_running)&&!cache[r.run_id])cache[r.run_id]=await api(`/api/run?mode=${mode}&run_id=${r.run_id}`);
  }
  let html='';
  runsCache.forEach(r=>{
    const ex=expandedRuns.has(r.run_id),d=cache[r.run_id],outs=((d&&d.outputs)||[]).filter(o=>o?.output_type!=='chapter_live_preview'),evts=(d&&d.events)||[];
    const taskLabel=inferTaskLabel(r,d);
    const streamGroups=collectStreamGroups(evts);
    const normalEvents=evts.filter(e=>!['llm_stream','llm_prompt','llm_reply'].includes(e.event_type));
    const timelineItems=[];
    const chapterTaskItems=d?collectChapterTaskOutputs(d):[];
    if(r.pending_message)timelineItems.push({key:`${r.run_id}:pending`,title:'任务状态',kind:'plain',text:r.pending_message,sortTs:''});
    chapterTaskItems.forEach(item=>timelineItems.push(item));
    outs.forEach(o=>timelineItems.push({key:`${r.run_id}:out:${o.id}`,title:`${esc(o.agent)} · ${esc(o.title)}`,kind:'output',outputType:o.output_type,rawPayload:o.payload,sortTs:o.created_at||''}));
    normalEvents.forEach(e=>timelineItems.push({key:`${r.run_id}:evt:${e.id}`,title:`${esc(e.agent||'System')} · ${esc(e.title||'')}`,kind:'event',eventType:e.event_type,rawPayload:e.payload,sortTs:e.ts||''}));
    sortTimelineItems(timelineItems);
    const items=attachStreamGroupsToItems(r.run_id,timelineItems,streamGroups,taskLabel||'当前任务');
    const activeKey=findActiveRunItemKey(items);
    syncActiveRunCard(r.run_id,activeKey);
    html+=`<div class='run'><div class='head' onclick="toggleRun('${r.run_id}')"><span class='tag'>${esc(stageText(r.stage))}</span>${taskLabel?`<span class='tag'>${esc(taskLabel)}</span>`:''}${r.is_running?"<span class='tag live'>运行中</span>":''}${r.cancel_requested?"<span class='tag stop'>停止中</span>":''}<span>${esc(r.run_id)}</span><span class='ts'>${esc(shortTs(r.updated_at))}</span></div>`;
    if(ex){
      html+="<div class='body'>";
      if(r.is_running)html+=`<div style='margin-bottom:8px'><button class='ghost' onclick="event.stopPropagation();stopRun('${r.run_id}')">停止并删除这次运行</button></div>`;
      if(!items.length)html+="<div class='payload'>暂无运行输出</div>";
      items.forEach((item)=>{const isActive=item.key===activeKey;const isOpen=(item.key in boxStates)?boxStates[item.key]:isActive;html+=boxHtml(item.key,item.title,renderItemPayload(item),isOpen,`task-box${isActive?' active':''}`);});
      html+='</div>';
    }
    html+='</div>';
  });
  evs.innerHTML=html;
  restoreLeftScrollState(scrollState);
}
function toggleRun(id){expandedRuns.has(id)?expandedRuns.delete(id):expandedRuns.add(id);renderRuns();}
async function stopCurrentRun(){const a=runsCache.find(x=>x.is_running)||(pendingRunId?{run_id:pendingRunId}:null);if(!a)return alert('当前没有运行中的任务。');await stopRun(a.run_id);}
async function stopRun(id){if(!confirm('确认删除此运行记录？'))return;await api('/api/runs/stop',{method:'POST',body:JSON.stringify({mode,run_id:id})});expandedRuns.delete(id);delete runActiveItemKeys[id];if(pendingRunId===id){pendingRunId='';pendingStepRevision=null;lastLivePreviewKey='';}runsCache=runsCache.filter(x=>x.run_id!==id);bookId?await refreshNovel():renderRuns();updateStopButton();}
function summarizeBlock(text){const cleaned=String(text||'').replaceAll(String.fromCharCode(13),' ').replaceAll(String.fromCharCode(10),' ').split(' ').filter(Boolean).join(' ');return cleaned||'（空白内容）';}
function isDetailOpen(key,defaultOpen=true){return key in detailStates?detailStates[key]:defaultOpen;}
function toggleDetailState(key,isOpen){
  detailStates[key]=isOpen;
  requestAnimationFrame(()=>{
    autoSizeTextareas('pnl-input');
    autoSizeTextareas('pnl-blueprint');
    autoSizeTextareas('pnl-text');
  });
}
function autoSizeTextareas(rootId){document.querySelectorAll(`#${rootId} textarea`).forEach(el=>{const resize=()=>{el.style.height='auto';el.style.height=`${el.scrollHeight}px`;el.style.overflow='hidden';};if(!el.dataset.autosizeBound){el.addEventListener('input',resize);el.dataset.autosizeBound='1';}resize();});}
function captureScrollState(){const activePanel=document.querySelector('.pnl.active');const tc=document.getElementById('tc');return{windowX:window.scrollX,windowY:window.scrollY,leftScrollTop:evs?evs.scrollTop:0,rightScrollTop:tc?tc.scrollTop:0,activePanelId:activePanel?activePanel.id:'',activePanelScrollTop:activePanel?activePanel.scrollTop:0};}
function captureLeftScrollState(){return{leftScrollTop:evs?evs.scrollTop:0};}
function restoreScrollState(state){if(!state)return;requestAnimationFrame(()=>{window.scrollTo(state.windowX||0,state.windowY||0);if(evs)evs.scrollTop=state.leftScrollTop||0;const tc=document.getElementById('tc');if(tc)tc.scrollTop=state.rightScrollTop||0;if(state.activePanelId){const panel=document.getElementById(state.activePanelId);if(panel)panel.scrollTop=state.activePanelScrollTop||0;}});}
function restoreLeftScrollState(state){if(!state)return;requestAnimationFrame(()=>{if(evs)evs.scrollTop=state.leftScrollTop||0;});}
function setAllInputBlocks(open){document.querySelectorAll('#pnl-input details.input-block').forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas('pnl-input');}
function setPanelSections(panelId,open){document.querySelectorAll(`#${panelId} details.section-card`).forEach(el=>{el.open=open;detailStates[el.dataset.detailKey]=open;});autoSizeTextareas(panelId);}
function snapshotPanelDetailStates(panelId){const root=document.getElementById(panelId);if(!root)return;root.querySelectorAll('details[data-detail-key]').forEach(el=>{const key=el.dataset.detailKey;if(key)detailStates[key]=!!el.open;});}
function normalizeMultiline(value){const cr=String.fromCharCode(13),lf=String.fromCharCode(10);return String(value??'').split(cr+lf).join(lf).split(cr).join(lf).trimEnd();}
function openNewNovelDialog(){newNovelModal.style.display='flex';newTitleInput.focus();}
function closeNewNovelDialog(){newNovelModal.style.display='none';}
async function startFormalFromDialog(){const title=newTitleInput.value.trim();const q=normalizeMultiline(newQueryInput.value);if(!q)return alert('请输入题材/需求。');const style=normalizeMultiline(newStyleInput.value);const r=await api('/api/novels/create',{method:'POST',body:JSON.stringify({mode,title,query:q,style_request:style})});if(!ensureOk(r))return;closeNewNovelDialog();bookId=r.book.id;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();lastRightRenderKey='';lastLivePreviewKey='';runActiveItemKeys={};currentBook=r.book;stagePill.textContent='未开始';await loadNovels();novelSel.value=bookId;await refreshNovel();updateStopButton();}
function setPendingRunState(runId,{stage,pendingMessage,taskLabel,clearLivePreview=false,clearActiveItem=false}={}){
  pendingRunId=runId||'';
  if(clearLivePreview)lastLivePreviewKey='';
  if(clearActiveItem&&pendingRunId)delete runActiveItemKeys[pendingRunId];
  if(!pendingRunId)return;
  expandedRuns.add(pendingRunId);
  boxStates={};
  runsCache=[{run_id:pendingRunId,is_running:true,stage:stage||'planning',updated_at:new Date().toISOString(),task_label:taskLabel||pendingMessage||'',pending_message:pendingMessage||taskLabel||''},...runsCache.filter(x=>x.run_id!==pendingRunId)];
}
async function startRunRequest(path,payload,{stage,pendingMessage,taskLabel,clearLivePreview=false,clearActiveItem=false}={}){
  const r=await api(path,{method:'POST',body:JSON.stringify(payload)});
  if(!ensureOk(r))return null;
  setPendingRunState(r.run_id||'',{stage,pendingMessage,taskLabel,clearLivePreview,clearActiveItem});
  await renderRuns();
  updateStopButton();
  return r;
}
async function startPlanningRun(path,message,taskLabel,payloadExtra={}){if(!bookId)return alert('请先选择一部小说。');return await startRunRequest(path,withLlmProvider({book_id:bookId,...(payloadExtra||{})}),{stage:'planning',pendingMessage:message,taskLabel});}
async function startConfiguredPlanningRun(configKey){const config=STEP_RUN_CONFIGS[configKey];if(!config)return alert('未找到对应步骤配置。');await startPlanningRun(config.path,config.pendingMessage,config.taskLabel,config.payload||{});}
async function continueFormal(){if(!bookId)return alert('请先选择一部小说。');await startRunRequest('/api/novels/continue',withLlmProvider({book_id:bookId}),{stage:'writing',pendingMessage:'正在写下一章，请稍候...',taskLabel:'正文生成',clearLivePreview:true,clearActiveItem:true});}
async function deleteNovel(){if(!bookId)return alert('请先选择一部小说。');if(!confirm('确认删除此小说？该操作不可撤销。'))return;await api('/api/novels/delete',{method:'POST',body:JSON.stringify({mode,book_id:bookId})});bookId='';currentBook=null;pendingRunId='';pendingStepRevision=null;runsCache=[];expandedRuns=new Set();lastLivePreviewKey='';runActiveItemKeys={};evs.innerHTML="<div class='empty'>选择小说或发起一次运行后查看过程</div>";renderEmptyRightPanels();stagePill.textContent='未开始';await loadNovels();updateStopButton();}
async function testBlueprint(){const q=prompt('输入题材需求（测试大纲）：');if(!q)return;const r=await startRunRequest('/api/test/blueprint',{query:q},{stage:'planning',pendingMessage:'测试大纲运行中'});if(!r)return;expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);}
async function testWrite(){let r;if(bookId)r=await startRunRequest('/api/test/write',{book_id:bookId},{stage:'writing',pendingMessage:'测试写作运行中'});else{const q=prompt('输入题材需求（测试写作）：');if(!q)return;r=await startRunRequest('/api/test/write',{query:q},{stage:'writing',pendingMessage:'测试写作运行中'});}if(!r)return;expandedRuns=new Set(pendingRunId?[pendingRunId]:[]);}
async function testCritique(){if(!bookId)return alert('请先选择一部小说。');await startRunRequest('/api/test/critique',{book_id:bookId},{stage:'critique',pendingMessage:'测试评价运行中'});}
async function testPatch(){if(!bookId)return alert('请先选择一部小说。');const blockId=prompt('请输入 block_id：');if(!blockId)return;const operation=prompt('操作类型 replace / append / prepend','replace')||'replace';const patchContent=prompt('补丁内容：');if(!patchContent)return;const reason=prompt('修改原因：','manual test patch')||'manual test patch';await startRunRequest('/api/test/patch',{book_id:bookId,block_id:blockId,operation,patch_content:patchContent,reason},{stage:'patching',pendingMessage:'测试补丁运行中'});}
async function aiReviseConcept(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt('描述你希望 AI 怎么修改概念：');if(!guidance)return;await startRunRequest('/api/novels/ai_update_concept',withLlmProvider({mode,book_id:bookId,scope,target_id:targetId,guidance}),{stage:'planning',pendingMessage:'AI 修改中'});}
async function aiReviseText(scope,targetId){if(!bookId)return alert('请先选择一部小说。');const guidance=prompt(scope==='chapter'?'描述你希望 AI 怎么修改这章：':'描述你希望 AI 怎么修改这段：');if(!guidance)return;await startRunRequest('/api/novels/ai_update_text',withLlmProvider({mode,book_id:bookId,scope,target_id:targetId,guidance}),{stage:'patching',pendingMessage:'AI 修改文本中'});}
async function applyBookMutationResult(result){if(!ensureOk(result))return false;currentBook=result.book;renderInputPanel(currentBook);renderBlueprint(currentBook);renderText(currentBook);await loadNovels();return true;}
async function deleteChapter(chapterId,chapterTitle){if(!bookId)return alert('请先选择一部小说。');const label=String(chapterTitle||chapterId||'该章节');if(!confirm(`确认删除章节：${label}？`))return;const result=await api('/api/novels/delete_chapter',{method:'POST',body:JSON.stringify({mode,book_id:bookId,chapter_id:chapterId})});if(!await applyBookMutationResult(result))return;alert('章节已删除。');}

async function resolveCharacterCandidate(candidateId,action){
  if(!bookId)return alert('请先选择一部小说。');
  const result=await api('/api/novels/resolve_character_candidate',{method:'POST',body:JSON.stringify({mode,book_id:bookId,candidate_id:candidateId,action})});
  if(!await applyBookMutationResult(result))return;
  alert('角色已添加');
}

function renderInputPanel(book){
  const currentQuery=book?.metadata?.query||'';
  const userTopic=book?.metadata?.user_topic||'';
  const styleRequest=book?.metadata?.style_request||'';
  const assistantPersonaPrompt=book?.metadata?.assistant_persona_prompt||'';
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
  const html=`<div class='card'><div class='sec'>用户输入</div><div class='input-hero'><div class='input-hero-copy'><div class='input-hero-kicker'>小说基础设置</div><div class='input-hero-title-row'><h2 class='input-hero-title'>${esc(book?.title||'未命名小说')}</h2><span class='input-hero-badge'>写作控制台</span></div><div class='input-hero-desc'>${heroSummary}</div></div><div class='input-toolbar'><div class='actions'><button class='ghost' onclick='setAllInputBlocks(true)'>全部展开</button><button class='ghost' onclick='setAllInputBlocks(false)'>全部折叠</button><button onclick='saveConcept()'>保存所有修改</button></div></div></div><div class='title-field'><label>书名标题</label><input id='concept-title' value='${esc(book?.title||'')}' placeholder='输入小说书名' /></div><div class='input-blocks'>${block('input-query','concept-query','题材与需求',currentQuery,'支持 Markdown 详细描述题材','此内容影响步骤 1-8 的生成',true)}${block('input-topic','concept-user-topic','用户主题',userTopic,'可选填写用户关注的主题方向','仅在明确时填写',false)}${block('input-style','concept-style-request','风格要求',styleRequest,'留空则由系统判断风格','明确时填写，不填则自动决策',false)}${block('input-assistant-persona','concept-assistant-persona','小说助手人设',assistantPersonaPrompt,'例如：你是一名擅长古风权谋禁忌言情的长篇作者……','会动态插入“写正文”提示词。可留空。',false)}${writingBlock}</div></div>`;
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
  const stepSection=(stepKey,title,summary,body,defaultOpen=false)=>{const badge=stepDraftDirty[stepKey]?`<span class='dirty-dot'>●未保存</span>`:'';const extra=stepKey==='step_5'?`<button class='ghost' onclick="addMilestoneLine()">增加角色</button>`:'';const acts=`${badge}${extra}<button class='ghost' onclick="clearStepDraft('${stepKey}')">清空</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('${stepKey}','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('${stepKey}')">保存</button>`;return toolbarSection(stepKey,title,summary,acts,body,defaultOpen);};
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
  const characterCards=displayCharacters.map((item,index)=>{const title=item.name||item.role||`角色 ${index+1}`;const summary=[item.role,item.personality,item.occupation].filter(Boolean).join(' · ')||'暂无信息';const editFields=[charField(index,'name','名称',item.name),charField(index,'role','角色定位',item.role),charField(index,'occupation','职业',item.occupation),charField(index,'appearance','外貌',item.appearance),charField(index,'personality','性格',item.personality),charField(index,'social_background','社会背景',item.social_background),charField(index,'education_background','教育背景',item.education_background),charField(index,'career','事业',item.career),charField(index,'initial_state','初始状态',item.initial_state),charField(index,'motivation','动机',item.motivation),charField(index,'behavior_pattern','行为模式',item.behavior_pattern),charField(index,'arc','成长弧',item.arc),charField(index,'relationships','关系',item.relationships)].join('');const axes=toArray(item.development_axes||[]);const body=`<div class='step-inline-root'>${editFields}</div>${axes.length?`<div style='margin-top:8px'>${listHtml(axes,'')}</div>`:''}<div style='display:flex;justify-content:flex-end;gap:8px;margin-top:12px'><button class='ghost' onclick='reviseSingleCharacterByInstruction(${index})'>指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存修改</button></div>`;return sectionCard(`step3-character-${index}`,title,summary,body,false);}).join('')||"<div class='relationship-empty'>暂无角色</div>";
  const charActions=`${dirtyBadge}<button class='ghost' onclick="clearStepDraft('step_3')">清空</button><button class='ghost' onclick="addCharacterByInstruction()">增加角色</button><button class='ghost' onclick="reviseStepDraft('step_3','review')">质检修改</button><button class='ghost' onclick="reviseStepDraft('step_3','instruction')">指令修改</button><button class='ghost' onclick="saveStepDraft('step_3')">保存</button>`;
  html+=toolbarSection('step3-characters','3 角色卡',`${displayCharacters.length} 个角色`,charActions,characterCards,false);
  html+=stepSection('step_4','4 客观事件时间线',`${(blueprint.event_timeline||[]).length} 条`,subStepEditor('step_4','event_timeline','事件时间线'));
  const step5State=ensureStepObject('step_5',stepPayloadFromBook(book,'step_5'));
  const milestoneItems=Array.isArray(step5State?.character_milestones)?step5State.character_milestones:[];
  const characterCardMap=new Map(displayCharacters.map(item=>[String(item?.name||'').trim(),item]));
  const milestoneCards=milestoneItems.map((item,index)=>{
    const name=String(item?.character_name||'').trim()||`角色 ${index+1}`;
    const card=characterCardMap.get(name)||null;
    const summary=card?[card.role,card.personality,card.occupation].filter(Boolean).join(' · ')||'已匹配角色卡':'未匹配到角色卡，请先确认角色名与角色卡一致';
    const detailKey=`step5-character-${index}`;
    const toolbar=`<button class='ghost' onclick='event.stopPropagation();saveStepDraft("step_5")'>保存修改</button><button class='ghost' onclick='event.stopPropagation();reviseSingleMilestoneByInstruction(${index})'>指令调整</button>`;
    const body=`<div class='step-editor'><div class='step-editor-body'>${renderStepEditorField('step_5',['character_milestones',index],item)}</div></div>`;
    return `<details class='section-card' data-detail-key='${detailKey}' ${isDetailOpen(detailKey,true)?'open':''} ontoggle="toggleDetailState('${detailKey}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${esc(name)}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-toolbar' onclick='event.stopPropagation()'>${toolbar}</div></summary><div class='section-body'>${body}</div></details>`;
  }).join('')||"<div class='relationship-empty'>暂无角色发展线</div>";
  html+=stepSection('step_5','5 角色发展线',`${milestoneItems.length} 条发展线`,milestoneCards);
  html+=stepSection('step_6','6 反转设计',`${(blueprint.twist_designs||[]).length} 个反转`,subStepEditor('step_6','twist_designs','反转设计'));
  const step8State=ensureStepObject('step_8',stepPayloadFromBook(book,'step_8'));
  const step8Inline=`<div class='step-editor'><div class='step-editor-body'>${renderStepEditorField('step_8',['chapter_briefs'],step8State.chapter_briefs??[])}</div></div>`;
  const step7Summary=`${(blueprint.story_lines||[]).length} 条故事线`;
  const step8Summary=`${(blueprint.chapter_briefs||[]).length} 章摘要`;
  html+=stepSection('step_7','7 明线暗线发展线',step7Summary,subStepEditor('step_7','story_lines','明线暗线（含关键章节推进）'));
  html+=stepSection('step_8','8 章节摘要（点一次生成一章）',step8Summary,step8Inline);
  const actualSummaries=Array.isArray(book?.metadata?.actual_chapter_summaries)?book.metadata.actual_chapter_summaries:[];
  const latestCritic=book?.metadata?.latest_critic_report||null;
  html+=sectionCard('actual-summaries','已完成章节 actual summaries',`${actualSummaries.length} 章`,listHtml(actualSummaries.map(item=>`${item.chapter_id||''}：${(item.actual_events||[]).join('；')}`),'暂无已完成章节'),false);
  if(latestCritic){html+=sectionCard('latest-critics','最近一次章节 critic',latestCritic.summary||'暂无总结',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', latestCritic.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((latestCritic.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}：${item.evidence||item.recommendation||''}`),'暂无问题')}</div></div>`,false);}
  if(blueprintReview){html+=sectionCard('blueprint-review','Critic Blueprint',blueprintReview.summary||'暂无评审结论',`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>总结</div>${infoRow('摘要', blueprintReview.summary||'')}</div><div class='relationship-card'><div class='subsec'>问题列表</div>${listHtml((blueprintReview.issues||[]).map(item=>`${item.severity||'未知'}·${item.title||'未命名问题'}`),'暂无问题')}</div></div>`,false);}
  document.getElementById('pnl-blueprint').innerHTML=html;
  autoSizeTextareas('pnl-blueprint');
}
function renderText(book,livePreview=null,runDetail=null){
  const volumes=book?.volumes||[];
  const chapters=[];
  const candidates=Array.isArray(book?.metadata?.new_character_candidates)?book.metadata.new_character_candidates:[];
  volumes.forEach(volume=>(volume.chapters||[]).forEach(chapter=>chapters.push({volume,chapter})));
  const recentPatchedBlockIds=latestPatchedBlockIds(runDetail);
  const draftPreview=latestChapterPreviewByMode(runDetail,'chapter_draft');
  const draftPreviewText=String(draftPreview?.payload?.final_text||'').trim();
  if(livePreview&&livePreview.chapter_id){
    const idx=chapters.findIndex(item=>String(item?.chapter?.id||'')===String(livePreview.chapter_id||''));
    const previewChapter={
      id:String(livePreview.chapter_id||''),
      title:String(livePreview.chapter_title||livePreview.chapter_id||'实时章节'),
      summary:'实时生成中',
      scenes:[],
      content_blocks:Array.isArray(livePreview.content_blocks)?livePreview.content_blocks:[],
      character_mindsets:Array.isArray(livePreview.character_mindsets)?livePreview.character_mindsets:[],
      final_text:String(livePreview.final_text||''),
      final_version:Number(livePreview.final_version||0),
      is_finalized:!!livePreview.is_finalized,
      preview_mode:String(livePreview.preview_mode||''),
      recent_patched_block_ids:recentPatchedBlockIds,
      draft_text:draftPreviewText,
    };
    const previewEntry={volume:{title:'运行中',id:'runtime'},chapter:previewChapter};
    if(idx>=0)chapters[idx]=previewEntry;
    else chapters.push(previewEntry);
  }
  const sectionCard=(key,title,summary,body,defaultOpen=false)=>`<details class='section-card' data-detail-key='${key}' ${isDetailOpen(key,defaultOpen)?'open':''} ontoggle="toggleDetailState('${key}', this.open)"><summary><div class='summary-text'><div class='summary-title'>${title}</div><div class='summary-desc'>${esc(summary)}</div></div><div class='summary-arrow'>›</div></summary><div class='section-body'>${body}</div></details>`;
  const renderLegacyScenes=(chapter)=>{
    return (chapter.scenes||[]).map((scene,sceneIndex)=>{
      const blocks=(scene.blocks||[]).map((block,blockIndex)=>`<div class='block' style='margin-top:8px'><div class='row'><strong>段落 ${blockIndex+1}</strong>${block.purpose?` <span class='muted'>${esc(block.purpose)}</span>`:''}${block.id?` <span class='muted'>${esc(block.id)}</span>`:''}</div><div>${esc(block.text||'')}</div></div>`).join('')||"<div class='relationship-empty'>暂无段落内容</div>";
      return `<div class='relationship-card'><div class='subsec'>场景 ${sceneIndex+1}${scene.title?` · ${esc(scene.title)}`:''}</div>${infoRow('场景概述', scene.summary||'')}${blocks}</div>`;
    }).join('')||"<div class='relationship-empty'>暂无场景</div>";
  };
  if(!chapters.length && !candidates.length){document.getElementById('pnl-text').innerHTML="<div class='empty'>暂无内容</div>";return;}
  let html=`<div class='panel-toolbar'><div class='title-wrap'><div class='panel-meta'>小说正文</div><div class='panel-title'>章节内容</div></div><div class='actions'><button class='ghost' onclick="setPanelSections('pnl-text',true)">全部展开</button><button class='ghost' onclick="setPanelSections('pnl-text',false)">全部折叠</button></div></div>`;
  if(candidates.length){
    const cards=candidates.map((item,index)=>{
      const traits=Array.isArray(item?.provisional_traits)?item.provisional_traits.filter(Boolean):[];
      const links=Array.isArray(item?.links_to_existing_characters)?item.links_to_existing_characters.filter(link=>link&&typeof link==='object'):[];
      const linkLines=links.length?links.map(link=>`<div class='kv'><div class='k'>${esc(link.target||'未知角色')}</div><div>${esc(link.relation||'未知关系')}</div></div>`).join(''):"<div class='relationship-empty'>暂无关联角色</div>";
      return `<div class='relationship-card'><div class='row' style='justify-content:space-between;align-items:flex-start;gap:12px'><div><div class='subsec'>${esc(item?.name||`角色候选 ${index+1}`)}</div><div class='muted'>首登场：${esc(item?.first_appearance_chapter||'待定')}</div></div><div class='actions'><button class='ghost' onclick="resolveCharacterCandidate('${esc(item?.candidate_id||'')}','add')">确认添加</button></div></div>${infoRow('场景作用', item?.role_in_scene||'')}${infoRow('存在理由', item?.why_needed||'')}${traits.length?sectionHtml('特征', chipsHtml(traits)):''}${sectionHtml('与现有角色关联', linkLines)}</div>`;
    }).join('');
    html+=sectionCard('text-character-candidates','新角色候选',`共 ${candidates.length} 个候选角色`,`<div class='relationship-stack'>${cards}</div>`,true);
  }
  chapters.forEach(({volume,chapter},index)=>{
    const title=chapter.title||chapter.id||`第${index+1}章`;
    const summary=chapter.summary||'暂无摘要';
    const chapterToolbar=`<div style='display:flex;justify-content:flex-end;gap:8px;margin-bottom:8px'><button class='ghost' onclick="aiReviseText('chapter','${esc(chapter.id||'')}')">整章指令修改</button><button class='ghost' onclick="deleteChapter('${esc(chapter.id||'')}')">删除章节</button></div>`;
    const contentBlocks=Array.isArray(chapter?.content_blocks)?chapter.content_blocks:[];
    const characterMindsets=Array.isArray(chapter?.character_mindsets)?chapter.character_mindsets:[];
    const finalText=String(chapter?.final_text||'').trim();
    const isFinalized=!!chapter?.is_finalized;
    const previewMode=String(chapter?.preview_mode||'').trim();
    const draftText=String(chapter?.draft_text||'').trim();
    const patchHighlightIds=Array.isArray(chapter?.recent_patched_block_ids)?chapter.recent_patched_block_ids:[];
    const hasChapterPreview=!!finalText;
    const assembledPreviewText=mergeChapterBlocksText(contentBlocks,finalText);
    const previewModeLabel=previewMode==='content_blocks'?'内容块逐块追加中':previewMode==='chapter_rewrite'?'整章审校重写中':previewMode==='final_polish'?'整章精修中':previewMode==='final_text'?'整章覆写已收口':'';
    const mindsetBody=renderCharacterMindsetsBlock(characterMindsets);
    let proseBody='';
    if(hasChapterPreview||contentBlocks.length){
      const proseLabel=isFinalized?'当前小说正文':'当前修订中的正文';
      const liveSummary=isFinalized?'终稿已经收口，可直接阅读当前正文。':'这里会持续显示本轮正在修订的正文，命中的 block 修完后会直接体现在这里。';
      proseBody=`<div class='relationship-card'><div class='subsec'>${proseLabel}</div><div class='task-note'>${esc(liveSummary)}</div><div class='block live-draft-text'>${esc(assembledPreviewText||finalText)}</div>${previewModeLabel?`<div class='live-draft-meta'><span class='block-badge status'>${esc(previewModeLabel)}</span>${patchHighlightIds.length?`<span class='block-badge patched'>本轮更新 ${patchHighlightIds.length} 个 block</span>`:''}</div>`:''}</div>`;
      if(draftText&&draftText!==assembledPreviewText){
        proseBody+=`<div class='relationship-card'><div class='subsec'>整章首稿快照</div><div class='block live-draft-text'>${esc(draftText)}</div></div>`;
      }
      if(contentBlocks.length){
        proseBody+=`<div class='relationship-card'><div class='subsec'>当前 block 视图</div><div class='chapter-live-blocks'><div class='relationship-stack'>${renderBlockCards(contentBlocks,{label:'内容块',highlightIds:patchHighlightIds})}</div></div></div>`;
      }
    }else if(contentBlocks.length){
      proseBody=`<div class='relationship-card'><div class='subsec'>增量写作中</div><div class='muted'>每个 content block 提交后，这里都会继续往下追加。</div><div class='relationship-stack'>${renderBlockCards(contentBlocks,{label:'内容块'})}</div></div>`;
    }else{
      proseBody=`<div class='relationship-card'><div class='subsec'>正文展示</div><div class='relationship-stack'>${renderLegacyScenes(chapter)}</div></div>`;
    }
    const modeSummary=isFinalized&&finalText?'已终稿覆盖':(hasChapterPreview||contentBlocks.length)&&previewMode?'实时修订视图':contentBlocks.length?'按内容块逐步追加':'场景回放';
    const body=`<div class='relationship-stack'><div class='relationship-card'><div class='subsec'>基础信息</div>${infoRow('卷名', volume.title||volume.id||'')}${infoRow('章节标题', title)}${infoRow('章节概述', summary)}${infoRow('展示模式', modeSummary)}${previewModeLabel?infoRow('运行状态', previewModeLabel):''}</div>${chapterToolbar}${mindsetBody}${proseBody}</div>`;
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
const btnNew=document.getElementById('btnNew'),btnStep1=document.getElementById('btnStep1'),btnStep2=document.getElementById('btnStep2'),btnStep3=document.getElementById('btnStep3'),btnStep4=document.getElementById('btnStep4'),btnStep5=document.getElementById('btnStep5'),btnStep6=document.getElementById('btnStep6'),btnStep7=document.getElementById('btnStep7'),btnStep8=document.getElementById('btnStep8'),btnBlueprintReview=document.getElementById('btnBlueprintReview'),btnContinue=document.getElementById('btnContinue'),btnBlueprint=document.getElementById('btnBlueprint'),btnWrite=document.getElementById('btnWrite'),btnCritique=document.getElementById('btnCritique'),btnPatch=document.getElementById('btnPatch'),btnStop=document.getElementById('btnStop'),stagePill=document.getElementById('stage-pill'),bootPill=document.getElementById('boot-pill'),novelSel=document.getElementById('novelSel'),modeSel=document.getElementById('modeSel'),modelSel=document.getElementById('modelSel'),evs=document.getElementById('evs'),newNovelModal=document.getElementById('newNovelModal'),newTitleInput=document.getElementById('newTitleInput'),newQueryInput=document.getElementById('newQueryInput'),newStyleInput=document.getElementById('newStyleInput');
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
    try{
      const savedMode=readStoredMode();
      mode=validMode(savedMode)?savedMode:'formal';
    }catch{mode='formal';}
    try{
      const savedProvider=String(localStorage.getItem(LLM_PROVIDER_STORAGE_KEY)||'').toLowerCase();
      llmProvider=validLlmProvider(savedProvider)?savedProvider:'doubao';
    }catch{llmProvider='doubao';}
    if(modeSel)modeSel.value=mode;
    if(modelSel)modelSel.value=llmProvider;
    toggleButtons();
    await loadNovels({autoSelectSingle:true});
    if(bootPill)bootPill.textContent=`前端已加载 ${Math.max((novelSel?.options?.length||1)-1,0)} 本`;
    updateStopButton();
    if(bookId)await refreshNovel();
    setInterval(async()=>{
      if(refreshPaused)return;
      // Avoid double re-render during active runs: polling both endpoints in one tick
      // causes the left run panel to redraw twice and appear as flicker.
      if(pendingRunId){
        await refreshPendingRun();
        return;
      }
      if(bookId)await refreshNovel();
    },1500);
  }catch(err){
    showFrontendError(err?.message||String(err));
  }
}
initApp();
