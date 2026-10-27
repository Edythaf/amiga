// Labels describe operational responsibility; invoice validation stays separate.
export const workLabels = {
  PROCESSING:'Dokumen sedang dibaca', EXTRACTION_FAILED:'Pembacaan dokumen gagal', UNCLAIMED:'Menunggu reviewer mengambil',
  WAITING_UPLOADER:'Menunggu konfirmasi uploader',
  IN_REVIEW:'Sedang dikerjakan reviewer', WAITING_CLIENT:'Menunggu perbaikan uploader',
  VOUCHER_READY:'Voucher siap diunduh', AWAITING_CLIENT_CLOSE:'Menunggu konfirmasi klien',
  CLOSED:'Pekerjaan ditutup',
};
const nextSteps = {
  PROCESSING:'Tunggu hasil pembacaan dokumen. Muat ulang untuk melihat perkembangan.',
  WAITING_UPLOADER:'Periksa analisis awal AI dan seluruh data sumber. Konfirmasi setiap invoice agar tugas dapat diambil reviewer.',
  EXTRACTION_FAILED:'Hasil invoice belum siap diperiksa. Periksa dokumen atau hubungi pengelola sebelum mencoba ekstraksi ulang.',
  UNCLAIMED:'Tugas tersedia bagi reviewer aktif. Klien dapat melengkapi data dan bukti.',
  IN_REVIEW:'Reviewer memeriksa dokumen, mengoreksi draft, lalu menerbitkan voucher.',
  WAITING_CLIENT:'Baca catatan reviewer, lengkapi data atau bukti, lalu simpan revisi.',
  VOUCHER_READY:'Klien mengunduh seluruh voucher terbaru sebelum mengonfirmasi pekerjaan selesai.',
  AWAITING_CLIENT_CLOSE:'Klien memeriksa hasil, lalu menutup pekerjaan atau meminta revisi.',
  CLOSED:'Layanan administrasi selesai. Voucher tetap dapat diunduh; revisi harus diminta secara eksplisit.',
};
const stages=['Dokumen masuk','Antrean reviewer','Pemeriksaan','Voucher terbit','Diunduh klien','Ditutup'];
let stopCompactProgress=()=>{};
export function releaseProgress(){stopCompactProgress();stopCompactProgress=()=>{};}
export function workBadge(r,escape){
  if(!r.work_status)return '';
  return `<span class="work-status">${escape(workLabels[r.work_status]??r.work_status)}</span><small>${r.lifecycle?.state==='CLOSED'?'CLOSED · Ditutup':'OPEN · Terbuka'}</small>`;
}
export function requestBadge(r,escape,badge){
  // Passing validation does not mean the uploader has submitted this version.
  if(r.status==='READY_FOR_REVIEW'&&(r.work_status==='WAITING_UPLOADER'||r.ready_for_review===false))
    return `<span class="tiny-tag">${escape('Belum dikirim ke reviewer')}</span>`;
  return badge(r.status);
}
export function requestOpenLabel(r,portal,vouchersOnly=false){
  return vouchersOnly?'Lihat voucher':portal==='uploader'&&r.work_status==='WAITING_UPLOADER'?'Periksa & konfirmasi':'Buka';
}
export function progressHTML(r,escape,portal){
  if(!['client','uploader'].includes(portal)||!r.lifecycle)return '';
  const code=r.work_status,closed=r.lifecycle.state==='CLOSED';
  const stage={PROCESSING:0,UNCLAIMED:1,IN_REVIEW:2,WAITING_CLIENT:2,VOUCHER_READY:3,AWAITING_CLIENT_CLOSE:4,CLOSED:5}[code]??0;
  const actions=portal==='client'?(r.allowed_actions??[]):[];
  return `<section class="panel work-progress" aria-label="Status pekerjaan"><div class="panel-body">
    <div class="task-card-head"><h2>${escape(workLabels[code]??code)}</h2><span class="tiny-tag">${closed?'CLOSED · Ditutup':'OPEN · Terbuka'}</span></div>
    <p>${escape(portal==='client'&&code==='WAITING_UPLOADER'?'Uploader sedang memeriksa hasil AI dan mengonfirmasi data.':portal==='client'&&code==='WAITING_CLIENT'?'Uploader sedang menyiapkan perbaikan sesuai catatan reviewer.':nextSteps[code]??'')}</p>
    <ol class="work-stages">${stages.map((label,i)=>`<li class="${i<=stage?'reached':''}" ${i===stage?'aria-current="step"':''}>${i+1}. ${label}</li>`).join('')}</ol>
    <p class="subtle">Penanggung jawab: <strong>${escape(r.pic_name||'Belum diambil')}</strong> · Voucher terbit: ${r.voucher_count??0}/${r.invoice_count} · Pembaruan: ${escape(new Date(r.updated_at).toLocaleString('id-ID'))}</p>
    ${r.client_revision_note?`<div class="callout warn"><strong>Permintaan revisi terakhir dari klien:</strong> ${escape(r.client_revision_note)}</div>`:''}
    <div class="actions">${portal==='uploader'&&code==='WAITING_UPLOADER'?'<button id="open-uploader-check" class="primary">Periksa & konfirmasi data</button>':''}<button id="refresh-work">Muat ulang status</button>${r.voucher_count>0?'<button id="open-work-vouchers">Lihat voucher</button>':''}</div>
    ${actions.includes('CLOSE')?`<form id="close-work-form" class="work-action"><label class="checkbox"><input id="accept-work" type="checkbox" required>Saya telah memeriksa seluruh voucher dan menerima hasil layanan administrasi.</label><button class="primary" id="close-work" type="submit">Terima hasil & tutup pekerjaan</button></form>`:''}
    ${actions.includes('REQUEST_REVISION')?`<details class="work-action"><summary>${closed?'Minta revisi & buka kembali':'Hasil belum sesuai? Minta revisi'}</summary><form id="revision-work-form"><label for="work-reason">Jelaskan bagian yang perlu diperbaiki</label><textarea id="work-reason" required minlength="3" maxlength="2000" placeholder="Contoh: rincian biaya pada baris kedua belum sesuai PDF."></textarea><p class="subtle">Semua invoice dibuatkan versi baru untuk direview ulang. Voucher sebelumnya tetap tersimpan dalam riwayat.</p><button id="request-revision" type="submit">Kirim permintaan revisi</button></form></details>`:''}
    <p class="subtle">Penutupan pekerjaan adalah penerimaan layanan administrasi. Persetujuan dan pelaksanaan pembayaran mengikuti proses perusahaan di luar AMIGA.</p>
  </div></section><div class="work-progress-pin"><button type="button" class="work-progress-compact" hidden aria-label="Lihat rincian progres: ${escape(workLabels[code]??code)}"><span class="work-progress-compact-label">${stage+1}/6 · ${escape(code==='EXTRACTION_FAILED'?'Pembacaan gagal':stages[stage])}</span><span class="work-progress-track" aria-hidden="true">${stages.map((_,i)=>`<i class="${i<=stage?'reached':''}"></i>`).join('')}</span></button></div>`;
}
export function bindProgress({r,api,run,navigate,toast,hasUnsaved=()=>false}){
  releaseProgress();
  const panel=document.querySelector('.work-progress'),compact=document.querySelector('.work-progress-compact');
  if(panel&&compact){
    const observer=new IntersectionObserver(()=>{compact.hidden=panel.getBoundingClientRect().bottom>0;});
    observer.observe(panel);
    compact.onclick=()=>panel.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    stopCompactProgress=()=>{observer.disconnect();compact.onclick=null;};
  }
  const guard=()=>{if(!hasUnsaved())return true;toast('Simpan atau batalkan perubahan sebelum melanjutkan.',true);return false;};
  document.querySelector('#refresh-work')?.addEventListener('click',()=>{if(guard())run(async()=>{});});
  document.querySelector('#open-uploader-check')?.addEventListener('click',()=>{
    const pending=r.invoices?.find(i=>i.review_status!=='APPROVED'&&!i.uploader_confirmation?.confirmed);
    if(pending&&document.querySelector('#invoice-selector')?.value!==pending.id){
      if(guard())navigate('review',r.id,pending.id);
      return;
    }
    const check=document.querySelector('#uploader-check');
    if(!check){toast('Konfirmasi dilakukan oleh uploader yang mengunggah request ini.');return;}
    check?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    check?.focus({preventScroll:true});
  });
  document.querySelector('#open-work-vouchers')?.addEventListener('click',()=>{if(guard())navigate('voucher',r.id);});
  const submit=(action,reason)=>{
    if(!guard())return;
    run(async()=>{
      await api.lifecycle(r.id,{action,reason,expected_lifecycle_revision:r.lifecycle.revision,
        expected_versions:Object.fromEntries(r.invoices.map(i=>[i.id,i.current_version]))});
      toast(action==='CLOSE'?'Pekerjaan ditutup. Voucher tetap tersedia.':'Revisi diminta. Pekerjaan dibuka untuk pemeriksaan ulang.');
      navigate('review',r.id);
    },false);
  };
  document.querySelector('#close-work-form')?.addEventListener('submit',e=>{
    e.preventDefault();if(document.querySelector('#accept-work').checked)submit('CLOSE','Klien memeriksa seluruh voucher dan menerima hasil layanan administrasi.');
  });
  document.querySelector('#revision-work-form')?.addEventListener('submit',e=>{
    e.preventDefault();submit('REQUEST_REVISION',document.querySelector('#work-reason').value.trim());
  });
}
