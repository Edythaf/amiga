export function passwordPageHTML({brand,themeControl,escape,email='',reset=false}){
  return `<div class="login-shell"><header class="login-header">${brand()}${themeControl()}</header><main class="login-layout"><section class="login-story"><div class="eyebrow">Akun AMIGA</div><h1>Masuk kembali,<br><span class="heading-soft">lanjutkan pekerjaanmu.</span></h1><p>Ubah sandi dengan sandi lama. Jika lupa, admin dapat memberikan kode reset yang berlaku 15 menit dan hanya dapat dipakai sekali.</p><p class="subtle">Setelah sandi berubah, masuk kembali pada perangkat yang kamu gunakan.</p></section><section class="panel login-card"><div class="panel-body"><h2>${reset?'Reset sandi':'Ubah sandi'}</h2><p class="subtle">${reset?'Minta admin membuka Reviewer & akun → akunmu → Buat kode reset sandi. Masukkan kode yang diberikan di bawah.':'Isi sandi lama dan tentukan sandi baru. Tidak memerlukan akun Google.'}</p><div id="password-result" role="status" class="callout" hidden></div><form id="password-form"><label for="password-email">Email akun</label><input id="password-email" name="email_input" type="email" autocomplete="username" value="${escape(email)}" required>${reset?'<label for="password-proof">Kode reset dari admin</label><input id="password-proof" name="reset_code" autocomplete="one-time-code" minlength="43" maxlength="43" spellcheck="false" autocapitalize="none" required>':'<label for="password-proof">Sandi lama</label><input id="password-proof" name="current_password" type="password" autocomplete="current-password" maxlength="72" required>'}<label for="password-new">Sandi baru</label><input id="password-new" name="new_password" type="password" autocomplete="new-password" minlength="10" maxlength="72" required><p class="subtle">Minimal 10 karakter, maksimal 72 byte.</p><label for="password-confirm">Ulangi sandi baru</label><input id="password-confirm" name="password_confirm" type="password" autocomplete="new-password" minlength="10" maxlength="72" required><button type="submit" id="password-save" class="primary full-width">Simpan sandi baru</button></form><button type="button" id="password-method" class="login-toggle">${reset?'Masih ingat sandi lama? Ubah langsung':'Lupa sandi lama? Pakai kode dari admin'}</button><button type="button" id="password-back" class="login-toggle">Kembali ke halaman masuk</button></div></section></main></div>`;
}

export function bindPasswordPage({root,api,reset,onBack,onMethod,onSuccess}){
  let saving=false;
  const form=root.querySelector('#password-form'),result=root.querySelector('#password-result'),button=root.querySelector('#password-save');
  root.querySelector('#password-back').onclick=()=>{if(!saving)onBack();};
  root.querySelector('#password-method').onclick=()=>{if(!saving)onMethod(form.elements.email_input.value);};
  form.onsubmit=async event=>{
    event.preventDefault();if(saving)return;
    result.hidden=true;
    const data=Object.fromEntries(new FormData(form));
    if(data.new_password!==data.password_confirm){result.textContent='Konfirmasi sandi baru belum sama.';result.className='callout error';result.hidden=false;return;}
    saving=true;button.disabled=true;
    try{
      if(reset)await api.resetPassword(data);else await api.changePassword(data);
      form.reset();form.hidden=true;root.querySelector('#password-method').hidden=true;
      result.className='callout';result.textContent='Sandi berhasil diubah. Masuk kembali dengan sandi baru.';result.hidden=false;
      onSuccess(data.email_input);
    }catch(error){result.className='callout error';result.textContent=error.message;result.hidden=false;}
    finally{saving=false;button.disabled=false;}
  };
}

export function passwordResetCodeHTML(result,escape){
  return `<p>Kode untuk <strong>${escape(result.email)}</strong>. Berlaku 15 menit, sekali pakai. Berikan langsung kepada pemilik akun setelah identitasnya dipastikan.</p><label>Kode reset sandi<textarea rows="2" readonly autocomplete="off" spellcheck="false">${escape(result.reset_code)}</textarea></label><p class="subtle">Pemilik akun membuka Lupa / ubah sandi → Pakai kode dari admin. Membuat kode baru membatalkan kode sebelumnya.</p><button type="button" class="hide-password-code">Tutup kode</button>`;
}
