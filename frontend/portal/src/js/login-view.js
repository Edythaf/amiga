// Shared sign-in page. The admin request is an email suffix, never a portal selector.
export function loginHTML({brand,themeControl,escape,email,error,preview,local=true,register=false,ownerSetup=false,company=true}){
  return `<div class="login-shell">
    <header class="login-header">${brand()}<div class="actions"><span class="tiny-tag">Workspace AMIGA</span>${themeControl()}</div></header>
    <main class="login-layout">
      <section class="login-story">
        <div class="eyebrow">Administrasi invoice</div>
        <h1>Setiap invoice,<br><span class="heading-soft">jelas tindak lanjutnya.</span></h1>
        <p>Unggah invoice, ikuti pemeriksaan tim AMIGA, lalu terima voucher yang siap ditindaklanjuti.</p>
        <div class="login-flow">
          <div><span>01</span><strong>Unggah</strong><small>Invoice & bukti pendukung</small></div><i>→</i>
          <div><span>02</span><strong>Tinjau</strong><small>Review manusia independen</small></div><i>→</i>
          <div><span>03</span><strong>Serahkan</strong><small>Voucher untuk proses klien</small></div>
        </div>
        <div class="login-assurance"><span class="workspace-dot"></span>Persetujuan dan pelaksanaan pembayaran tetap menjadi kewenangan klien.</div>
      </section>
      <section class="panel login-card"><div class="panel-body">
        <div class="card-kicker">Selamat datang</div>
        <h2 id="login-title">${ownerSetup?'Siapkan akun pemilik':register?'Buat akun AMIGA':'Masuk ke workspace'}</h2>
        <p id="login-description" class="subtle">${ownerSetup?'Buat passwordmu sendiri untuk mengaktifkan akun admin pertama.':register?'Email biasa untuk Klien perusahaan. Tambahkan /uploder pada email untuk akun Uploader.':'Masuk dengan email biasa. Ruang kerja terbuka sesuai peran akunmu.'}</p>
        ${preview?'<div class="callout warn">Pratinjau: identitas dan ekstraksi memakai data simulasi.</div>':''}
        ${error?`<div id="login-error" class="callout error" role="alert">${escape(error)}</div>`:''}
        <form id="login-form">
          ${local&&register?'<label for="login-name">Nama</label><input id="login-name" name="display_name" type="text" autocomplete="name" maxlength="200" required>':''}
          <label for="login-email">Email akun</label>
          <input id="login-email" name="email" type="text" autocomplete="${register?'email':'username'}" autocapitalize="none" spellcheck="false" placeholder="nama@gmail.com" value="${escape(email)}" ${local&&register?'':'aria-describedby="login-hint"'} ${ownerSetup?'readonly':''} required>
          <div class="login-context">${local&&register?'':'<p class="subtle login-hint" id="login-hint">Gunakan email dan password akunmu. Peran dikenali otomatis.</p>'}<span id="login-intent" class="admin-trigger" role="status" hidden>Aktivasi admin</span></div>
          ${local&&register&&!ownerSetup?`<div id="registration-company" ${company?'':'hidden'}><label for="company-name">Nama perusahaan</label><input id="company-name" name="company_name" minlength="2" maxlength="200" autocomplete="organization" ${company?'required':'disabled'}><p class="subtle">Admin akan menghubungkan akun Klien ke perusahaan yang benar.</p></div><div id="registration-telegram" ${company?'':'hidden'}><label for="register-telegram">Telegram penerima (opsional)</label><input id="register-telegram" name="telegram_contact" maxlength="32" placeholder="@username atau Chat ID pribadi" autocomplete="off" ${company?'':'disabled'}><p class="subtle">Untuk menerima voucher yang sudah jadi. Verifikasi penerima tersedia pada menu Telegram penerima; nomor HP saja tidak dapat dipakai.</p></div>`:''}
          ${!local&&!preview?'<div id="google-company"><label for="google-company-name">Nama perusahaan (untuk akun Klien baru)</label><input id="google-company-name" name="company_name" minlength="2" maxlength="200" autocomplete="organization"><p class="subtle">Akun yang sudah terdaftar cukup memakai email. Untuk Uploader baru, tambahkan /uploder pada email.</p></div>':''}
          ${local?`<label for="login-password">Password AMIGA</label><input id="login-password" name="password" type="password" autocomplete="${register?'new-password':'current-password'}" minlength="10" maxlength="72" aria-describedby="password-hint" required><p class="subtle login-hint" id="password-hint">${register?'Buat password khusus AMIGA, minimal 10 karakter.':'Gunakan password yang kamu buat khusus untuk AMIGA.'}</p>`:''}
          ${local&&register?'<label for="login-password-confirm">Ulangi password AMIGA</label><input id="login-password-confirm" name="password_confirm" type="password" autocomplete="new-password" minlength="10" maxlength="72" required>':''}
          <button class="primary full-width" id="login-submit" type="submit">${register?'Daftar':'Masuk'}</button>
        </form>
        ${local&&!ownerSetup?`<button type="button" id="login-toggle" class="login-toggle">${register?'Sudah punya akun? Masuk':'Belum punya akun? Daftar'}</button>`:''}
        ${local&&!register&&!ownerSetup?'<button type="button" id="login-password-help" class="login-toggle">Lupa / ubah sandi</button>':''}
        <div id="google-button" class="google-container"></div>
        <p class="login-foot">AMIGA · Robot Admin</p>
      </div></section>
    </main>
  </div>`;
}
