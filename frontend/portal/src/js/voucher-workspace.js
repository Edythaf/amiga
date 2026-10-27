import {requestLabel,bindDoubleOpen} from './workspace-interactions.js';
import {workBadge} from './work-progress.js';

export async function voucherWorkspace({api,shell,pageTitle,escape,badge,navigate,run,isCurrent}){
  let page=1;
  async function load(){
    const result=await api.list({scope:'mine',page,page_size:50});
    if(!isCurrent())return;
    shell(pageTitle('Voucher reviewer','Pusat penerbitan voucher dari tugas yang kamu tangani. Pilih draft, periksa hasil, lalu terbitkan voucher resmi.')+
      `<div class="callout">Voucher resmi diterbitkan setelah data tersimpan, seluruh validasi lolos, dan reviewer independen menyetujui. Setiap invoice memiliki voucher sendiri.</div>
      <div class="task-grid">${result.items.map(r=>`<section class="panel task-card" data-open-request="${escape(r.id)}"><div class="panel-body"><div class="task-card-head">${badge(r.status)}<span class="tiny-tag">${escape(r.client_name)}</span></div><h2>${escape(r.vendor_names.join(', ')||'Dokumen sedang diproses')}</h2><p>${escape(r.invoice_numbers.join(', '))}</p>${workBadge(r,escape)}<p>${r.voucher_count??0} dari ${r.invoice_count} voucher terbit</p><div class="actions"><button class="primary voucher-open" data-id="${escape(r.id)}" ${r.invoice_count?'':'disabled'}>${r.voucher_count===r.invoice_count&&r.invoice_count?'Lihat voucher terbit':'Periksa draft & terbitkan'}</button><button class="voucher-review" data-id="${escape(r.id)}">Review data</button></div></div></section>`).join('')||'<div class="panel panel-body"><h2>Belum ada tugas untuk diterbitkan</h2><p>Ambil tugas di Tugas tersedia untuk mulai memeriksa dokumen.</p></div>'}</div>
      <div class="table-footer"><span>Halaman ${page} · ${result.total} tugas</span><div class="actions"><button id="voucher-prev" ${page===1?'disabled':''}>Sebelumnya</button><button id="voucher-next" ${page*50>=result.total?'disabled':''}>Berikutnya</button></div></div>`,'voucher');
    bindDoubleOpen(document,'[data-open-request]',row=>row.querySelector('.voucher-open')?.click());
    document.querySelectorAll('.voucher-open').forEach(b=>b.onclick=()=>navigate('voucher',b.dataset.id));
    document.querySelectorAll('.voucher-review').forEach(b=>b.onclick=()=>navigate('review',b.dataset.id));
    document.querySelector('#voucher-prev').onclick=()=>run(async()=>{page--;await load();},false);
    document.querySelector('#voucher-next').onclick=()=>run(async()=>{page++;await load();},false);
  }
  await load();
}
