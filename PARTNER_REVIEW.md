# Menjalankan dan me-review AMIGA terbaru

Mulai dari [API_TERBARU.md](API_TERBARU.md). Backend ZIP yang ditentukan pengguna tetap implementasi utama; controller tambahan memakai database, autentikasi dan policy yang sama.

## Paket portabel

Jalankan dari folder proyek:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-PartnerReview.ps1 -ListOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\Prepare-PartnerReview.ps1
```

Perintah pertama hanya memeriksa daftar file. Perintah kedua membuat `AMIGA-Partner-Review.zip` saat pengguna memilih menjalankannya. ZIP tidak dibuat otomatis ketika dokumen ini ditulis. Script menolak menimpa ZIP existing; gunakan `-OutputPath` baru jika perlu.

Isi paket: source backend/frontend, vendor/font lokal beserta lisensi, migrasi SQL, tes fiktif, launcher/setup dan dokumen kontrak. Tidak termasuk kredensial, `.env` aktif, database, folder storage, unggahan klien, arsip data sumber, `.venv`, `.git`, node_modules, cache dan screenshot runtime.

## Konfigurasi milik partner

1. Ekstrak paket, lalu salin `backend/.env.example` menjadi `backend/.env`.
2. Isi `ADMIN_BOOTSTRAP_EMAIL` dengan email pemilik instalasi partner. Password dibuat pemilik sendiri pada halaman aktivasi launcher.
3. Untuk menjalankan AI nyata, isi kredensial AWS Bedrock pada lingkungan server dan `OPENAI_API_KEY` milik instalasi partner, atau arahkan `OPENAI_API_KEY_FILE` ke file privat pada komputer partner. Jangan memakai path absolut milik komputer pengembang.
4. Ekstraksi: `AI_PROVIDER=bedrock`, `BEDROCK_MODEL_ID=apac.amazon.nova-lite-v1:0`. Agent: `AGENT_MODEL=gpt-6-luna`, default batas 60 panggilan per akun per hari, termasuk analisis awal. Riwayat/input identik dapat menggunakan cache.
5. Telegram boleh dibiarkan kosong. Untuk mengujinya, isi `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_BOT_USERNAME` dari bot khusus instalasi tersebut. Alur lokal memakai getUpdates, jadi bot tidak boleh sedang memakai webhook atau konsumen polling lain. Uploader menautkan akun dari Asisten uploader setelah login.
6. Jalankan `Setup-Backend.cmd`, kemudian `Start-AMIGA.cmd`. Instalasi lokal baru memakai SQLite tanpa data pengguna lama. Untuk PostgreSQL, review migrasi berurutan dan siapkan database sendiri.

Tidak ada kunci API atau password yang perlu dikirim melalui percakapan. Jangan memasukkan kredensial partner ke source yang akan dibagikan lagi.

## Verifikasi offline

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/backend -p "test_*.py"
node --test --test-isolation=none frontend/tests/domain.test.mjs frontend/tests/analytics.test.mjs frontend/tests/portal.test.mjs
node frontend/scripts/build.mjs
```

Tes unit/integrasi memakai database sementara dan transport Luna/Telegram fiktif. Tidak menghabiskan kuota AI atau mengirim Telegram nyata. Browser integration memerlukan Playwright dan Chrome; `frontend/tests/browser-integration.mjs` menjalankan aplikasi melalui WSGI stdio bridge khusus tes, tanpa endpoint fixture di server produksi.

Uji nyata memerlukan konfigurasi milik partner dan dokumen fiktif. Telegram opsional, tidak memblokir daftar/login maupun hasil review di website. Pengiriman nyata baru terjadi ketika reviewer menyetujui pratinjau pada instalasi yang dikonfigurasi.
