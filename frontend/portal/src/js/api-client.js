export class ApiError extends Error{constructor(message,status=0,code='API_ERROR',fields={}){super(message);this.name='ApiError';Object.assign(this,{status,code,fields});}}
const id=value=>encodeURIComponent(String(value));
const serviceMessages={
  GOOGLE_NOT_CONFIGURED:'Login belum tersedia. Silakan hubungi pengelola AMIGA.',
  DATABASE_UNAVAILABLE:'AMIGA sedang sibuk atau belum tersedia. Silakan coba kembali.',
  BACKEND_NOT_CONNECTED:'AMIGA belum dapat dihubungi. Silakan coba lagi.',
  AUTH_SERVER_OUTDATED:'AMIGA masih menjalankan versi lama. Tutup terminal AMIGA lama dengan Ctrl+C, jalankan Start-AMIGA.cmd, lalu muat ulang halaman.',
};
export class ApiClient{
  constructor(fetchImpl=globalThis.fetch){this.fetch=(...args)=>fetchImpl.call(globalThis,...args);this.csrf='';this.mode='live';this.authMethod='local_password';}
  async call(path,{method='GET',body,binary=false}={}){
    const headers={Accept:binary?'application/pdf, image/*':'application/json'};
    if(!['GET','HEAD'].includes(method)){if(!this.csrf)throw new ApiError('Token sesi belum tersedia. Muat ulang halaman masuk.',403,'CSRF_MISSING');headers['X-CSRF-Token']=this.csrf;}
    const multipart=typeof FormData!=='undefined'&&body instanceof FormData;if(body!==undefined&&!multipart){headers['Content-Type']='application/json';body=JSON.stringify(body);}
    let response;try{response=await this.fetch('/api'+path,{method,headers,body,credentials:'same-origin',cache:'no-store',redirect:'error'});}catch{throw new ApiError('AMIGA belum dapat dihubungi. Periksa koneksi lalu coba kembali.',0,'BACKEND_UNAVAILABLE');}
    if(binary&&response.ok){const type=response.headers.get('Content-Type')??'';if(!/^(application\/pdf|image\/)/i.test(type))throw new ApiError('Berkas yang diminta belum dapat dibuka. Silakan coba kembali.',502,'INVALID_FILE');return {bytes:new Uint8Array(await response.arrayBuffer()),type,voucherId:response.headers.get('X-Voucher-ID'),handoverRecorded:response.headers.get('X-Handover-Recorded')==='true'};}
    let value;try{value=await response.json();}catch{throw new ApiError('AMIGA belum dapat memproses permintaan ini. Silakan coba lagi.',response.status,'INVALID_RESPONSE');}
    if(!response.ok)throw new ApiError(serviceMessages[value.error?.code]??value.error?.message??'Permintaan belum dapat diproses.',response.status,value.error?.code??'API_ERROR',value.error?.fields??{});
    if(!Object.hasOwn(value,'data'))throw new ApiError('AMIGA belum dapat memproses permintaan ini. Silakan coba lagi.',502,'INVALID_RESPONSE');
    if(value.data?.csrf_token)this.csrf=value.data.csrf_token;return value.data;
  }
  async config(){const value=await this.call('/auth/csrf');if(!['local_password','google'].includes(value.auth_method))throw new ApiError(serviceMessages.AUTH_SERVER_OUTDATED,503,'AUTH_SERVER_OUTDATED');this.authMethod=value.auth_method;return value;}me(){return this.call('/auth/me');}
  ownerSetup(setup_token){return this.call('/auth/owner-setup',{method:'POST',body:{setup_token}});}
  login(input){return this.call(this.authMethod==='google'?'/auth/google':'/auth/login',{method:'POST',body:input});}
  register(input){return this.call('/auth/register',{method:'POST',body:input});}
  changePassword(input){return this.call('/auth/password/change',{method:'POST',body:input});}
  resetPassword(input){return this.call('/auth/password/reset',{method:'POST',body:input});}
  issuePasswordReset(user){return this.call('/admin/users/'+id(user)+'/password-reset',{method:'POST',body:{}});}
  async logout(){const value=await this.call('/auth/logout',{method:'POST',body:{}});this.csrf='';await this.config();return value;}
  list(query={}){return this.call('/requests?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!==undefined&&v!=='')));}
  detail(request){return this.call('/requests/'+id(request));}
  lifecycle(request,body){return this.call(`/requests/${id(request)}/lifecycle`,{method:'POST',body});}
  tasks(scope='available'){return this.call('/tasks?'+new URLSearchParams({scope}));}
  claim(request){return this.call(`/tasks/${id(request)}/claim`,{method:'POST',body:{}});}
  release(request,reason){return this.call(`/tasks/${id(request)}/release`,{method:'POST',body:{reason}});}
  analysis(request,invoice,body){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/analysis`,body?{method:'POST',body}:{});}
  upload(form){return this.call('/requests',{method:'POST',body:form});}
  uploadBatch(form){return this.call('/requests/batch',{method:'POST',body:form});}
  document(request,document){return this.call(`/requests/${id(request)}/documents/${id(document)}`,{binary:true});}
  evidence(request,form){return this.call(`/requests/${id(request)}/evidence`,{method:'POST',body:form});}
  process(request,body){return this.call(`/requests/${id(request)}/process`,{method:'POST',body});}
  invoice(request,invoice,fields){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}`,{method:'PATCH',body:fields});}
  decision(request,invoice,action,body){if(!['approve','reject','validate','resolve'].includes(action))throw new ApiError('Aksi review tidak dikenal.');return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/${action}`,{method:'POST',body});}
  audit(request){return this.call(`/requests/${id(request)}/audit`);}
  voucher(request,invoice,version,official=false){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/voucher/${official?'download':'preview.pdf'}`+(official?'':'?version='+id(version)),official?{method:'POST',body:{expected_version:version},binary:true}:{binary:true});}
  users(){return this.call('/admin/users');}updateUser(user,body){return this.call('/admin/users/'+id(user),{method:'PATCH',body});}
  clients(){return this.call('/admin/clients');}createClient(body){return this.call('/admin/clients',{method:'POST',body});}
  renameClient(client,body){return this.call('/admin/clients/'+id(client),{method:'PATCH',body});}
  reviewers(request){return this.call(`/requests/${id(request)}/reviewers`);}
  assign(request,body){return this.call(`/requests/${id(request)}/assignment`,{method:'PATCH',body});}
  initialRetry(request,invoice,version){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/initial-analysis/retry`,{method:'POST',body:{expected_version:version}});}
  confirmUploader(request,invoice,version){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/confirm-uploader`,{method:'POST',body:{expected_version:version,acknowledged:true,item_count_confirmed:true}});}
  documentRevision(request,form){return this.call(`/requests/${id(request)}/document-revision`,{method:'POST',body:form});}
  agentOverview(request=''){return this.call('/agents/overview?'+new URLSearchParams(request?{request_id:request}:{}));}
  agentHistory(request=''){return this.call('/agents/history?'+new URLSearchParams(request?{request_id:request}:{}));}
  agentChat(body){return this.call('/agents/chat',{method:'POST',body});}
  telegramStatus(){return this.call('/telegram/status');}
  telegramAutomatic(enabled){return this.call('/telegram/automatic',{method:'PATCH',body:{enabled}});}
  telegramContact(contact){return this.call('/telegram/contact',{method:'PATCH',body:{contact}});}
  telegramBotStatus(){return this.call('/admin/telegram-bot');}
  telegramBotSave(body){return this.call('/admin/telegram-bot',{method:'PATCH',body});}
  telegramLink(){return this.call('/telegram/link',{method:'POST',body:{}});}
  telegramVerify(){return this.call('/telegram/verify',{method:'POST',body:{}});}
  telegramUnlink(){return this.call('/telegram/link',{method:'DELETE',body:{}});}
  telegramPreview(request,invoice,body){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/telegram-preview`,{method:'POST',body});}
  telegramSend(preview,hash){return this.call(`/telegram/previews/${id(preview)}/send`,{method:'POST',body:{approved:true,preview_hash:hash}});}
  telegramDeliveries(request){return this.call(`/requests/${id(request)}/telegram-deliveries`);}
  uploadManual(request,invoice,body){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/manual-pdf`,{method:'POST',body});}
  manualPDF(request,invoice,pdf){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/manual-pdf/${id(pdf)}`,{binary:true});}
  manualSignature(request,invoice,pdf,version){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/manual-pdf/${id(pdf)}/signature`,{method:'POST',body:{expected_version:version}});}
  saveReviewDraft(request,invoice,body){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/review-draft`,{method:'PATCH',body});}
  saveVoucherTax(request,invoice,body){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/voucher-tax`,{method:'PATCH',body});}
  analyzeVoucherTax(request,invoice,version){return this.call(`/requests/${id(request)}/invoices/${id(invoice)}/voucher-tax/analyze`,{method:'POST',body:{expected_version:version}});}
  voucherHistory(request){return this.call(`/requests/${id(request)}/voucher-history`);}
  archiveVoucher(request,voucher){return this.call(`/requests/${id(request)}/vouchers/${id(voucher)}/archive-download`,{method:'POST',body:{},binary:true});}
}
