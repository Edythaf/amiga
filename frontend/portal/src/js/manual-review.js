const previewPDF=async(...args)=>(await import('./pdf-preview.js')).previewPDF(...args);
import {inspectPDF} from './pdf.js';
const states={PENDING:'Belum diperiksa AI',RUNNING:'AI sedang memeriksa',DETECTED:'Tanda tangan terdeteksi',NOT_DETECTED:'Tanda tangan belum terdeteksi',UNCERTAIN:'Tanda tangan belum dapat dipastikan',FAILED:'Pemeriksaan AI belum berhasil'};
export function manualReviewHTML(inv,escape){
  const row=inv.manual_review_pdf,decided=['APPROVED','REJECTED'].includes(inv.review_status);
  return `<section class="panel"><div class="panel-head"><h2>Voucher final hasil revisi reviewer</h2><span class="tiny-tag">Opsional</span></div><div class="panel-body"><p>Unduh draft, lakukan koreksi dan tambahkan tanda tangan bila diperlukan, lalu unggah PDF voucher hasil akhirmu. PDF boleh berbeda dari dokumen sumber karena memuat hasil revisi reviewer. Setelah disetujui, PDF ini yang diterima Klien dan dikirim melalui Telegram.</p><div class="actions"><button id="manual-draft">Unduh draft untuk direvisi</button>${row?'<button id="manual-download">Unduh voucher hasil revisi</button><button id="manual-preview">Lihat / perbesar hasil unggahan</button>':''}</div><div id="manual-pdf-preview" class="pdf-view" hidden></div>${row?`<div class="callout" role="status"><strong>${escape(row.filename)}</strong><p>${escape(states[row.signature_state]??'Belum diperiksa')}</p><p>${escape(row.signature_result?.note||'AI hanya memeriksa tanda tangan yang terlihat; bukan keaslian tanda tangan.')}</p></div>`:''}<p class="subtle">PDF tanpa tanda tangan tetap boleh diunggah dan diterbitkan. Reviewer bertanggung jawab atas isi voucher final; data nominal hasil koreksi juga perlu disimpan pada invoice.</p>${!decided?`<form id="manual-review-form"><label for="manual-review-file">PDF voucher final hasil revisi</label><input id="manual-review-file" name="review_pdf" type="file" accept="application/pdf,.pdf" required><label class="checkbox"><input id="manual-content-confirmed" type="checkbox" required>Saya menetapkan PDF ini sebagai voucher hasil akhir revisi saya untuk invoice versi ${inv.current_version}.</label><button type="submit">Unggah voucher final & periksa tanda tangan</button></form>`:'<p class="subtle">Versi ini sudah diputuskan. PDF resmi tetap tersimpan; perubahan hasil memerlukan revisi invoice.</p>'}</div></section>`;
}
export function bindManualReview({api,r,inv,run,toast,saveFile,hasUnsaved}){
  const clean=()=>{if(!hasUnsaved())return true;toast('Simpan perubahan invoice sebelum menggunakan PDF manual.',true);return false;};
  document.querySelector('#manual-draft')?.addEventListener('click',()=>{if(clean())run(async()=>saveFile(await api.voucher(r.id,inv.id,inv.current_version,false),'draft-review.pdf'),false);});
  document.querySelector('#manual-download')?.addEventListener('click',()=>{if(clean())run(async()=>saveFile(await api.manualPDF(r.id,inv.id,inv.manual_review_pdf.id),inv.manual_review_pdf.filename),false);});
  document.querySelector('#manual-preview')?.addEventListener('click',()=>run(async()=>{const target=document.querySelector('#manual-pdf-preview');target.hidden=false;const file=await api.manualPDF(r.id,inv.id,inv.manual_review_pdf.id);if(target.isConnected)await previewPDF(file.bytes,target);},false));
  document.querySelector('#manual-review-file')?.addEventListener('change',async event=>{const file=event.target.files[0],target=document.querySelector('#manual-pdf-preview');if(!file){target.hidden=true;return;}try{const checked=await inspectPDF(file);if(target.isConnected&&event.target.files[0]===file){target.hidden=false;await previewPDF(checked.bytes,target);}}catch(error){target.hidden=true;toast(error.message,true);}});
  const form=document.querySelector('#manual-review-form');
  if(form)form.onsubmit=e=>{
    e.preventDefault();if(!clean())return;
    const file=document.querySelector('#manual-review-file').files[0];if(!file)return;
    run(async()=>{
      await inspectPDF(file);const data=new FormData(form);data.set('expected_version',inv.current_version);data.set('expected_previous_id',inv.manual_review_pdf?.id??'');data.set('content_confirmed','true');
      const row=await api.uploadManual(r.id,inv.id,data);
      try{await api.manualSignature(r.id,inv.id,row.id,inv.current_version);toast('PDF hasil review tersimpan. Pemeriksaan tanda tangan hanya pemberitahuan.');}
      catch{toast('PDF tersimpan. AI belum dapat memeriksa tanda tangan; penerbitan tetap tersedia.');}
    });
  };
}
