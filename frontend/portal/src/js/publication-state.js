import {canReview} from './portal-policy.js';

// Explain a missing server capability; never infer or grant permission to publish.
export function publicationBlock(request,invoice,user){
  const actions=invoice.allowed_actions??[];
  if(!canReview(user)||actions.includes('APPROVE')||actions.includes('DOWNLOAD_VOUCHER'))return null;
  const block=(code,message)=>({code,message});
  if(request.lifecycle?.state==='CLOSED')return block('CLOSED','Pekerjaan sudah ditutup. Uploader perlu membuka permintaan revisi sebelum pemeriksaan dilanjutkan.');
  if(['QUEUED','PROCESSING'].includes(request.processing?.status))return block('PROCESSING','Pembacaan dokumen masih berjalan. Tunggu proses selesai, lalu muat ulang status.');
  if(request.processing?.status==='FAILED')return block('PROCESSING_FAILED','Pembacaan dokumen gagal. Periksa kendala ekstraksi sebelum menerbitkan voucher.');
  if(request.uploaded_by===user.id||(request.documents??[]).some(d=>d.uploaded_by===user.id))return block('INDEPENDENCE','Voucher harus disetujui reviewer independen yang tidak mengunggah dokumen atau bukti pada request ini.');
  if(request.pic_id!==user.id)return block('ASSIGNMENT','Hanya reviewer yang menangani tugas ini yang dapat menerbitkan voucher. Periksa penugasan pada Tugas saya.');
  if(invoice.review_status==='REJECTED')return block('REJECTED','Invoice sudah dikembalikan untuk perbaikan. Tunggu revisi uploader dan konfirmasi versi baru.');
  if(request.ready_for_review===false){
    const message=invoice.uploader_confirmation?.confirmed
      ?'Invoice ini sudah dikonfirmasi, tetapi ada invoice lain dalam request yang belum siap. Uploader perlu mengonfirmasi seluruh invoice aktif.'
      :`Menunggu konfirmasi uploader untuk versi ${invoice.current_version}. Uploader membuka Dokumen saya → detail invoice → Konfirmasi & kirim ke reviewer. Perubahan data atau bukti meminta konfirmasi ulang.`;
    return block('UPLOADER_CONFIRMATION',message+' Setelah selesai, muat ulang status di sini.');
  }
  return block('UNAVAILABLE','Penerbitan belum diizinkan server. Muat ulang status; jika tetap sama, minta admin memeriksa status dan penugasan.');
}

export function publicationBlockHTML(request,invoice,user,escape){
  const state=publicationBlock(request,invoice,user);
  if(!state)return '';
  return `<div class="callout warn" id="publication-blocked-reason" role="status"><strong>Voucher belum dapat diterbitkan.</strong><p>${escape(state.message)}</p></div><div class="actions"><button type="button" class="primary" disabled aria-describedby="publication-blocked-reason">Setujui & terbitkan voucher</button><button type="button" id="refresh-publication">Muat ulang status</button></div>`;
}
