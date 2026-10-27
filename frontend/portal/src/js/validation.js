import {calculate,cents} from './money.js';
export const VENDORS = [
  {id:'A-paper',client:'A',name:'PT Kertas Demo',aliases:['pt kertas demo','kertas demo','vendor bersama']},
  {id:'A-other',client:'A',name:'PT Mitra Demo',aliases:['pt mitra demo','vendor bersama']},
  {id:'B-paper',client:'B',name:'PT Kertas Demo',aliases:['pt kertas demo','kertas demo','vendor bersama']}
];
export const normalize = value=>String(value??'').normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();
export const vendorMatches = (client,name)=>VENDORS.filter(v=>v.client===client && v.aliases.includes(normalize(name)));
export function validate(state,request) {
  const v=request.versions.at(-1), d=v.draft, flags=[]; let calc=null;
  const add=(code,severity,message)=>flags.push({code,severity,message});
  const required=['vendor_name','invoice_number','invoice_date','currency','subtotal','total_amount','invoice_discount_amount','invoice_tax_amount'];
  const missing=required.filter(k=>d[k]===null || d[k]===undefined || String(d[k]).trim()==='');
  if(missing.length) add('REQUIRED_HEADER','BLOCK',`Field wajib belum lengkap: ${missing.join(', ')}`);
  if(d.currency!=='IDR') add('UNSUPPORTED_CURRENCY','BLOCK','Demo ini hanya mendukung IDR; jangan menghitung currency lain sebagai Rupiah.');
  const vm=vendorMatches(request.client,d.vendor_name);
  if(vm.length!==1) add(vm.length?'AMBIGUOUS_VENDOR':'UNKNOWN_VENDOR','BLOCK',vm.length?'Alias vendor ambigu. Pilih nama master yang tepat.':'Vendor belum cocok dengan master klien.');
  if(!d.account_number || !d.bank_name || !d.account_holder) add('MISSING_EVIDENCE','BLOCK','Rekening, nama bank, atau pemilik rekening belum lengkap.');
  if(!v.sources.account_number || (!v.sources.account_number.startsWith('Invoice PDF:') && !request.documents.some(x=>x.type==='EVIDENCE' && v.sources.account_number.includes(x.id)))) add('MISSING_EVIDENCE','BLOCK','Rekening memerlukan sumber dari invoice atau bukti pendukung yang diunggah.');
  if(v.sources.account_number?.startsWith('Invoice PDF:')&&!request.runs.some(run=>run.raw?.draft?.account_number)) add('MISSING_EVIDENCE','BLOCK','Tidak ada rekening pada hasil invoice terdaftar. Tambahkan bukti rekening sebelum review.');
  if(!d.line_items.length || v.expectedItems===null || d.line_items.length!==v.expectedItems || d.line_items.some(x=>!x.description || ['quantity','unit_price','discount_amount','tax_amount','line_total'].some(k=>x[k]===null || x[k]===undefined || x[k]===''))) add('INCOMPLETE_ITEMS','BLOCK','Semua baris dan nilai item harus lengkap; jumlah item harus dikonfirmasi sesuai dokumen.');
  try {
    calc=calculate(d);
    const tolerance=cents(state.tolerance);
    if(tolerance<0) throw Error('Toleransi harus positif.');
    if(calc.rows.some((n,i)=>Math.abs(n-cents(d.line_items[i].line_total))>tolerance) || Math.abs(calc.subtotal-cents(d.subtotal))>tolerance || Math.abs(calc.delta)>tolerance) add('FALSE_CALCULATION','BLOCK','Nilai dokumen berbeda dari hasil hitung di luar toleransi.');
    if(calc.total<0 || cents(d.invoice_discount_amount)<0 || cents(d.invoice_tax_amount)<0) add('INVALID_AMOUNT','BLOCK','Nominal negatif belum didukung.');
  } catch(e) { add('INVALID_AMOUNT','BLOCK',e.message); }
  const others=state.requests.filter(x=>x.id!==request.id && x.client===request.client);
  const sameFile=others.filter(x=>x.documents[0].hash===request.documents[0].hash);
  if(sameFile.length) add('DUPLICATE_FILE','BLOCK',`PDF identik: ${sameFile.map(x=>x.id).join(', ')}`);
  const sameInvoice=others.filter(x=>{const od=x.versions.at(-1)?.draft; return od && normalize(od.invoice_number) && normalize(od.invoice_number)===normalize(d.invoice_number) && vendorMatches(x.client,od.vendor_name).some(a=>vm.some(b=>a.id===b.id));});
  if(sameFile.length || sameInvoice.length) add('POSSIBLE_DUPLICATE','BLOCK',`Periksa invoice terkait: ${[...new Set([...sameFile,...sameInvoice].map(x=>x.id))].join(', ')}`);
  if(d.invoice_date && !/^\d{4}-\d{2}-\d{2}$/.test(d.invoice_date)) add('INVALID_DATE','BLOCK','Tanggal invoice harus menggunakan YYYY-MM-DD.');
  if(d.invoice_date && d.due_date && d.due_date<d.invoice_date) add('SUSPICIOUS_DATE','WARN','Tanggal jatuh tempo lebih awal dari invoice; wajib acknowledgement dengan alasan.');
  const resolutions=request.resolutions.filter(x=>x.version===v.number);
  return {version:v.number,at:new Date().toISOString(),calc,flags:flags.map(f=>({...f,resolution:resolutions.findLast(x=>x.code===f.code)??null}))};
}
export const unresolved = validation=>validation.flags.filter(f=>!f.resolution);
export const RESOLVABLE = ['DUPLICATE_FILE','POSSIBLE_DUPLICATE','SUSPICIOUS_DATE'];
