'use strict';
Object.assign(state,{study:null,studyProject:null,noteDrafts:new Map(),noteQueue:Promise.resolve(),noteTimer:null,positionTimer:null,readerHistory:[],historyIndex:-1,readerMode:'source',selection:null,restoreReader:null,helpIntent:'ask',helpOpen:false,helpDrafts:new Map(),helpPending:null,helpPoll:null,adjustProposal:null,resumed:false});
const studyTask=()=>state.study?.tasks.find(t=>t.id===selectedStep(state.project)?.id);
const preference=key=>state.study?.adjustments?.[state.study.route_id]?.[key];
const draftKey=(id,key)=>'exampleproof-study-draft:'+id+':'+key;
const labelPreference=p=>({known:'已会 · 跳过',later:'稍后再学',hard:'需要帮助',split:'已拆分',prerequisite:'先补前提'}[p]||'');

async function loadStudy(p){
  const workspace=await api(`/api/projects/${p.id}/workspace`);
  if(location.hash!=='#/project/'+p.id)return false;
  state.study=workspace;state.studyProject=p.id;
  const position=workspace.positions[workspace.route_id];
  state.selectedStep=workspace.tasks.find(t=>t.key===position?.step_key)?.id||null;
  state.restoreReader=position?.reader||null;state.resumed=!!position;
  state.readerHistory=position?.history||[];state.historyIndex=Number.isInteger(position?.history_index)?position.history_index:state.readerHistory.length-1;
  state.helpPending=workspace.pending_requests[0]||null;
  if(state.helpPending)pollStudyHelp(p.id,state.helpPending.id);
  return true;
}

function mergeStudy(store,id){
  if(state.project?.id===id&&state.studyProject===id)Object.assign(state.study,store);
}
async function studyMutation(body,id=state.project.id){
  const store=await api(`/api/projects/${id}/workspace`,{method:'POST',json:body});
  mergeStudy(store,id);return store;
}
function studyBody(action,extra={}){const task=studyTask();return {action,route_id:state.study.route_id,step_key:task.key,...extra};}

function noteEntry(){
  const p=state.project,t=studyTask();if(!p||!t)return null;
  const key=draftKey(p.id,t.key);if(state.noteDrafts.has(key))return state.noteDrafts.get(key);
  const saved=state.study.notes[t.key];
  let draft=null,legacy='';
  try{draft=JSON.parse(localStorage.getItem(key)||'null');if(!saved)legacy=localStorage.getItem(noteKey(p,selectedStep(p)))||'';}catch{}
  const entry={project:p.id,key:t.key,route_id:state.study.route_id,title:t.title,text:draft?.text??saved?.text??legacy,
    version:draft?.version??saved?.version??0,evidence:draft?.evidence||saved?.evidence||t.evidence,dirty:!!draft||!!legacy,error:null};
  state.noteDrafts.set(key,entry);
  if(entry.dirty)state.noteTimer=setTimeout(()=>flushStudyNote(),700);
  return entry;
}
function backupNote(entry){try{localStorage.setItem(draftKey(entry.project,entry.key),JSON.stringify(entry));return true;}catch{return false;}}
function noteMessage(entry){return entry.error?`保存未完成：${entry.error}。草稿仍保留。`:entry.dirty?'有草稿等待保存到本机服务。':'已保存到本机服务，可在学习记录中查看和导出。';}
function showNoteStatus(message){const status=$('#note-status');if(status)status.textContent=message;}
function flushStudyNote(){
  clearTimeout(state.noteTimer);
  state.noteQueue=state.noteQueue.catch(()=>{}).then(async()=>{
    for(const entry of state.noteDrafts.values()){
      if(!entry.dirty)continue;
      const text=entry.text,body={action:'note',route_id:entry.route_id,step_key:entry.key,text,version:entry.version,evidence:entry.evidence};
      try{
        const store=await studyMutation(body,entry.project);entry.version=store.notes[entry.key].version;entry.error=null;
        if(entry.text===text){entry.dirty=false;try{localStorage.removeItem(draftKey(entry.project,entry.key));}catch{}}
        else{backupNote(entry);state.noteTimer=setTimeout(()=>flushStudyNote(),500);}
        if(state.project?.id===entry.project&&studyTask()?.key===entry.key)showNoteStatus(entry.dirty?'正在保存后续修改…':'已保存到本机服务。');
      }catch(error){entry.error=error.message;backupNote(entry);if(state.project?.id===entry.project&&studyTask()?.key===entry.key)showNoteStatus('保存未完成：'+error.message+' 草稿仍保留，请复制或重试。');}
    }
  });return state.noteQueue;
}

function saveStudyPosition(){
  clearTimeout(state.positionTimer);
  if(!state.study||!state.project||state.project.status!=='ready'||!studyTask())return;
  const id=state.project.id,r=state.reader;
  const reader=r?{path:r.path,start_line:r.first,end_line:r.last,scroll:$('#source-reader .reader-scroll')?.scrollTop||0,mode:state.readerMode}:null;
  if(reader&&state.historyIndex>=0)state.readerHistory[state.historyIndex]={...reader};
  const body=studyBody('position',{reader,history:state.readerHistory.slice(-30),history_index:state.historyIndex});
  state.positionTimer=setTimeout(()=>studyMutation(body,id).catch(()=>{}),350);
}
function nextStudyStep(p,after){
  const steps=p.guide.steps,index=steps.findIndex(t=>t.id===after),ordered=[...steps.slice(index+1),...steps.slice(0,index)];
  return ordered.find(s=>{const t=state.study?.tasks.find(t=>t.id===s.id);return !p.completed_steps.includes(s.id)&&!['known','later'].includes(preference(t?.key)?.preference);});
}
function selectStudyStep(id){
  if(!state.project?.guide.steps.some(s=>s.id===id))return;
  void flushStudyNote();state.selectedStep=id;state.tab='route';state.reader=null;state.restoreReader=null;state.selection=null;state.adjustProposal=null;state.helpOpen=false;++state.sourceRequest;
  projectView(state.project);saveStudyPosition();$('#study-title')?.focus({preventScroll:true});
  if(innerWidth<=760)$('#project-content')?.scrollIntoView({block:'start'});
}
async function completeStudyStep(button){
  if(state.progressBusy)return;
  const p=state.project,id=button.dataset.step,done=p.completed_steps.includes(id);state.progressBusy=true;button.disabled=true;
  try{
    await flushStudyNote();
    const updated=await api(`/api/projects/${p.id}/progress`,{method:'POST',json:{completed_steps:done?p.completed_steps.filter(s=>s!==id):[...p.completed_steps,id]}});
    if(state.project?.id!==p.id)return;
    if(!done&&state.selectedStep===id){state.selectedStep=nextStudyStep(updated,id)?.id||id;state.reader=null;state.restoreReader=null;++state.sourceRequest;}
    state.progressBusy=false;projectView(updated);saveStudyPosition();toast(done?'已撤销完成记录。':'已保存你记录的完成状态。');
  }catch(error){toast(error.message);}finally{state.progressBusy=false;document.querySelectorAll('[data-action="complete"]').forEach(b=>b.disabled=false);}
}

function adjustmentView(task){
  const current=preference(task.key),choice=state.adjustProposal;
  const proposals={known:['跳过已掌握的内容','连续学习会跳过这一步，目录和原文仍可回看。不会记作独立验证通过。'],later:['把这一步留待以后','连续学习会先进入其他未完成步骤，这一步保留在目录中。'],hard:['先降低这一步的难度','可以拆成定位、操作、核对三个小任务，或先回看环境与概念。']};
  return `<section class="study-adapt"><div class="adapt-actions"><span>调整这一步</span>${[['known','已经会了'],['hard','这步太难'],['later','当前不需要']].map(([key,label])=>`<button class="button small" data-action="adapt-propose" data-preference="${key}">${label}</button>`).join('')}</div>
    ${choice?`<div class="adapt-proposal"><strong>${proposals[choice][0]}</strong><p>${proposals[choice][1]}</p><div class="row">${choice==='hard'?'<button class="button small primary" data-action="adapt-apply" data-preference="split">采用拆分</button><button class="button small" data-action="adapt-apply" data-preference="prerequisite">先补前提</button>':`<button class="button small primary" data-action="adapt-apply" data-preference="${choice}">确认调整</button>`}<button class="text-button" data-action="adapt-cancel">取消</button></div></div>`:''}
    ${current?`<p class="adapt-current">当前安排：${labelPreference(current.preference)} <button class="text-button" data-action="adapt-undo">撤销上次调整</button></p>`:''}
    ${current?.preference==='split'?`<div class="microtasks">${task.actions.map((a,i)=>`<label><input type="checkbox" data-microtask="${i}" ${current.subtasks.includes(i)?'checked':''}><span><strong>${a.title}</strong>${esc(a.detail)}</span></label>`).join('')}<small>这些勾选由你记录，不会自动完成整个步骤。</small></div>`:''}
    ${current?.preference==='prerequisite'?'<p class="adapt-current">建议先展开下面的“开始前”，看完环境要求和相关概念，再返回当前操作。</p>':''}</section>`;
}

function lessonText(value){
  const pattern=/(`[^`]+`|\b[\w./-]+\.(?:py|md|rst|json|toml|js|ts|yaml|yml)\b|\b\w+\([^\n()]{0,30}\))/g;
  let html='',offset=0;for(const match of String(value).matchAll(pattern)){html+=esc(value.slice(offset,match.index))+`<code>${esc(match[0].replace(/^`|`$/g,''))}</code>`;offset=match.index+match[0].length;}return html+esc(value.slice(offset));
}
function instructionCopy(value){
  const chunks=String(value).match(/[^。；\n]+[。；]?|\n/g)?.map(s=>s.trim()).filter(Boolean)||[];
  const lead=chunks.shift()||String(value);
  const clauses=lead.match(/[^，]+，?/g)||[lead],structured=lead.length>75&&clauses.length>=3&&clauses.length<=4&&clauses.every(s=>s.length>=8);
  return `<div class="instruction-lead">${structured?clauses.map((s,i)=>`<p class="action-clause ${i?'supporting-clause':''}">${lessonText(s)}</p>`).join(''):`<p>${lessonText(lead)}</p>`}</div>${chunks.length?`<details class="instruction-detail"><summary>展开操作说明</summary>${chunks.map(s=>`<p>${lessonText(s)}</p>`).join('')}</details>`:''}`;
}
function taskReferences(items){
  const button=r=>`<button class="ref" data-action="source" data-path="${esc(r.path)}" data-line="${r.start_line}" data-end="${r.end_line}" title="${esc(r.path)} · L${r.start_line}–${r.end_line}">${icon('source')}<span>${esc(r.path.split('/').pop())}</span><small>L${r.start_line}</small></button>`;
  return `<div class="task-references"><span>打开原文</span>${items.slice(0,2).map(button).join('')}${items.length>2?`<details><summary>＋${items.length-2}</summary><div>${items.slice(2).map(button).join('')}</div></details>`:''}</div>`;
}
function showStudyTool(name,scroll=false){
  state.studyTool=name;
  if(name==='help')state.helpOpen=true;
  document.querySelectorAll('[data-study-panel]').forEach(panel=>panel.hidden=panel.dataset.studyPanel!==name);
  document.querySelectorAll('[data-action="study-tool"]').forEach(button=>button.setAttribute('aria-expanded',String(button.dataset.tool===name)));
  const panel=document.querySelector(`[data-study-panel="${name}"]`);
  if(panel){const details=panel.querySelector('.study-help,.exercise-panel,.lesson-notes');if(details)details.open=true;if(scroll)panel.scrollIntoView({block:'nearest',behavior:'auto'});}
  if(name==='context'&&panel?.querySelector('.task-prerequisites'))panel.querySelector('.task-prerequisites').open=true;
}

function studyRoute(p){
  if(!state.study)return '<section class="study-sheet"><p>正在读取学习记录…</p></section>';
  const task=studyTask();if(!task)return '<section class="panel"><h2>还没有可用的任务</h2><button class="button" data-action="project-tab" data-tab="files">浏览项目文件</button></section>';
  state.selectedStep=task.id;
  const index=p.guide.steps.findIndex(s=>s.id===task.id),done=p.completed_steps.includes(task.id),entry=noteEntry(),unresolved=state.study.discussions.filter(d=>d.step_key===task.key&&!d.resolved&&d.intent!=='feedback');
  const pref=preference(task.key)?.preference;
  if(state.toolStep!==task.key){state.toolStep=task.key;state.studyTool=pref==='split'?'adjust':pref==='prerequisite'?'context':null;}
  const panel=(name,title,content)=>`<section class="learning-tool-panel" id="tool-${name}" data-study-panel="${name}" ${state.studyTool===name?'':'hidden'}><div class="tool-panel-heading"><h3>${title}</h3><button class="text-button" data-action="close-study-tool" aria-label="收起${title}">收起 ×</button></div>${content}</section>`;
  return `<div class="study-toolbar"><span>${state.resumed?'上次学到这里':'当前任务'} <span class="toolbar-divider">/</span> 第 ${index+1} 步</span><button class="button small" data-action="focus" aria-pressed="${state.focus}">${state.focus?'退出专注':'专注阅读'} ${icon('focus')}</button></div>
    ${p.guide.steps.every(s=>p.completed_steps.includes(s.id))?'<div class="route-finished" role="status">全部步骤已记录完成，可继续回顾。</div>':''}
    <article class="study-sheet task-focus">
      <div class="lesson-meta"><span>STEP ${String(index+1).padStart(2,'0')} <span>/ ${String(p.guide.steps.length).padStart(2,'0')}</span></span><span class="task-state">${p.guide.mode==='ai'?'<span title="AI 安排的任务，请结合原文核对">AI 路线</span>':''}<span class="lesson-status ${done?'finished':''}">${done?'自报完成':'进行中'}</span></span></div>
      <h2 id="study-title" tabindex="-1">${esc(task.title)}</h2>
      <section class="task-action"><h3>现在做</h3>${instructionCopy(task.action)}${task.original_code?`<pre class="task-original-code"><code>${highlightCode(task.original_code)}</code></pre><p class="task-code-note">原文示例 · 沿用前一步的上下文</p>`:''}${taskReferences(task.evidence)}</section>
      <section class="task-outcome"><span class="outcome-mark">${icon('check')}</span><div><h3>做到什么程度</h3><p>${lessonText(task.expected)}</p></div></section>
      <div class="task-primary-actions"><button class="text-button" data-action="study-tool" data-tool="context" aria-controls="tool-context" aria-expanded="${state.studyTool==='context'}">${icon('book')} 前提与位置</button><button class="button ${done?'':'primary'}" data-action="complete" data-step="${esc(task.id)}" aria-pressed="${done}" ${state.progressBusy?'disabled':''}>${done?'撤销完成':nextStudyStep(p,task.id)?'完成，继续':'标记完成'} ${icon(done?'check':'arrow')}</button></div>
      <div class="task-support"><span>需要帮助？</span><button class="text-button" data-action="open-help" data-intent="explain">解释这段</button><button class="text-button" data-action="open-help" data-intent="hint">给个提示</button><button class="text-button" data-action="open-help" data-intent="error">排查报错</button></div>
    </article>
    <div class="study-tools"><div class="tool-launchers" aria-label="学习工具">${[['help','问答',unresolved.length||''],['notes','笔记',entry.dirty?'未保存':entry.text?'1':''],['practice','练习',''],['run','运行',''],['adjust','调整',pref?'已调整':'']].map(([name,label,count])=>`<button data-action="study-tool" data-tool="${name}" aria-controls="tool-${name}" aria-expanded="${state.studyTool===name}">${icon({help:'spark',notes:'edit',practice:'check',run:'source',adjust:'route'}[name])}<span>${label}</span>${count?`<small>${count}</small>`:''}</button>`).join('')}</div>
      ${panel('context','开始前',`<div class="task-location"><strong>操作位置</strong><span>${esc(task.where)}</span></div><details class="task-prerequisites" ${preference(task.key)?.preference==='prerequisite'?'open':''}><summary>开始前 · 环境与概念</summary>${task.prerequisites.length?task.prerequisites.map(item=>`<div><h3>${esc(item.title)}</h3><p>${esc(item.detail)}</p>${refs(item.evidence)}</div>`).join(''):'<p>原文没有提供明确前提，请先核对项目说明中的环境、工作目录与依赖。</p>'}${task.concepts.map(c=>`<details><summary>${esc(c.title)}</summary><p>${esc(c.detail)}</p>${refs(c.evidence)}</details>`).join('')}</details>${task.implementations?.length?`<details class="task-prerequisites"><summary>沿示例找到实现 · ${task.implementations.length} 处同名定义</summary><p>根据原文中的调用名称定位；请核对模块与实际调用关系。阅读区左箭头可返回。</p>${task.implementations.map(item=>`<div><strong>${esc(item.title)}</strong>${refs(item.evidence)}</div>`).join('')}</details>`:''}<details class="study-overview"><summary><span>项目导读</span>${icon('chevron')}</summary><div><p class="overview-text">${esc(p.guide.overview)}</p>${refs(p.guide.overview_evidence)}</div></details>${p.guide.commands.length?`<details class="study-commands"><summary>原文命令 · ${p.guide.commands.length} 条</summary><p class="tiny muted">未执行，请核对环境和运行位置。</p><div class="commands">${p.guide.commands.map(c=>`<code>${esc(c.text)}</code>${refs(c.evidence)}`).join('')}</div></details>`:''}`)}
      ${panel('help','围绕当前任务提问',`<section id="help-region">${helpView(task)}</section>`)}
      ${panel('notes','这一步的笔记',`<details class="lesson-notes" open><summary><span>${icon('edit')} 随手记</span><span>本机保存</span></summary><label class="sr-only" for="step-note">当前步骤的学习笔记</label><textarea id="step-note" maxlength="12000" placeholder="记录理解、实际输出和未解决的问题…">${esc(entry.text)}</textarea><div class="note-tools"><span id="note-status" role="status">${esc(noteMessage(entry))}</span><button class="text-button" data-action="note-retry">保存</button><button class="text-button" data-action="note-anchor">关联当前原文</button></div><div id="note-refs">${refs(entry.evidence)}</div></details>`)}
      ${panel('practice','检查一下理解',`<details class="exercise-panel"><summary>练一练 · 可选</summary><p class="tiny muted">反馈用于回顾理解，不计为自动验收或掌握证明。</p><form id="exercise-form"><label>选择练习<select id="exercise-kind">${task.exercises.map(e=>`<option value="${e.id}">${e.title}</option>`).join('')}</select></label><p id="exercise-prompt">${esc(task.exercises[0].prompt)}</p><label class="sr-only" for="exercise-answer">你的回答</label><textarea id="exercise-answer" maxlength="4000" required placeholder="先写下你的判断和依据，再查看反馈…"></textarea><div class="row"><button class="button small primary" type="submit">保存回答并查看反馈</button><button class="text-button" type="button" data-action="open-reference">回看原文</button></div></form>${discussionRows(task.key,true)}</details>`)}
      ${panel('run','运行 Python 示例',`<details class="exercise-panel run-panel"><summary>运行检查 · 可选</summary><p class="tiny muted">粘贴完整的 Python 示例，在隔离环境运行。项目副本只读、无网络、最多 5 秒，不自动安装依赖。需要系统库或外部服务的项目可能无法在这里运行。</p><form id="run-form"><label for="run-code">要执行的代码（包含必要的导入与前置步骤）</label><textarea id="run-code" maxlength="6000" required spellcheck="false" placeholder="粘贴完整 Python 示例…">${esc(state.runDrafts?.get(task.key)||'')}</textarea><button class="button small" type="submit" ${state.runPending?'disabled':''}>${state.runPending?'正在隔离运行…':'运行并保存实际结果'}</button></form><p class="tiny muted">执行结束只说明代码运行情况；未设置独立行为断言，不计为掌握证明。</p><div id="run-results">${runRows(task.key)}</div></details>`)}
      ${panel('adjust','调整这一步',`<div id="adapt-region">${adjustmentView(task)}</div>`)}
    </div>
    <nav class="lesson-pagination" aria-label="步骤翻页"><button data-action="select-step" data-step="${esc(p.guide.steps[index-1]?.id||'')}" ${index===0?'disabled':''}>← 上一步</button><span>${index+1} / ${p.guide.steps.length}</span><button data-action="select-step" data-step="${esc(p.guide.steps[index+1]?.id||'')}" ${index===p.guide.steps.length-1?'disabled':''}>下一步 →</button></nav>`;
}

function responseView(response){return `<span class="pill ${response.origin==='ai_feedback'?'warn':'local'}">${response.origin==='ai_feedback'?'AI 反馈 · 未独立验证':'本地阅读线索'}</span><p class="answer-text">${esc(response.answer)}</p>${refs(response.evidence)}<ol class="answer-actions">${response.next_actions.map(a=>`<li>${esc(a.text)}${refs(a.evidence)}</li>`).join('')}</ol>${response.uncertainties.length?`<p class="answer-uncertainty">仍需确认：${response.uncertainties.map(esc).join('；')}</p>`:''}`;}
function runRows(key){return (state.study?.run_checks||[]).filter(r=>!key||r.step_key===key).slice(key?-20:0).reverse().map(r=>`<details class="discussion run-result"><summary>${esc(r.title)} · ${{passed:'执行结束',failed:'运行失败',timeout:'运行超时',blocked:'环境阻止运行'}[r.execution.status]||esc(r.execution.status)}</summary><p class="tiny muted">${esc(r.note)} · ${r.execution.duration_seconds} 秒</p><pre>${esc(r.code)}</pre><h4>标准输出</h4><pre>${esc(r.execution.stdout||'（空）')}</pre><h4>错误输出</h4><pre>${esc(r.execution.stderr||'（空）')}</pre>${refs(r.evidence)}${r.execution.status!=='passed'?`<button class="text-button" data-action="run-error-help" data-id="${r.id}">带着这次结果排错</button>`:''}</details>`).join('');}
function discussionRows(key,exercise=false){
  const rows=(state.study?.discussions||[]).filter(d=>(!key||d.step_key===key)&&(exercise?d.intent==='feedback':d.intent!=='feedback'));
  return (key?rows.slice(-12):rows).map(d=>`<details class="discussion"><summary>${d.resolved?'✓ ':''}${esc(d.question.slice(0,100))}</summary><p class="tiny muted">${esc(d.title)} · ${esc(d.at.slice(0,16).replace('T',' '))}</p>${d.exercise?`<p>${esc(d.exercise.prompt)}</p><blockquote>${esc(d.question)}</blockquote>`:`<p class="answer-text">${esc(d.question)}</p>`}${d.error?`<details><summary>当时的命令与报错</summary><pre>${esc(d.environment+'\n'+d.command+'\n'+d.error)}</pre></details>`:''}${responseView(d.response)}<button class="text-button" data-action="resolve-question" data-id="${d.id}" data-resolved="${!d.resolved}">${d.resolved?'重新标为待回顾':'标记为已解决'}</button></details>`).join('')+(key&&rows.length>12?'<button class="text-button" data-action="project-tab" data-tab="journal">在学习记录中查看全部讨论</button>':'');
}
function helpView(task){
  const key=task.key,draft=state.helpDrafts.get(key)||{},intent=state.helpIntent,labels={ask:'围绕这一步提问',explain:'解释选中的原文',hint:'给一点提示',error:'一起定位报错',feedback:'练习反馈'};
  return `<details class="study-help" ${state.helpOpen?'open':''}><summary>${icon('spark')} ${labels[intent]||labels.ask} <span>带原文依据</span></summary><div class="help-context">关联：${esc(task.title)}${state.selection?` · ${esc(state.selection.path)}:${state.selection.start_line}–${state.selection.end_line}`:''}</div><form id="help-form"><label class="sr-only" for="help-question">你的问题</label><textarea id="help-question" maxlength="4000" required placeholder="哪里还不理解？">${esc(draft.question||({explain:'请解释选中的原文如何用于当前任务。',hint:'请给我一个小提示，先不要给出完整答案。',error:'请根据实际报错帮我确定下一项检查操作。'}[intent]||''))}</textarea>${intent==='error'?`<label>运行环境<input id="help-environment" maxlength="1000" placeholder="例如：Windows / Python 版本 / 虚拟环境" value="${esc(draft.environment||'')}"></label><label>实际运行的命令<input id="help-command" maxlength="2000" placeholder="粘贴实际命令" value="${esc(draft.command||'')}"></label><label>实际报错<textarea id="help-error" maxlength="6000" required placeholder="粘贴完整的关键报错…">${esc(draft.error||'')}</textarea></label>`:''}<div class="row"><button class="button small primary" type="submit" ${state.helpPending?'disabled':''}>${state.helpPending?'正在生成…':state.config.ai_available?'查看发送内容':'获取本地线索'}</button>${state.config.ai_available?'<button class="text-button" type="button" data-action="help-local">仅查看本地线索</button>':''}</div><p id="help-status" role="status" class="tiny muted">${state.helpPending?'请求处理中，可离开页面，结果会保存在学习记录。':'会结合当前目标、步骤、原文与近期讨论。'}</p></form>${discussionRows(key)}</details>`;
}

function currentSelection(){const r=state.reader;return state.selection||(r?{path:r.path,start_line:r.first,end_line:Math.min(r.last,r.first+79)}:null);}
async function prepareStudyHelp(intent,question,useAI=true,exercise=null){
  if(state.helpPending){toast('已有问题正在生成，请稍候。');return;}
  const id=state.project.id,task=studyTask(),body=studyBody('help',{intent,question,use_ai:useAI,exercise_id:exercise,selection:currentSelection(),environment:$('#help-environment')?.value||'',command:$('#help-command')?.value||'',error:$('#help-error')?.value||''});
  const submit=$('#help-form button[type=submit]');if(submit)submit.disabled=true;
  try{
    const request=await api(`/api/projects/${id}/help-prepare`,{method:'POST',json:body});
    if(state.project?.id!==id)return;
    if(request.status==='ready'){await refreshStudy(id);toast(intent==='feedback'?'回答和反馈已保存在学习记录。':'本地线索已保存。');return;}
    state.pendingHelpReview={id,request};
    openDialog('确认问答发送内容',`<p>将发送给 ${esc(request.provider)} · ${esc(request.model)}。请核对问题、运行信息、历史讨论和原文片段。</p><div class="review-request"><h3>${esc(task.title)}</h3><p class="answer-text">${esc(request.preview.question)}</p>${request.preview.exercise?`<p>练习：${esc(request.preview.exercise.prompt)}</p>`:''}<pre>${esc([request.preview.environment,request.preview.command,request.preview.error].filter(Boolean).join('\n'))}</pre><p>学习目标：${esc(request.preview.learner.goal)}</p>${request.preview.conversation.length?`<details><summary>将发送的近期讨论</summary>${request.preview.conversation.map(d=>`<blockquote>${esc(d.question)}<p>${esc(d.answer)}</p></blockquote>`).join('')}</details>`:''}${request.preview.evidence.map(e=>`<details class="preview-item"><summary>${esc(e.path)}:${e.start_line}–${e.end_line}</summary><pre>${esc(e.text)}</pre></details>`).join('')}</div><p class="tiny muted">自动脱敏不能识别所有敏感内容；仅发送当前预览。</p><button class="button primary" data-action="help-confirm">确认发送并生成回答</button>`);
  }finally{if(submit)submit.disabled=false;}
}
async function refreshStudy(id){
  const workspace=await api(`/api/projects/${id}/workspace`);
  if(state.project?.id!==id)return;
  state.study=workspace;
  if(state.tab==='journal')$('#project-content').innerHTML=journalView();
  else if(state.tab==='route'){
    const region=$('#help-region');if(region)region.innerHTML=helpView(studyTask());
    // Exercises are refreshed without replacing an unsaved note or question.
    const panel=$('.exercise-panel:not(.run-panel)');if(panel){panel.querySelectorAll('.discussion').forEach(d=>d.remove());panel.insertAdjacentHTML('beforeend',discussionRows(studyTask().key,true));}
    if($('#run-results'))$('#run-results').innerHTML=runRows(studyTask().key);
  }
}
function pollStudyHelp(id,requestID){
  clearTimeout(state.helpPoll);
  const tick=async()=>{
    try{
      const job=await api(`/api/projects/${id}/help-status?id=${requestID}`);
      if(['queued','running'].includes(job.status)){if(state.project?.id===id)state.helpPoll=setTimeout(tick,900);return;}
      if(state.project?.id!==id)return;
      state.helpPending=null;await refreshStudy(id);
      if(job.status==='failed')toast('回答未完成：'+job.error);else toast('回答已保存到学习记录。');
    }catch(error){if(state.project?.id===id){state.helpPending=null;toast(error.message);}}
  };state.helpPoll=setTimeout(tick,700);
}

function journalView(){
  const w=state.study;if(!w)return '<p>正在读取记录…</p>';
  const notes=Object.values(w.notes).filter(n=>n.text),routes=Object.values(w.routes),unresolved=w.discussions.filter(d=>!d.resolved&&d.intent!=='feedback');
  const drafts=[...state.noteDrafts.values()].filter(d=>d.project===state.project.id&&d.dirty);
  return `<div class="journal-head"><div><h2>我的学习记录</h2><p class="tiny muted">${notes.length} 条笔记 · ${unresolved.length} 个待解决问题 · ${routes.length} 个路线版本</p></div><button class="button small" data-action="export-journal">导出学习记录</button></div>
    ${drafts.length?`<section class="panel"><h3>未保存的草稿</h3><p class="tiny muted">这些内容仍在本页或浏览器中，请保存或复制备份。</p>${drafts.map(d=>`<details><summary>${esc(d.title)}</summary><pre class="journal-note">${esc(d.text)}</pre></details>`).join('')}</section>`:''}
    <section class="panel"><h3>笔记与原文</h3>${notes.length?notes.map(n=>`<article class="journal-entry"><h3>${esc(n.title)}</h3><p class="journal-note">${esc(n.text)}</p>${refs(n.evidence)}${w.tasks.some(t=>t.key===n.key)?`<button class="text-button" data-action="select-step" data-step="${esc(w.tasks.find(t=>t.key===n.key).id)}">返回这一步</button>`:'<span class="tiny muted">来自历史路线，已保留</span>'}</article>`).join(''):'<p class="muted">还没有笔记。可在任务页记录理解并关联原文。</p>'}</section>
    <section class="panel"><h3>问题与排错</h3>${discussionRows(null)||'<p class="muted">还没有问题记录。</p>'}</section><section class="panel"><h3>练习与反馈</h3>${discussionRows(null,true)||'<p class="muted">练习是可选的，反馈不会改变完成状态。</p>'}</section><section class="panel"><h3>实际运行记录</h3><p class="tiny muted">实际执行结果单独记录，没有独立行为断言，不自动改变学习进度。</p>${runRows(null)||'<p class="muted">还没有运行记录。</p>'}</section>
    <section class="panel"><h3>路线版本与调整</h3>${routes.map(r=>`<details class="route-archive"><summary>${r.id===w.route_id?'当前路线':'历史路线'} · ${r.mode==='ai'?'AI':'基础'} · ${r.steps.length} 步</summary><ol>${r.steps.map(t=>`<li>${esc(t.title)}${r.completed_steps.includes(t.id)?' · 自报完成':''}</li>`).join('')}</ol></details>`).join('')}${w.events.slice().reverse().map(e=>`<p class="tiny muted">${esc(e.title)} · ${e.action==='undo'?'撤销调整':labelPreference(e.action)||'恢复原安排'}${e.undone?'（已撤销）':''}</p>`).join('')}</section>`;
}

function highlightCode(text){
  const pattern=/(#[^\n]*|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:def|class|return|import|from|as|if|else|elif|for|while|with|try|except|raise|async|await|function|const|let|var|new|export|default|true|false|None|True|False|null)\b|\b\d+(?:\.\d+)?\b)/g;
  let result='',at=0;for(const match of text.matchAll(pattern)){result+=esc(text.slice(at,match.index));const token=match[0],kind=token.startsWith('#')||token.startsWith('//')?'comment':/^['"]/.test(token)?'string':/^\d/.test(token)?'number':'keyword';result+=`<span class="syntax-${kind}">${esc(token)}</span>`;at=match.index+token.length;}return result+esc(text.slice(at));
}
function inlineDocument(text,path){
  const tokens=/(`[^`]+`|\*\*[^*]+\*\*|\[([^\]]+)\]\(([^)]+)\))/g;let out='',at=0;
  for(const m of text.matchAll(tokens)){out+=esc(text.slice(at,m.index));
    if(m[0].startsWith('`'))out+=`<code>${esc(m[0].slice(1,-1))}</code>`;
    else if(m[0].startsWith('**'))out+=`<strong>${esc(m[0].slice(2,-2))}</strong>`;
    else{
      let target=null;try{target=new URL(m[3],'https://project.invalid/'+path);}catch{}
      if(target?.origin==='https://project.invalid'){
        let relative='';try{relative=decodeURIComponent(target.pathname.slice(1));}catch{}
        out+=state.project?.guide.files.some(f=>f.path===relative)?`<button class="document-link" data-action="source" data-path="${esc(relative)}" data-anchor="${esc(target.hash.slice(1))}" data-line="1" data-end="1">${esc(m[2])}</button>`:esc(m[2]);
      }else if(target&&['https:','http:'].includes(target.protocol))out+=`<a href="${esc(target.href)}" target="_blank" rel="noopener noreferrer">${esc(m[2])} ↗</a>`;
      else out+=esc(m[2]);
    }at=m.index+m[0].length;
  }return out+esc(text.slice(at));
}
function documentMarkup(r){
  const lines=r.text.split('\n'),headings=new Map((r.outline||[]).filter(h=>h.kind==='heading').map(h=>[h.line,h]));
  let out='',i=0;const attribute=(line,end=line)=>`data-source-line="${line}" data-source-end="${end}" class="document-block ${line<=r.last&&end>=r.first?'cited-block':''}"`;
  while(i<lines.length){const line=lines[i],n=i+1;
    if(/^\s*(```|~~~)/.test(line)){const fence=line.trim().slice(0,3),start=i+1; i++;while(i<lines.length&&!lines[i].trim().startsWith(fence))i++;out+=`<pre ${attribute(start,i+1)}><code>${lines.slice(start,i).map((text,j)=>`<span data-source-line="${start+j+1}">${highlightCode(text)}</span>`).join('\n')}</code></pre>`;i++;continue;}
    if(headings.has(n)){const h=headings.get(n),level=Math.min(4,h.level+1);out+=`<h${level} ${attribute(n)}>${inlineDocument(h.title,r.path)}</h${level}>`;if(i+1<lines.length&&/^[=~\-^"`:+*#]{3,}$/.test(lines[i+1].trim()))i++;i++;continue;}
    if(/^\s*[-*+]\s+/.test(line)||/^\s*\d+[.)]\s+/.test(line)){const start=i;let rows='';while(i<lines.length&&/^\s*(?:[-*+]|\d+[.)])\s+/.test(lines[i])){rows+=`<li>${inlineDocument(lines[i].replace(/^\s*(?:[-*+]|\d+[.)])\s+/,''),r.path)}</li>`;i++;}out+=`<ul ${attribute(start+1,i)}>${rows}</ul>`;continue;}
    if(/^>\s?/.test(line)){out+=`<blockquote ${attribute(n)}>${inlineDocument(line.replace(/^>\s?/,''),r.path)}</blockquote>`;i++;continue;}
    if(/^\s*[-*_]{3,}\s*$/.test(line)){out+='<hr>';i++;continue;}
    if(!line.trim()){i++;continue;}
    out+=`<p ${attribute(n)}>${inlineDocument(line,r.path)}</p>`;i++;
  }return out||'<p>空文件</p>';
}
function rawSourceMarkup(r){return `<pre class="source-code reader-scroll" tabindex="0" aria-label="项目原文，可滚动">${r.text.split('\n').map((line,i)=>`<span data-source-line="${i+1}" class="source-line ${i+1>=r.first&&i+1<=r.last?'current':''}"><span class="line-no" aria-hidden="true">${i+1}</span>${highlightCode(line)}</span>`).join('')}</pre>`;}
function studyReaderView(){
  const r=state.reader,ready=r&&!r.loading&&!r.error,document=ready&&r.kind==='document';
  return `<div class="reader-heading"><h2>${icon('source')} 原文阅读</h2>${ready?'<button class="text-button" data-action="expand-source">放大阅读 ↗</button>':''}</div>
    <div class="reader-navigation"><button class="button small" data-action="reader-back" aria-label="上一处阅读位置" ${state.historyIndex<=0?'disabled':''}>←</button><button class="button small" data-action="reader-forward" aria-label="下一处阅读位置" ${state.historyIndex>=state.readerHistory.length-1?'disabled':''}>→</button><span>阅读历史</span>${document?`<button class="button small" data-action="reader-mode" aria-pressed="${state.readerMode==='document'}">${state.readerMode==='document'?'查看原文':'正文阅读'}</button>`:''}</div>
    ${!r?`<div class="reader-empty">${icon('book')}<h3>选择任务原文开始阅读</h3><button class="button small" data-action="project-tab" data-tab="files">浏览项目文件</button></div>`:`<div class="reader-file">${icon('book')}<span>${esc(r.path)}</span></div><div class="reader-caption"><span>项目原文</span><span>引用 L${r.first}–${r.last}</span></div>${r.loading?'<p class="reader-message" role="status">正在读取原文…</p>':r.error?`<div class="reader-message" role="alert"><p>${esc(r.error)}</p><button class="button small" data-action="source" data-path="${esc(r.path)}" data-line="${r.first}" data-end="${r.last}">重新读取</button></div>`:`<details class="reader-search-tools"><summary>查找内容 / 定位章节与函数</summary><div class="reader-controls"><label class="sr-only" for="source-find">在当前文件中查找</label><input id="source-find" placeholder="在当前文件中查找…" value="${esc(r.query||'')}"><label class="sr-only" for="source-outline">章节或函数定位</label><select id="source-outline"><option value="">${document?'章节目录':'函数 / 类入口'}</option>${(r.outline||[]).map(h=>`<option value="${h.line}">${esc(h.title)} · L${h.line}</option>`).join('')}</select></div><div id="source-matches" class="source-matches" role="status"></div></details>${state.readerMode==='document'&&document?`<div class="document-reading reader-scroll" tabindex="0" aria-label="文档正文">${documentMarkup(r)}</div>`:rawSourceMarkup(r)}<div class="reader-excerpt-note"><span>${state.readerScope==='full'?'完整原文':`当前节选 L${readerBounds(r).first}–${readerBounds(r).last}`}</span><button class="text-button" data-action="reader-scope">${state.readerScope==='full'?'回到当前引用':'展开全文'}</button></div><div class="reader-help"><button class="text-button" data-action="reader-explain">解释选中内容</button><button class="text-button" data-action="note-anchor">关联到笔记</button><span id="selected-lines">${state.selection?`已选择 L${state.selection.start_line}–${state.selection.end_line}`:'可选择文字后提问'}</span></div>`}<div class="reader-footer"><span class="source-legend"></span> 原文引用范围 · ${state.readerMode==='document'?'正文排版，原始行号可切换查看':'代码按原文显示'}</div>`}`;
}
function readerBounds(reader){
  const total=reader.text.split('\n').length,first=Math.min(total,Math.max(1,reader.first));
  return {first,last:Math.min(total,Math.max(first,Math.min(reader.last,first+21)))};
}
function applyReaderScope(){
  const r=state.reader,box=$('#source-reader .reader-scroll');if(!box||!r?.text)return;
  const range=readerBounds(r),all=state.readerScope==='full';
  for(const el of box.children){
    const start=Number(el.dataset.sourceLine),end=Number(el.dataset.sourceEnd||start);
    el.hidden=!all&&(!start||end<range.first||start>range.last);
    if(el.matches('pre'))el.querySelectorAll('code > [data-source-line]').forEach(line=>line.hidden=!all&&(Number(line.dataset.sourceLine)<range.first||Number(line.dataset.sourceLine)>range.last));
  }
}
function jumpReader(line){
  if(state.reader?.text&&state.readerScope!=='full'){const range=readerBounds(state.reader);if(line<range.first||line>range.last){state.readerScope='full';renderStudyReader(0);}}
  const box=$('#source-reader .reader-scroll');if(!box)return;
  const blocks=[...box.querySelectorAll('[data-source-line]')].filter(el=>!el.hidden&&!el.closest('[hidden]')),target=blocks.find(el=>Number(el.dataset.sourceLine)>=line)||blocks.at(-1);
  if(target){box.scrollTop+=target.getBoundingClientRect().top-box.getBoundingClientRect().top-box.clientHeight/4;box.querySelector('.search-target')?.classList.remove('search-target');target.classList.add('search-target');}saveStudyPosition();
}
function renderStudyReader(restore=null){
  const pane=$('#source-reader');if(!pane)return;pane.innerHTML=studyReaderView();applyReaderScope();
  if(state.reader&&!state.reader.loading&&!state.reader.error){if(restore!==null){const box=pane.querySelector('.reader-scroll');if(box)box.scrollTop=restore;}else jumpReader(state.reader.first);}
}
async function readStudySource(button,reveal=true,options={}){
  const p=state.project;if(!p)return;
  const path=button.dataset.path,first=Math.max(1,Number(button.dataset.line)||1),last=Math.max(first,Number(button.dataset.end)||first),request=++state.sourceRequest;
  if(!options.history&&state.reader&&!state.reader.loading&&state.historyIndex>=0){const old=state.readerHistory[state.historyIndex];if(old){old.scroll=$('#source-reader .reader-scroll')?.scrollTop||0;old.mode=state.readerMode;}}
  state.reader={path,first,last,loading:true};state.selection=null;state.readerScope=options.scroll>0?'full':'excerpt';
  if(reveal){state.focus=false;$('.study-workspace')?.classList.remove('is-focused');const b=$('[data-action=focus]');if(b){b.setAttribute('aria-pressed','false');b.innerHTML='专注阅读 '+icon('focus');}}
  if(!options.history){state.readerHistory=state.readerHistory.slice(0,state.historyIndex+1);const previous=state.readerHistory.at(-1);if(!previous||previous.path!==path||previous.start_line!==first){state.readerHistory.push({path,start_line:first,end_line:last});state.readerHistory=state.readerHistory.slice(-30);}state.historyIndex=state.readerHistory.length-1;}
  renderStudyReader();if(reveal&&innerWidth<=1100)$('#source-reader')?.scrollIntoView({block:'start'});
  try{
    const data=await api(`/api/projects/${p.id}/source?path=${encodeURIComponent(path)}`);
    if(state.project?.id!==p.id||state.sourceRequest!==request)return;
    state.reader={...data,first,last,loading:false};state.readerMode=options.mode||(data.kind==='document'?'document':'source');
    renderStudyReader(options.scroll??null);
    if(button.dataset.anchor){const slug=s=>s.toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu,'').replace(/\s+/g,'-');const heading=data.outline?.find(h=>slug(h.title)===button.dataset.anchor);if(heading)jumpReader(heading.line);}
    saveStudyPosition();
  }catch(error){if(state.project?.id!==p.id||state.sourceRequest!==request)return;state.reader={path,first,last,error:error.message,loading:false};renderStudyReader();}
}
function resumeStudyReader(p){
  if(state.tab!=='route'||state.reader)return;
  const saved=state.restoreReader;state.restoreReader=null;
  const ref=saved||selectedStep(p)?.evidence?.[0];if(ref)void readStudySource({dataset:{path:ref.path,line:ref.start_line,end:ref.end_line}},false,saved?{history:true,mode:saved.mode,scroll:saved.scroll}:{});
}

document.addEventListener('input',e=>{
  if(e.target.id==='run-code'){state.runDrafts??=new Map();state.runDrafts.set(studyTask().key,e.target.value);}
  if(e.target.id==='step-note'){
    const entry=noteEntry();entry.text=e.target.value;entry.dirty=true;entry.error=null;
    showNoteStatus(backupNote(entry)?'草稿已备份，正在保存到本机服务…':'浏览器草稿备份不可用，正在保存到本机服务…');
    clearTimeout(state.noteTimer);state.noteTimer=setTimeout(()=>flushStudyNote(),600);
  }
  if(e.target.closest('#help-form')&&studyTask())state.helpDrafts.set(studyTask().key,{question:$('#help-question')?.value,environment:$('#help-environment')?.value,command:$('#help-command')?.value,error:$('#help-error')?.value});
  if(e.target.id==='source-find'&&state.reader?.text){const query=e.target.value;state.reader.query=query;const matches=query?state.reader.text.split('\n').map((line,i)=>({line,i})).filter(x=>x.line.toLowerCase().includes(query.toLowerCase())):[];$('#source-matches').innerHTML=query?`<p>${matches.length} 处匹配</p>`+matches.slice(0,60).map(x=>`<button data-action="reader-jump" data-line="${x.i+1}">L${x.i+1} · ${esc(x.line.slice(0,130))}</button>`).join(''):'';}
});
document.addEventListener('change',async e=>{
  try{
    if(e.target.id==='source-outline'&&e.target.value)jumpReader(Number(e.target.value));
    if(e.target.id==='exercise-kind')$('#exercise-prompt').textContent=studyTask().exercises.find(x=>x.id===e.target.value).prompt;
    if(e.target.matches('[data-microtask]'))await studyMutation(studyBody('subtask',{completed:[...document.querySelectorAll('[data-microtask]:checked')].map(x=>Number(x.dataset.microtask))}));
  }catch(error){toast(error.message);}
});
document.addEventListener('scroll',e=>{if(e.target.matches?.('#source-reader .reader-scroll'))saveStudyPosition();},true);
document.addEventListener('selectionchange',()=>{
  const selection=getSelection();if(!selection||selection.isCollapsed)return;
  const anchor=selection.anchorNode?.parentElement?.closest('[data-source-line]'),focus=selection.focusNode?.parentElement?.closest('[data-source-line]');
  if(!anchor||!focus||!$('#source-reader')?.contains(anchor)||!$('#source-reader').contains(focus)||!state.reader)return;
  const first=Math.min(Number(anchor.dataset.sourceLine),Number(focus.dataset.sourceLine)),last=Math.max(Number(anchor.dataset.sourceEnd||anchor.dataset.sourceLine),Number(focus.dataset.sourceEnd||focus.dataset.sourceLine));
  state.selection={path:state.reader.path,start_line:first,end_line:Math.min(last,first+79)};const label=$('#selected-lines');if(label)label.textContent=`已选择 L${first}–${Math.min(last,first+79)}`;
});
document.addEventListener('submit',async e=>{
  if(e.target.id==='run-form'){
    e.preventDefault();if(state.runPending)return;state.runPending=true;const id=state.project.id,button=e.target.querySelector('button');button.disabled=true;button.textContent='正在隔离运行…';
    try{await api(`/api/projects/${id}/run-check`,{method:'POST',json:studyBody('run',{code:$('#run-code').value})});await refreshStudy(id);toast('实际运行结果已单独保存。');}catch(error){toast(error.message);}finally{state.runPending=false;button.disabled=false;button.textContent='运行并保存实际结果';}return;
  }
  if(!['help-form','exercise-form'].includes(e.target.id))return;e.preventDefault();
  try{if(e.target.id==='help-form')await prepareStudyHelp(state.helpIntent,$('#help-question').value.trim());else await prepareStudyHelp('feedback',$('#exercise-answer').value.trim(),true,$('#exercise-kind').value);}catch(error){toast(error.message);}
});
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;
  try{
    if(action==='study-tool')showStudyTool(state.studyTool===b.dataset.tool?null:b.dataset.tool,true);
    if(action==='close-study-tool'){const name=state.studyTool;showStudyTool(null);document.querySelector(`[data-action=study-tool][data-tool="${name}"]`)?.focus({preventScroll:true});}
    if(action==='dismiss-resume'){state.resumed=false;$('.resume-banner')?.remove();}
    if(action==='adapt-propose'){state.adjustProposal=b.dataset.preference;$('#adapt-region').innerHTML=adjustmentView(studyTask());}
    if(action==='adapt-cancel'){state.adjustProposal=null;$('#adapt-region').innerHTML=adjustmentView(studyTask());}
    if(action==='adapt-apply'||action==='adapt-undo'){
      const current=studyTask().id;b.disabled=true;await studyMutation(studyBody(action==='adapt-undo'?'undo-adjust':'adjust',{preference:b.dataset.preference}));state.adjustProposal=null;
      if(['known','later'].includes(b.dataset.preference)){const next=nextStudyStep(state.project,current);if(next){selectStudyStep(next.id);return;}}
      await flushStudyNote();if(b.dataset.preference==='prerequisite')state.studyTool='context';projectView(state.project);toast(action==='adapt-undo'?'已撤销路线调整。':'已采用调整，随时可以撤销。');
    }
    if(action==='note-retry'){
      const entry=noteEntry();await flushStudyNote();
      if(entry.error){const workspace=await api(`/api/projects/${entry.project}/workspace`),saved=workspace.notes[entry.key];if(saved&&saved.version!==entry.version){state.noteMerge={entry,version:saved.version};openDialog('合并笔记修改',`<p>另一页面保存了不同内容。请核对两份笔记，编辑下面的合并结果后保存。</p><h3>服务中已有内容</h3><pre class="journal-note">${esc(saved.text)}</pre><label for="note-merge-text">合并后的内容</label><textarea id="note-merge-text" maxlength="12000">${esc(saved.text+'\n\n'+entry.text)}</textarea><button class="button primary" data-action="note-merge-save">保存合并结果</button>`);}}
    }
    if(action==='note-merge-save'){const {entry,version}=state.noteMerge;entry.text=$('#note-merge-text').value;entry.version=version;entry.dirty=true;entry.error=null;backupNote(entry);await flushStudyNote();if(!entry.error){$('#detail-dialog').close();if($('#step-note'))$('#step-note').value=entry.text;}}
    if(action==='run-error-help'){
      const run=state.study.run_checks.find(r=>r.id===b.dataset.id);if(!run)return;
      const task=state.study.tasks.find(t=>t.key===run.step_key);if(task)selectStudyStep(task.id);else{state.tab='route';projectView(state.project);}
      state.helpDrafts.set(studyTask().key,{question:'请根据这次实际隔离运行结果，给出下一项检查操作。',environment:'ExampleProof Bubblewrap / 系统 Python / 无网络 / 无第三方依赖安装',command:'运行已提交的 Python 示例',error:((run.execution.stderr||run.execution.status).slice(0,3500)+'\n提交代码（可能截断）：\n'+run.code.slice(0,2300))});state.helpIntent='error';state.helpOpen=true;$('#help-region').innerHTML=helpView(studyTask());showStudyTool('help');$('#help-region').scrollIntoView({block:'center'});
    }
    if(action==='note-anchor'){
      const entry=noteEntry(),ref=currentSelection();if(!ref){toast('先打开一处原文。');return;}entry.evidence=[ref];entry.dirty=true;backupNote(entry);if($('#note-refs'))$('#note-refs').innerHTML=refs(entry.evidence);await flushStudyNote();showStudyTool('notes',true);toast('已将当前原文关联到笔记。');
    }
    if(action==='open-help'||action==='reader-explain'){
      if(state.tab!=='route'){state.tab='route';projectView(state.project);}
      state.helpIntent=action==='reader-explain'?'explain':b.dataset.intent;state.helpOpen=true;$('#help-region').innerHTML=helpView(studyTask());showStudyTool('help');$('#help-region').scrollIntoView({block:'center'});$('#help-question').focus({preventScroll:true});
    }
    if(action==='help-local')await prepareStudyHelp(state.helpIntent,$('#help-question').value.trim(),false);
    if(action==='help-confirm'){
      const pending=state.pendingHelpReview;if(!pending)return;b.disabled=true;
      const job=await api(`/api/projects/${pending.id}/help-send`,{method:'POST',json:{request_id:pending.request.id,approval:pending.request.approval}});
      $('#detail-dialog').close();state.pendingHelpReview=null;
      if(state.project?.id===pending.id){state.helpPending=job;$('#help-region').innerHTML=helpView(studyTask());pollStudyHelp(pending.id,job.id);}
    }
    if(action==='resolve-question'){await studyMutation({action:'resolve',id:b.dataset.id,resolved:b.dataset.resolved==='true'});await refreshStudy(state.project.id);}
    if(action==='export-journal'){
      await flushStudyNote();const response=await fetch(`/api/projects/${state.project.id}/journal`);if(!response.ok)throw Error('导出未完成，请重试。');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=state.project.name.replace(/[\\/]/g,'-')+'-学习记录.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    if(action==='reader-back'||action==='reader-forward'){
      const index=state.historyIndex+(action==='reader-back'?-1:1),ref=state.readerHistory[index];if(ref){saveStudyPosition();state.historyIndex=index;await readStudySource({dataset:{path:ref.path,line:ref.start_line,end:ref.end_line}},false,{history:true,scroll:ref.scroll,mode:ref.mode});}
    }
    if(action==='reader-scope'){state.readerScope=state.readerScope==='full'?'excerpt':'full';renderStudyReader();saveStudyPosition();}
    if(action==='reader-mode'){state.readerMode=state.readerMode==='document'?'source':'document';renderStudyReader();saveStudyPosition();}
    if(action==='reader-jump')jumpReader(Number(b.dataset.line));
    if(action==='open-reference'){const ref=studyTask().evidence[0];if(ref)await readStudySource({dataset:{path:ref.path,line:ref.start_line,end:ref.end_line}});}
    if(action==='regenerate'){
      await flushStudyNote();if([...state.noteDrafts.values()].some(n=>n.project===state.project.id&&n.dirty))throw Error('请先保存或复制未保存的笔记，再重新规划。');
      const id=state.project.id,review=await api(`/api/projects/${id}/regenerate-preview`,{method:'POST',json:{}});state.regeneration={id,approval:review.preview.approval};
      openDialog('重新规划学习路线',`<p>将生成新的路线版本。已有笔记、问答、练习与旧路线完成记录会保留在学习记录中。</p><p>目标：${esc(review.payload.learner.goal)}</p>${review.payload.evidence.map(e=>`<details class="preview-item"><summary>${esc(e.path)}:${e.start_line}–${e.end_line}</summary><pre>${esc(e.text)}</pre></details>`).join('')}<p class="tiny muted">将发送给 ${esc(review.preview.provider)} · ${esc(review.preview.model)}；请核对这些片段适合发送。</p><button class="button primary" data-action="regenerate-send">确认发送并重新规划</button>`);
    }
    if(action==='regenerate-send'){
      const plan=state.regeneration;if(!plan)return;b.disabled=true;const p=await api(`/api/projects/${plan.id}/analyze`,{method:'POST',json:{approval:plan.approval,regenerate:true}});$('#detail-dialog').close();
      if(state.project?.id===p.id){state.study=null;state.reader=null;state.selectedStep=null;projectView(p);await openProject(p.id);}
    }
  }catch(error){toast(error.message);b.disabled=false;}
});
window.addEventListener('beforeunload',e=>{if([...state.noteDrafts.values()].some(n=>n.dirty)){void flushStudyNote();e.preventDefault();e.returnValue='';}});
matchMedia('(max-width:760px)').addEventListener('change',event=>{if(event.matches&&$('.course-outline'))$('.course-outline').open=false;});
