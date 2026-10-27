import {agentPage} from './agent-page.js';

const chatIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2A8.5 8.5 0 0 1 21 11.5Z"/><path d="M7 10h9M7 14h6"/></svg>';
let widget=null;

function routeContext(){
  const [page,id='',invoice='']=location.hash.slice(1).split('/');
  try{return ['review','voucher','history','agent'].includes(page)?{requestId:decodeURIComponent(id),invoiceId:decodeURIComponent(invoice)}:{requestId:'',invoiceId:''};}
  catch{return {requestId:'',invoiceId:''};}
}

export function destroyAssistantBubble(){
  if(!widget)return;
  widget.revision++;
  document.removeEventListener('keydown',widget.keydown);
  widget.host.remove();widget=null;
}

export function syncAssistantBubble(options){
  if(options.hidden){destroyAssistantBubble();return;}
  const identity=options.session.user.id+':'+options.session.portal;
  if(widget?.identity!==identity)destroyAssistantBubble();
  if(!widget){
    const host=document.createElement('div');host.className='assistant-widget';
    host.innerHTML=`<section id="assistant-dialog" class="assistant-dialog" role="dialog" aria-modal="false" aria-labelledby="assistant-title" hidden><header class="assistant-header"><div><h2 id="assistant-title"></h2><small>Luna · Data pekerjaan tersimpan</small></div><div class="assistant-header-actions"><button type="button" id="assistant-expand" aria-label="Buka asisten di halaman penuh" title="Halaman penuh">↗</button><button type="button" id="assistant-close" aria-label="Tutup asisten" title="Tutup">×</button></div></header><div class="assistant-context"><span id="assistant-context-label"></span><button type="button" id="assistant-refresh" class="small">Muat ulang</button></div><div class="assistant-content"></div><div class="assistant-feedback" role="status" aria-live="polite" hidden></div></section><button type="button" class="assistant-launcher" id="assistant-launcher" aria-controls="assistant-dialog" aria-expanded="false">${chatIcon}<span>Tanya AMIGA</span></button>`;
    document.body.append(host);
    widget={host,identity,options,revision:0,open:false,context:routeContext(),pageContext:JSON.stringify(routeContext()),loaded:false,busy:false,drafts:new Map()};
    const w=widget;
    w.keydown=e=>{if(e.key==='Escape'&&w.open){e.preventDefault();close(w);}};
    document.addEventListener('keydown',w.keydown);
    host.querySelector('#assistant-launcher').onclick=()=>w.open?close(w):openAssistantBubble();
    host.querySelector('#assistant-close').onclick=()=>close(w);
    host.querySelector('#assistant-refresh').onclick=()=>{if(!w.busy){remember(w);render(w);}};
    host.querySelector('#assistant-expand').onclick=()=>{remember(w);close(w);w.options.navigate('agent',w.context.requestId,w.context.invoiceId);};
  }
  const w=widget;w.options=options;w.host.hidden=options.hidden;
  if(options.hidden){close(w,false);w.loaded=false;return;}
  const next=routeContext(),key=JSON.stringify(next);
  if(key!==w.pageContext){
    remember(w);w.pageContext=key;w.context=next;w.loaded=false;w.revision++;
    if(w.open)render(w);
  }
}

function remember(w){
  const input=w.host.querySelector('#agent-question');
  if(input)w.drafts.set(w.context.requestId,input.value);
}

function close(w,restore=true){
  remember(w);w.open=false;
  w.host.querySelector('#assistant-dialog').hidden=true;
  w.host.querySelector('#assistant-launcher').setAttribute('aria-expanded','false');
  if(restore&&!w.host.hidden)w.host.querySelector('#assistant-launcher').focus({preventScroll:true});
}

export function openAssistantBubble(context){
  const w=widget;if(!w||w.host.hidden)return;
  if(context&&(context.requestId!==w.context.requestId||context.invoiceId!==w.context.invoiceId)){
    remember(w);w.context={requestId:context.requestId||'',invoiceId:context.invoiceId||''};w.loaded=false;w.revision++;
  }
  w.open=true;
  w.host.querySelector('#assistant-dialog').hidden=false;
  w.host.querySelector('#assistant-launcher').setAttribute('aria-expanded','true');
  if(!w.loaded)render(w);
  else w.host.querySelector('#agent-question')?.focus({preventScroll:true});
}

function compact(root){
  root.querySelector('.page-heading')?.remove();
  const sections=[...root.querySelectorAll(':scope > .panel')];
  const chat=sections.find(section=>section.querySelector('#agent-chat-form'));
  if(!chat)return;
  const tools=document.createElement('div');tools.className='assistant-tools';
  for(const section of sections){
    if(section===chat)continue;
    const details=document.createElement('details');details.className='assistant-details';details.name='assistant-tools';
    const summary=document.createElement('summary');
    summary.textContent=section.querySelector('h2')?.textContent||'Request ID & konteks';
    section.querySelector('.panel-head')?.remove();details.append(summary,section);tools.append(details);
  }
  root.prepend(tools);chat.classList.add('assistant-chat');chat.querySelector('.panel-head')?.remove();
  const body=chat.querySelector('.panel-body');body.querySelector(':scope > p')?.remove();
  const messages=chat.querySelector('#agent-messages');messages.setAttribute('role','log');messages.setAttribute('aria-label','Percakapan asisten');
  chat.querySelector('#agent-send').textContent='Kirim';
  chat.querySelector('#agent-question').rows=2;
  chat.querySelector('#agent-question').placeholder='Tulis pertanyaan tentang pekerjaan…';
  chat.querySelector('#agent-question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();chat.querySelector('#agent-chat-form').requestSubmit();}};
}

async function render(w){
  const revision=++w.revision;w.loaded=true;w.busy=false;
  const current=()=>widget===w&&w.revision===revision&&!w.host.hidden;
  const root=w.host.querySelector('.assistant-content');
  const role=w.options.session.portal;
  w.host.querySelector('#assistant-title').textContent=role==='admin'?'Asisten admin':role==='reviewer'?'Asisten reviewer':'Asisten uploader';
  w.host.querySelector('#assistant-context-label').textContent=w.context.requestId||'Ringkasan pekerjaan sesuai akses akun';
  const feedback=w.host.querySelector('.assistant-feedback');feedback.hidden=true;
  const inform=(message,error=false)=>{if(!current())return;feedback.textContent=message;feedback.hidden=false;feedback.classList.toggle('error',error);};
  const report=e=>{if(!current())return;if(e.status===401){destroyAssistantBubble();w.options.onUnauthorized();return;}inform(e.message||'Asisten belum dapat dihubungi. Coba kembali.',true);};
  const run=async fn=>{
    if(w.busy||!current())return;
    w.busy=true;feedback.hidden=true;root.setAttribute('aria-busy','true');
    const submit=root.querySelector('#agent-send');if(submit)submit.disabled=true;
    try{await fn();}catch(e){report(e);}finally{
      if(current()){
        w.busy=false;root.removeAttribute('aria-busy');
        if(submit)submit.disabled=false;
      }
    }
  };
  try{
    await agentPage({...w.options,...w.context,root,isCurrent:current,toast:inform,run,
      pageTitle:()=>'',shell:content=>{if(current()){root.innerHTML=content;compact(root);}},
      navigate:(page,id='',invoice='')=>{
        if(page==='agent'){remember(w);w.context={requestId:id,invoiceId:invoice};render(w);}
        else{close(w);w.options.navigate(page,id,invoice);}
      }});
    if(!current())return;
    const input=root.querySelector('#agent-question');
    if(input){input.value=w.drafts.get(w.context.requestId)||'';if(w.open)input.focus({preventScroll:true});}
    const messages=root.querySelector('#agent-messages');if(messages)messages.scrollTop=messages.scrollHeight;
  }catch(e){report(e);if(current()&&!root.querySelector('#agent-chat-form')){root.innerHTML='<div class="assistant-empty"><p>Gunakan “Muat ulang” untuk mencoba kembali, atau buka ringkasan pekerjaan.</p><button id="assistant-reset">Kembali ke ringkasan</button></div>';root.querySelector('#assistant-reset').onclick=()=>{w.context={requestId:'',invoiceId:''};render(w);};}}
}
