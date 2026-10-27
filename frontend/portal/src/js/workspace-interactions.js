export const requestLabel=r=>r.request_code||r.id;

export function bindDoubleOpen(root,selector,open){
  root.querySelectorAll(selector).forEach(row=>{
    row.tabIndex=0;row.classList.add('double-open');
    row.addEventListener('dblclick',event=>{if(!event.target.closest('button,a,input,select,textarea,summary'))open(row);});
    row.addEventListener('keydown',event=>{if(event.target===row&&event.key==='Enter'){event.preventDefault();open(row);}});
  });
}

let activeDialog;
export function closeWorkspaceDialog(){activeDialog?.close();}
export function workspaceDialog(title,{wide=false,onClose=()=>{}}={}){
  closeWorkspaceDialog();const previous=document.activeElement,dialog=document.createElement('dialog');
  dialog.className='workspace-dialog'+(wide?' workspace-dialog-wide':'');
  const head=document.createElement('div');head.className='workspace-dialog-head';
  const heading=document.createElement('h2');heading.id='workspace-dialog-title';heading.textContent=title;
  const close=document.createElement('button');close.type='button';close.textContent='Tutup';close.onclick=()=>dialog.close();
  head.append(heading,close);dialog.setAttribute('aria-labelledby',heading.id);
  const body=document.createElement('div');body.className='workspace-dialog-body';dialog.append(head,body);
  dialog.addEventListener('close',()=>{onClose();dialog.remove();if(activeDialog===dialog)activeDialog=null;if(previous?.isConnected)previous.focus();},{once:true});
  document.body.append(dialog);activeDialog=dialog;dialog.showModal();return {dialog,body};
}

export function showReason(text,{editable=false,onSave=()=>{},title='Alasan / hasil pemeriksaan'}={}){
  const {dialog,body}=workspaceDialog(title);
  if(editable){
    const label=document.createElement('label');label.textContent='Alasan lengkap';
    const input=document.createElement('textarea');input.value=text;input.maxLength=2000;input.required=true;input.rows=12;label.append(input);
    const apply=document.createElement('button');apply.className='primary';apply.textContent='Gunakan alasan ini';
    const hint=document.createElement('p');hint.className='subtle';hint.textContent='Perubahan masuk ke draft. Simpan hasil review untuk menerapkan.';
    apply.onclick=()=>{if(input.reportValidity()){onSave(input.value);dialog.close();}};body.append(label,hint,apply);
  }else{const content=document.createElement('p');content.className='reason-text';content.textContent=text||'Belum ada alasan tambahan.';body.append(content);}
}
