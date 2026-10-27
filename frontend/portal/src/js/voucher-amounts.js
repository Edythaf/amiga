import {invoiceField} from './invoice-inputs.js';
import {decimal,cents} from './money.js';
import {readMoneyValue,writeMoneyValue} from './money-fields.js';
import {calculateVoucherTax} from './voucher-tax.js';
import {amountFromCents} from './automatic-invoice.js';

export function headerTaxForEffectiveTax(fields,desired){
  const lineTax=fields.line_items.reduce((sum,row)=>sum+decimal(row.tax_amount,6),0n);
  const header=decimal(desired,6)-lineTax;
  if(header<0n)throw Error('Pajak akhir lebih kecil dari pajak pada item. Koreksi pajak item terlebih dahulu.');
  return `${header/1000000n}.${String(header%1000000n).padStart(6,'0')}`;
}
export function baseTotalForEffectiveNet(fields,plan,desired){
  const c=calculateVoucherTax(fields,plan);
  return amountFromCents(BigInt(cents(desired))-BigInt(c.vat)+BigInt(c.withholding));
}
export function voucherAmountFieldsHTML(fields,escape){
  const primary=(id,label,value,kind,readonly=false)=>`<div><label for="${id}">${label}</label><input id="${id}" data-voucher-amount="${kind}" data-money inputmode="decimal" value="${escape(value)}" ${readonly?'readonly':''}></div>`;
  return `<div class="form-grid">${invoiceField(escape,'Subtotal rincian','subtotal',fields.subtotal,'number')}${invoiceField(escape,'Diskon tingkat invoice','invoice_discount_amount',fields.invoice_discount_amount,'number')}${primary('field-invoice_tax_amount','PPN / pajak voucher setelah koreksi',fields.invoice_tax_amount,'vat')}${primary('field-voucher-pph','PPh / potongan voucher','0','pph')}${primary('field-total_amount','Total akhir voucher',fields.total_amount,'net')}</div><div class="actions"><button type="button" id="edit-voucher-tax">Ubah persentase / dasar PPN</button><button type="button" id="edit-voucher-pph">Ubah persentase / dasar PPh</button></div><p class="subtle">Nominal di atas sudah mengikuti koreksi pajak. Total akhir dapat dikoreksi manual; ini mematikan hitung otomatis.</p><details><summary>Angka invoice sebelum penyesuaian pajak</summary><p class="subtle">Nilai dasar untuk perhitungan; penyesuaian pajak hanya diterapkan sekali.</p><div class="form-grid">${invoiceField(escape,'Pajak tingkat invoice sebelum penyesuaian','invoice_tax_amount',fields.invoice_tax_amount,'number').replaceAll('field-invoice_tax_amount','source-invoice-tax')}${invoiceField(escape,'Total sebelum penyesuaian pajak','total_amount',fields.total_amount,'number').replaceAll('field-total_amount','source-total-amount')}</div></details>`;
}
export function mountVoucherAmounts({form,getFields,getPlan,setVatMode,setWithholdingAmount}){
  const vat=form.querySelector('[data-voucher-amount="vat"]'),net=form.querySelector('[data-voucher-amount="net"]'),pph=form.querySelector('[data-voucher-amount="pph"]');
  if(!vat)return {update:()=>{}};
  function update(c,fields){
    for(const [input,value] of [[vat,c?.vatTotal],[pph,c?.withholdingTotal],[net,c?.net]]){
      if(input===document.activeElement||input.validity.customError)continue;
      writeMoneyValue(input,value==null?null:amountFromCents(value),fields.currency);
    }
  }
  vat.addEventListener('input',()=>{
    try{const desired=readMoneyValue(vat);if(desired==null)throw Error('Isi nominal pajak voucher.');const fields=getFields();if(cents(desired)===calculateVoucherTax(fields,getPlan()).vatTotal){vat.setCustomValidity('');return;}writeMoneyValue(form.querySelector('[data-field="invoice_tax_amount"]'),headerTaxForEffectiveTax(fields,desired),fields.currency);setVatMode('KEEP');vat.setCustomValidity('');}
    catch(error){vat.setCustomValidity(error.message);}
  });
  pph.addEventListener('input',()=>{try{const value=readMoneyValue(pph);if(value==null||decimal(value,6)<0n)throw Error('Isi potongan yang valid.');setWithholdingAmount(value);pph.setCustomValidity('');}catch(error){pph.setCustomValidity(error.message);}});
  net.addEventListener('input',()=>{
    try{const desired=readMoneyValue(net);if(desired==null)throw Error('Isi total akhir voucher.');const fields=getFields(),base=baseTotalForEffectiveNet(fields,getPlan(),desired);const toggle=form.querySelector('#automatic-invoice');if(toggle)toggle.checked=false;writeMoneyValue(form.querySelector('[data-field="total_amount"]'),base,fields.currency);net.setCustomValidity('');}
    catch(error){net.setCustomValidity(error.message);}
  });
  for(const input of [vat,net,pph])input.addEventListener('blur',()=>{try{update(calculateVoucherTax(getFields(),getPlan()),getFields());}catch{/* Keep invalid input visible. */}});
  for(const [id,name] of [['edit-voucher-tax','vat_rate'],['edit-voucher-pph','withholding_rate']])form.querySelector('#'+id)?.addEventListener('click',()=>document.querySelector(`#voucher-tax-form [name="${name}"]`)?.focus());
  return {update};
}
