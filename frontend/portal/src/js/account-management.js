import {botSettingsHTML,bindBotSettings} from './telegram-settings.js';
import {passwordResetCodeHTML} from './password-page.js';

function bindClientSearch(form){
  const input=form.querySelector('.account-client-search');
  const choices=[...form.querySelectorAll('.account-client-list .checkbox')].map(label=>({label,name:label.textContent.normalize('NFKC').toLocaleLowerCase('id-ID')}));
  const count=form.querySelector('.account-client-count'),empty=form.querySelector('.account-client-empty'),list=form.querySelector('.account-client-list');
  function filter(){
    const query=input.value.trim().normalize('NFKC').toLocaleLowerCase('id-ID');
    let visible=0;
    for(const choice of choices){choice.label.hidden=!choice.name.includes(query);if(!choice.label.hidden)visible++;}
    count.textContent=`${visible} dari ${choices.length} perusahaan`;
    empty.hidden=!choices.length||visible>0;
    list.scrollTop=0;
  }
  input.addEventListener('input',filter);
  input.addEventListener('search',filter);
  filter();
}

export async function manageAccounts({api,session,shell,pageTitle,escape,run,toast,isCurrent}){
  const [users,clients,bot]=await Promise.all([api.users(),api.clients(),api.mode==='live'?api.telegramBotStatus():Promise.resolve(null)]);if(!isCurrent())return;
  const roleNames=['CLIENT_OWNER','CLIENT_BACKUP','COMPANY_CLIENT','FINANCE_REVIEWER','SERVICE_LEAD','SYSTEM_ADMIN'];
  const labels={CLIENT_OWNER:'Uploader',CLIENT_BACKUP:'Backup uploader',COMPANY_CLIENT:'Klien perusahaan (akun terpisah)',FINANCE_REVIEWER:'Reviewer',SERVICE_LEAD:'Koordinator tim',SYSTEM_ADMIN:'Admin'};
  const reviewers=users.items.filter(u=>u.roles.includes('FINANCE_REVIEWER')||u.account_status==='PENDING_REVIEWER');
  shell(pageTitle('Reviewer & akun','Reviewer langsung aktif saat mendaftar. Admin dapat menonaktifkan dan mengaktifkan kembali akun.')+`
    ${bot?botSettingsHTML(bot,escape):''}
    <section class="panel"><div class="panel-body"><h2>Status reviewer</h2><p class="subtle">Reviewer aktif dapat mengambil tugas terbuka tanpa meminta akses per klien.</p>${reviewers.map(u=>`<div class="reviewer-access-row"><div><strong>${escape(u.display_name)}</strong><p class="subtle">${escape(u.email)} · ${u.account_status==='ACTIVE'?'Aktif':'Nonaktif'}</p></div><button class="${u.account_status==='ACTIVE'?'danger disable-reviewer':'primary enable-reviewer'}" data-user="${escape(u.id)}">${u.account_status==='ACTIVE'?'Nonaktifkan reviewer':'Aktifkan reviewer'}</button></div>`).join('')||'<p class="subtle">Belum ada reviewer terdaftar.</p>'}<p class="subtle">Menonaktifkan reviewer mencabut sesi dan mengembalikan tugas yang belum selesai ke antrean. Voucher dan riwayat tetap tersimpan. Mengaktifkan kembali akun tidak mengembalikan penugasan lama secara otomatis.</p></div></section>
    <section class="panel"><div class="panel-body"><h2>Master klien</h2><p class="subtle">${clients.items.length} perusahaan terdaftar. Nama dapat diperbarui; data dan hubungan akun tetap memakai ID perusahaan yang sama.</p>${clients.items.map(c=>`<form class="company-rename actions" data-company="${escape(c.id)}"><label>Nama perusahaan<input name="name" value="${escape(c.name)}" minlength="2" maxlength="200" required></label><button type="submit">Simpan nama</button></form>`).join('')}<form id="client-create" class="actions"><label>Nama klien baru<input name="name" minlength="2" maxlength="200" required></label><button class="primary">Buat klien</button></form></div></section>
    ${users.items.map(u=>`<section class="panel"><form class="panel-body access-form" data-user="${escape(u.id)}"><h2>${escape(u.display_name)}</h2><p class="subtle">${escape(u.email)}</p>${u.requested_company_name?`<p class="callout">Perusahaan yang diminta: <strong>${escape(u.requested_company_name)}</strong>. Pilih perusahaan di bawah dan aktifkan akun Klien perusahaan.</p>`:''}${u.requested_role?`<p class="subtle">Permintaan akses: ${escape(u.requested_role)}</p>`:""}<fieldset ${u.id===session.user.id?'disabled':''} style="border:0;padding:0"><div class="form-grid"><div><h3>Peran</h3>${roleNames.map(role=>`<label class="checkbox"><input type="checkbox" name="role" value="${role}" ${(u.roles.includes(role)||(!u.roles.length&&u.requested_role===role))?'checked':''}>${labels[role]}</label>`).join('')}</div><div class="account-client-picker"><h3>Perusahaan untuk Uploader / Klien</h3><label>Cari perusahaan<input class="account-client-search" type="search" placeholder="Cari nama perusahaan…" autocomplete="off"></label><p class="subtle account-client-count" role="status" aria-live="polite"></p><div class="account-client-list" role="group" aria-label="Daftar perusahaan untuk akun" tabindex="0">${clients.items.map(c=>`<label class="checkbox"><input type="checkbox" name="client" value="${escape(c.id)}" ${u.clients.some(x=>x.id===c.id)?'checked':''}>${escape(c.name)}</label>`).join('')||'<p class="subtle">Reviewer tidak memerlukan assignment klien.</p>'}<p class="subtle account-client-empty" hidden>Tidak ada perusahaan yang cocok.</p></div></div><label>Status akun<select name="status">${['ACTIVE','DISABLED','PENDING_ADMIN','PENDING_REVIEWER','PENDING_CLIENT','PENDING_COMPANY'].map(status=>`<option ${status===u.account_status?'selected':''}>${status}</option>`).join('')}</select></label></div><button class="primary" style="margin-top:16px">Simpan akses</button></fieldset>${u.id===session.user.id?'<p class="subtle">Akses diri sendiri dikelola administrator lain atau operator lokal.</p>':''}</form></section>`).join('')}`,'users');
  document.querySelectorAll('.company-rename').forEach(form=>form.onsubmit=e=>{e.preventDefault();const old=clients.items.find(c=>c.id===form.dataset.company);run(async()=>{await api.renameClient(old.id,{name:new FormData(form).get('name'),expected_name:old.name});toast('Nama perusahaan diperbarui.');});});
  if(bot)bindBotSettings({api,state:bot,run,toast,isCurrent});
  if(api.mode==='live')document.querySelectorAll('.access-form').forEach(form=>{
    const button=document.createElement('button');button.type='button';button.textContent='Buat kode reset sandi';
    const result=document.createElement('div');result.className='callout';result.hidden=true;result.setAttribute('role','status');
    form.append(button,result);
    button.onclick=()=>run(async()=>{
      result.replaceChildren();result.hidden=true;
      const value=await api.issuePasswordReset(form.dataset.user);if(!isCurrent())return;
      result.innerHTML=passwordResetCodeHTML(value,escape);result.hidden=false;
      result.querySelector('.hide-password-code').onclick=()=>{result.replaceChildren();result.hidden=true;};
      toast('Kode reset dibuat. Sandi lama tetap berlaku sampai kode dipakai.');
    },false);
  });
  document.querySelector('#client-create').onsubmit=e=>{e.preventDefault();const form=new FormData(e.target);run(async()=>{await api.createClient({name:form.get('name')});toast('Klien dibuat.');});};
  document.querySelectorAll('.enable-reviewer').forEach(b=>b.onclick=()=>run(async()=>{await api.updateUser(b.dataset.user,{roles:['FINANCE_REVIEWER'],client_ids:[],account_status:'ACTIVE'});toast('Reviewer aktif. Ia cukup login ulang untuk mulai mengambil tugas.');}));
  document.querySelectorAll('.disable-reviewer').forEach(b=>b.onclick=()=>run(async()=>{await api.updateUser(b.dataset.user,{account_status:'DISABLED'});toast('Reviewer dinonaktifkan. Tugas yang belum selesai kembali ke antrean.');}));
  document.querySelectorAll('.access-form').forEach(form=>{bindClientSearch(form);form.onsubmit=e=>{e.preventDefault();const input=new FormData(form);run(async()=>{await api.updateUser(form.dataset.user,{roles:input.getAll('role'),client_ids:input.getAll('client'),account_status:input.get('status')});toast('Akses diperbarui. Akun terkait perlu login ulang.');});};});
}

export async function mountAssignment({api,session,request,escape,run,toast,isCurrent}){
  if(!session.user.roles.some(r=>['SYSTEM_ADMIN','SERVICE_LEAD'].includes(r))||api.mode!=='live'||['AMIGA_REVIEWED','SENT_TO_CLIENT'].includes(request.status))return;
  const candidates=await api.reviewers(request.id);if(!isCurrent())return;
  const section=document.createElement('section');section.className='panel';
  section.innerHTML=`<form class="panel-body actions"><label>Finance Reviewer untuk request ini<select name="reviewer" required><option value="">Pilih reviewer independen</option>${candidates.items.map(u=>`<option value="${escape(u.id)}" ${u.id===request.pic_id?'selected':''}>${escape(u.display_name)} · ${escape(u.email)}</option>`).join('')}</select></label><button class="primary">Tetapkan PIC</button></form>`;
  document.querySelector('.content').prepend(section);
  section.querySelector('form').onsubmit=e=>{e.preventDefault();const pic_id=new FormData(e.target).get('reviewer');run(async()=>{await api.assign(request.id,{pic_id});toast('PIC reviewer diperbarui.');});};
}
