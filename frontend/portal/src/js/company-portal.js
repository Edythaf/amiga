import {requestLabel,bindDoubleOpen} from './workspace-interactions.js';

import {progressHTML,bindProgress,workLabels} from './work-progress.js';

import {recipientHTML,mountRecipient,automaticRecipientHTML,automaticDeliveryHTML} from './telegram-settings.js';

import {money} from './money.js';



export function currentHandler(r){

  if(r.work_status==='CLOSED')return {role:'Selesai',name:'Hasil diterima perusahaan',next:'Voucher dan riwayat tetap tersedia.'};

  if(['VOUCHER_READY','AWAITING_CLIENT_CLOSE'].includes(r.work_status))return {role:'Klien perusahaan',name:r.client_name,next:r.work_status==='VOUCHER_READY'?'Unduh voucher resmi, lalu periksa hasilnya.':'Terima hasil atau minta revisi bila belum sesuai.'};

  if(r.work_status==='IN_REVIEW')return {role:'Reviewer',name:r.pic_name||'Belum ditugaskan',next:'Reviewer memeriksa rincian dan menyiapkan voucher.'};

  if(r.work_status==='UNCLAIMED')return {role:'Antrean reviewer',name:'Menunggu tugas diambil',next:'Reviewer aktif akan mengambil pekerjaan ini.'};

  if(r.work_status==='PROCESSING')return {role:'Sistem',name:'Pembacaan dokumen oleh AI',next:'Hasil pembacaan diteruskan ke uploader untuk diperiksa.'};

  return {role:'Uploader',name:r.uploader_name||'Tim uploader',next:r.work_status==='EXTRACTION_FAILED'?'Uploader perlu memeriksa dokumen yang belum berhasil dibaca.':r.work_status==='WAITING_CLIENT'?'Uploader menyiapkan perbaikan sesuai catatan reviewer.':'Uploader memeriksa hasil AI dan mengonfirmasi seluruh invoice.'};

}

const stamp=v=>new Date(v).toLocaleString('id-ID',{timeZone:'Asia/Jakarta',dateStyle:'medium',timeStyle:'short'});

const handlerHTML=(r,escape)=>{const h=currentHandler(r);return `<div class="company-handler"><span class="tiny-tag">${escape(h.role)}</span><div><strong>${escape(h.name)}</strong><p class="subtle">${escape(h.next)}</p></div></div>`;};



export async function companyPage({api,session,page,id,escape,shell,pageTitle,navigate,run,toast,isCurrent}){

  if(page==='telegram'){

    shell(pageTitle('Terima kabar saat voucher selesai','Hubungkan Telegram akun perusahaanmu dan aktifkan penerimaan PDF voucher otomatis.')+recipientHTML()+automaticRecipientHTML(),'telegram');

    await mountRecipient({api,run,toast,isCurrent});return;

  }

  if(page==='help'){

    shell(pageTitle('Pantau pekerjaan perusahaan','Portal ini terpisah dari pekerjaan uploader dan reviewer.')+'<section class="panel"><div class="panel-body"><h2>Dari dokumen masuk sampai hasil diterima</h2><p>Uploader mengunggah dokumen, memeriksa hasil AI dan mengonfirmasi invoice. Reviewer mengambil tugas, memeriksa hasil secara independen, lalu menerbitkan voucher.</p><p>Di Progres perusahaan, buka request untuk melihat tahap, penanggung jawab dan kendala. Setelah voucher terbit, unduh dan periksa hasilnya. Kamu dapat menerima hasil atau meminta revisi.</p><p>Telegram penerima bersifat opsional. Buka menu Telegram penerima, tekan Start melalui tautan verifikasi, lalu periksa koneksi di AMIGA. Aktifkan Voucher otomatis dan simpan pilihan untuk menerima PDF resmi pada penerbitan berikutnya. Status pengiriman tercantum pada detail progres. Pembayaran tetap mengikuti prosedur perusahaan di luar AMIGA.</p></div></section>','help');return;

  }

  if(page==='review'&&id){

    const r=await api.detail(id);if(!isCurrent())return;

    shell(pageTitle('Progres invoice perusahaan',`${escape(r.client_name)} · ${escape(requestLabel(r))}`,'<button id="company-back">Semua pekerjaan</button>')+

      handlerHTML(r,escape)+progressHTML(r,escape,'client')+automaticDeliveryHTML(r,escape)+`<section class="panel"><div class="panel-head"><h2>Invoice & hasil voucher</h2></div><div class="panel-body">${r.invoices.map(inv=>`<div class="company-invoice"><div><strong>${escape(inv.fields.invoice_number||'Nomor belum tersedia')}</strong><p class="subtle">${escape(inv.fields.vendor_name||'Vendor belum terbaca')} · versi ${inv.current_version}</p><p>Nilai invoice ${escape(money(inv.fields.total_amount,inv.fields.currency))}</p>${inv.voucher_tax?.applied?`<p><strong>Nilai akhir voucher ${escape(money(inv.voucher_tax.calculated?.net_payable,inv.fields.currency))}</strong></p>`:''}</div>${inv.allowed_actions.includes('DOWNLOAD_VOUCHER')?`<button class="primary company-voucher" data-invoice="${escape(inv.id)}">Lihat & unduh voucher</button>`:'<span class="tiny-tag">Voucher belum terbit</span>'}</div>`).join('')||'<p>Dokumen masih diproses. Belum ada invoice yang siap ditampilkan.</p>'}</div></section><section class="panel"><div class="panel-body"><h2>Catatan proses</h2><p class="subtle">Pembaruan ${escape(stamp(r.updated_at))}</p>${r.invoices.filter(i=>i.review_note).map(i=>`<p>${escape(i.review_note)}</p>`).join('')||'<p>Belum ada catatan tambahan dari reviewer.</p>'}${r.client_revision_note?`<p>Permintaan revisi perusahaan: ${escape(r.client_revision_note)}</p>`:''}</div></section>`,'queue');

    bindProgress({r,api,run,navigate,toast});

    document.querySelector('#company-telegram-settings')?.addEventListener('click',()=>navigate('telegram'));
    document.querySelector('#company-back').onclick=()=>navigate('queue');

    document.querySelectorAll('.company-voucher').forEach(b=>b.onclick=()=>navigate('voucher',r.id,b.dataset.invoice));

    return;

  }

  let pageNumber=1,query='',company='';

  async function load(){

    const result=await api.list({page:pageNumber,page_size:12,search:query,client_id:company,...(page==='voucher'?{has_voucher:'1'}:{})});if(!isCurrent())return;

    const rows=result.items;

    shell(pageTitle(page==='voucher'?'Voucher perusahaan':'Setiap invoice, jelas siapa yang menangani.',session.user.clients.map(c=>escape(c.name)).join(' · '),'<button id="company-refresh">Muat ulang status</button>')+

      `<div class="company-summary"><div class="stat"><span>Request sesuai filter</span><strong class="stat-number">${result.total}</strong></div><div class="callout"><strong>Lihat proses dan hasil perusahaanmu.</strong><p>Uploader menyiapkan dokumen, reviewer memeriksa, lalu perusahaan menerima voucher.</p></div></div><section class="panel"><form id="company-filter" class="panel-body actions"><label>Cari invoice / Request ID<input id="company-search" type="search" value="${escape(query)}" placeholder="Nomor invoice atau nama vendor"></label><label>Perusahaan<select id="company-filter-id"><option value="">Semua perusahaan saya</option>${session.user.clients.map(c=>`<option value="${escape(c.id)}" ${c.id===company?'selected':''}>${escape(c.name)}</option>`).join('')}</select></label><button type="submit">Cari</button></form></section><div class="company-grid">${rows.map(r=>`<section class="panel company-card" data-open-request="${escape(r.id)}"><div class="panel-body"><div class="task-card-head"><span class="tiny-tag">${escape(workLabels[r.work_status]||r.work_status)}</span><small>${r.lifecycle.state==='CLOSED'?'CLOSED':'OPEN'}</small></div><p class="subtle">${escape(r.client_name)} · ${escape(requestLabel(r))}</p><h2>${escape(r.vendor_names.join(', ')||'Dokumen sedang dibaca')}</h2><p>${escape(r.invoice_numbers.join(', ')||'Nomor invoice belum tersedia')}</p>${handlerHTML(r,escape)}<p class="subtle">Tenggat ${escape(r.deadline)} · ${r.voucher_count}/${r.invoice_count} voucher terbit</p><p class="subtle">${escape(stamp(r.updated_at))}</p><button class="primary company-open" data-id="${escape(r.id)}">Lihat progres</button></div></section>`).join('')||'<section class="panel"><div class="panel-body"><h2>Belum ada pekerjaan</h2><p>Request akan muncul setelah uploader mengunggah dokumen untuk perusahaan yang dihubungkan ke akunmu.</p></div></section>'}</div><div class="actions"><button id="company-prev" ${pageNumber===1?'disabled':''}>Sebelumnya</button><span>Halaman ${pageNumber}</span><button id="company-next" ${pageNumber*result.page_size>=result.total?'disabled':''}>Berikutnya</button></div>`,page==='voucher'?'voucher':'queue');

    document.querySelector('#company-filter').onsubmit=e=>{e.preventDefault();query=document.querySelector('#company-search').value.trim();company=document.querySelector('#company-filter-id').value;pageNumber=1;run(load,false);};

    document.querySelector('#company-refresh').onclick=()=>run(load,false);

    document.querySelector('#company-prev').onclick=()=>{pageNumber--;run(load,false);};

    document.querySelector('#company-next').onclick=()=>{pageNumber++;run(load,false);};

    bindDoubleOpen(document,'[data-open-request]',row=>navigate('review',row.dataset.openRequest));

    document.querySelectorAll('.company-open').forEach(b=>b.onclick=()=>navigate('review',b.dataset.id));

  }

  await load();

}
