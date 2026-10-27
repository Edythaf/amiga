// Company recipients control automatic delivery; bot credentials belong to admins.
export function telegramUnavailableHTML(configured){
  return configured===true
    ?'<div class="callout warn"><strong>Bot Telegram AMIGA sudah dikonfigurasi.</strong><p>Akun Telegram Klien perusahaan penerima voucher belum terverifikasi. Klien perusahaan membuka Telegram penerima → Terima voucher di Telegram → Verifikasi penerima, lalu membuka tautan yang muncul dan menekan Start di Telegram. Setelah itu, klik “Saya sudah menekan Start, periksa koneksi” di AMIGA.</p><p>Sesudah penerima perusahaan terhubung, muat ulang asisten ini untuk membuat pratinjau pengiriman. Voucher tetap dapat diunduh dari AMIGA.</p></div>'
    :'<div class="callout warn"><strong>Bot Telegram belum dikonfigurasi.</strong><p>Admin membuka Reviewer & akun → Bot Telegram AMIGA untuk memverifikasi dan menyimpan token bot. Setelah bot tersedia, Klien perusahaan perlu memverifikasi akun penerima pada Telegram penerima. Voucher tetap dapat diunduh dari AMIGA.</p></div>';
}

export function recipientHTML(){
  return `<section class="panel" id="telegram-recipient"><div class="panel-body"><h2>Terima voucher di Telegram</h2><p class="subtle">Opsional. Hasil tetap tersedia di AMIGA jika Telegram tidak diisi.</p><form id="telegram-contact-form"><label for="telegram-contact">Telegram penerima</label><input id="telegram-contact" name="contact" maxlength="32" placeholder="@username atau Chat ID pribadi" autocomplete="off" aria-describedby="telegram-contact-help"><p id="telegram-contact-help" class="subtle">Nomor HP saja tidak dapat dipakai. Tekan Start sekali untuk memverifikasi akun, lalu aktifkan Voucher otomatis agar PDF resmi dikirim setelah reviewer menerbitkannya.</p><button type="submit">Simpan tujuan Telegram</button></form><p id="telegram-account-status" class="subtle" role="status">Memuat tujuan…</p><div id="telegram-link-target"></div><div class="actions"><button id="telegram-connect">Verifikasi penerima</button><button id="telegram-verify" hidden>Saya sudah menekan Start, periksa koneksi</button><button id="telegram-disconnect" hidden>Hapus koneksi</button></div></div></section>`;
}

export async function mountRecipient({api,root=document,run,toast,isCurrent}){
  const input=root.querySelector('#telegram-contact');if(!input)return;
  let dirty=false;input.oninput=()=>{dirty=true;};
  async function load(){
    const state=await api.telegramStatus();if(!isCurrent())return;
    if(!dirty)input.value=state.contact||'';
    root.querySelector('#telegram-account-status').textContent=state.connected?'Penerima terverifikasi'+(state.username?': @'+state.username:'')+'.':state.configured?'Belum terverifikasi. Tekan Verifikasi penerima untuk menerima voucher.':'Bot belum diaktifkan admin. Kamu tetap bisa mengunggah invoice.';
    root.querySelector('#telegram-connect').disabled=!state.configured;
    root.querySelector('#telegram-disconnect').hidden=!state.connected;
    const automatic=root.querySelector('#telegram-automatic');
    if(automatic){
      automatic.checked=state.automatic_enabled===true;
      automatic.disabled=!state.connected;
      root.querySelector('#telegram-automatic-save').disabled=!state.connected&&!state.automatic_enabled;
      root.querySelector('#telegram-automatic-status').textContent=state.automatic_enabled
        ?'Aktif. PDF voucher resmi akan dikirim ke akun Telegram ini setelah reviewer menerbitkannya.'
        :state.connected?'Belum aktif. Centang pilihan di atas lalu simpan untuk menerima voucher berikutnya otomatis.'
        :'Verifikasi penerima terlebih dahulu untuk mengaktifkan pengiriman otomatis.';
    }
  }
  await load();if(!isCurrent())return;
  root.querySelector('#telegram-contact-form').onsubmit=e=>{e.preventDefault();run(async()=>{await api.telegramContact(input.value.trim());dirty=false;await load();if(!isCurrent())return;root.querySelector('#telegram-link-target').replaceChildren();root.querySelector('#telegram-verify').hidden=true;toast('Tujuan Telegram disimpan. Verifikasi jika belum terhubung.');},false);};
  root.querySelector('#telegram-connect').onclick=()=>run(async()=>{
    await api.telegramContact(input.value.trim());dirty=false;
    const result=await api.telegramLink();if(!isCurrent())return;
    const a=document.createElement('a');a.href=result.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Buka Telegram dan tekan Start untuk memverifikasi penerima';
    root.querySelector('#telegram-link-target').replaceChildren(a);root.querySelector('#telegram-verify').hidden=false;await load();
  },false);
  root.querySelector('#telegram-verify').onclick=()=>run(async()=>{const state=await api.telegramVerify();await load();toast(state.connected?'Penerima Telegram terverifikasi.':'Start belum cocok dengan tujuan yang diisi. Periksa akun Telegram dan coba lagi.');},false);
  root.querySelector('#telegram-disconnect').onclick=()=>run(async()=>{await api.telegramUnlink();await load();if(!isCurrent())return;root.querySelector('#telegram-link-target').replaceChildren();root.querySelector('#telegram-verify').hidden=true;},false);
  root.querySelector('#telegram-automatic-form')?.addEventListener('submit',e=>{
    e.preventDefault();run(async()=>{
      if(dirty)throw Error('Simpan tujuan Telegram terlebih dahulu sebelum mengubah pengiriman otomatis.');
      const enabled=root.querySelector('#telegram-automatic').checked;
      await api.telegramAutomatic(enabled);await load();
      toast(enabled?'Voucher otomatis diaktifkan untuk penerbitan berikutnya.':'Pengiriman otomatis dinonaktifkan.');
    },false);
  });
}

export function automaticRecipientHTML(){
  return `<section class="panel"><div class="panel-body"><h2>Voucher otomatis</h2><p>Terima PDF resmi hasil akhir reviewer beserta pemberitahuan voucher selesai di akun Telegram yang kamu verifikasi.</p><form id="telegram-automatic-form"><label class="checkbox"><input id="telegram-automatic" type="checkbox" disabled>Terima voucher otomatis setelah reviewer menerbitkan hasil final</label><p class="subtle">Berlaku untuk penerbitan berikutnya dari perusahaan yang terhubung ke akunmu. Mengaktifkan pilihan ini tidak mengirim ulang voucher lama. Pengiriman Telegram tidak menutup pekerjaan; kamu tetap memeriksa dan menerima hasil di AMIGA.</p><button id="telegram-automatic-save" class="primary" type="submit" disabled>Simpan pilihan otomatis</button></form><p id="telegram-automatic-status" role="status" class="subtle">Memuat pengaturan otomatis…</p></div></section>`;
}

export function automaticDeliveryHTML(r,escape){
  const automatic=r.telegram?.automatic;if(!automatic)return '';
  const names={QUEUED:'Menunggu pengiriman',SENDING:'Sedang dikirim',SENT:'Terkirim',FAILED:'Gagal dikirim',UNKNOWN:'Status belum pasti — periksa Telegram',CANCELLED:'Pengiriman dibatalkan'};
  return `<section class="panel"><div class="panel-head"><h2>Pengiriman Telegram</h2><span class="tiny-tag">${automatic.enabled?'Otomatis aktif':'Otomatis belum aktif'}</span></div><div class="panel-body"><p>${automatic.enabled?'Voucher yang diterbitkan setelah pengiriman otomatis diaktifkan akan dikirim ke Telegram terverifikasimu.':'Aktifkan Voucher otomatis di menu Telegram penerima untuk menerima penerbitan berikutnya.'}</p>${automatic.items.map(row=>{const inv=r.invoices.find(i=>i.id===row.invoice_id);return `<div class="validation-flag"><strong>${escape(inv?.fields.invoice_number||'Invoice')} · versi ${row.version}</strong><p>${escape(names[row.state]||row.state)}</p>${row.sent_at?`<small>${escape(new Date(row.sent_at).toLocaleString('id-ID',{timeZone:'Asia/Jakarta'}))}</small>`:''}${['FAILED','UNKNOWN'].includes(row.state)?'<p class="subtle">Periksa Telegram atau hubungi reviewer. Voucher tetap tersedia di AMIGA; pengiriman ini tidak diulang otomatis.</p>':''}</div>`;}).join('')||'<p class="subtle">Belum ada pengiriman otomatis untuk request ini.</p>'}<button id="company-telegram-settings">Pengaturan Telegram penerima</button></div></section>`;
}

export function botSettingsHTML(state,escape){
  return `<section class="panel"><div class="panel-body"><h2>Bot Telegram AMIGA</h2><p class="subtle">Satu bot perusahaan untuk pengiriman voucher otomatis ke penerima terverifikasi, serta pengiriman manual reviewer atau admin.</p><p id="bot-config-status" role="status">${state.configured?'Bot aktif: '+escape(state.username?'@'+state.username:'nama belum diverifikasi')+' · ID '+escape(state.bot_id||'—'):'Bot belum dikonfigurasi.'}</p><form id="telegram-bot-form"><label for="telegram-bot-token">Token API bot</label><input id="telegram-bot-token" type="password" autocomplete="off" spellcheck="false" required placeholder="Tempel token dari BotFather"><p class="subtle">ID dan username dibaca otomatis dari token. Token tidak ditampilkan kembali. Mengganti bot meminta penerima memverifikasi ulang dan membatalkan pratinjau lama.</p><button class="primary" type="submit">Verifikasi & simpan bot</button></form></div></section>`;
}

export function bindBotSettings({api,root=document,state,run,toast,isCurrent}){
  const form=root.querySelector('#telegram-bot-form');if(!form)return;
  form.onsubmit=e=>{e.preventDefault();const input=root.querySelector('#telegram-bot-token'),token=input.value.trim();input.value='';
    run(async()=>{const saved=await api.telegramBotSave({token,expected_revision:state.revision});if(!isCurrent())return;state=saved;root.querySelector('#bot-config-status').textContent='Bot aktif: @'+saved.username+' · ID '+saved.bot_id;toast('Bot terverifikasi dan disimpan privat. Tidak ada pesan yang dikirim.');},false);
  };
}
