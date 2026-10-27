// Decimal input -> integer cents with BigInt intermediates; no binary-float money arithmetic.
export function decimal(value, places = 2) {
  if (value === null || value === undefined || String(value).trim() === '') throw Error('Nilai angka belum diisi.');
  const text = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(text)) throw Error(`Angka tidak valid: ${text}. Gunakan titik untuk desimal.`);
  const negative = text.startsWith('-'), [whole, fraction = ''] = text.replace('-', '').split('.');
  if (fraction.length > places && /[1-9]/.test(fraction.slice(places))) throw Error(`Maksimal ${places} angka desimal.`);
  const n = BigInt(whole) * 10n ** BigInt(places) + BigInt(fraction.slice(0, places).padEnd(places, '0') || '0');
  return negative ? -n : n;
}
function safe(n) { const v = Number(n); if (!Number.isSafeInteger(v)) throw Error('Nominal melampaui batas perhitungan browser. Simpan untuk pemeriksaan server.'); return v; }
function roundDivide(n, d) { return n < 0n ? -((-n + d / 2n) / d) : (n + d / 2n) / d; }
export const cents = value => safe(roundDivide(decimal(value,6),10000n));
export function calculateLine(item) {
    const qty=decimal(item.quantity,6),price=decimal(item.unit_price,6),discount=decimal(item.discount_amount,6),tax=decimal(item.tax_amount,6);
    if ([qty,price,discount,tax].some(n=>n<0n)) throw Error('Nilai negatif belum didukung.');
    return safe(roundDivide(qty*price-discount*1000000n+tax*1000000n,10000000000n));
}
export function calculate(draft) {
  if(!draft.line_items.length)throw Error('Belum ada rincian item.');
  const rows = draft.line_items.map(calculateLine);
  const subtotal = safe(rows.reduce((sum, v) => sum + BigInt(v), 0n));
  const total=safe(roundDivide(BigInt(subtotal)*10000n-decimal(draft.invoice_discount_amount,6)+decimal(draft.invoice_tax_amount,6),10000n));
  return {rows, subtotal, total, delta: total-cents(draft.total_amount)};
}
export function money(value, currency = 'IDR') {
  if (value === null || value === undefined || value === '') return 'Belum diisi';
  try{return new Intl.NumberFormat('id-ID', {style: 'currency', currency, minimumFractionDigits:0, maximumFractionDigits:2}).format(Number(value));}
  catch{return `${new Intl.NumberFormat('id-ID',{maximumFractionDigits:2}).format(Number(value))} (${String(currency||'mata uang belum valid')})`;}
}
