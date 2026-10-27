import {requestLabel,bindDoubleOpen} from './workspace-interactions.js';
let cancelPolling=()=>{};
export function releaseUploader(){cancelPolling();cancelPolling=()=>{};}
export function requestContext(r,session,escape){
  return `<div class="request-context"><div><span class="subtle">Kode request</span> <code>${escape(requestLabel(r))}</code><button type="button" id="copy-request-id" class="small">Salin ID</button></div><button id="open-request-agent">${session.portal==='reviewer'?'Asisten reviewer':session.portal==='admin'?'Asisten admin':'Asisten uploader'}</button></div>`;
}
export function analysisHTML(a,escape){
  if(!a)return '';
  return `<div class="analysis-summary"><span class="tiny-tag">${escape({LOW:'Risiko rendah',MEDIUM:'Perlu diperiksa',HIGH:'Prioritas tinggi'}[a.risk]??'Analisis awal')}</span><p>${escape(a.summary)}</p></div>${a.findings.map(f=>`<div class="validation-flag"><strong>${escape(f.field||'Pemeriksaan')}</strong><p>${escape(f.observation)}</p><p class="subtle">${escape(f.recommendation)}</p></div>`).join('')}<ol>${a.next_steps.map(s=>`<li>${escape(s)}</li>`).join('')}</ol>`;
}
export function uploaderHTML(r,inv,session,escape){
  if(session.portal!=='uploader'||session.user.id!==r.uploaded_by||!inv.initial_analysis)return '';
  const a=inv.initial_analysis,confirmed=inv.uploader_confirmation?.confirmed;
  if(inv.review_status==='APPROVED')return '';
  return `<section class="panel" id="uploader-check" tabindex="-1"><div class="panel-head"><h2>${confirmed?'Data sudah dikonfirmasi':'Periksa hasil AI, lalu konfirmasi'}</h2><span class="tiny-tag">Versi ${inv.current_version}</span></div><div class="panel-body">${confirmed?'':`<div class="callout warn"><strong>Versi ${inv.current_version} belum dikirim ke reviewer.</strong><p>Periksa data, lalu centang konfirmasi dan tekan Konfirmasi & kirim ke reviewer di bawah hasil AI. Setiap perubahan data atau bukti memerlukan konfirmasi ulang. Setelah seluruh invoice dikonfirmasi, tugas muncul di Tugas tersedia untuk diambil reviewer.</p></div>`}<p>Periksa seluruh item, nominal, rekening dan catatan reviewer. Tambahan hasil review tidak wajib tercantum pada PDF sumber. Hasil AI membantu pemeriksaan; keputusan konfirmasi tetap milikmu.</p>${a.state==='READY'?analysisHTML(a.result,escape):`<div class="callout ${a.state==='FAILED'?'warn':''}">${a.state==='FAILED'?'Analisis awal belum berhasil. Coba ulang atau hubungi pengelola bila batas percobaan tercapai.':'Luna sedang menyiapkan analisis awal. Kamu bisa membaca dokumen sambil menunggu.'}</div>`}
    ${confirmed?'<div class="callout">Konfirmasi berlaku untuk versi dan bukti yang tersimpan ini. Perubahan data akan meminta konfirmasi ulang.</div>':`<label class="checkbox"><input id="uploader-ack" type="checkbox" ${a.state==='READY'?'':'disabled'}>Saya sudah memeriksa hasil AI, seluruh baris item, dokumen sumber dan tambahan reviewer, serta memahami indikasi yang perlu ditindaklanjuti reviewer.</label><button id="confirm-uploader" class="primary" disabled>Konfirmasi & kirim ke reviewer</button>`}
    <div class="actions"><button id="refresh-initial">Muat ulang analisis</button>${a.state==='FAILED'?'<button id="retry-initial">Coba analisis awal lagi</button>':''}</div></div></section>`;
}
export function revisionHTML(r,session){
  if(session.portal!=='uploader'||session.user.id!==r.uploaded_by||!r.allowed_actions.includes('UPLOAD_REVISION'))return '';
  return `<section class="panel"><div class="panel-body"><details><summary>Dokumen sumber salah? Unggah revisi</summary><p>Request ID tetap sama. Dokumen dan voucher lama disimpan; versi baru dibaca AI dan perlu dikonfirmasi kembali.</p><form id="source-revision-form"><label for="source-revision-file">PDF atau foto revisi</label><input id="source-revision-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" required><label for="source-revision-reason">Alasan revisi</label><textarea id="source-revision-reason" minlength="3" maxlength="2000" required></textarea><label for="source-revision-category">Kategori menurut uploader</label><select id="source-revision-category"><option value="UNSPECIFIED">Belum dikategorikan</option><option value="SOURCE_ERROR">Kesalahan dokumen sumber</option><option value="REVIEW_CORRECTION">Koreksi hasil review</option></select>${r.voucher_count>0?'<label class="checkbox"><input id="source-supersede" type="checkbox" required>Saya memahami voucher yang sudah terbit menjadi arsip; versi baru wajib diperiksa ulang.</label>':''}<button type="submit" class="primary">Unggah revisi & baca ulang</button></form></details></div></section>`;
}
export function bindUploader({r,inv,api,session,navigate,run,toast,hasUnsaved=()=>false,refresh}){
  releaseUploader();
  const clean=()=>{if(!hasUnsaved())return true;toast('Simpan atau batalkan perubahan sebelum melanjutkan.',true);return false;};
  document.querySelector('#copy-request-id')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(requestLabel(r));toast('Request ID disalin.');}catch{toast('Kode request: '+requestLabel(r));}});
  document.querySelector('#open-request-agent')?.addEventListener('click',()=>{if(clean())navigate('agent',r.id,inv?.id);});
  const ack=document.querySelector('#uploader-ack'),confirm=document.querySelector('#confirm-uploader');
  if(ack)ack.onchange=()=>{confirm.disabled=!ack.checked;};
  if(confirm)confirm.onclick=()=>{if(clean()&&ack.checked)run(async()=>{await api.confirmUploader(r.id,inv.id,inv.current_version);toast('Data dikonfirmasi. Tugas diteruskan ke reviewer setelah semua invoice dikonfirmasi.');});};
  document.querySelector('#refresh-initial')?.addEventListener('click',()=>{if(clean())refresh();});
  document.querySelector('#retry-initial')?.addEventListener('click',()=>{if(clean())run(()=>api.initialRetry(r.id,inv.id,inv.current_version));});
  const form=document.querySelector('#source-revision-form');
  if(form)form.onsubmit=e=>{e.preventDefault();if(!clean())return;const data=new FormData();data.append('invoice_file',document.querySelector('#source-revision-file').files[0]);data.append('reason',document.querySelector('#source-revision-reason').value.trim());data.append('category',document.querySelector('#source-revision-category').value);if(document.querySelector('#source-supersede')?.checked)data.append('supersede_published','true');data.append('expected_versions',JSON.stringify(Object.fromEntries(r.invoices.map(i=>[i.id,i.current_version]))));run(async()=>{await api.documentRevision(r.id,data);toast('Dokumen revisi tersimpan. Menunggu pembacaan AI.');navigate('review',r.id);},false);};
  if(api.mode==='live'&&session.portal==='uploader'&&(r.processing?.status==='QUEUED'||r.processing?.status==='PROCESSING'||inv&&['PENDING','RUNNING'].includes(inv.initial_analysis?.state))){
    const interval=setInterval(()=>{if(!document.hidden&&!hasUnsaved()&&!document.querySelector('#source-revision-file')?.files.length&&!document.querySelector('#source-revision-reason')?.value&&!document.querySelector('.content.busy')&&!document.activeElement?.matches('input,textarea,select'))refresh();},5000);
    cancelPolling=()=>clearInterval(interval);
  }
}
