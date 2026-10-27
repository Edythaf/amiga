import {showReason} from './workspace-interactions.js';
import {bindMoneyFields,readMoneyForm,writeMoneyValue} from './money-fields.js';
import {decimal,cents,money} from './money.js';
const rounded=(n,d)=>n<0n?-((-n+d/2n)/d):(n+d/2n)/d;
export function calculateVoucherTax(fields,p){
  const val=v=>decimal(v,6),percent=(base,rate)=>{const b=val(base),r=val(rate);if(b<0n||r<0n||r>100000000n)throw Error('Periksa dasar dan tarif pajak (0–100%).');return rounded(b*r,1000000000000n);};
  const taxes=[fields.invoice_tax_amount,...fields.line_items.map(r=>r.tax_amount)];
  if(p.vat_mode!=='KEEP'&&taxes.some(v=>v==null||v===''))throw Error('Konfirmasikan pajak sumber dahulu.');
  const sourceVat=rounded(taxes.reduce((sum,v)=>sum+val(v??'0'),0n),10000n),sourcePph=BigInt(cents(p.source_withholding));
  if(sourcePph<0n)throw Error('PPh sumber tidak boleh negatif.');
  if(p.vat_mode==='ADD'&&sourceVat>0n)throw Error('Pajak sudah ada; gunakan Pertahankan atau Ganti.');
  if(p.withholding_mode==='DEDUCT'&&sourcePph>0n)throw Error('PPh sudah ada; gunakan Pertahankan atau Ganti.');
  const vat=percent(p.vat_base,p.vat_rate),pph=p.withholding_amount!=null&&p.withholding_amount!==''?BigInt(cents(p.withholding_amount)):percent(p.withholding_base,p.withholding_rate);if(pph<0n)throw Error('Potongan tidak boleh negatif.');
  const vatDelta=p.vat_mode==='KEEP'?0n:vat-(p.vat_mode==='REPLACE'?sourceVat:0n),pphDelta=p.withholding_mode==='KEEP'?0n:pph-(p.withholding_mode==='REPLACE'?sourcePph:0n);
  const net=BigInt(cents(fields.total_amount))+vatDelta-pphDelta;
  if(net<0n||[net,vatDelta,pphDelta,sourceVat+vatDelta,sourcePph+pphDelta].some(v=>v>BigInt(Number.MAX_SAFE_INTEGER)||v< -BigInt(Number.MAX_SAFE_INTEGER)))throw Error('Nilai akhir voucher di luar batas.');
  return {vat:Number(vatDelta),withholding:Number(pphDelta),net:Number(net),vatTotal:Number(sourceVat+vatDelta),withholdingTotal:Number(sourcePph+pphDelta)};
}
function taxHTML(inv,escape,editable){
  const tax=inv.voucher_tax,p=tax?.plan??{vat_mode:'KEEP',vat_rate:'0',vat_base:inv.fields.subtotal??'0',withholding_mode:'KEEP',withholding_kind:'PPh',withholding_rate:'0',withholding_base:inv.fields.subtotal??'0',source_withholding:'0',note:''};
  const follows=key=>{try{return decimal(p[key],6)===decimal(inv.fields.subtotal,6);}catch{return false;}};
  const input=(key,label)=>`<div><label>${label}<input name="${key}" type="${key.endsWith('rate')?'number':'text'}" ${key.endsWith('rate')?'min="0" max="100" step="any"':'data-money inputmode="decimal"'} value="${escape(p[key])}" ${key==='withholding_amount'?'':'required'}></label>${['vat_base','withholding_base'].includes(key)?`<label class="checkbox"><input type="checkbox" data-follow-base="${key}" ${follows(key)?'checked':''}>Ikuti subtotal rincian</label>`:''}</div>`;
  const select=(key,label,options)=>`<label>${label}<select name="${key}">${Object.entries(options).map(([k,v])=>`<option value="${k}" ${p[key]===k?'selected':''}>${v}</option>`).join('')}</select></label>`;
  return `<div class="panel-head"><h2>Pajak & nilai akhir voucher</h2><span class="tiny-tag">${tax?.applied?'Tersimpan':'Usulan / belum diterapkan'}</span></div><div class="panel-body"><p>AI mengusulkan jenis dan tarif dari transaksi. Reviewer boleh mengubah dasar, tarif dan perlakuannya. Nilai invoice sumber tetap tersimpan.</p><div class="callout" role="status" id="tax-ai-status">${tax?.ai_state==='RUNNING'?'AI sedang memeriksa pajak…':escape(tax?.ai_result?.note||'AI akan memeriksa pajak yang sudah ada dan usulan pajak yang belum tertulis.')}${tax?.ai_result?.missing_facts?.length?`<ul>${tax.ai_result.missing_facts.map(v=>`<li>${escape(v)}</li>`).join('')}</ul>`:''}</div>${tax?.ai_result?.evidence?.length?`<details><summary>Dasar usulan AI</summary>${tax.ai_result.evidence.map(v=>`<p>${escape(v)}</p>`).join('')}</details>`:''}<form id="voucher-tax-form"><fieldset class="review-fields" ${editable?'':'disabled'}><div class="form-grid">${select('vat_mode','PPN',{KEEP:'Pertahankan pajak sumber',ADD:'Tambahkan PPN yang belum ada',REPLACE:'Ganti nilai PPN sumber'})}${input('vat_rate','Tarif efektif PPN (%)')}${input('vat_base','Dasar perhitungan PPN')}${select('withholding_mode','PPh',{KEEP:'Pertahankan potongan sumber',DEDUCT:'Potong PPh yang belum ada',REPLACE:'Ganti potongan PPh sumber'})}<label>Jenis PPh<input name="withholding_kind" value="${escape(p.withholding_kind)}" maxlength="80" required></label>${input('withholding_rate','Tarif PPh (%)')}${input('withholding_base','Dasar perhitungan PPh')}${input('source_withholding','PPh yang SUDAH dikurangi dalam total PDF')}${input('withholding_amount','Koreksi nominal PPh (opsional)')}</div><p class="subtle">Jika koreksi nominal PPh diisi, nominal itu yang digunakan. Ubah tarif atau dasar PPh untuk kembali menghitung berdasarkan persentase.</p><p class="subtle">Pajak yang sudah ada tidak ditambahkan lagi. Gunakan Ganti bila perlu koreksi. Dasar PPh untuk invoice campuran dapat hanya mencakup nilai jasa.</p><label>Alasan / hasil pemeriksaan pajak<textarea class="review-reason" name="note" rows="5" maxlength="2000" required>${escape(p.note)}</textarea></label><div id="tax-calculation" class="callout" role="status"></div>${editable?'<label class="checkbox"><input name="acknowledged" type="checkbox" required>Saya memeriksa objek pajak, tarif, dasar, dan potongan yang sudah tercatat.</label><div class="actions"><button class="primary" type="submit">Simpan hasil review & pajak</button><button type="button" id="tax-discard">Batalkan perubahan pajak</button><button type="button" id="tax-retry">Periksa pajak dengan AI</button></div>':''}</fieldset></form><button type="button" id="tax-reason-open">Alasan lengkap</button>${!editable?'<p class="callout">Versi voucher ini sudah diputuskan atau ditutup. Gunakan alur revisi untuk mengoreksi hasil terbit.</p>':''}${inv.manual_review_pdf&&tax?.edited_at&&inv.manual_review_pdf.created_at<tax.edited_at?'<p class="callout warn">Pajak berubah setelah PDF final diunggah. Pilih voucher otomatis dari data terbaru saat penerbitan, atau unggah PDF final yang disesuaikan.</p>':''}</div>`;
}

export function liveTaxSummaryHTML(){return `<div class="callout" id="live-review-summary" role="status"><strong>Ringkasan voucher setelah pajak</strong><div class="form-grid"><div>Subtotal rincian<br><strong id="live-subtotal">—</strong></div><div>PPN / pajak setelah koreksi<br><strong id="live-vat">—</strong></div><div>PPh / potongan setelah koreksi<br><strong id="live-pph">—</strong></div><div>Total akhir voucher<br><strong id="live-net">—</strong></div></div><p id="live-tax-state">Perubahan angka langsung dihitung; simpan untuk menerapkan.</p></div>`;}

export function mountVoucherTax({root,api,r,inv,escape,run,toast,editable,isCurrent,invoiceDirty,onDirty,getFields=()=>inv.fields,onPreview=()=>{},onSave,onChange=()=>{}}){
  if(!root)return null;let dirty=false,read=()=>inv.voucher_tax?.plan,refresh=()=>{},check=()=>true;
  function render(){
    root.innerHTML=taxHTML(inv,escape,editable);
    const form=root.querySelector('#voucher-tax-form'),moneyFields=bindMoneyFields(form,()=>getFields().currency||'IDR');let displayedCurrency=getFields().currency;
    read=()=>editable?Object.fromEntries(Object.entries(readMoneyForm(form)).filter(([k])=>k!=='acknowledged')):(inv.voucher_tax?.plan??{vat_mode:'KEEP',vat_rate:'0',vat_base:'0',withholding_mode:'KEEP',withholding_rate:'0',withholding_base:'0',source_withholding:'0',withholding_amount:null});
    root.querySelector('#tax-reason-open').onclick=()=>showReason(form.elements.note.value,{editable,onSave:value=>{form.elements.note.value=value;form.elements.note.dispatchEvent(new Event('input',{bubbles:true}));}});
    check=()=>form.reportValidity();
    refresh=()=>{
      const fields=getFields();if(fields.currency!==displayedCurrency){moneyFields.reformat();displayedCurrency=fields.currency;}if(editable){for(const key of ['vat_base','withholding_base']){if(form.querySelector(`[data-follow-base="${key}"]`)?.checked){try{writeMoneyValue(form.elements[key],fields.subtotal,fields.currency);}catch{/* Unknown subtotal stays invalid, never zero. */}}}}const plan=read(),target=root.querySelector('#tax-calculation');
      try{const c=calculateVoucherTax(fields,plan);target.innerHTML=`<strong>Ringkasan voucher terbaru</strong><div class="form-grid"><div>Subtotal rincian<br><strong>${escape(money(fields.subtotal,fields.currency))}</strong></div><div>PPN / pajak setelah koreksi<br><strong>${escape(money(c.vatTotal/100,fields.currency))}</strong></div><div>PPh / potongan setelah koreksi<br><strong>${escape(money(c.withholdingTotal/100,fields.currency))}</strong></div><div>Total akhir voucher<br><strong>${escape(money(c.net/100,fields.currency))}</strong></div></div><small>${dirty||invoiceDirty()||!inv.voucher_tax?.applied?'Pratinjau langsung — simpan hasil review untuk menerapkan.':'Data dan pajak tersimpan.'}</small>`;onPreview(c,fields,plan,null);}
      catch(error){target.textContent=error.message;onPreview(null,fields,plan,error);}
    };
    refresh();
    form.oninput=event=>{
      // A changed rate expresses an adjustment; retaining the old tax unchanged
      // would otherwise hide the effect of the edit. The selected mode is visible.
      const key=event.target.name;if(['withholding_rate','withholding_base'].includes(key))writeMoneyValue(form.elements.withholding_amount,null,getFields().currency);if(key==='withholding_amount'&&event.target.value.trim())form.elements.withholding_mode.value=Number(read().source_withholding)>0?'REPLACE':'DEDUCT';if(['vat_base','withholding_base'].includes(key))form.querySelector(`[data-follow-base="${key}"]`).checked=false;
      if(['vat_rate','vat_base'].includes(key)&&form.elements.vat_mode.value==='KEEP'){
        const f=getFields();form.elements.vat_mode.value=[f.invoice_tax_amount,...f.line_items.map(i=>i.tax_amount)].some(v=>Number(v)>0)?'REPLACE':'ADD';
      }
      if(['withholding_rate','withholding_base'].includes(key)&&form.elements.withholding_mode.value==='KEEP')form.elements.withholding_mode.value=Number(read().source_withholding)>0?'REPLACE':'DEDUCT';
      dirty=true;onDirty(true);refresh();onChange();
    };
    root.querySelector('#tax-discard')?.addEventListener('click',()=>{dirty=false;onDirty(false);render();onChange();});
    form.onsubmit=e=>{e.preventDefault();save();};
    root.querySelector('#tax-retry')?.addEventListener('click',()=>{if(dirty||invoiceDirty()){toast('Simpan hasil review atau batalkan perubahan sebelum analisis pajak.',true);return;}analyze();});
  }
  function save(){
    if(!check())return;
    const plan=read(),acknowledged=root.querySelector('[name="acknowledged"]')?.checked===true;
    if(onSave){onSave({plan,acknowledged});return;}
    if(invoiceDirty()){toast('Simpan data invoice dahulu.',true);return;}
    run(async()=>{inv.voucher_tax=await api.saveVoucherTax(r.id,inv.id,{expected_version:inv.current_version,expected_tax_revision:inv.voucher_tax?.revision??0,acknowledged,plan});dirty=false;onDirty(false);toast('Pajak tersimpan. Ringkasan dan voucher memakai nilai akhir terbaru.');});
  }
  async function analyze(){
    if(!editable)return;const status=root.querySelector('#tax-ai-status');status.textContent='AI sedang memeriksa pajak…';
    try{const result=await api.analyzeVoucherTax(r.id,inv.id,inv.current_version);if(!isCurrent())return;inv.voucher_tax=result;if(!dirty){render();onChange();}else status.textContent='Usulan AI tersimpan. Koreksi yang sedang kamu isi tetap dipertahankan.';}
    catch(error){if(isCurrent())status.textContent=error.message;}
  }
  render();if(editable&&!inv.voucher_tax?.applied&&(!inv.voucher_tax||inv.voucher_tax.ai_state==='NONE'))analyze();
  return {getPlan:()=>read(),refresh:()=>refresh(),save,setWithholdingAmount(value){const form=root.querySelector('#voucher-tax-form');if(!editable)return;writeMoneyValue(form.elements.withholding_amount,value,getFields().currency);form.elements.withholding_mode.value=Number(read().source_withholding)>0?'REPLACE':'DEDUCT';dirty=true;onDirty(true);},setMode(key,value){const field=root.querySelector(`[name="${key}"]`);if(field){field.value=value;dirty=true;onDirty(true);}},clearDirty(){dirty=false;onDirty(false);}};
}
