import {calculateLine,decimal} from './money.js';
import {readMoneyValue,writeMoneyValue} from './money-fields.js';
const rounded=(n,d)=>n<0n?-((-n+d/2n)/d):(n+d/2n)/d;
export function amountFromCents(value){const n=BigInt(value);if(n<0n)throw Error('Hasil hitung tidak boleh negatif.');return `${n/100n}.${String(n%100n).padStart(2,'0')}`;}
export function deriveTotals(rows,discount,tax,withholding='0'){
  if(!rows.length||rows.some(v=>v==null))throw Error('Lengkapi seluruh rincian item untuk menghitung total.');
  if(rows.some(v=>BigInt(v)<0n))throw Error('Hasil baris tidak boleh negatif.');
  const subtotal=rows.reduce((sum,v)=>sum+BigInt(v),0n),d=decimal(discount,6),t=decimal(tax,6),p=decimal(withholding,6);
  if([subtotal,d,t,p].some(n=>n<0n))throw Error('Nominal tidak boleh negatif.');
  const total=rounded(subtotal*10000n-d+t-p,10000n);
  return {subtotal:amountFromCents(subtotal),total:amountFromCents(total)};
}
export function automaticInvoiceHTML(){
  return `<div class="callout"><label class="checkbox"><input id="automatic-invoice" type="checkbox" checked>Hitung otomatis total baris, subtotal dan total akhir dari data AI</label><p>Hasil AI langsung terisi. Koreksi jumlah, harga, diskon atau pajak; total mengikuti otomatis. Matikan pilihan ini untuk mengoreksi total secara manual. Angka asli tetap tersedia di PDF dan riwayat.</p><span id="automatic-invoice-status" role="status"></span></div>`;
}
export function mountAutomaticInvoice({form,readFields,getWithholding=()=> '0'}){
  const toggle=form.querySelector('#automatic-invoice');if(!toggle)return {sync:()=>false};
  const set=(input,value,currency)=>{const before=readMoneyValue(input);let equal=before===value;try{if(before!=null&&value!=null)equal=decimal(before,6)===decimal(value,6);}catch{/* Invalid old value is replaced only in automatic output fields. */}writeMoneyValue(input,value,currency);return !equal;};
  return {sync(){
    const derived=[...form.querySelectorAll('[data-item="line_total"],[data-field="subtotal"],[data-field="total_amount"]')];derived.forEach(i=>i.readOnly=toggle.checked);
    if(!toggle.checked){form.querySelector('#automatic-invoice-status').textContent='Koreksi total manual aktif; perhitungan tetap diperiksa saat disimpan.';return false;}
    const draft=readFields(),rows=[];let changed=false,invalid=false;
    form.querySelectorAll('#item-body tr').forEach((row,index)=>{
      let value=null;try{const cents=calculateLine(draft.line_items[index]);value=amountFromCents(cents);rows.push(cents);}catch{rows.push(null);invalid=true;}
      changed=set(row.querySelector('[data-item="line_total"]'),value,draft.currency)||changed;
    });
    let subtotal=null,total=null;
    if(rows.length&&rows.every(v=>v!=null))subtotal=amountFromCents(rows.reduce((sum,v)=>sum+BigInt(v),0n));
    try{const result=deriveTotals(rows,draft.invoice_discount_amount,draft.invoice_tax_amount,getWithholding());total=result.total;}catch{invalid=true;}
    changed=set(form.querySelector('[data-field="subtotal"]'),subtotal,draft.currency)||changed;
    changed=set(form.querySelector('[data-field="total_amount"]'),total,draft.currency)||changed;
    form.querySelector('#automatic-invoice-status').textContent=invalid?'Lengkapi atau koreksi angka yang belum valid. Nilai yang belum dapat dihitung tidak dianggap nol.':'Total sudah dihitung otomatis. Periksa hasil sebelum menyimpan.';
    return changed;
  }};
}
