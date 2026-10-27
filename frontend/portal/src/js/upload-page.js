import {inspectInvoice} from './document-input.js';
import {inspectPDF} from './pdf.js';
import {dateKey} from './analytics.js';

export function batchUploadHTML(clients,escape){
  return `<section class="panel"><div class="panel-body"><form id="batch-upload-form"><div class="form-grid"><label>Perusahaan<select name="client_id">${clients.map(c=>`<option value="${escape(c.id)}">${escape(c.name)}</option>`).join('')}</select></label><label>Jenis permintaan<select name="request_type"><option>Invoice vendor</option></select></label><label>Saluran<select name="channel"><option>Portal</option><option>Email</option><option>WhatsApp</option></select></label><label>Tanggal<input name="request_date" type="date" value="${dateKey(new Date())}" required></label><label>Tenggat pekerjaan<input name="deadline" type="date" required></label></div><label class="dropzone" id="batch-drop" for="batch-files"><strong>Pilih atau tarik beberapa PDF / foto invoice</strong><small>Maksimal 10 berkas, 10 MB per berkas dan total unggahan 32 MB. Satu PDF maksimal 5 halaman.</small><input id="batch-files" type="file" name="invoice_files[]" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple required></label><div id="batch-file-list" class="subtle" role="status">Belum ada invoice dipilih.</div><label>Bukti pendukung bersama (opsional, PDF)<input type="file" name="evidence_files[]" accept=".pdf,application/pdf" multiple></label><p class="callout">Setiap invoice mendapat Request ID dan tugas reviewer sendiri. PDF berisi beberapa invoice dipisah setelah ekstraksi; uploader mengonfirmasi setiap tugas sebelum reviewer mengambilnya. Bukti bersama dilampirkan pada seluruh tugas.</p><button type="submit" id="batch-submit" class="primary">Unggah & buat tugas invoice</button></form></div></section>`;
}

export function batchUploadPage({api,session,escape,shell,pageTitle,run,toast,navigate}){
  shell(pageTitle('Unggah beberapa invoice','Invoice untuk perusahaan yang sama dapat diunggah sekaligus, dengan penugasan review terpisah.')+batchUploadHTML(session.user.clients,escape),'upload');
  const form=document.querySelector('#batch-upload-form'),input=document.querySelector('#batch-files'),info=document.querySelector('#batch-file-list'),submit=document.querySelector('#batch-submit'),drop=document.querySelector('#batch-drop');
  let checked=[],generation=0,checking=false,key=crypto.randomUUID();
  async function inspect(){
    const current=++generation,files=[...input.files];checked=[];checking=true;submit.disabled=true;info.textContent='Memeriksa seluruh berkas…';
    try{
      if(!files.length||files.length>10)throw Error('Pilih 1–10 PDF atau foto invoice.');
      if(files.reduce((sum,f)=>sum+f.size,0)>30*1024*1024)throw Error('Total invoice maksimal 30 MB; sisakan ruang untuk bukti dan formulir.');
      const results=[];for(const file of files)results.push(await inspectInvoice(file));
      if(current!==generation)return;checked=files;key=crypto.randomUUID();
      info.replaceChildren();for(let i=0;i<files.length;i++){const line=document.createElement('p');line.textContent=`${i+1}. ${files[i].name} · ${results[i].pages} halaman`;info.append(line);}
    }catch(error){if(current===generation){checked=[];info.textContent=error.message;toast(error.message,true);}}
    finally{if(current===generation){checking=false;submit.disabled=false;}}
  }
  input.onchange=inspect;drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag');};drop.ondragleave=()=>drop.classList.remove('drag');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');const transfer=new DataTransfer();for(const file of e.dataTransfer.files)transfer.items.add(file);input.files=transfer.files;inspect();};
  form.onsubmit=e=>{e.preventDefault();run(async()=>{
    if(checking||!checked.length)throw Error('Tunggu pemeriksaan invoice selesai.');
    const data=new FormData(form),evidence=data.getAll('evidence_files[]').filter(f=>f.size);
    if(evidence.length>10)throw Error('Maksimal 10 bukti pendukung bersama.');
    if([...checked,...evidence].reduce((sum,f)=>sum+f.size,0)>31*1024*1024)throw Error('Total invoice dan bukti maksimal 31 MB.');
    for(const file of evidence)await inspectPDF(file);
    data.set('idempotency_key',key);const result=await api.uploadBatch(data);
    toast(`${result.items.length} request dibuat. Setiap invoice memiliki tugas review terpisah setelah ekstraksi.`);
    if(result.items.length===1)navigate('review',result.items[0].id);else navigate('requests');
  },false);};
}
