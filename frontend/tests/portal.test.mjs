import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import {ApiClient,ApiError} from '../portal/src/js/api-client.js';
import {parseEmailInput,portalForUser,canReview,canManageUsers,routeAllowed} from '../portal/src/js/portal-policy.js';
import {DemoAdapter} from '../portal/src/js/demo-adapter.js';import {initialState} from '../portal/src/js/domain.js';
import {consumeOwnerSetup} from '../portal/src/js/auth-setup.js';
import {progressHTML,requestBadge,requestOpenLabel} from '../portal/src/js/work-progress.js';
import {taskGuidanceHTML} from '../portal/src/js/task-workspace.js';
import {uploaderHTML} from '../portal/src/js/uploader-workflow.js';
import {calculate} from '../portal/src/js/money.js';
import {publicationBlock,publicationBlockHTML} from '../portal/src/js/publication-state.js';
import {telegramUnavailableHTML,automaticRecipientHTML,automaticDeliveryHTML} from '../portal/src/js/telegram-settings.js';
import {currentHandler} from '../portal/src/js/company-portal.js';
import {manualReviewHTML} from '../portal/src/js/manual-review.js';
import {passwordPageHTML,passwordResetCodeHTML} from '../portal/src/js/password-page.js';
import {loginHTML} from '../portal/src/js/login-view.js';
import {calculateVoucherTax} from '../portal/src/js/voucher-tax.js';
import {batchUploadHTML} from '../portal/src/js/upload-page.js';
import {accountSourceOptions,accountSourcePayload,reviewAdditionsHTML,generatedVoucherHTML,manualTaxStale} from '../portal/src/js/review-additions.js';
const fixtures=JSON.parse(await fs.readFile(new URL('../portal/public/fixtures/manifest.json',import.meta.url),'utf8'));

test('Passing validation without submission never advertises a request as ready for reviewers',()=>{
  const r={status:'READY_FOR_REVIEW',ready_for_review:false,work_status:'WAITING_UPLOADER'};
  const badge=s=>`<span>${s==='READY_FOR_REVIEW'?'Siap direview':s}</span>`;
  assert.match(requestBadge(r,String,badge),/Belum dikirim ke reviewer/);
  assert.doesNotMatch(requestBadge(r,String,badge),/Siap direview/);
  assert.equal(requestOpenLabel(r,'uploader'),'Periksa & konfirmasi');
  assert.equal(requestOpenLabel(r,'client'),'Buka');
  assert.equal(requestOpenLabel(r,'uploader',true),'Lihat voucher');
  assert.match(requestBadge({...r,ready_for_review:true,work_status:'UNCLAIMED'},String,badge),/Siap direview/);
  assert.match(requestBadge({...r,status:'EXCEPTION'},String,badge),/EXCEPTION/);
  assert.equal(requestBadge({status:'AMIGA_REVIEWED'},String,badge),badge('AMIGA_REVIEWED'));
});

test('Current uploader version requires explicit confirmation, with a shortcut visible in progress',()=>{
  const r={uploaded_by:'u',work_status:'WAITING_UPLOADER',lifecycle:{state:'OPEN'},updated_at:'2026-10-16',invoice_count:1};
  const inv={current_version:2,initial_analysis:{state:'READY',result:{risk:'LOW',summary:'Contoh',findings:[],next_steps:[]}},uploader_confirmation:{confirmed:false}};
  const session={portal:'uploader',user:{id:'u'}};
  const html=uploaderHTML(r,inv,session,String);
  assert.match(html,/Versi 2 belum dikirim/);assert.match(html,/Tugas tersedia/);
  assert.match(html,/id="uploader-ack" type="checkbox"/);
  assert.match(html,/id="confirm-uploader" class="primary" disabled/);
  assert.match(progressHTML(r,String,'uploader'),/id="open-uploader-check"/);
  assert.doesNotMatch(progressHTML(r,String,'client'),/id="open-uploader-check"/);
  assert.doesNotMatch(uploaderHTML(r,{...inv,uploader_confirmation:{confirmed:true}},session,String),/id="confirm-uploader"|belum dikirim/);
  assert.equal(uploaderHTML(r,inv,{portal:'uploader',user:{id:'other'}},String),'');
});

test('Reviewer guidance distinguishes available work from claimed tasks without offering an automatic claim',()=>{
  const mine=taskGuidanceHTML('reviewer','my-tasks');
  assert.match(mine,/id="open-available-tasks"/);assert.match(mine,/sudah kamu ambil/);
  assert.match(mine,/mengonfirmasi seluruh invoice/);assert.doesNotMatch(mine,/task-claim/);
  const available=taskGuidanceHTML('reviewer','queue');
  assert.match(available,/menunggu konfirmasi uploader belum muncul/);
  assert.doesNotMatch(available,/id="open-available-tasks"/);
  assert.equal(taskGuidanceHTML('admin','queue'),'');
});

test('Company accounts use a separate portal and uploader progress remains available without client acceptance controls',()=>{
  const company={account_status:'ACTIVE',roles:['COMPANY_CLIENT']};
  assert.equal(portalForUser(company),'client');assert.equal(routeAllowed(company,'uploader'),false);assert.equal(canReview(company),false);
  const request={work_status:'AWAITING_CLIENT_CLOSE',lifecycle:{state:'OPEN'},allowed_actions:['CLOSE'],updated_at:'2026-10-16T00:00:00Z',invoice_count:1,voucher_count:1};
  assert.match(progressHTML(request,String,'client'),/id="close-work"/);
  const uploader=progressHTML(request,String,'uploader');assert.match(uploader,/work-stages/);assert.doesNotMatch(uploader,/id="close-work"/);
  assert.equal(progressHTML(request,String,'reviewer'),'');
});
test('Company tracker shows actual operational responsibility without claiming a reviewer has taken queued work',()=>{
  const r={client_name:'PT Contoh',uploader_name:'Uploader A',pic_name:'Reviewer B'};
  assert.equal(currentHandler({...r,work_status:'WAITING_UPLOADER'}).name,'Uploader A');
  assert.equal(currentHandler({...r,work_status:'WAITING_CLIENT'}).role,'Uploader');
  assert.equal(currentHandler({...r,work_status:'UNCLAIMED'}).role,'Antrean reviewer');
  assert.equal(currentHandler({...r,work_status:'IN_REVIEW'}).name,'Reviewer B');
  assert.equal(currentHandler({...r,work_status:'PROCESSING'}).role,'Sistem');
  assert.equal(currentHandler({...r,work_status:'VOUCHER_READY'}).name,'PT Contoh');
  assert.equal(currentHandler({...r,work_status:'CLOSED'}).role,'Selesai');
});
test('Manual review form remains available when signature is absent, uncertain or AI failed; decided PDF stays immutable',()=>{
  const escape=v=>String(v).replaceAll('<','&lt;').replaceAll('>','&gt;');
  for(const signature_state of ['PENDING','NOT_DETECTED','UNCERTAIN','FAILED']){
    const html=manualReviewHTML({review_status:'PENDING',current_version:3,manual_review_pdf:{filename:'<script>',signature_state}},escape);
    assert.match(html,/manual-review-form/);assert.match(html,/versi 3/);assert.doesNotMatch(html,/<script>/);
  }
  assert.doesNotMatch(manualReviewHTML({review_status:'APPROVED',current_version:3},escape),/manual-review-form/);
});

test('Telegram distinguishes configured bot from unverified recipient without exposing sending controls',()=>{
  const recipient=telegramUnavailableHTML(true);
  assert.match(recipient,/sudah dikonfigurasi/);assert.match(recipient,/penerima voucher belum terverifikasi/);assert.match(recipient,/Verifikasi penerima/);assert.match(recipient,/Start/);
  assert.doesNotMatch(recipient,/belum dikonfigurasi|telegram-dispatch|telegram-prepare/);
  for(const configured of [false,undefined]){
    const bot=telegramUnavailableHTML(configured);
    assert.match(bot,/Bot Telegram belum dikonfigurasi/);assert.match(bot,/Reviewer & akun/);
    assert.doesNotMatch(bot,/sudah dikonfigurasi|telegram-dispatch|telegram-prepare/);
  }
});

test('Automatic voucher delivery is explicit for a verified company account and never marks service as accepted',()=>{
  const html=automaticRecipientHTML();
  assert.match(html,/Terima voucher otomatis setelah reviewer menerbitkan/);
  assert.match(html,/id="telegram-automatic" type="checkbox" disabled/);
  assert.doesNotMatch(html,/checked|close-work|telegram-dispatch/);
  assert.match(html,/tidak mengirim ulang voucher lama/);
  const escape=v=>String(v).replaceAll('<','&lt;').replaceAll('>','&gt;');
  const r={invoices:[{id:'i',fields:{invoice_number:'<script>'}}],telegram:{automatic:{enabled:true,items:[
    {invoice_id:'i',version:2,state:'QUEUED'},{invoice_id:'i',version:1,state:'UNKNOWN'}]}}};
  const output=automaticDeliveryHTML(r,escape);
  assert.match(output,/Menunggu pengiriman/);assert.match(output,/Status belum pasti/);
  assert.match(output,/&lt;script&gt;/);assert.doesNotMatch(output,/<script>|chat_id|close-work/);
  assert.equal(automaticDeliveryHTML({},escape),'');
});

test('Automatic preference uses authenticated CSRF PATCH with a boolean and no user-supplied recipient',async()=>{
  let captured;
  const api=new ApiClient(async(url,opts)=>{captured={url,opts};return new Response(JSON.stringify({data:{automatic_enabled:true}}));});
  api.csrf='fixture-csrf';
  await api.telegramAutomatic(true);
  assert.equal(captured.url,'/api/telegram/automatic');assert.equal(captured.opts.method,'PATCH');
  assert.deepEqual(JSON.parse(captured.opts.body),{enabled:true});assert.equal(captured.opts.headers['X-CSRF-Token'],'fixture-csrf');
});

const publishingReviewer={id:'reviewer',account_status:'ACTIVE',roles:['FINANCE_REVIEWER']};
const publishingRequest={pic_id:'reviewer',uploaded_by:'client',lifecycle:{state:'OPEN'},processing:{status:'COMPLETE'},ready_for_review:false,documents:[]};
const publishingInvoice={current_version:8,allowed_actions:['EDIT','VALIDATE'],review_status:'PENDING',validation:{valid:true},uploader_confirmation:{confirmed:false}};
test('Passing arithmetic cannot replace uploader confirmation or a server approval capability',()=>{
  const state=publicationBlock(publishingRequest,publishingInvoice,publishingReviewer);
  assert.equal(state.code,'UPLOADER_CONFIRMATION');assert.match(state.message,/versi 8/);
  const html=publicationBlockHTML(publishingRequest,publishingInvoice,publishingReviewer,String);
  assert.match(html,/disabled aria-describedby="publication-blocked-reason"/);
  assert.match(html,/Setujui & terbitkan voucher/);assert.match(html,/Muat ulang status/);
  assert.doesNotMatch(html,/id="approve-invoice"|id="publish-voucher"/);
  assert.equal(publicationBlock({...publishingRequest,ready_for_review:true},publishingInvoice,publishingReviewer).code,'UNAVAILABLE');
  assert.equal(publicationBlock(publishingRequest,{...publishingInvoice,allowed_actions:['APPROVE']},publishingReviewer),null);
});
test('Confirmed selection explains missing confirmations on other invoices without claiming it is unconfirmed',()=>{
  const state=publicationBlock(publishingRequest,{...publishingInvoice,uploader_confirmation:{confirmed:true}},publishingReviewer);
  assert.equal(state.code,'UPLOADER_CONFIRMATION');assert.match(state.message,/invoice lain/);assert.doesNotMatch(state.message,/Menunggu konfirmasi uploader untuk versi/);
});
test('Publication blockers prioritize lifecycle, processing, independence, assignment and rejection',()=>{
  const check=(request,invoice=publishingInvoice)=>publicationBlock({...publishingRequest,...request},invoice,publishingReviewer).code;
  assert.equal(check({lifecycle:{state:'CLOSED'}}),'CLOSED');
  for(const status of ['QUEUED','PROCESSING'])assert.equal(check({processing:{status}}),'PROCESSING');
  assert.equal(check({processing:{status:'FAILED'}}),'PROCESSING_FAILED');
  assert.equal(check({uploaded_by:'reviewer'}),'INDEPENDENCE');
  assert.equal(check({documents:[{uploaded_by:'reviewer'}]}),'INDEPENDENCE');
  assert.equal(check({pic_id:'other'}),'ASSIGNMENT');
  assert.equal(check({}, {...publishingInvoice,review_status:'REJECTED'}),'REJECTED');
});
test('Clients, admins, disabled reviewers and official vouchers have no blocked reviewer publication control',()=>{
  for(const user of [{...publishingReviewer,roles:['CLIENT_OWNER']},{...publishingReviewer,roles:['SYSTEM_ADMIN','FINANCE_REVIEWER']},{...publishingReviewer,account_status:'DISABLED'}])assert.equal(publicationBlockHTML(publishingRequest,publishingInvoice,user,String),'');
  assert.equal(publicationBlock(publishingRequest,{...publishingInvoice,allowed_actions:['DOWNLOAD_VOUCHER']},publishingReviewer),null);
});

test('Browser and backend share half-up rounding, six-decimal inputs and delta direction',async()=>{
  const cases=JSON.parse(await fs.readFile(new URL('../../tests/fixtures/invoice_math.json',import.meta.url),'utf8'));
  const expectedCents=value=>{const [whole,fraction='']=value.split('.');return Number(BigInt(whole+fraction.padEnd(2,'0')));};
  for(const c of cases){
    const draft={invoice_discount_amount:c.discount,invoice_tax_amount:c.tax,total_amount:c.reported,
      line_items:c.items.map(row=>Object.fromEntries(['quantity','unit_price','discount_amount','tax_amount','line_total'].map((k,i)=>[k,row[i]])))};
    const actual=calculate(draft);
    assert.deepEqual(actual,{rows:c.items.map(row=>expectedCents(row[4])),subtotal:expectedCents(c.subtotal),total:expectedCents(c.total),delta:expectedCents(c.delta)},c.name);
    assert.equal(draft.total_amount,c.reported,'Source total must remain unchanged');
  }
});

test('Client lifecycle carries both optimistic versions through the authenticated API',async()=>{
  let captured;
  const api=new ApiClient(async(url,opts)=>{captured={url,opts};return new Response(JSON.stringify({data:{lifecycle:{state:'CLOSED'}}}));});
  api.csrf='test';
  const payload={action:'CLOSE',reason:'Accepted',expected_lifecycle_revision:2,expected_versions:{invoice:4}};
  await api.lifecycle('request/encoded',payload);
  assert.equal(captured.url,'/api/requests/request%2Fencoded/lifecycle');
  assert.deepEqual(JSON.parse(captured.opts.body),payload);
  assert.equal(captured.opts.headers['X-CSRF-Token'],'test');
});

test('Work progress escapes client notes and renders only server-authorized controls',()=>{
  const escape=v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const request={lifecycle:{state:'CLOSED'},work_status:'CLOSED',updated_at:'2026-10-15T00:00:00Z',
    client_revision_note:'<script>alert(1)</script>',invoice_count:1,voucher_count:1,allowed_actions:[]};
  const html=progressHTML(request,escape,'client');
  assert.doesNotMatch(html,/<script>|id="close-work"|id="request-revision"/);
  assert.match(html,/Pekerjaan ditutup/);
  const client=progressHTML({...request,allowed_actions:['REQUEST_REVISION']},escape,'client');
  assert.match(client,/id="request-revision"/);
  assert.doesNotMatch(client,/id="close-work"/);
});

for(const suffix of ['review','view'])test(`/${suffix} activates reviewer access and retains exact email identity`,async()=>{assert.deepEqual(parseEmailInput(` Reviewer.Test+amiga@Example.test /${suffix.toUpperCase()} `),{email:'reviewer.test+amiga@example.test',adminRequested:false,reviewerRequested:true,uploaderRequested:false});for(const invalid of ['admin/view','admin/review','review/view','view/admin'])assert.throws(()=>parseEmailInput('a@example.test/'+invalid));const a=mockAdapter();let session=await a.login({email_input:'new@example.test/'+suffix});assert.equal(session.user.account_status,'ACTIVE');assert.deepEqual(session.user.roles,['FINANCE_REVIEWER']);assert.equal(session.portal,'reviewer');session=await a.login({email_input:'reviewer@amiga.example/'+suffix});assert.equal(session.portal,'reviewer');assert.equal(canReview(session.user),true);});

test('Old auth server is rejected without guessing Google or sending credentials',async()=>{const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push(url);return new Response(JSON.stringify({data:{csrf_token:'old',google_client_id:'',auth_configured:false}}));});await assert.rejects(()=>api.config(),e=>e.code==='AUTH_SERVER_OUTDATED'&&/Start-AMIGA.cmd/.test(e.message));assert.deepEqual(calls,['/api/auth/csrf']);assert.equal(api.authMethod,'local_password');});

test('Google login is selected only when the server explicitly configures Google',async()=>{const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push(url);return new Response(JSON.stringify({data:url.endsWith('/csrf')?{csrf_token:'test',auth_method:'google'}:{portal:'client'}}));});await api.config();await api.login({credential:'fixture'});assert.deepEqual(calls,['/api/auth/csrf','/api/auth/google']);});

test('Owner setup capability is removed from the URL immediately and never accepted as a regular route',()=>{const calls=[],history={replaceState(...args){calls.push(args);}},token='x'.repeat(43);assert.equal(consumeOwnerSetup({pathname:'/login',search:'',hash:'#owner-setup='+token},history),token);assert.deepEqual(calls,[[null,'','/login']]);assert.equal(consumeOwnerSetup({pathname:'/admin',search:'',hash:'#owner-setup='+token},history),'');assert.equal(consumeOwnerSetup({pathname:'/login',search:'',hash:'#owner-setup=bad'},history),'');});
const mockAdapter=()=>new DemoAdapter(initialState(),fixtures,{readFile:async()=>new Uint8Array(),storeFile:async()=>'stored'},()=>{});
async function add(adapter,fixture='normal',actor='owner-a',client='A'){const f=fixtures.find(x=>x.id===fixture);return adapter.service.submit(actor,{client,date:'2026-10-15',due:'2026-10-22',requestType:'Invoice vendor',channel:'Portal'},{type:'INVOICE',name:f.file,hash:f.sha256,pages:1,size:1500,storageKey:'stored'});}
test('Email /admin is parsed as an activation request without altering Gmail dots/plus',()=>{assert.deepEqual(parseEmailInput(' Gerardus.Test+amiga@Gmail.com /admin '),{email:'gerardus.test+amiga@gmail.com',adminRequested:true,reviewerRequested:false,uploaderRequested:false});assert.deepEqual(parseEmailInput('gerardus@gmail.com'),{email:'gerardus@gmail.com',adminRequested:false,reviewerRequested:false,uploaderRequested:false});assert.throws(()=>parseEmailInput('x@gmail.com /unknown'),/valid/);assert.throws(()=>parseEmailInput('xgmail.com /admin'));});
test('Portal roles: clients cannot enter admin; System Admin cannot approve even with reviewer combination',()=>{const owner={account_status:'ACTIVE',roles:['CLIENT_OWNER']},admin={account_status:'ACTIVE',roles:['SYSTEM_ADMIN','FINANCE_REVIEWER']};assert.equal(portalForUser(owner),'uploader');assert.equal(routeAllowed(owner,'admin'),false);assert.equal(canReview(owner),false);assert.equal(canManageUsers(admin),true);assert.equal(canReview(admin),false);assert.equal(portalForUser({...admin,account_status:'PENDING_ADMIN'}),'pending');});
test('Unknown email /admin remains pending and gains no admin privileges in preview',async()=>{const adapter=mockAdapter();const s=await adapter.login({email_input:'example@gmail.com /admin'});assert.equal(s.user.email,'example@gmail.com');assert.equal(s.user.account_status,'PENDING_ADMIN');assert.deepEqual(s.user.roles,[]);assert.equal(s.portal,'pending');await assert.rejects(()=>adapter.list(),e=>e.status===403);});
test('Registered preview admin logs in without suffix later; session logout removes access',async()=>{const a=mockAdapter();let s=await a.login({email_input:'admin@amiga.example /admin'});assert.equal(s.portal,'admin');await a.logout();s=await a.login({email_input:'admin@amiga.example'});assert.deepEqual(s.user.roles,['SYSTEM_ADMIN']);assert.equal((await a.me()).user.email,'admin@amiga.example');await a.logout();await assert.rejects(()=>a.me(),e=>e.status===401);});
test('Preview adapter preserves tenant restriction on detail/list/document and rejects client account management',async()=>{const a=mockAdapter();const r=await add(a,'normal','owner-b','B');await a.login({email_input:'klien-a@amiga.example'});assert.equal((await a.list()).total,0);await assert.rejects(()=>a.detail(r.id),/Akses ditolak/);await assert.rejects(()=>a.document(r.id,r.documents[0].id),/Akses ditolak/);await assert.rejects(()=>a.users(),e=>e.status===403);});
test('Preview API shape exposes all line items and exact currency values; reviewer can approve',async()=>{const a=mockAdapter();const r=await add(a);await a.login({email_input:'reviewer@amiga.example'});let d=await a.detail(r.id);assert.equal(d.invoices[0].fields.line_items.length,3);assert.equal(d.invoices[0].validation.calculated.total,'650000.00');assert.equal(d.invoices[0].current_version,1);await a.decision(r.id,d.invoices[0].id,'approve',{expected_version:1});d=await a.detail(r.id);assert.equal(d.invoices[0].review_status,'APPROVED');assert.ok(d.invoices[0].allowed_actions.includes('DOWNLOAD_VOUCHER'));});
test('Preview pending or disabled user never obtains request data',async()=>{const a=mockAdapter();await add(a);await a.login({email_input:'admin@amiga.example'});await assert.rejects(()=>a.updateUser('owner-a',{account_status:'INVENTED'}),/ACTIVE/);await a.updateUser('owner-a',{account_status:'DISABLED'});const s=await a.login({email_input:'klien-a@amiga.example'});assert.equal(s.portal,'pending');assert.equal(s.user.account_status,'DISABLED');await assert.rejects(()=>a.list(),e=>e.status===403);});
test('API client sends cookie credentials and server CSRF, encodes ids and preserves decimal strings',async()=>{const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push({url,opts});return new Response(JSON.stringify({data:url.endsWith('/csrf')?{csrf_token:'server-csrf',auth_method:'local_password'}:{ok:true}}),{headers:{'Content-Type':'application/json'}});});await api.config();await api.invoice('req/id','invoice?1',{expected_version:2,fields:{total_amount:'650000.10'},reason:'Test'});assert.equal(calls[1].url,'/api/requests/req%2Fid/invoices/invoice%3F1');assert.equal(calls[1].opts.credentials,'same-origin');assert.equal(calls[1].opts.headers['X-CSRF-Token'],'server-csrf');assert.equal(JSON.parse(calls[1].opts.body).fields.total_amount,'650000.10');});
test('Live backend failure never falls back to simulated data',async()=>{const api=new ApiClient(async()=>{throw Error('offline');});await assert.rejects(()=>api.list(),e=>e instanceof ApiError&&e.code==='BACKEND_UNAVAILABLE');assert.equal(api.mode,'live');});

test('Local auth config selects register/login endpoints without storing password or JWT',async()=>{const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push({url,opts});return new Response(JSON.stringify({data:url.endsWith('/csrf')?{csrf_token:'local-csrf',auth_method:'local_password',auth_configured:true}:{portal:'pending',csrf_token:'rotated'}}),{headers:{'Content-Type':'application/json'}});});await api.config();await api.register({email_input:'a@example.test/admin',password:'test-fixture-password'});await api.login({email_input:'a@example.test',password:'test-fixture-password'});assert.deepEqual(calls.map(c=>c.url),['/api/auth/csrf','/api/auth/register','/api/auth/login']);assert.equal(calls.at(-1).opts.headers['X-CSRF-Token'],'rotated');assert.equal(calls.at(-1).opts.credentials,'same-origin');assert.equal(api.password,undefined);assert.equal(api.access_token,undefined);});

test('Service setup errors retain their code while displaying a plain login message',async()=>{const api=new ApiClient(async()=>new Response(JSON.stringify({error:{code:'GOOGLE_NOT_CONFIGURED',message:'GOOGLE_CLIENT_ID internal configuration missing'}}),{status:503,headers:{'Content-Type':'application/json'}}));api.csrf='test';await assert.rejects(()=>api.login({credential:'x'}),e=>e.status===503&&e.code==='GOOGLE_NOT_CONFIGURED'&&!/backend|client_id|configuration/i.test(e.message));});

test('API client preserves the browser fetch receiver instead of calling native fetch with ApiClient as this',async()=>{const api=new ApiClient(async function(){assert.equal(this,globalThis);return new Response(JSON.stringify({data:{csrf_token:'bound',auth_method:'local_password'}}),{headers:{'Content-Type':'application/json'}});});await api.config();assert.equal(api.csrf,'bound');});

test('Logout renews pre-login CSRF so Google login can be repeated without a page reload',async()=>{const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push({url,opts});return new Response(JSON.stringify({data:url.endsWith('/csrf')?{csrf_token:'new-prelogin-token',auth_method:'local_password'}:{logged_out:true}}),{headers:{'Content-Type':'application/json'}});});api.csrf='old-login-token';await api.logout();assert.equal(api.csrf,'new-prelogin-token');await api.login({credential:'verified-elsewhere',email_input:'test@example.test'});assert.equal(calls.at(-1).opts.headers['X-CSRF-Token'],'new-prelogin-token');});
test('Mutation requires CSRF; structured 409/401 errors remain visible',async()=>{const api=new ApiClient(async()=>new Response(JSON.stringify({error:{code:'STALE_VERSION',message:'Versi berubah'}}),{status:409,headers:{'Content-Type':'application/json'}}));await assert.rejects(()=>api.login({credential:'x'}),e=>e.code==='CSRF_MISSING');api.csrf='test';await assert.rejects(()=>api.decision('r','i','approve',{expected_version:1}),e=>e.status===409&&e.code==='STALE_VERSION');const noSession=new ApiClient(async()=>new Response(JSON.stringify({error:{code:'SESSION_EXPIRED',message:'Masuk kembali'}}),{status:401}));await assert.rejects(()=>noSession.me(),e=>e.status===401);});
test('Multipart boundary is browser-owned, PDF content type validated, malformed responses rejected',async()=>{let sent;const api=new ApiClient(async(url,opts)=>{sent=opts;return new Response(JSON.stringify({data:{id:'r'}}),{headers:{'Content-Type':'application/json'}});});api.csrf='test';const form=new FormData();form.set('client_id','A');await api.upload(form);assert.ok(!sent.headers['Content-Type']);assert.equal(sent.body,form);const bad=new ApiClient(async()=>new Response('<html>login</html>',{headers:{'Content-Type':'text/html'}}));await assert.rejects(()=>bad.document('r','d'),e=>e.code==='INVALID_FILE');await assert.rejects(()=>bad.me(),e=>e.code==='INVALID_RESPONSE');});

for(const suffix of ['uploder','uploader'])test(`/${suffix} selects uploader without changing identity or other roles`,()=>{assert.deepEqual(parseEmailInput(` Uploader.Test+demo@Example.test /${suffix.toUpperCase()} `),{email:'uploader.test+demo@example.test',adminRequested:false,reviewerRequested:false,uploaderRequested:true});for(const marker of ['review','view','admin','uploder']){assert.throws(()=>parseEmailInput('a@example.test/'+suffix+'/'+marker));assert.throws(()=>parseEmailInput('a@example.test/'+marker+'/'+suffix));}});

test('Local password recovery is reachable after a wrong login and distinguishes old-password proof from admin code',()=>{
  const escape=v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const options={brand:()=>'',themeControl:()=>'',escape,email:'demo@example.test',local:true};
  assert.match(loginHTML({...options,error:'Email atau password AMIGA salah.'}),/login-password-help/);
  const change=passwordPageHTML(options),reset=passwordPageHTML({...options,reset:true});
  assert.match(change,/name="current_password"/);assert.doesNotMatch(change,/name="reset_code"/);
  assert.match(reset,/name="reset_code"/);assert.doesNotMatch(reset,/name="current_password"/);
  assert.match(reset,/15 menit/);assert.match(change,/name="password_confirm"/);
  assert.doesNotMatch(loginHTML({...options,register:true}),/login-password-help/);
  assert.doesNotMatch(passwordPageHTML({...options,email:'"><script>unsafe</script>'}),/<script>/);
  assert.doesNotMatch(passwordResetCodeHTML({email:'<script>',reset_code:'<script>'},escape),/<script>/);
});
test('Password API sends proof via CSRF POST and never stores new passwords or reset codes on the client',async()=>{
  const calls=[];const api=new ApiClient(async(url,opts)=>{calls.push({url,opts});return new Response(JSON.stringify({data:{password_changed:true,csrf_token:'rotated'}}),{headers:{'Content-Type':'application/json'}});});
  api.csrf='prelogin';await api.changePassword({email_input:'a@example.test',current_password:'fixture-old',new_password:'fixture-new',password_confirm:'fixture-new'});
  await api.resetPassword({email_input:'a@example.test',reset_code:'fixture-code',new_password:'fixture-new',password_confirm:'fixture-new'});await api.issuePasswordReset('test/id');
  assert.deepEqual(calls.map(c=>c.url),['/api/auth/password/change','/api/auth/password/reset','/api/admin/users/test%2Fid/password-reset']);
  assert.ok(calls.every(c=>c.opts.method==='POST'&&c.opts.headers['X-CSRF-Token']&&c.opts.credentials==='same-origin'));
  assert.equal(api.password,undefined);assert.equal(api.reset_code,undefined);
});
test('Reviewer PDF represents a revised final voucher rather than an unchanged source invoice',()=>{
  const html=manualReviewHTML({review_status:'PENDING',current_version:3},String);
  assert.match(html,/voucher hasil akhir revisi saya/);assert.match(html,/boleh berbeda dari dokumen sumber/);
  assert.doesNotMatch(html,/memastikan isi PDF sesuai invoice/);
});

test('Voucher tax browser math matches backend decimal fixtures for missing/existing/replaced tax and half-up rounding',async()=>{
  const cases=JSON.parse(await fs.readFile(new URL('../../tests/fixtures/voucher_tax_math.json',import.meta.url),'utf8'));
  for(const c of cases){const result=calculateVoucherTax(c.fields,c.plan);assert.equal(result.net,Number(c.expected.net_payable)*100,c.name);assert.equal(result.vat,Math.round(Number(c.expected.vat_adjustment)*100),c.name);assert.equal(result.withholding,Math.round(Number(c.expected.withholding_adjustment)*100),c.name);}
  const c=cases.find(c=>c.name==='existing_vat');assert.throws(()=>calculateVoucherTax(c.fields,{...c.plan,vat_mode:'ADD'}));
  assert.throws(()=>calculateVoucherTax(c.fields,{...c.plan,source_withholding:'-1'}));
});
test('Batch upload accepts multiple invoice documents and explains separate reviewer tasks',()=>{
  const escape=v=>String(v).replaceAll('<','&lt;').replaceAll('>','&gt;');
  const html=batchUploadHTML([{id:'A',name:'<script>'}],escape);
  assert.match(html,/name="invoice_files\[\]"[^>]*multiple/);assert.match(html,/Setiap invoice mendapat Request ID/);assert.match(html,/tugas reviewer sendiri/);assert.doesNotMatch(html,/<script>/);
});

test('Reviewer bank input is explicitly human provenance without a new PDF; retained annotations are escaped',()=>{
  const escape=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const r={documents:[{id:'original',type:'INVOICE',current_source:true,original_filename:'invoice.pdf'},{id:'evidence',type:'EVIDENCE',original_filename:'bank.pdf'}]};
  const original={account_number:{document_id:'original',source_type:'EXTRACTED',page:1,notes:null}};
  assert.match(accountSourceOptions(r,original,true,escape),/Hasil pemeriksaan reviewer \(tanpa PDF tambahan\)/);
  assert.doesNotMatch(accountSourceOptions(r,original,false,escape),/value="REVIEWER"/);
  const addition=accountSourcePayload(r,original,'REVIEWER');assert.equal(addition.document_id,'original');assert.equal(addition.source_type,'REVIEWER');assert.equal(addition.page,null);
  const sources={account_number:{...addition,notes:'<script>not in PDF</script>'}};
  assert.deepEqual(accountSourcePayload(r,sources,'REVIEWER'),sources.account_number);
  assert.equal(accountSourcePayload(r,sources,'evidence').source_type,'EVIDENCE');
  assert.equal(accountSourcePayload(r,sources,'original').source_type,'MANUAL');
  assert.match(reviewAdditionsHTML(sources,escape),/tidak harus tercantum pada PDF/);assert.doesNotMatch(reviewAdditionsHTML(sources,escape),/<script>/);
});
test('An old manual PDF offers explicit generated output without pretending to copy its signature',()=>{
  const inv={manual_review_pdf:{created_at:'2026-10-16T01:00:00Z'},voucher_tax:{applied:true,edited_at:'2026-10-16T02:00:00Z'}};
  assert.equal(manualTaxStale(inv),true);const html=generatedVoucherHTML(inv);
  assert.match(html,/tanpa mengunggah PDF baru/);assert.match(html,/tanda tangan.*tidak disalin/);
  assert.match(html,/type="checkbox" id="use-generated-voucher"/);assert.doesNotMatch(html,/checked/);
  assert.equal(manualTaxStale({...inv,voucher_tax:{applied:false}}),false);
  assert.equal(generatedVoucherHTML({}), '');
});


test('Changed tax rates update final amounts from the current invoice draft without changing subtotal twice',()=>{
  const f={subtotal:'1000000',total_amount:'1000000',invoice_tax_amount:'0',currency:'IDR',line_items:[{tax_amount:'0'}]};
  const p={vat_mode:'ADD',vat_rate:'11',vat_base:'1000000',withholding_mode:'DEDUCT',withholding_rate:'2',withholding_base:'1000000',source_withholding:'0'};
  assert.equal(calculateVoucherTax(f,p).net,109000000);
  assert.equal(calculateVoucherTax(f,{...p,vat_rate:'12'}).net,110000000);
  const result=calculateVoucherTax(f,{...p,vat_rate:'12',withholding_rate:'13'});
  assert.equal(result.net,99000000);assert.equal(result.vatTotal,12000000);assert.equal(result.withholdingTotal,13000000);assert.equal(f.subtotal,'1000000');
  assert.equal(calculateVoucherTax({...f,subtotal:'2000000',total_amount:'2000000'},{...p,vat_base:'2000000',withholding_base:'2000000'}).net,218000000);
});
test('Atomic review save carries both optimistic revisions, decimal invoice fields and the tax plan in one CSRF request',async()=>{
  let sent;const api=new ApiClient(async(url,opts)=>{sent={url,opts};return new Response(JSON.stringify({data:{invoice:{current_version:2},voucher_tax:{revision:1}}}),{headers:{'Content-Type':'application/json'}});});api.csrf='fixture';
  await api.saveReviewDraft('request/id','invoice/id',{expected_version:1,expected_tax_revision:2,acknowledged:true,invoice:{fields:{total_amount:'1090000.50'}},plan:{vat_rate:'11'}});
  assert.equal(sent.url,'/api/requests/request%2Fid/invoices/invoice%2Fid/review-draft');assert.equal(sent.opts.method,'PATCH');assert.equal(sent.opts.headers['X-CSRF-Token'],'fixture');
  assert.equal(JSON.parse(sent.opts.body).invoice.fields.total_amount,'1090000.50');assert.equal(JSON.parse(sent.opts.body).expected_tax_revision,2);
});
