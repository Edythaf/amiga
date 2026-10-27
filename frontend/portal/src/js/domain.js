import {USERS,access,assertUpload,assertEdit,assertReviewer,assertFinance,user} from './authorization.js';
import {PROFILES,cacheKey,blankDraft} from './extractor.js';
import {validate,unresolved,RESOLVABLE} from './validation.js';
export const now=()=>new Date().toISOString();
const clone=x=>structuredClone(x);
export function initialState() { return {schema:1,requests:[],cache:{},counter:0,sequence:0,backupActive:true,disabledUsers:[],tolerance:'1',profileId:'demo-v1',selectedUser:'owner-a',adminNotes:[],storageWarning:''}; }
function event(r,actor,action,detail='',changes=[]) { r.audit.push({id:crypto.randomUUID(),at:now(),actor,action,detail,changes}); r.updatedAt=now(); }
function transition(r,status,actor) { if(r.status!==status) {const old=r.status;r.status=status;event(r,actor,'Perubahan status',`${old} → ${status}`);} }
function current(r) { return r.versions.at(-1); }
function requireIdle(r) { if(['QUEUED','PROCESSING'].includes(r.status)) throw Error('Proses sedang berjalan. Tunggu sampai selesai.'); }
export class AmigaService {
  constructor(state,extractor,persist=()=>{}) {this.state=state;this.extractor=extractor;this.persist=persist;}
  commit() {this.persist(this.state);}
  get(actor,id) {return clone(access(this.state,actor,id));}
  list(actor) {const u=user(actor);return this.state.requests.filter(r=>!(this.state.disabledUsers??[]).includes(actor)&&u.clients.includes(r.client) && (!u.roles.includes('BACKUP')||this.state.backupActive)).map(clone);}
  async submit(actor,metadata,document) {
    assertUpload(this.state,actor,metadata.client);
    if(document.type!=='INVOICE' || !document.hash || !document.storageKey || document.pages<1 || document.pages>5 || document.size>10*1024*1024) throw Error('Invoice harus PDF valid, maksimal 5 halaman dan 10 MB (asumsi demo).');
    if(!metadata.date || !metadata.requestType || !metadata.channel) throw Error('Metadata wajib belum lengkap.');
    const r={id:`AMG-${String(++this.state.sequence).padStart(4,'0')}`,client:metadata.client,uploader:actor,pic:actor,metadata:clone(metadata),status:'QUEUED',documents:[{...clone(document),id:crypto.randomUUID(),uploadedBy:actor,at:now()}],versions:[],runs:[],resolutions:[],reviews:[],vouchers:[],audit:[],validation:null,updatedAt:now()};
    this.state.requests.push(r);event(r,actor,'Unggah invoice',document.name);this.commit();
    await this.extract(actor,r.id,false,'Ekstraksi awal'); return this.get(actor,r.id);
  }
  async extract(actor,id,force=false,reason='') {
    const r=access(this.state,actor,id); if(r.status==='PROCESSING') throw Error('Ekstraksi sedang berjalan.');
    assertEdit(this.state,actor,r); if(force) {assertFinance(this.state,actor,r);if(!reason.trim())throw Error('Force reextract wajib alasan.');}
    const profile=PROFILES.find(x=>x.id===this.state.profileId), key=cacheKey(r.client,r.documents[0].hash,profile.id);
    const cached=!force&&this.state.cache[key];
    transition(r,'PROCESSING',actor);event(r,actor,force?'Force reextract':'Ekstraksi simulasi',`${profile.id}; ${reason}`);this.commit();
    const run={id:crypto.randomUUID(),profile:clone(profile),at:now(),status:'PROCESSING',raw:null,error:null};r.runs.push(run);
    try {
      let output;
      if(cached) {output=clone(cached);run.status='CACHE_HIT';}
      else {this.state.counter++;output=await this.extractor.extract(r.documents[0],profile);this.state.cache[key]=clone(output);run.status='SUCCEEDED';}
      run.raw=clone(output.raw);run.finishedAt=now();
      r.versions.push({number:(current(r)?.number??0)+1,draft:clone(output.draft),sources:clone(output.sources),expectedItems:output.draft.line_items.length,at:now(),createdBy:actor});
      r.vouchers.forEach(x=>x.superseded=true);
      event(r,'SYSTEM',run.status==='CACHE_HIT'?'Cache hit':'Ekstraksi selesai',`Run ${run.id}; raw output immutable; versi ${current(r).number}`);
    } catch(e) {
      run.status='FAILED';run.error=e.message;run.finishedAt=now();
      if(!r.versions.length) r.versions.push({number:1,draft:blankDraft(),sources:{},expectedItems:null,at:now(),createdBy:actor});
      event(r,'SYSTEM','Ekstraksi tidak tersedia',e.message);
    }
    this.runValidation(r,actor);this.commit(); return this.get(actor,id);
  }
  runValidation(r,actor) {
    r.validation=validate(this.state,r);transition(r,unresolved(r.validation).length?'EXCEPTION':'READY_FOR_REVIEW',actor);
    event(r,'SYSTEM','Validasi',`Versi ${current(r).number}: ${r.validation.flags.length} indikasi; ${unresolved(r.validation).length} belum diselesaikan; toleransi Rp${this.state.tolerance}`);
  }
  revalidate(actor,id,expectedVersion) {
    const r=access(this.state,actor,id);assertEdit(this.state,actor,r);requireIdle(r);
    if(current(r).number!==expectedVersion) throw Error('Versi sudah berubah. Muat ulang review.');
    if(['AMIGA_REVIEWED','SENT_TO_CLIENT'].includes(r.status)) throw Error('Buat revisi baru sebelum validasi ulang versi approved.');
    transition(r,'PROCESSING',actor);event(r,actor,'REVALIDATE','Tidak memanggil FakeExtractor.');this.runValidation(r,actor);this.commit();return this.get(actor,id);
  }
  revise(actor,id,draft,sources,expectedVersion,reason,expectedItems=null) {
    const r=access(this.state,actor,id);assertEdit(this.state,actor,r);requireIdle(r);
    if(current(r).number!==expectedVersion) throw Error('Versi stale: data sudah berubah. Muat ulang sebelum menyimpan.');
    if(!reason.trim()) throw Error('Catatan revisi wajib diisi.');
    const old=current(r), changes=[];
    for(const k of Object.keys(draft)) if(JSON.stringify(old.draft[k])!==JSON.stringify(draft[k])) changes.push({field:k,before:clone(old.draft[k]),after:clone(draft[k])});
    for(const k of Object.keys(sources)) if(old.sources[k]!==sources[k]) changes.push({field:`source.${k}`,before:old.sources[k]??null,after:sources[k]});
    const sourceCount=r.runs.findLast(run=>run.raw?.draft)?.raw.draft.line_items.length??old.expectedItems;
    r.versions.push({number:old.number+1,draft:clone(draft),sources:clone(sources),expectedItems:expectedItems===null?null:(sourceCount??expectedItems),at:now(),createdBy:actor});
    r.vouchers.forEach(x=>x.superseded=true);event(r,actor,'Revisi draft',reason,changes);transition(r,'EXCEPTION',actor);transition(r,'PROCESSING',actor);event(r,actor,'REVALIDATE','Versi koreksi divalidasi tanpa ekstraksi.');
    this.runValidation(r,actor);this.commit();return this.get(actor,id);
  }
  addEvidence(actor,id,document) {
    const r=access(this.state,actor,id);assertEdit(this.state,actor,r);requireIdle(r);
    if(['AMIGA_REVIEWED','SENT_TO_CLIENT'].includes(r.status)) throw Error('Buat revisi baru sebelum menambah bukti.');
    if(document.type!=='EVIDENCE'||document.pages<1||document.pages>5||document.size>10*1024*1024) throw Error('Bukti harus PDF ≤5 halaman dan ≤10 MB.');
    const doc={...clone(document),id:crypto.randomUUID(),uploadedBy:actor,at:now()};r.documents.push(doc);event(r,actor,'Tambah bukti',`${doc.id}: ${doc.name}`);transition(r,'EXCEPTION',actor);r.validation=null;this.commit();return clone(doc);
  }
  resolve(actor,id,code,reason,expectedVersion) {
    const r=access(this.state,actor,id);assertFinance(this.state,actor,r);requireIdle(r);
    if(current(r).number!==expectedVersion)throw Error('Versi sudah berubah.');
    if(!r.validation||!r.validation.flags.some(x=>x.code===code)||!RESOLVABLE.includes(code)||!reason.trim())throw Error('Resolusi hanya untuk duplikat/peringatan dengan alasan wajib.');
    if(['AMIGA_REVIEWED','SENT_TO_CLIENT'].includes(r.status)) throw Error('Versi approved tidak dapat diubah.');
    r.resolutions.push({code,version:current(r).number,reason,actor,at:now()});event(r,actor,'Resolusi validasi',`${code}: ${reason}`);this.runValidation(r,actor);this.commit();
  }
  approve(actor,id,expectedVersion) {
    const r=access(this.state,actor,id);assertReviewer(this.state,actor,r);requireIdle(r);
    if(current(r).number!==expectedVersion) throw Error('Approval ditolak: versi yang direview bukan versi terkini.');
    if(r.status!=='READY_FOR_REVIEW')throw Error('Approval memerlukan status READY_FOR_REVIEW.');
    // Recompute duplicate and all blockers immediately before approval.
    this.runValidation(r,actor);if(unresolved(r.validation).length){this.commit();throw Error('Approval ditolak: validasi/acknowledgement belum selesai.');}
    const review={id:crypto.randomUUID(),actor,version:expectedVersion,status:'APPROVED',at:now(),draft:clone(current(r).draft),sources:clone(current(r).sources),evidence:r.documents.filter(x=>x.type==='EVIDENCE').map(x=>({id:x.id,name:x.name,hash:x.hash}))};
    r.reviews.push(review);event(r,actor,'Approval reviewer',`Versi ${expectedVersion}; bukan otorisasi pembayaran.`);transition(r,'AMIGA_REVIEWED',actor);this.commit();return clone(review);
  }
  reject(actor,id,reason,expectedVersion) {
    const r=access(this.state,actor,id);assertReviewer(this.state,actor,r);requireIdle(r);
    if(current(r).number!==expectedVersion||!reason.trim())throw Error('Penolakan wajib alasan dan versi terkini.');
    if(!['READY_FOR_REVIEW','EXCEPTION'].includes(r.status))throw Error('Status ini tidak dapat ditolak.');
    r.reviews.push({id:crypto.randomUUID(),actor,version:expectedVersion,status:'REJECTED',at:now(),reason});event(r,actor,'Review ditolak',reason);transition(r,'EXCEPTION',actor);this.commit();
  }
  approved(actor,id) {
    const r=access(this.state,actor,id);if(!['AMIGA_REVIEWED','SENT_TO_CLIENT'].includes(r.status))throw Error('Voucher resmi belum tersedia.');
    const review=r.reviews.findLast(x=>x.status==='APPROVED'&&x.version===current(r).number);if(!review)throw Error('Approval versi terkini tidak ditemukan.');return clone(review);
  }
  issue(actor,id,reviewId) {
    const r=access(this.state,actor,id), review=this.approved(actor,id);if(review.id!==reviewId)throw Error('Approval telah berubah.');
    let v=r.vouchers.find(x=>x.reviewId===reviewId);
    if(!v){v={id:`VCH-${r.id}-${review.version}`,reviewId,version:review.version,at:now(),superseded:false};r.vouchers.push(v);event(r,actor,'Voucher PDF dibuat',v.id);this.commit();} return clone(v);
  }
  handover(actor,id,voucherId) {
    const r=access(this.state,actor,id);this.approved(actor,id);
    const v=r.vouchers.find(x=>x.id===voucherId&&!x.superseded);if(!v)throw Error('Voucher tidak tersedia atau sudah digantikan.');
    event(r,actor,'Unduhan resmi / handover',`${voucherId}; file diserahkan melalui unduhan browser, tidak ada email dikirim.`);transition(r,'SENT_TO_CLIENT',actor);this.commit();
  }
  allocate(actor,id,pic) {
    const r=access(this.state,actor,id);if(!user(actor).roles.includes('LEAD'))throw Error('Alokasi tugas hanya Service Lead.');
    const target=user(pic);if(!target.clients.includes(r.client)||target.roles.includes('ADMIN'))throw Error('PIC tidak sesuai klien.');const before=r.pic;r.pic=pic;event(r,actor,'Alokasi PIC',`${before} → ${pic}`);this.commit();
  }
  toggleUser(actor,targetId) {
    if(!user(actor).roles.includes('ADMIN'))throw Error('Pengelolaan akun hanya System Admin.');
    const target=user(targetId);if(target.roles.includes('ADMIN'))throw Error('Akun admin tetap aktif pada demo.');
    this.state.disabledUsers??=[];const active=this.state.disabledUsers.includes(targetId);
    this.state.disabledUsers=active?this.state.disabledUsers.filter(x=>x!==targetId):[...this.state.disabledUsers,targetId];
    this.state.adminNotes.push({actor,at:now(),patch:{user:targetId,active}});this.commit();
  }
  settings(actor,patch) {
    if((this.state.disabledUsers??[]).includes(actor))throw Error('Akun demo dinonaktifkan.');
    const u=user(actor);if(!u.roles.some(x=>['ADMIN','LEAD','REVIEWER'].includes(x)))throw Error('Pengaturan memerlukan Admin, Lead, atau Reviewer.');
    if('backupActive' in patch&&!u.roles.some(x=>['ADMIN','LEAD'].includes(x)))throw Error('Delegasi memerlukan Admin/Lead.');
    if(patch.profileId&&!PROFILES.some(x=>x.id===patch.profileId))throw Error('Profil tidak dikenal.');
    if(patch.tolerance!==undefined&&(!/^\d+(\.\d{1,2})?$/.test(String(patch.tolerance))||Number(patch.tolerance)>1000))throw Error('Toleransi demo harus Rp0–Rp1.000.');
    for(const key of Object.keys(patch))if(!['profileId','tolerance','backupActive'].includes(key))throw Error('Pengaturan tidak diizinkan.');
    Object.assign(this.state,patch);this.state.adminNotes.push({actor,at:now(),patch:clone(patch)});
    // Validation policy changes invalidate eligibility; approved snapshots stay unchanged.
    if('tolerance' in patch)for(const r of this.state.requests)if(r.versions.length&&!['AMIGA_REVIEWED','SENT_TO_CLIENT','PROCESSING','QUEUED'].includes(r.status))this.runValidation(r,actor);
    this.commit();
  }
}
