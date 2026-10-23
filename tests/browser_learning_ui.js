/* Synthetic browser interactions against in-memory responses. No live model calls. */
(() => {
  const fixture=window.UI_FIXTURE,record=structuredClone(fixture.record),workspace=structuredClone(fixture.workspace);
  const checks=[],errors=[],jobs=new Map();let sequence=0,modelState='ready',failNote=false,failProgress=false,failPoll=false,prepares=0,sends=0;
  const copy=value=>structuredClone(value),response=(value,ok=true)=>({ok,json:async()=>copy(value)});
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const ref={path:'README.md',start_line:1,end_line:3};
  const answer={origin:'ai_feedback',answer:'合成回答：先检查输入 3，再对照函数中的乘法，结果应由原文和实际操作核对。',evidence:[ref],next_actions:[{text:'打开函数定义，核对输入与返回表达式。',evidence:[ref]}],uncertainties:['这是交互测试，不代表真实模型或执行结果。']};
  const draft=body=>({question:body.question,intent:body.intent,environment:body.environment||'',command:body.command||'',error:body.error||'',reply_to:body.reply_to||null});
  window.addEventListener('error',e=>errors.push(e.message));
  window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
  try{localStorage.removeItem('exampleproof-workspace-layout-v1');localStorage.removeItem('exampleproof-reader-wrap');}catch{}
  location.hash='#/project/'+record.id;
  window.fetch=async (path,options={})=>{
    const url=new URL(path,'http://fixture'),action=url.pathname.split('/').at(-1),body=options.body?JSON.parse(options.body):{};
    if(url.pathname==='/api/config')return response({csrf:'synthetic',ai_available:true,provider:'synthetic',model:'fixture'});
    if(url.pathname==='/api/projects')return response({projects:[record]});
    if(action===record.id)return response(record);
    if(action==='source'){const name=url.searchParams.get('path');return response({path:name,text:fixture.files[name],kind:name.endsWith('.md')?'document':'source',outline:[{title:'Usage',line:9}]});}
    if(action==='workspace'){
      if(options.method==='POST'){
        if(body.action==='note'){
          if(failNote)return response({error:'合成保存失败'},false);
          workspace.notes[body.step_key]={...body,key:body.step_key,title:'合成笔记',version:body.version+1};
        }
        if(body.action==='position')workspace.positions[body.route_id]={...body};
        if(body.action==='resolve')workspace.discussions.find(d=>d.id===body.id).resolved=body.resolved;
      }
      workspace.pending_requests=[...jobs.values()].filter(j=>j.status==='queued');
      return response(workspace);
    }
    if(action==='progress'){
      if(failProgress)return response({error:'合成进度保存失败'},false);
      record.completed_steps=body.completed_steps;return response(record);
    }
    if(action==='help-prepare'){
      prepares++;await delay(80);
      const parent=workspace.discussions.find(d=>d.id===body.reply_to);
      const job={id:'fixture-'+(++sequence),status:'prepared',step_key:body.step_key,route_id:body.route_id,draft:draft(body)};
      const preview={learner:{goal:record.goal,level:record.level},question:body.question,environment:body.environment,command:body.command,error:body.error,exercise:null,conversation:[],evidence:[{...ref,text:fixture.files['README.md']}]};
      if(parent)preview.reply_to={id:parent.id,question:parent.question,answer:parent.response.answer};
      jobs.set(job.id,job);
      if(body.use_ai===false){job.status='ready';workspace.discussions.push({id:job.id,step_key:job.step_key,route_id:job.route_id,title:'合成任务',question:job.draft.question,intent:body.intent,response:{...answer,origin:'local_guidance'},resolved:false,reply_to:body.reply_to});return response(job);}
      return response({...job,approval:'synthetic-approval',provider:'synthetic',model:'fixture',preview});
    }
    if(action==='help-send'){sends++;const job=jobs.get(body.request_id);if(job.status!=='prepared')return response({error:'已发送'},false);job.status='queued';return response(job);}
    if(action==='help-status'){
      if(failPoll)throw Error('synthetic offline');
      const job=jobs.get(url.searchParams.get('id'));
      job.status=modelState;
      if(job.status==='failed')job.error='合成模型失败';
      if(job.status==='ready'&&!workspace.discussions.some(d=>d.id===job.id))workspace.discussions.push({id:job.id,step_key:job.step_key,route_id:job.route_id,title:'合成任务',question:job.draft.question,intent:job.draft.intent,response:answer,resolved:false,reply_to:job.draft.reply_to});
      return response(job);
    }
    return response({error:'Unhandled synthetic endpoint: '+path},false);
  };

  const query=s=>document.querySelector(s),click=s=>{const element=query(s);if(!element)throw Error('Missing: '+s);element.click();return element;};
  const input=(s,value)=>{const element=query(s);element.value=value;element.dispatchEvent(new Event('input',{bubbles:true}));};
  const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
  const until=async (test,label)=>{for(let i=0;i<400;i++){if(test())return;await delay(25);}throw Error('Timeout: '+label);};
  const visible=s=>{const element=query(s);return element&&element.getClientRects().length>0;};
  window.addEventListener('load',async()=>{
    const preview=new URLSearchParams(location.search).get('preview')||new URLSearchParams(parent.location.search).get('preview');
    if(preview){if(preview==='reader'){await until(()=>query('#study-title'),'preview load');await readStudySource({dataset:{path:'reader-demo.js',line:2,end:8}});click('[data-action="reader-scope"]');query('#source-reader').scrollIntoView({block:'start'});}if(preview==='help'){await until(()=>query('#study-title'),'preview load');click('[data-tool="help"]');query('#help-region').scrollIntoView({block:'start'});}return;}
    const result=document.createElement('pre');result.id='ui-check-result';result.textContent='RUNNING';document.body.append(result);
    try{
      await until(()=>query('#study-title')&&query('.reader-scroll'),'initial workspace');
      check(visible('.resume-banner'),'restored position shows a continue banner');
      await readStudySource({dataset:{path:'reader-demo.js',line:2,end:8}});
      check(query('.reader-language').textContent==='JavaScript','reader detects source language');
      check(query('[data-source-line="4"] .syntax-comment')?.textContent.includes('return'),'multiline comment context survives source line boundaries');
      check(query('.source-line.current .line-no').textContent==='2','citations retain original line numbers');
      check(!query('#source-reader img'),'source HTML stays inert text');
      const sourceLines=[...document.querySelectorAll('.editor-code .line-content')];
      check(sourceLines.map(line=>line.textContent).join('\n')===fixture.files['reader-demo.js'],'highlighted DOM preserves exact source whitespace and blank lines');
      let copied=null;
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{copied=text;}}});
      click('[data-action="reader-copy"]');await until(()=>copied!==null,'copy excerpt');
      check(copied===fixture.files['reader-demo.js'].split('\n').slice(1,8).join('\n'),'copy excerpt contains only cited source, without line numbers');
      click('[data-action="reader-scope"]');
      const code=query('.editor-code');
      check(code.scrollWidth>code.clientWidth,'long unwrapped lines scroll within the reader');
      code.scrollLeft=200;
      check(Math.abs(query('.line-no').getBoundingClientRect().left-code.getBoundingClientRect().left)<2,'line-number gutter stays visible during horizontal scroll');
      click('[data-action="reader-wrap"]');
      check(code.scrollWidth<=code.clientWidth+1&&localStorage.getItem('exampleproof-reader-wrap')==='true','wrapping fits long lines within the pane and persists preference');
      check(query('[data-source-line="11"] .line-content').textContent===fixture.files['reader-demo.js'].split('\n')[10],'wrapping preserves original long-line content');
      copied=null;click('[data-action="reader-copy"]');await until(()=>copied!==null,'copy full');
      check(copied===fixture.files['reader-demo.js'],'copy full source preserves the trailing newline');
      navigator.clipboard.writeText=async()=>{throw Error('synthetic permission denial');};
      click('[data-action="reader-copy"]');await until(()=>query('#reader-copy-text'),'copy fallback');
      check(query('#reader-copy-text').readOnly&&query('#reader-copy-text').value===fixture.files['reader-demo.js'],'clipboard denial exposes exact source for manual copying');
      click('[data-action="close-dialog"]');
      query('.reader-search-tools').open=true;input('#source-find','count');click('#source-matches button');
      check(query('.source-line.search-target').dataset.sourceLine==='6','search locates the original highlighted source line');
      check(document.documentElement.scrollWidth<=innerWidth+1,'long source lines never overflow the page');
      await readStudySource({dataset:{path:'README.md',line:1,end:3}});
      click('[data-action="reader-scope"]');
      check(query('.document-reading pre[data-language="JavaScript"] .syntax-comment')?.textContent==='/* first','Markdown fenced blocks use their declared language');
      check(query('.document-reading [data-source-line="19"] .syntax-comment')?.textContent==='return false','Markdown code highlighting retains multiline context and original line references');
      click('[data-action="reader-mode"]');
      check(query('.editor-code').classList.contains('is-wrapped'),'wrap preference survives switching files and modes');
      click('[data-action="reader-back"]');await until(()=>query('.reader-language')?.textContent==='JavaScript','reader back');
      check(query('.reader-caption').textContent.includes('L2–8'),'reading history restores source reference range');
      click('[data-action="reader-forward"]');await until(()=>query('.reader-language')?.textContent==='Markdown','reader forward');

      check(query('.next-task-preview').textContent.includes('下一步'),'next task appears by the completion action');
      check(document.querySelectorAll('.tool-launchers > button').length===5&&['help','notes','practice','run','adjust'].every(name=>visible('[data-tool="'+name+'"]')),'all five learning tools are directly visible');
      check(!query('.more-study-tools')&&!query('[data-action="layout-preset"]'),'more-tools menu and layout presets are absent');
      click('[data-tool="practice"]');
      check(visible('#tool-practice'),'practice opens directly from its tool button');
      click('[data-tool="help"]');
      check(document.querySelectorAll('.conversation-turn').length===12,'recent questions and answers form a visible conversation');
      click('[data-action="help-history"]');
      check(document.querySelectorAll('.conversation-turn').length===14,'older conversations can be expanded');
      check(query('#help-form button[type=submit]').textContent==='预览并提问','question action clearly describes preview and send');
      const style=getComputedStyle(query('#help-form button[type=submit]'));
      check(style.color==='rgb(255, 255, 255)'&&style.backgroundImage.includes('linear-gradient'),'small primary button is readable without hover');
      input('#help-question','尚未提交的问题');const originalInput=query('#help-question');
      click('[data-tool="notes"]');input('#step-note','需要保留的笔记草稿');
      click('[data-tool="help"]');check(query('#help-question')===originalInput&&query('#help-question').value==='尚未提交的问题','switching tools preserves forms and questions');
      click('[data-action="toggle-outline"]');check(!visible('#study-outline'),'outline collapses');
      check(query('#help-question')===originalInput,'layout changes do not recreate inputs');
      click('[data-action="toggle-outline"]');check(visible('#study-outline'),'outline restores');
      if(innerWidth>1180){
        const width=query('#source-reader').getBoundingClientRect().width;
        const grip=query('#reader-resizer');grip.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));
        check(query('#source-reader').getBoundingClientRect().width>width,'separator expands source pane without presets');
        grip.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
        check(grip.getAttribute('aria-valuenow')==='63','separator supports keyboard resizing');
        grip.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));check(grip.getAttribute('aria-valuenow')==='45','double click restores balanced panes');
        grip.setPointerCapture=()=>{};grip.hasPointerCapture=()=>false;
        grip.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:7,button:0,clientX:600}));
        grip.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerId:7,clientX:540}));
        check(Number(grip.getAttribute('aria-valuenow'))>45,'dragging separator expands source pane');
        grip.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:7}));
        check(Number(JSON.parse(localStorage.getItem('exampleproof-workspace-layout-v1')).reader)>45,'layout preference is saved');
      }else check(!visible('#reader-resizer')&&visible('.compact-reader-links'),'narrow layout has source navigation without a drag handle');
      click('[data-action="focus"]');check(!visible('#source-reader')&&!visible('#study-outline'),'task focus hides supporting panes');
      click('[data-action="focus"]');check(visible('#source-reader'),'leaving focus restores source pane');
      check(document.documentElement.scrollWidth<=innerWidth+1,'workspace has no horizontal page overflow');
      click('[data-action="help-followup"]');
      check(query('.reply-context').textContent.includes('合成问题 1'),'followup identifies the selected older answer');
      input('#help-question','请再解释一次返回值');
      const count=prepares;query('#help-form').requestSubmit();query('#help-form').requestSubmit();
      await until(()=>query('#detail-dialog').open,'preview');
      check(prepares===count+1&&sends===0,'duplicate preview clicks create one preview and send nothing');
      check(query('#dialog-body').textContent.includes('正在追问的回答'),'preview includes selected parent answer');
      click('[data-action="close-dialog"]');await delay(30);
      check(query('#help-question').value==='请再解释一次返回值'&&!query('#detail-dialog').open,'canceling preview keeps the draft');
      query('#help-form').requestSubmit();await until(()=>query('#detail-dialog').open,'second preview');
      failPoll=true;click('[data-action="help-confirm"]');
      await until(()=>visible('[data-action="help-check"]'),'poll connection failure');
      check(query('#help-form button[type=submit]').disabled&&sends===1,'poll failure prevents accidental duplicate sends');
      failPoll=false;click('[data-action="help-check"]');
      await until(()=>query('#help-status')?.textContent.includes('回答已保存'),'response');
      check(query('#help-question').value===''&&document.querySelectorAll('.conversation-turn').length===15,'saved answer appends to conversation and clears only the sent draft');
      click('.chat-answer .ref');await until(()=>query('.reader-file')?.textContent.includes('README.md'),'answer reference');
      check(visible('#source-reader'),'answer citation opens the source pane');
      modelState='failed';input('#help-question','合成失败的问题');query('#help-form').requestSubmit();
      await until(()=>query('#detail-dialog').open,'failure preview');click('[data-action="help-confirm"]');
      await until(()=>visible('[data-action="help-retry"]'),'inline model error');
      check(query('#help-question').value==='合成失败的问题'&&query('#help-status').textContent.includes('合成模型失败'),'generation failure preserves question and shows retry next to it');
      modelState='ready';click('[data-action="help-retry"]');await until(()=>query('#detail-dialog').open,'retry preview');click('[data-action="close-dialog"]');
      failNote=true;click('[data-tool="notes"]');input('#step-note','失败时也保留的笔记');
      await until(()=>query('#note-status')?.textContent.includes('保存未完成'),'note failure');
      check(query('#step-note').value==='失败时也保留的笔记','failed note save preserves the text');
      failNote=false;click('[data-action="note-retry"]');await until(()=>query('#note-status')?.textContent.includes('已保存'),'note retry');
      check(query('[data-tool="notes"] .tool-badge').textContent==='已保存','note save state is reflected on its tool entry');
      const title=query('#study-title').textContent;failProgress=true;click('[data-action="complete"]');
      await until(()=>query('#progress-status')?.textContent.includes('进度未保存'),'progress failure');
      check(query('#study-title').textContent===title,'failed progress save does not advance the task');
      failProgress=false;click('[data-action="complete"]');await until(()=>query('#study-title')?.textContent!==title,'next task');
      check(query('#progress-status').textContent.includes('上一项已记录完成'),'successful completion advances with local feedback');
      await until(()=>query('#position-status')?.textContent.includes('已保存'),'position persistence');
      check(Object.values(workspace.notes).some(n=>n.text==='失败时也保留的笔记'),'saved notes remain after moving to the next step');
      check(errors.length===0,'no uncaught browser errors');
      result.textContent=JSON.stringify({status:'PASS',viewport:innerWidth,checks,prepares,sends,kind:'synthetic browser fixture'});
    }catch(error){result.textContent=JSON.stringify({status:'FAIL',viewport:innerWidth,error:String(error.stack||error),readerGeometry:{box:query('.editor-code')?.getBoundingClientRect(),line:query('.line-no')?.getBoundingClientRect(),scroll:query('.editor-code')?.scrollLeft,gutterPosition:query('.line-no')&&getComputedStyle(query('.line-no')).position},checks,errors,prepares,sends,pending:state.helpPending,review:state.pendingHelpReview?.request.id});}
  });
})();
