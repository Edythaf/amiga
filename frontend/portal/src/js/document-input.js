import {inspectPDF} from './pdf.js';

export async function inspectInvoice(file,{allowImages=true}={}){
  if(file.name.toLowerCase().endsWith('.pdf'))return {...await inspectPDF(file),kind:'pdf'};
  if(!allowImages)throw Error('Pratinjau ini mendukung PDF. Gunakan aplikasi AMIGA untuk unggah foto.');
  if(!/\.(jpe?g|png|webp)$/i.test(file.name))throw Error('Pilih PDF, JPG, JPEG, PNG, atau WEBP.');
  if(!file.size||file.size>10*1024*1024)throw Error('Ukuran foto harus antara 1 byte dan 10 MB.');
  let picture;
  try{
    picture=await createImageBitmap(file);
    if(picture.width*picture.height>20_000_000)throw Error('Resolusi foto maksimal 20 megapiksel.');
    return {kind:'image',pages:1,width:picture.width,height:picture.height,name:file.name};
  }catch(e){throw Error(e.message==='Resolusi foto maksimal 20 megapiksel.'?e.message:'Foto tidak dapat dibaca. Pilih gambar yang valid.');}
  finally{picture?.close();}
}
