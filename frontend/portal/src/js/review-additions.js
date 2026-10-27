// A reviewer annotation is human input scoped to an invoice, not PDF evidence.
export function accountSourceOptions(r,sources,reviewer,escape){
  const source=sources.account_number;
  return `<option value="">Pilih asal data</option>${reviewer||source?.source_type==='REVIEWER'?`<option value="REVIEWER" ${source?.source_type==='REVIEWER'?'selected':''}>Hasil pemeriksaan reviewer (tanpa PDF tambahan)</option>`:''}${r.documents.filter(d=>d.type==='EVIDENCE'||source?.document_id===d.id).map(d=>`<option value="${escape(d.id)}" ${source?.source_type!=='REVIEWER'&&source?.document_id===d.id?'selected':''}>${escape(d.original_filename)}</option>`).join('')}`;
}
export function accountSourcePayload(r,sources,selection){
  if(!selection)return null;
  if(selection==='REVIEWER'){
    if(sources.account_number?.source_type==='REVIEWER')return sources.account_number;
    const doc=r.documents.find(d=>d.type==='INVOICE'&&d.current_source)??r.documents.find(d=>d.type==='INVOICE');
    return {document_id:doc?.id,source_type:'REVIEWER',page:null,notes:null};
  }
  const doc=r.documents.find(d=>d.id===selection),previous=sources.account_number?.document_id===selection?sources.account_number:{};
  return {...previous,document_id:selection,source_type:doc?.type==='EVIDENCE'?'EVIDENCE':previous.source_type==='REVIEWER'?'MANUAL':previous.source_type??'MANUAL'};
}
export function reviewAdditionsHTML(sources,escape){
  const rows=Object.entries(sources).filter(([,s])=>s?.source_type==='REVIEWER');
  if(!rows.length)return '';
  const names={vendor_name:'Vendor',invoice_number:'Nomor invoice',invoice_date:'Tanggal invoice',due_date:'Jatuh tempo',currency:'Mata uang',subtotal:'Subtotal',invoice_discount_amount:'Diskon',invoice_tax_amount:'Pajak',total_amount:'Total',bank_name:'Bank',account_number:'Nomor rekening',account_holder:'Pemilik rekening'};
  return `<div class="callout"><strong>Tambahan / koreksi reviewer</strong><p>Data ini berasal dari pemeriksaan reviewer dan tidak harus tercantum pada PDF sumber.</p><ul>${rows.map(([field,s])=>`<li>${escape(names[field]??field)}: ${escape(s.notes??'Dicatat pada hasil pemeriksaan.')}</li>`).join('')}</ul></div>`;
}
export function manualTaxStale(inv){return Boolean(inv.manual_review_pdf&&inv.voucher_tax?.applied&&inv.voucher_tax.edited_at&&inv.manual_review_pdf.created_at<inv.voucher_tax.edited_at);}
export function generatedVoucherHTML(inv){
  if(!inv.manual_review_pdf)return '';
  return `<div class="callout ${manualTaxStale(inv)?'warn':''}">${manualTaxStale(inv)?'<p>Pajak diperbarui setelah PDF manual diunggah. Kamu bisa memakai voucher otomatis dari data terbaru tanpa mengunggah PDF baru.</p>':''}<label class="checkbox"><input type="checkbox" id="use-generated-voucher">Gunakan voucher otomatis dari data tersimpan. PDF manual tetap di riwayat; tanda tangan pada PDF manual tidak disalin.</label></div>`;
}
