import {PDFDocument,StandardFonts,rgb} from '../../vendor/pdf-lib.js';
import {money,calculate} from './money.js';
const safe=s=>String(s??'Belum diisi').replace(/[^\x20-\x7E\n]/g,' ');
const rupiah=n=>safe(money(n,'IDR'));
export async function renderPDF({kind='voucher',draft,request=null,review=null,number='DRAFT',subtitle=''}) {
  const pdf=await PDFDocument.create();pdf.setTitle(kind==='invoice'?'Invoice Demo AMIGA':`Voucher ${number}`);
  // Fixed fixture timestamps make fixture output reproducible; vouchers reflect their review.
  pdf.setCreationDate(new Date('2026-10-12T00:00:00Z'));pdf.setModificationDate(new Date('2026-10-12T00:00:00Z'));
  const font=await pdf.embedFont(StandardFonts.Helvetica),bold=await pdf.embedFont(StandardFonts.HelveticaBold);
  let page,y;const width=595,height=842,margin=42;
  function addPage(){page=pdf.addPage([width,height]);y=height-margin;}
  addPage();
  function line(text,size=10,emphasis=false,color=rgb(.16,.22,.3)) {
    const words=safe(text).split(' ');let row='';
    const rows=[];for(const word of words){if(font.widthOfTextAtSize(`${row} ${word}`,size)>width-2*margin){rows.push(row);row=word;}else row=row?`${row} ${word}`:word;}rows.push(row);
    for(const rowText of rows){if(y<65)addPage();page.drawText(rowText,{x:margin,y,size,font:emphasis?bold:font,color});y-=size+7;}
  }
  line('AMIGA / ROBOT ADMIN',12,true,rgb(.02,.42,.4));y-=10;
  line(kind==='invoice'?'INVOICE DEMO - DATA FIKTIF':review?'VOUCHER ADMINISTRASI':'DRAFT VOUCHER',21,true);line(subtitle||'Mode Demo - Ekstraksi Simulasi',9);y-=14;
  if(kind==='voucher'){line(`Nomor voucher: ${number}`);line(`Request: ${request?.id??'-'} | Klien ${request?.client??'-'}`);}
  line(`Vendor: ${draft.vendor_name??'-'}`,11,true);
  line(`Invoice: ${draft.invoice_number??'-'} | Tanggal: ${draft.invoice_date??'-'}`);
  line(`Jatuh tempo: ${draft.due_date??'-'} | Mata uang: ${draft.currency??'IDR'}`);y-=14;
  line('RINCIAN BARANG / JASA',11,true);
  for(const [i,item]of draft.line_items.entries()) {
    line(`${i+1}. ${item.description}`,10,true);
    line(`Qty ${item.quantity??'?'} x ${rupiah(item.unit_price)} | Diskon ${rupiah(item.discount_amount)} | Pajak ${rupiah(item.tax_amount)} | Total ${rupiah(item.line_total)}`,9);
  }
  y-=12;line(`Subtotal dokumen: ${rupiah(draft.subtotal)}`);line(`Diskon invoice: ${rupiah(draft.invoice_discount_amount)}`);line(`Pajak invoice: ${rupiah(draft.invoice_tax_amount)}`);line(`TOTAL DOKUMEN: ${rupiah(draft.total_amount)}`,13,true);
  if(kind==='voucher'){try{const calc=calculate(draft);line(`Total hasil hitung: ${rupiah(calc.total/100)} | Selisih: ${rupiah(calc.delta/100)}`,9);}catch{line('Hasil hitung belum tersedia; draft belum lengkap.',9);}}
  y-=12;line(`Bank: ${draft.bank_name??'Belum diisi'}`);line(`Rekening: ${draft.account_number??'Belum diisi'} | Pemilik: ${draft.account_holder??'Belum diisi'}`);
  if(kind==='voucher') {
    y-=12;line(`Reviewer: ${review?.actor??'Belum disetujui'}`);line(`Waktu review: ${review?.at??'-'} | Versi: ${review?.version??request?.versions.at(-1)?.number??'-'}`);
    line(`Bukti: ${review?.evidence?.map(x=>`${x.name} (${x.id})`).join('; ')||'Rekening bersumber dari invoice / belum ada lampiran bukti'}`,8);
    line(`Sumber rekening: ${review?.sources?.account_number??request?.versions.at(-1)?.sources?.account_number??'Belum tersedia'}`,8);
    y-=12;line('Voucher ini telah ditinjau oleh AMIGA. Persetujuan pembayaran dan pelaksanaan pembayaran merupakan kewenangan klien.',9,true);
    if(!review)for(const p of pdf.getPages())p.drawText('DRAFT',{x:150,y:400,size:65,font:bold,color:rgb(.7,.72,.75),opacity:.22});
  }
  pdf.getPages().forEach((p,i)=>p.drawText(`AMIGA Demo | ${i+1}/${pdf.getPageCount()} | Data fiktif, bukan bukti pembayaran`,{x:margin,y:27,size:8,font,color:rgb(.4,.45,.5)}));
  return await pdf.save({useObjectStreams:false});
}
export async function inspectPDF(file) {
  if(!file.name.toLowerCase().endsWith('.pdf'))throw Error('Format harus PDF (.pdf).');
  if(file.size>10*1024*1024)throw Error('Ukuran melebihi 10 MB (asumsi konfigurasi demo).');
  const bytes=new Uint8Array(await file.arrayBuffer());
  if(new TextDecoder().decode(bytes.slice(0,5))!=='%PDF-')throw Error('Isi berkas bukan PDF valid.');
  let doc;try{doc=await PDFDocument.load(bytes);}catch{throw Error('PDF rusak atau terenkripsi. Unggah PDF yang dapat dibaca.');}
  const pages=doc.getPageCount();if(pages<1||pages>5)throw Error(`PDF berisi ${pages} halaman; batas demo 1–5 halaman.`);
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  return {bytes,hash,pages,size:file.size,name:file.name};
}
