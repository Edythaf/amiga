// Adapter contract: extract(document, profile) -> { draft, sources, raw }.
export class Extractor { async extract() { throw Error('Adapter ekstraksi belum diimplementasikan.'); } }
export class FakeExtractor extends Extractor {
  constructor(fixtures, delay = 500) { super(); this.fixtures=fixtures; this.delay=delay; }
  async extract(document, profile) {
    if(this.delay) await new Promise(resolve=>setTimeout(resolve,this.delay));
    const fixture=this.fixtures.find(x=>x.sha256===document.hash);
    if(!fixture) throw Error('Ekstraksi otomatis tidak tersedia pada demo; gunakan fixture atau isi draft secara manual.');
    const draft=structuredClone(fixture.draft);
    const sources=Object.fromEntries(Object.keys(draft).filter(key=>draft[key]!==null).map(key=>[key,`Invoice PDF: ${document.name} • fixture terdaftar, halaman 1`]));
    return {draft,sources,raw:{adapter:'FakeExtractor',profile:structuredClone(profile),sha256:document.hash,fixture:fixture.id,draft:structuredClone(draft)}};
  }
}
export const PROFILES = [
  {id:'demo-v1',model:'fake-model-1',schema:'invoice-1',prompt:'prompt-1',extractor:'fake-1',config:'config-1'},
  {id:'demo-v2',model:'fake-model-1',schema:'invoice-1',prompt:'prompt-2',extractor:'fake-1',config:'config-1'}
];
export const cacheKey=(client,hash,profile)=>JSON.stringify([client,hash,profile]);
export function blankDraft() { return {vendor_name:null,invoice_number:null,invoice_date:null,due_date:null,currency:'IDR',line_items:[],subtotal:null,invoice_discount_amount:'0',invoice_tax_amount:'0',total_amount:null,bank_name:null,account_number:null,account_holder:null}; }
