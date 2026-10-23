'use strict';
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={config:null,project:null,tab:'route',timer:null,file:null,importMode:'github',busy:false,selectedStep:null,reader:null,sourceRequest:0,focus:false,progressBusy:false,notes:new Map(),noteFailures:new Set()};
const levels={beginner:'刚开始',familiar:'有基础',experienced:'深入源码'};
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4500);}
async function api(path,options={}){const headers={...(options.headers||{})};if(options.method==='POST')headers['X-ExampleProof-Token']=state.config.csrf;if(options.json){headers['Content-Type']='application/json';options.body=JSON.stringify(options.json);delete options.json;}const response=await fetch(path,{...options,headers});const value=await response.json();if(!response.ok)throw Error(value.error||'请求未完成，请重试。');return value;}
const refs=items=>`<div class="refs">${(items||[]).map(e=>`<button class="ref" data-action="source" data-path="${esc(e.path)}" data-line="${e.start_line}" data-end="${e.end_line}">↗ ${esc(e.path)}:${e.start_line}</button>`).join('')}</div>`;
const icons={
  route:'<path d="M5 5h4M5 12h4M5 19h4M13 5h6M13 12h6M13 19h6"/><circle cx="6" cy="5" r="2"/><circle cx="6" cy="12" r="2"/><circle cx="6" cy="19" r="2"/>',
  assessment:'<path d="M4 19V5M4 19h16M9 15v-4M14 15V7M19 15v-7"/>',
  files:'<path d="M3 7V5a1 1 0 0 1 1-1h6l2 3h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  source:'<path d="m9 7-5 5 5 5m6-10 5 5-5 5"/>',
  book:'<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4V4Zm9 3a3 3 0 0 1 3-3h5v15h-4a4 4 0 0 0-4 2"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
  github:'<circle cx="12" cy="12" r="9"/><path d="m9 8-4 4 4 4m6-8 4 4-4 4"/>',
  focus:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  chevron:'<path d="m6 9 6 6 6-6"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  edit:'<path d="m15 4 5 5-10 10-6 1 1-6L15 4ZM12 7l5 5"/>',
  spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>'
};
const icon=name=>`<svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.source}</svg>`;
const motionPreference=matchMedia('(prefers-reduced-motion:reduce)'),motionAnimations=new Set();
const motionAllowed=()=>!motionPreference.matches;
function stopInterfaceMotion(){for(const animation of motionAnimations)animation.cancel();motionAnimations.clear();}
motionPreference.addEventListener('change',event=>{if(event.matches)stopInterfaceMotion();});
function animateInterface(element,frames,options={}){
  if(!element?.isConnected||!element.animate||!motionAllowed())return;
  const animation=element.animate(frames,{duration:360,easing:'cubic-bezier(.2,.7,.2,1)',...options});
  motionAnimations.add(animation);
  const release=()=>motionAnimations.delete(animation);
  animation.finished.then(release,release);
  animation.addEventListener('finish',release,{once:true});animation.addEventListener('cancel',release,{once:true});
  return animation;
}
function revealInterface(elements){
  [...elements].filter(Boolean).slice(0,8).forEach((element,index)=>animateInterface(element,[{opacity:.4,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}],{delay:index*35}));
}
function workspaceEmblem(){
  return `<span class="workspace-emblem" aria-hidden="true"><span class="emblem-orbit"></span><span class="emblem-tile emblem-source">${icon('source')}</span><span class="emblem-tile emblem-book">${icon('book')}</span><span class="emblem-spark">${icon('spark')}</span></span>`;
}
function captureWorkspaceMotion(){
  const progress=$('.route-progress progress');
  return {key:$('#main').dataset.motionView,project:$('#main').dataset.motionProject,tab:$('#main').dataset.motionTab,marker:$('.workspace-tab-marker')?.getBoundingClientRect(),ratio:progress?progress.value/progress.max:null,lastAnswer:$('.conversation-turn:last-child')?.id};
}
function animateWorkspace(previous,p){
  const main=$('#main'),key=JSON.stringify([p.id,state.tab,state.tab==='route'?state.selectedStep:null]);
  main.dataset.motionView=key;main.dataset.motionProject=p.id;main.dataset.motionTab=state.tab;
  const changedProject=previous.project!==p.id;
  if(changedProject)revealInterface([$('.project-head'),$('.workspace-tabs'),$('#project-content')]);
  else if(previous.key!==key)revealInterface([$('#project-content')]);
  const marker=$('.workspace-tab-marker');
  if(!changedProject&&previous.tab!==state.tab&&previous.marker&&marker){
    const current=marker.getBoundingClientRect();
    if(current.width)animateInterface(marker,[{transform:`translateX(${previous.marker.left-current.left}px) scaleX(${previous.marker.width/current.width})`},{transform:'translateX(0) scaleX(1)'}]);
  }
  const progress=$('.route-progress progress'),fill=$('.route-progress-fill');
  if(!changedProject&&progress&&previous.ratio!==null&&previous.ratio!==progress.value/progress.max){
    animateInterface(fill,[{transform:`scaleX(${previous.ratio})`},{transform:`scaleX(${progress.value/progress.max})`}],{duration:650});
    animateInterface($('.route-progress strong'),[{transform:'scale(1)'},{transform:'scale(1.1)',offset:.4},{transform:'scale(1)'}],{duration:440});
  }
  const answer=$('.conversation-turn:last-child');
  if(previous.key===key&&state.studyTool==='help'&&answer&&answer.id!==previous.lastAnswer)revealInterface([answer.querySelector('.chat-answer')]);
}
function importIllustration(){
  return `<div class="source-visual">
    <div class="source-art" aria-hidden="true"><div class="art-scene">
      <div class="art-glow"></div><div class="art-ground"></div>
      <div class="art-orbit orbit-one"></div><div class="art-orbit orbit-two"></div>
      <span class="art-spark spark-one">${icon('spark')}</span><span class="art-spark spark-two">${icon('spark')}</span>
      <div class="source-sheet sheet-back"><div class="sheet-top">${icon('source')}<span>源码</span><span class="sheet-status"></span></div><div class="code-bars"><i></i><i></i><i></i><i></i><i></i></div><div class="code-caption">read · explore · understand</div></div>
      <div class="source-sheet sheet-front"><div class="sheet-top">${icon('book')}<span>README.md</span><b>↗</b></div><div class="sheet-title"></div><div class="paper-lines"><i></i><i></i><i></i></div><div class="paper-code"><i></i><i></i><i></i></div><div class="paper-footer"><span></span><span></span><span></span></div></div>
      <div class="art-note note-route">${icon('route')}<span>学习路线</span><span class="note-dots"><i></i><i></i><i></i></span></div>
      <div class="art-note note-source"><span class="note-check">${icon('check')}</span><span>从原文开始</span></div>
    </div></div>
    <div class="art-footer"><p class="art-caption"><span class="caption-line"></span>文档与源码，始终在手边。</p></div>
  </div>`;
}

function home(){
  state.file=null;state.importMode='github';
  $('#main').innerHTML=`<div class="hero">
    <section class="hero-copy">
      <div class="entry-label"><span></span>学习空间</div>
      <h1>开始一个<br><span>新的学习项目。</span></h1>
      <p class="lead">从源码出发，找到你的下一步。</p>
      ${importIllustration()}
    </section>
    <section class="import-card" aria-labelledby="import-heading">
      <div class="import-title"><h2 id="import-heading">导入项目</h2><span class="card-symbol">${icon('files')}</span></div>
      <div class="tabs" role="tablist" aria-label="项目导入方式"><button type="button" role="tab" aria-selected="true" class="active" data-action="import-mode" data-mode="github">${icon('github')}GitHub 仓库</button><button type="button" role="tab" aria-selected="false" data-action="import-mode" data-mode="zip">${icon('upload')}上传 ZIP</button></div>
      <form id="import-form"><div id="github-input"><label class="field"><span>公开仓库地址</span><input id="repository" type="text" placeholder="https://github.com/owner/project" autocomplete="off"></label><details class="version-options"><summary>分支或版本 <span>可选</span></summary><label class="field"><span class="sr-only">分支、标签或提交</span><input id="ref" placeholder="默认最新提交" maxlength="256"><small>导入时固定到一个提交。</small></label></details></div>
      <div id="zip-input" hidden><label class="dropzone" id="dropzone" for="zip-file" tabindex="0">${icon('upload')}<strong id="file-name">选择或拖入 ZIP</strong><span>源码文件 · 最大 20 MB</span></label><input class="sr-only" id="zip-file" type="file" accept=".zip,application/zip"></div>
      <label class="field"><span>学习目标</span><textarea id="goal" maxlength="2000" required placeholder="想用这个项目完成什么？"></textarea></label><div class="examples"><button type="button" data-action="goal" data-goal="配置环境并跑通项目的第一个示例">跑通示例</button><button type="button" data-action="goal" data-goal="理解核心 API，完成一个最小可用功能">实现功能</button><button type="button" data-action="goal" data-goal="理解项目结构和核心实现，为参与贡献做准备">理解源码</button></div>
      <fieldset class="level-field"><legend>你的基础</legend><div class="levels">${Object.entries(levels).map(([k,v],i)=>`<label><input type="radio" name="level" value="${k}" ${i===0?'checked':''}><span>${v}</span></label>`).join('')}</div></fieldset>
      ${state.config.ai_available?`<label class="ai-import-option"><input id="auto-ai" type="checkbox" checked aria-describedby="ai-import-hint"><span>自动用 AI 细化学习路线</span></label><p class="ai-import-hint" id="ai-import-hint">创建后，${esc(state.config.provider)} 将使用学习目标与经自动脱敏的项目片段生成路线。取消勾选可仅在本机整理。</p>`:'<p class="ai-import-hint">尚未配置 AI，先根据项目原文生成基础路线。</p>'}
      <button class="button primary full" id="import-submit" type="submit">${state.config.ai_available?'创建 AI 学习路线':'创建学习路线'} ${icon('arrow')}</button><div id="form-error" class="error-text" role="alert"></div></form>
    </section></div>`;
}

async function projects(){
  const {projects}=await api('/api/projects');
  $('#main').innerHTML=`<div class="page-head collection-head"><div><div class="entry-label"><span></span>我的空间</div><h1>学习项目 <span class="collection-count">${projects.length}</span></h1></div><div class="collection-actions">${workspaceEmblem()}<a href="#/new" class="button primary">导入项目 ${icon('arrow')}</a></div></div>${projects.length?`<div class="project-grid">${projects.map(p=>`<a class="project-card ${p.status==='failed'?'project-failed':''}" href="#/project/${p.id}"><div class="project-card-top"><span class="project-symbol">${icon('files')}</span><span class="pill ${p.status==='failed'?'warn':p.mode==='ai'?'':'local'}">${p.status==='failed'?'导入失败':p.status==='ready'?(p.mode==='ai'?'AI 路线':'基础路线'):'处理中'}</span></div><h3>${esc(p.name)}</h3><p>${esc(p.goal)}</p><div class="card-bottom"><span>${(p.completed_steps||[]).length} / ${p.step_count} 步</span><span>${p.status==='failed'?'查看详情':'继续学习'} ${icon('arrow')}</span></div></a>`).join('')}</div>`:`<div class="empty"><span class="empty-symbol">${icon('files')}</span><h2>还没有学习项目</h2><p>导入 GitHub 仓库或源码 ZIP。</p><a class="button primary" href="#/new">导入项目 ${icon('arrow')}</a></div>`}`;
  revealInterface([$('.collection-head'),...document.querySelectorAll('.project-card'),$('.empty')]);
}

function enhancementView(p){
  if(p.guide.mode==='ai')return '<details class="assist-panel"><summary>路线与记录</summary><p>重新规划后，旧笔记和学习记录仍会保留。</p><button class="button small" data-action="regenerate">重新规划路线</button></details>';
  if(!p.ai_preview)return '<details class="assist-panel"><summary>关于基础路线</summary><p>由本地原文整理。配置模型后，可在新导入的项目中启用 AI 细化。</p></details>';
  return `<details class="assist-panel" ${p.auto_ai&&p.error?'open':''}><summary><span>${icon('spark')}${p.error?'重试 AI 路线':'AI 细化路线'}</span></summary><div class="assist-content"><p>向 ${esc(p.ai_preview.provider)} 发送 ${p.ai_preview.excerpts} 段经自动脱敏的内容。</p><button class="text-button" data-action="preview">查看发送内容</button><button class="button primary full" data-action="analyze">${p.error?'重试 AI 生成':'用 AI 细化学习路线'} ${icon('arrow')}</button></div></details>`;
}

function selectedStep(p){
  return p.guide.steps.find(s=>s.id===state.selectedStep)||p.guide.steps.find(s=>!p.completed_steps.includes(s.id))||p.guide.steps[0];
}

function courseOutline(p){
  const current=selectedStep(p);
  return `<details class="course-outline" ${window.innerWidth>760?'open':''}><summary><span>学习目录</span><span>${p.guide.steps.length} 步</span></summary><ol>${p.guide.steps.map((s,i)=>{
    const done=p.completed_steps.includes(s.id),active=s.id===current?.id,task=state.study?.tasks.find(t=>t.id===s.id),pref=preference(task?.key)?.preference;
    return `<li><button data-action="select-step" data-step="${esc(s.id)}" class="course-step ${active?'selected':''} ${done?'is-complete':''}" ${active?'aria-current="step"':''}><span class="course-number" aria-hidden="true">${done?'✓':String(i+1).padStart(2,'0')}</span><span class="course-label">${esc(s.title)}<small>${labelPreference(pref)||(done?'自报完成':active?'正在学习':'')}</small></span></button></li>`;
  }).join('')}</ol></details>`;
}

function noteKey(p,step){return 'exampleproof-note:'+JSON.stringify([p.id,p.snapshot_id||'',p.guide.mode,step.id,step.title,step.action]);}
function readNote(p,step){
  const key=noteKey(p,step);
  if(state.notes.has(key))return state.notes.get(key);
  try{return localStorage.getItem(key)||'';}catch{return '';}
}
function noteStatus(p,step){
  if(state.noteFailures.has(noteKey(p,step)))return '浏览器存储不可用，笔记暂存于本页；关闭前请复制保存。';
  return readNote(p,step)?'已恢复笔记；仅保存在此浏览器。':'自动保存到此浏览器，不随项目导出。';
}

function routeView(p){return studyRoute(p);}

function sourceMarkup(reader){return rawSourceMarkup(reader);}

function readerView(){return studyReaderView();}

function renderReader(){renderStudyReader();}

function projectView(p){
  const previousMotion=captureWorkspaceMotion();
  const readerScroll=$('#source-reader .reader-scroll')?.scrollTop??null;
  if(state.project&&state.studyProject!==p.id&&(state.project.id!==p.id||state.project.guide?.mode!==p.guide?.mode)){
    state.selectedStep=null;state.reader=null;++state.sourceRequest;
  }
  state.project=p;
  if(p.status==='failed'){$('#main').classList.remove('learning-main');$('#main').innerHTML=`<div class="empty"><h2>导入未完成</h2><p role="alert">${esc(p.error)}</p><a href="#/new" class="button primary">重新导入 ${icon('arrow')}</a></div>`;return;}
  if(p.status!=='ready'){$('#main').classList.remove('learning-main');progressView(p);return;}
  $('#main').classList.add('learning-main');
  const g=p.guide,completed=g.steps.filter(s=>p.completed_steps.includes(s.id)).length;
  $('#main').innerHTML=`<div class="breadcrumb"><a href="#/projects">学习项目</a><span>/</span>${esc(p.name)}<span>/</span>学习空间</div>
    <div class="page-head project-head"><div class="project-identity"><h1>${esc(p.name)}</h1><details class="project-goal"><summary>学习目标 ${icon('chevron')}</summary><div><p>${esc(p.goal)}</p><span>${esc(levels[p.level])}</span></div></details></div><div class="project-header-actions">${workspaceEmblem()}<div><button class="text-button export-button" data-action="export">${icon('upload')} 导出指南</button></div></div></div>
    <nav class="workspace-tabs" aria-label="项目内容" style="--active-tab:${['route','files','journal','assessment'].indexOf(state.tab)}"><span class="workspace-tab-marker" aria-hidden="true"></span>${[['route','学习路线'],['files','项目文件'],['journal','学习记录'],['assessment','项目评估']].map(([t,label])=>`<button class="${state.tab===t?'active':''}" data-action="project-tab" data-tab="${t}" aria-current="${state.tab===t?'page':'false'}">${label}</button>`).join('')}</nav>
    ${p.error?`<div class="notice" role="alert">${esc(p.error)} 当前路线仍可使用。</div>`:''}${g.warnings.length?`<details class="project-notices"><summary>阅读提示 · ${g.warnings.length} 项</summary>${g.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details>`:''}
    ${layoutControls()}
    <div class="workspace study-workspace ${state.focus&&state.tab==='route'?'is-focused':''}"><aside class="side-stack" id="study-outline"><div class="side-panel"><div class="route-progress"><span>我的进度 <small>自己记录</small></span><strong>${completed}<small> / ${g.steps.length}</small></strong><progress class="sr-only" value="${completed}" max="${g.steps.length||1}" aria-label="自己记录的学习进度"></progress><span class="route-progress-track" aria-hidden="true"><span class="route-progress-fill" style="transform:scaleX(${completed/(g.steps.length||1)})"></span></span></div>${courseOutline(p)}</div>${enhancementView(p)}</aside>
    <div id="project-content">${state.tab==='route'?routeView(p):state.tab==='assessment'?assessmentView(p):state.tab==='journal'?journalView():filesView(p)}</div><div id="reader-resizer" class="reader-resizer" role="separator" tabindex="0" aria-label="调整任务与原文宽度，左右方向键调整，双击恢复均衡" aria-orientation="vertical" aria-controls="source-reader" aria-valuemin="25" aria-valuemax="65" aria-valuenow="${Math.round(state.layout.reader)}"><span></span></div><aside id="source-reader" class="source-reader" aria-label="原文阅读区">${readerView()}</aside></div>`;
  applyStudyLayout();
  renderStudyReader(readerScroll);
  resumeStudyReader(p);
  if(state.tab==='route'){showStudyTool(state.studyTool,false,false);updateStudyBadges();}
  animateWorkspace(previousMotion,p);
}

async function source(button,reveal=true){return readStudySource(button,reveal);}

function selectStep(id){selectStudyStep(id);}

async function completeStep(button){return completeStudyStep(button);}

function progressView(p){
  const current=p.status==='analyzing'?2:p.stage?.startsWith('整理')?1:0;
  const steps=['读取项目文件','整理文档与源码',p.auto_ai||p.status==='analyzing'?'AI 生成学习路线':'整理入门步骤'];
  $('#main').innerHTML=`<div class="breadcrumb"><a href="#/projects">我的学习项目</a> / ${esc(p.name)}</div><div class="loading"><span class="spinner"></span><h1>${p.status==='importing'?'正在准备你的项目':'正在生成 AI 学习路线'}</h1><p id="job-stage" role="status" aria-live="polite">${esc(p.stage)}</p><ol class="generation-steps" aria-label="生成进度">${steps.map((label,index)=>`<li class="${index<current?'finished':index===current?'current':''}" ${index===current?'aria-current="step"':''}><span>${index<current?'✓':index+1}</span>${label}<small>${index<current?'已完成':index===current?'进行中':'待处理'}</small></li>`).join('')}</ol><p class="tiny">后台会继续处理。可以离开此页，稍后从学习项目中继续。</p><a class="button" href="#/projects">返回我的项目</a></div>`;
}
function assessmentView(p){const g=p.guide;return `<div class="stats"><div class="stat"><strong>${g.coverage.documents}</strong><span>文档文件</span></div><div class="stat"><strong>${g.coverage.files}</strong><span>纳入分析的文件</span></div><div class="stat"><strong>${g.findings.length}</strong><span>注意事项</span></div></div><section class="panel"><h2>环境与前提</h2>${g.prerequisites.length?g.prerequisites.map(r=>`<div class="finding"><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p>${refs(r.evidence)}</div>`).join(''):'<p class="muted tiny">尚未定位到明确的环境说明，可从项目文件查看安装入口。</p>'}</section><section class="panel"><h2>注意事项</h2><p class="muted tiny">静态观察与 AI 建议分别标记；未执行项目代码。</p>${g.findings.length?g.findings.map(f=>`<article class="finding"><span class="pill ${f.origin==='ai'?'warn':'local'}">${f.origin==='ai'?'AI 建议 · 待确认':'原文静态观察'}</span><h3>${esc(f.title)}</h3><p>${esc(f.impact)}</p><p><strong>建议：</strong>${esc(f.suggestion)}</p>${refs(f.evidence)}${f.source_search?.hits?.length?`<details><summary class="tiny muted">相关原文</summary>${refs(f.source_search.hits)}</details>`:''}</article>`).join(''):'<div class="checkpoint">当前检查没有提出事项，不代表项目已经完整验证。可以沿入门路线继续核对。</div>'}</section><p class="inline-note">敏感文件名、依赖目录、二进制和超大文件会跳过。ZIP 导入跳过 ${Number(p.import_summary?.skipped_files||0)} 个文件；分析期间另有 ${Object.values(g.coverage.skipped||{}).reduce((a,b)=>a+Number(b||0),0)} 条跳过记录（含目录）。</p>`;}
function filesView(p){return `<section class="panel"><h2>项目文件</h2><label><span class="sr-only">搜索项目文件</span><input class="search" id="file-search" placeholder="搜索文件名…"></label><div class="file-list" id="file-list">${fileRows(p.guide.files)}</div></section>`;}
function fileRows(files){return files.map(f=>`<button class="file-row" data-action="source" data-path="${esc(f.path)}" data-line="1" data-end="1"><span class="file-icon">${f.kind==='document'?'文':'〈〉'}</span><span>${esc(f.path)}</span></button>`).join('')||'<p class="muted tiny">没有匹配的文件。</p>';}
async function openProject(id){
  const p=await api('/api/projects/'+id);
  if(location.hash!=='#/project/'+id)return;
  if(p.status==='ready'&&(!state.study||state.studyProject!==id||state.project?.guide_revision!==p.guide_revision)){
    if(!await loadStudy(p))return;
  }
  projectView(p);
  if(['importing','analyzing'].includes(p.status))state.timer=setTimeout(()=>openProject(id).catch(e=>toast(e.message)),1200);
}

async function navigate(){stopInterfaceMotion();delete $('#main').dataset.motionView;delete $('#main').dataset.motionProject;delete $('#main').dataset.motionTab;document.querySelectorAll('.topbar nav a').forEach(a=>{const current=a.hash===(location.hash.startsWith('#/project/')?'#/projects':location.hash||'#/new');if(current)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});clearTimeout(state.timer);void flushStudyNote();clearTimeout(state.helpPoll);state.study=null;state.studyProject=null;state.helpPending=null;state.restoreReader=null;state.selection=null;state.project=null;state.tab='route';state.selectedStep=null;state.reader=null;state.focus=false;++state.sourceRequest;$('#main').classList.remove('learning-main');const route=location.hash||'#/new';try{if(route.startsWith('#/project/'))await openProject(route.slice(10));else if(route==='#/projects')await projects();else home();}catch(e){$('#main').innerHTML=`<div class="empty"><h2>暂时无法打开</h2><p>${esc(e.message)}</p><a href="#/projects" class="button">返回我的项目</a></div>`;}window.scrollTo(0,0);}
function openDialog(title,html){$('#dialog-title').textContent=title;$('#dialog-body').innerHTML=html;if(!$('#detail-dialog').open){$('#detail-dialog').showModal();revealInterface([$('#detail-dialog')]);}}
async function preview(){openDialog('AI 将使用哪些内容？','<p class="muted">正在读取发送内容…</p>');const {payload,preview}=await api(`/api/projects/${state.project.id}/preview`);$('#dialog-body').innerHTML=`<p class="tiny muted">点击 AI 生成或重试按钮后，将向 ${esc(preview.provider)} 发送以下内容。请确认这些片段适合发送。</p><div class="checkpoint"><strong>你的目标</strong>${esc(payload.learner.goal)} · ${esc(payload.learner.level)}</div>${payload.evidence.map(e=>`<section class="preview-item"><h3>${esc(e.path)}:${e.start_line}–${e.end_line}</h3><pre>${esc(e.text)}</pre></section>`).join('')}`;}
function selectFile(file){if(!file)return;if(!file.name.toLowerCase().endsWith('.zip')||file.size>20000000){toast('请选择不超过 20 MB 的 ZIP 项目文件。');return;}state.file=file;$('#file-name').textContent=file.name;}
document.addEventListener('submit',async e=>{if(e.target.id!=='import-form')return;e.preventDefault();if(state.busy)return;const goal=$('#goal').value.trim(),level=$('input[name=level]:checked').value,auto_ai=Boolean($('#auto-ai')?.checked);state.busy=true;$('#import-submit').disabled=true;$('#form-error').textContent='';try{let result;if(state.importMode==='zip'){if(!state.file)throw Error('请先选择项目 ZIP。');const query=new URLSearchParams({name:state.file.name.replace(/\.zip$/i,''),goal,level,auto_ai:String(auto_ai)});result=await api('/api/projects/upload?'+query,{method:'POST',headers:{'Content-Type':'application/zip'},body:state.file});}else{result=await api('/api/projects',{method:'POST',json:{repository:$('#repository').value.trim(),ref:$('#ref').value.trim()||null,goal,level,auto_ai}});}location.hash='#/project/'+result.id;}catch(error){$('#form-error').textContent=error.message;}finally{state.busy=false;if($('#import-submit'))$('#import-submit').disabled=false;}});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;try{if(action==='import-mode'){state.importMode=b.dataset.mode;$('#github-input').hidden=state.importMode!=='github';$('#zip-input').hidden=state.importMode!=='zip';document.querySelectorAll('[data-action=import-mode]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-selected',String(x===b));});}if(action==='select-step')selectStep(b.dataset.step);if(action==='focus'){state.focus=!state.focus;$('.study-workspace').classList.toggle('is-focused',state.focus);b.setAttribute('aria-pressed',String(state.focus));b.innerHTML=(state.focus?'退出专注':'专注阅读')+' '+icon('focus');}if(action==='expand-source'&&state.reader?.text!==undefined){openDialog(state.reader.path,sourceMarkup(state.reader));const code=$('#dialog-body .source-code'),line=code.querySelector('.current');if(line)code.scrollTop+=line.getBoundingClientRect().top-code.getBoundingClientRect().top-code.clientHeight/3;}if(action==='goal')$('#goal').value=b.dataset.goal;if(action==='project-tab'){await flushStudyNote();state.tab=b.dataset.tab;projectView(state.project);}if(action==='close-dialog')$('#detail-dialog').close();if(action==='source')await source(b);if(action==='preview')await preview();if(action==='analyze'){b.disabled=true;const p=await api(`/api/projects/${state.project.id}/analyze`,{method:'POST',json:{approval:state.project.ai_preview.approval}});if(state.project?.id===p.id){state.study=null;state.reader=null;state.selectedStep=null;projectView(p);await openProject(p.id);}}if(action==='complete')await completeStep(b);if(action==='export'){const response=await fetch(`/api/projects/${state.project.id}/export`);if(!response.ok)throw Error('导出未完成，请重试。');const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=state.project.name.replace(/[\\/]/g,'-')+'-入门指南.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}}catch(error){toast(error.message);b.disabled=false;}});
document.addEventListener('input',e=>{if(e.target.id==='file-search')$('#file-list').innerHTML=fileRows(state.project.guide.files.filter(f=>f.path.toLowerCase().includes(e.target.value.toLowerCase())));});
document.addEventListener('change',e=>{if(e.target.id==='zip-file')selectFile(e.target.files[0]);if(e.target.id==='auto-ai')$('#import-submit').innerHTML=(e.target.checked?'创建 AI 学习路线':'创建学习路线')+' '+icon('arrow');});
document.addEventListener('keydown',e=>{if(e.target.id==='dropzone'&&(e.key==='Enter'||e.key===' ')){e.preventDefault();$('#zip-file').click();}});
for(const event of ['dragover','dragleave','drop'])document.addEventListener(event,e=>{const zone=e.target.closest('#dropzone');if(!zone)return;e.preventDefault();zone.classList.toggle('dragging',event==='dragover');if(event==='drop')selectFile(e.dataTransfer.files[0]);});
window.addEventListener('hashchange',()=>{if(state.config)void navigate();});
window.addEventListener('DOMContentLoaded',()=>api('/api/config').then(config=>{state.config=config;return navigate();}).catch(()=>{$('#main').innerHTML='<div class="empty"><h2>学习服务尚未连接</h2><p>请保持本机 ExampleProof 服务运行，然后刷新此页面。</p></div>';}));
