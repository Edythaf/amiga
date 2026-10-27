import {headerTaxForEffectiveTax,baseTotalForEffectiveNet,voucherAmountFieldsHTML} from '../portal/src/js/voucher-amounts.js';
import {calculateVoucherTax} from '../portal/src/js/voucher-tax.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {formatAmount,parseAmount,readMoneyValue,currencyField,currencyOptions} from '../portal/src/js/money-fields.js';
import {amountFromCents,deriveTotals} from '../portal/src/js/automatic-invoice.js';
import {calculateLine} from '../portal/src/js/money.js';

test('Grouped currency inputs round-trip exact decimal strings without floating point or stripping cents',()=>{
  assert.equal(formatAmount('1000000','IDR'),'Rp 1.000.000');
  assert.equal(formatAmount('1000000.50','IDR'),'Rp 1.000.000,50');
  assert.equal(formatAmount('0','IDR'),'Rp 0');assert.equal(formatAmount(null),'');
  for(const currency of Object.keys(currencyOptions))for(const raw of ['0','1000000','1250.000001','999999999999999999.123456'])assert.equal(parseAmount(formatAmount(raw,currency)),raw,currency+raw);
  assert.equal(parseAmount('1.000.000,50'),'1000000.50');assert.equal(parseAmount('1000000'),'1000000');
  assert.equal(parseAmount('Rp 1,'),'1.');assert.equal(parseAmount(''),null);
  assert.equal(formatAmount('0000100.05','USD'),'US$ 100,05');
});
test('Invalid or negative input remains invalid instead of becoming zero or losing decimal precision',()=>{
  for(const raw of ['Rp -100','1.23','1.000.00','NaN','1e6','1,2345678','1000.50','Rp 1.000,00,00'])assert.throws(()=>parseAmount(raw),raw);
  for(const raw of ['-1','1.1234567','1000000000000000000','Infinity'])assert.throws(()=>formatAmount(raw),raw);
  const input={value:'Rp 1.234,50',hasAttribute:()=>true};assert.equal(readMoneyValue(input),'1234.50');input.value='-5';assert.equal(readMoneyValue(input),'-5');
});
test('Automatic invoice math matches existing backend fixtures and includes existing source withholding once',async()=>{
  const fixtures=JSON.parse(await fs.readFile(new URL('../../tests/fixtures/invoice_math.json',import.meta.url),'utf8'));
  for(const c of fixtures){const rows=c.items.map(([quantity,unit_price,discount_amount,tax_amount])=>calculateLine({quantity,unit_price,discount_amount,tax_amount}));const actual=deriveTotals(rows,c.discount,c.tax);assert.equal(actual.subtotal,c.subtotal,c.name);assert.equal(actual.total,c.total,c.name);}
  assert.deepEqual(deriveTotals([250000000],'0','0','50000'),{subtotal:'2500000.00',total:'2450000.00'});
  assert.throws(()=>deriveTotals([null],'0','0'));assert.throws(()=>deriveTotals([100],null,'0'));assert.throws(()=>deriveTotals([-1,100],'0','0'));
  assert.throws(()=>amountFromCents(-1));assert.equal(amountFromCents(100000001),'1000000.01');
});
test('Currency choices retain an existing foreign currency and do not imply exchange-rate conversion',()=>{
  const escape=v=>String(v).replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const html=currencyField('KRW',escape);assert.match(html,/value="KRW" selected/);assert.match(html,/value="IDR"/);assert.match(html,/value="USD"/);assert.match(html,/tidak mengonversi nominal/);
  assert.doesNotMatch(currencyField('<script>',escape),/<script>/);
});


test('Primary tax and total show effective voucher amounts while payload keeps the calculation basis, including source line taxes',()=>{
  const f={subtotal:'10760000',invoice_discount_amount:'0',invoice_tax_amount:'1155000',total_amount:'11915000',currency:'IDR',line_items:[{tax_amount:'10000'}]};
  const p={vat_mode:'REPLACE',vat_base:'10760000',vat_rate:'0',withholding_mode:'DEDUCT',withholding_base:'10760000',withholding_rate:'7',source_withholding:'0'};
  const before=JSON.stringify(f),result=calculateVoucherTax(f,p);
  assert.equal(formatAmount(amountFromCents(result.vatTotal)),'Rp 0,00');assert.equal(formatAmount(amountFromCents(result.net)),'Rp 9.996.800,00');
  assert.equal(baseTotalForEffectiveNet(f,p,'9996800'),'11915000.00');assert.equal(calculateVoucherTax({...f,total_amount:baseTotalForEffectiveNet(f,p,'9000000')},p).net,900000000);
  assert.equal(JSON.stringify(f),before);
  const html=voucherAmountFieldsHTML(f,String);assert.match(html,/id="field-total_amount" data-voucher-amount="net"/);assert.match(html,/id="source-total-amount" data-field="total_amount"/);assert.doesNotMatch(html,/id="field-total_amount" data-field=/);
});
test('Direct correction of final tax converts only the header remainder; line tax cannot be hidden or deducted twice',()=>{
  const f={total_amount:'1110000',invoice_tax_amount:'100000',line_items:[{tax_amount:'10000'}]};
  const header=headerTaxForEffectiveTax(f,'120000');assert.equal(header,'110000.000000');
  const plan={vat_mode:'KEEP',vat_base:'0',vat_rate:'0',withholding_mode:'KEEP',withholding_base:'0',withholding_rate:'0',source_withholding:'0'};
  assert.equal(calculateVoucherTax({...f,invoice_tax_amount:header,total_amount:'1120000'},plan).vatTotal,12000000);
  assert.throws(()=>headerTaxForEffectiveTax(f,'5000'));assert.throws(()=>baseTotalForEffectiveNet(f,plan,'-1'));
});
import {requestLabel,bindDoubleOpen} from '../portal/src/js/workspace-interactions.js';
test('Readable request codes retain canonical identity and fallback to old ids',()=>{
  assert.equal(requestLabel({id:'req_old',request_code:'REQ-20261016-0001-PT-MAJU-0001'}),'REQ-20261016-0001-PT-MAJU-0001');
  assert.equal(requestLabel({id:'req_old'}),'req_old');
});
test('Double-open and Enter navigate once without intercepting inline actions',()=>{
  const listeners={},row={classList:{add(){}},addEventListener:(type,fn)=>listeners[type]=fn};let opens=0;
  bindDoubleOpen({querySelectorAll:()=>[row]},'rows',()=>opens++);
  listeners.dblclick({target:{closest:()=>null}});assert.equal(opens,1);
  listeners.dblclick({target:{closest:()=>({})}});assert.equal(opens,1);
  let prevented=false;listeners.keydown({target:row,key:'Enter',preventDefault(){prevented=true;}});
  assert.equal(opens,2);assert.equal(prevented,true);assert.equal(row.tabIndex,0);
});
test('Direct PPh correction overrides the AI percentage exactly without deducting source twice',()=>{
  const f={invoice_tax_amount:'0',line_items:[{tax_amount:'0'}],total_amount:'900'};
  const p={vat_mode:'KEEP',vat_rate:'0',vat_base:'1000',withholding_mode:'REPLACE',withholding_rate:'2',withholding_base:'1000',source_withholding:'100',withholding_amount:'123.45'};
  const c=calculateVoucherTax(f,p);assert.equal(c.withholdingTotal,12345);assert.equal(c.withholding,2345);assert.equal(c.net,87655);
  assert.equal(calculateVoucherTax(f,{...p,withholding_amount:null}).net,98000);
  assert.throws(()=>calculateVoucherTax(f,{...p,withholding_amount:'-1'}));
  const html=voucherAmountFieldsHTML({subtotal:'1',currency:'IDR'},String);
  assert.doesNotMatch(html,/data-voucher-amount="pph"[^>]*readonly/);
});
