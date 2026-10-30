'use strict';
let questions=[], current=0, drafts={}, saved={}, session=null, client=null, busy=false;
const $=id=>document.getElementById(id);
const text=(id,value)=>{$(id).textContent=value;};
function table(target,columns,rows){
  target.replaceChildren(); target.classList.remove('empty');
  const t=document.createElement('table'), head=t.createTHead().insertRow();
  columns.forEach(c=>{const th=document.createElement('th');th.scope='col';th.textContent=c;head.append(th);});
  const body=t.createTBody();
  rows.forEach(row=>{const tr=body.insertRow();row.forEach(v=>{const td=tr.insertCell();td.textContent=v===null?'NULL':String(v);});});
  target.append(t);
  if(!rows.length){const p=document.createElement('p');p.textContent='No rows returned.';target.append(p);}
}
function status(message,error=false){text('status',message);$('status').classList.toggle('error',error);}
function controls(){
  $('run').disabled=busy||!session; $('save').disabled=busy||!session;
  $('query').disabled=busy; $('generate').disabled=busy||!session; $('rag-question').disabled=busy;
  text('auth-toggle',session?'Sign out':'Sign in');
  text('identity',session?.user?.email||'Guest session');
  text('query-help',session?'Your drafts save to your account. Ctrl/⌘ + Enter to run.':'Sign in to run queries and save your progress.');
}
function nav(){
  $('question-nav').replaceChildren();
  questions.forEach((q,i)=>{
    const b=document.createElement('button');b.className='nav-question'+(i===current?' active':'');
    b.setAttribute('aria-label',`Question ${q.id}: ${q.title}${saved[q.id]?' (saved)':''}`);
    if(i===current)b.setAttribute('aria-current','step');
    const n=document.createElement('span');n.className='nav-number';n.textContent=String(q.id).padStart(2,'0');
    const copy=document.createElement('span'),title=document.createElement('span'),points=document.createElement('span');
    title.className='nav-title';title.textContent=q.title; points.className='nav-points';points.textContent='4 points';copy.append(title,points);b.append(n,copy);
    if(saved[q.id]){const dot=document.createElement('span');dot.className='saved-dot';dot.textContent='✓';b.append(dot);}
    b.disabled=busy;b.onclick=()=>show(i);$('question-nav').append(b);
  });
  text('saved-count',`${Object.keys(saved).length} / 5 saved`);
}
function show(i){
  if(questions[current])drafts[questions[current].id]=$('query').value;
  current=i;const q=questions[i];
  $('rag-question').value=q.prompt; $('rag-output').hidden=true; text('rag-status','');
  text('question-number',`QUESTION ${String(q.id).padStart(2,'0')}`);text('question-title',q.title);text('question-prompt',q.prompt);text('question-concept',q.concept);
  $('query').value=drafts[q.id]??saved[q.id]??'';
  text('expected-sql',q.sql);table($('expected-result'),q.columns,q.rows);$('hint').open=false;
  $('results').replaceChildren();$('results').classList.add('empty');
  const title=document.createElement('h3');title.textContent='Your next discovery starts here.';
  const p=document.createElement('p');p.textContent='Write a query, hit Run, and explore the rows.';$('results').append(title,p);
  text('result-meta','Ready when you are');status('');
  $('previous').disabled=i===0||busy;$('next').disabled=i===questions.length-1||busy;
  nav();controls();
}
async function api(path,options={}){
  const {data:{session:latest}}=await client.auth.getSession();session=latest;controls();
  if(!session)throw new Error('Sign in to run queries or save answers.');
  const r=await fetch(path,{...options,headers:{'Content-Type':'application/json','Authorization':`Bearer ${session.access_token}`,...options.headers}});
  const data=await r.json();if(!r.ok)throw new Error(data.error||'Request failed. Please try again.');return data;
}
async function action(kind){
  if(busy||!session)return;
  const q=questions[current],query=$('query').value;if(!query.trim())return status('Write a SQL query first.',true);
  busy=true;controls();status(kind==='run'?'Running against the live database…':'Saving your answer…');
  try{
    const start=performance.now();const data=await api(`/api/${kind}`,{method:'POST',body:JSON.stringify({question_id:q.id,query})});
    if(kind==='run'){
      // A question switch during a request must not paint results into another question.
      if(questions[current].id===q.id){table($('results'),data.columns,data.rows);text('result-meta',`${data.rows.length}${data.truncated?'+':''} rows · ${((performance.now()-start)/1000).toFixed(1)}s`);status(data.truncated?'Showing the first 200 rows. Add a LIMIT or filter to narrow your query.':'Live results returned. Open the hint to compare your answer.');}
    }else{saved[q.id]=query;nav();if(questions[current].id===q.id)status('Answer saved to your account.');}
  }catch(e){status(e.message,true);}finally{busy=false;controls();}
}
async function authChanged(next){
  const previousUser=session?.user?.id;session=next;controls();
  if(previousUser!==next?.user?.id){drafts={};saved={};$('query').value='';}
  if(session){
    $('auth-panel').hidden=true;
    if(previousUser===next.user.id)return;
    try{const data=await api('/api/answers');saved=data.answers;drafts={...saved};$('query').value=drafts[questions[current].id]??'';nav();status('Signed in. Your saved answers are ready.');}
    catch(e){status(e.message,true);}
  }else{saved={};nav();}
}
async function init(){
  try{
    const [config,quiz]=await Promise.all([fetch('/api/config').then(r=>r.json()),fetch('/api/quiz').then(r=>r.json())]);
    questions=quiz.questions;Object.entries(quiz.schema).forEach(([name,columns])=>{const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('p');s.textContent=name;p.textContent=columns;d.append(s,p);$('schema').append(d);});
    show(0);
    if(!config.url||!config.key||!window.supabase)throw new Error('Sign-in configuration is unavailable. Contact the quiz owner.');
    client=window.supabase.createClient(config.url,config.key);
    // Avoid awaiting other Auth calls inside the SDK callback.
    client.auth.onAuthStateChange((_event,next)=>setTimeout(()=>authChanged(next),0));
    $('auth-toggle').onclick=async()=>{
      if(session){const {error}=await client.auth.signOut();if(error)status(error.message,true);else{session=null;saved={};drafts={};$('query').value='';table($('results'),[],[]);text('result-meta','Signed out');nav();controls();status('Signed out.');}}
      else{$('auth-panel').hidden=!$('auth-panel').hidden;if(!$('auth-panel').hidden)$('email').focus();}
    };
    $('auth-form').onsubmit=async e=>{
      e.preventDefault();$('email-button').disabled=true;text('auth-message','Sending your sign-in link…');$('auth-message').classList.remove('error');
      try{const {error}=await client.auth.signInWithOtp({email:$('email').value.trim(),options:{emailRedirectTo:location.origin+'/'}});if(error)throw error;text('auth-message','Check your inbox (and spam) and open the sign-in link on this device.');}
      catch(e){text('auth-message',e.message);$('auth-message').classList.add('error');}finally{$('email-button').disabled=false;}
    };
    $('run').onclick=()=>action('run');$('save').onclick=()=>action('save');$('generate').onclick=generateSQL;
    $('previous').onclick=()=>show(current-1);$('next').onclick=()=>show(current+1);
    $('use-hint').onclick=()=>{$('query').value=questions[current].sql;drafts[questions[current].id]=$('query').value;status('Example loaded. Run it to see live rows.');$('query').focus();};
    $('query').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();action('run');}});
  }catch(e){status(e.message,true);}
}
async function generateSQL(){
  if(busy||!session)return;
  const question=$('rag-question').value.trim(),q=questions[current];
  if(question.length<5){text('rag-status','Enter a question of at least 5 characters.');return;}
  busy=true;controls();nav();$('previous').disabled=true;$('next').disabled=true;
  $('rag-output').hidden=true;text('rag-status','Retrieving café knowledge from ChromaDB, then asking the AI…');$('rag-status').classList.remove('error');
  try{
    const data=await api('/api/generate',{method:'POST',body:JSON.stringify({question,question_id:q.id,execute:$('rag-execute').checked})});
    if(questions[current].id!==q.id)return;
    text('rag-sql',data.sql);text('rag-model',data.model);$('query').value=data.sql;drafts[q.id]=data.sql;
    text('retrieval-summary',`Retrieved knowledge · ${data.sources.length} matches from ${data.retrieval.documents} documents`);
    text('rag-retrieval-meta',`${data.retrieval.database} · ${data.retrieval.metric} distance (lower is closer) · ${data.retrieval.embedding} · retrieval ${data.retrieval.latency_ms}ms`);
    $('rag-sources').replaceChildren();
    data.sources.forEach((s,i)=>{const a=document.createElement('article');a.className='source-item';const h=document.createElement('h4'),m=document.createElement('small'),p=document.createElement('p');h.textContent=`${i+1}. ${s.title}`;m.textContent=`${s.id} · ${s.kind} · distance ${s.distance}`;p.textContent=s.text;a.append(h,m,p);$('rag-sources').append(a);});
    $('rag-validation').className='';
    if(data.execution){table($('results'),data.execution.columns,data.execution.rows);text('result-meta',`${data.execution.rows.length} rows · read-only live PostgreSQL`);}
    else{table($('results'),[],[]);text('result-meta','No automatic execution');}
    if(data.validation){const ok=data.validation.correct; text('rag-validation',ok?'✓ Correct: the live result matches this quiz question.':'Result differs from this quiz answer. Review the SQL, requested order, and selected question.');$('rag-validation').className=ok?'correct':'incorrect';}
    else text('rag-validation',data.execution_error||'SQL generated. Automatic execution is off; click Run query to try it.');
    $('rag-output').hidden=false;text('rag-status',`Generated from retrieved context in ${(data.latency_ms/1000).toFixed(1)}s. SQL is also loaded in the editor below.`);
  }catch(e){text('rag-status',e.message);$('rag-status').classList.add('error');}
  finally{busy=false;controls();nav();$('previous').disabled=current===0;$('next').disabled=current===questions.length-1;}
}
init();
