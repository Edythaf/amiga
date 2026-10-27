const prefixes={IDR:'Rp',USD:'US$',SGD:'S$',MYR:'RM',EUR:'€',JPY:'¥',CNY:'CN¥',AUD:'A$',GBP:'£',THB:'฿'};
export const currencyOptions={IDR:'IDR — Rupiah Indonesia',USD:'USD — Dolar AS',SGD:'SGD — Dolar Singapura',MYR:'MYR — Ringgit Malaysia',EUR:'EUR — Euro',JPY:'JPY — Yen Jepang',CNY:'CNY — Yuan Tiongkok',AUD:'AUD — Dolar Australia',GBP:'GBP — Pound Inggris',THB:'THB — Baht Thailand'};
export function currencyField(value,escape){
  const options={...currencyOptions};if(value&&!options[value])options[value]=value;
  return `<div><label for="field-currency">Mata uang</label><select id="field-currency" data-field="currency"><option value="" ${!value?'selected':''}>Pilih mata uang</option>${Object.entries(options).map(([key,label])=>`<option value="${escape(key)}" ${key===value?'selected':''}>${escape(label)}</option>`).join('')}</select><small>Pilihan ini tidak mengonversi nominal dengan kurs.</small></div>`;
}
export function formatAmount(value,currency='IDR'){
  if(value==null||value==='')return '';
  const raw=String(value);if(!/^\d{1,18}(?:\.\d{0,6})?$/.test(raw))throw Error('Nominal harus positif atau nol, maksimal 6 desimal.');
  const [whole,fraction]=raw.split('.'),grouped=whole.replace(/^0+(?=\d)/,'').replace(/\B(?=(\d{3})+(?!\d))/g,'.');
  return `${prefixes[currency||'IDR']??currency} ${grouped}${fraction!==undefined?','+fraction:''}`;
}
export function parseAmount(text){
  let raw=String(text??'').trim();if(!raw)return null;
  // Accept the displayed prefix or an unformatted integer paste. Decimal input
  // uses Indonesian comma; dots must be well-formed thousand separators.
  const known=Object.values(prefixes).sort((a,b)=>b.length-a.length).find(p=>raw.startsWith(p));
  if(known)raw=raw.slice(known.length).trim();else raw=raw.replace(/^[A-Z]{3}\s+/, '');
  const [whole,fraction,...extra]=raw.split(',');
  if(extra.length||!( /^\d+$/.test(whole)||/^\d{1,3}(?:\.\d{3})+$/.test(whole))||fraction!==undefined&&!/^\d{0,6}$/.test(fraction))throw Error('Gunakan format 1.000.000 atau 1.000.000,50; nominal tidak boleh negatif.');
  const number=whole.replaceAll('.','');if(number.length>18)throw Error('Nominal maksimal 18 angka dan 6 desimal.');
  return number.replace(/^0+(?=\d)/,'')+(fraction!==undefined?'.'+fraction:'');
}
export function readMoneyValue(input){
  if(!input.hasAttribute('data-money'))return input.value.trim()||null;
  try{return parseAmount(input.value)?.replace(/\.$/,'')??null;}catch{return input.value.trim()||null;}
}
export function writeMoneyValue(input,value,currency){input.value=formatAmount(value,currency);input.setCustomValidity('');}
export function readMoneyForm(form){
  const data=Object.fromEntries(new FormData(form));
  form.querySelectorAll('[data-money][name]').forEach(i=>data[i.name]=readMoneyValue(i));return data;
}
export function bindMoneyFields(root,getCurrency){
  const init=()=>root.querySelectorAll('[data-money]:not([data-money-bound])').forEach(input=>{input.dataset.moneyBound='true';try{writeMoneyValue(input,input.value,getCurrency());}catch(error){input.setCustomValidity(error.message);}});
  init();
  root.addEventListener('input',event=>{
    const input=event.target;if(!input.matches('[data-money]'))return;
    const offset=input.value.slice(0,input.selectionStart??input.value.length).replace(/[^\d,]/g,'').length;
    try{
      const raw=parseAmount(input.value);writeMoneyValue(input,raw,getCurrency());
      let remaining=offset,pos=0;while(pos<input.value.length&&remaining>0){if(/[\d,]/.test(input.value[pos]))remaining--;pos++;}input.setSelectionRange(pos,pos);
    }catch(error){input.setCustomValidity(error.message);}
  },true);
  return {init,reformat(){root.querySelectorAll('[data-money]').forEach(i=>{const raw=readMoneyValue(i);try{writeMoneyValue(i,raw,getCurrency());}catch{/* Keep invalid input visible for correction. */}});}};
}
