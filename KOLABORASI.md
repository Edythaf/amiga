# Integrasi source AMIGA untuk kolaborasi

Source lengkap diadaptasikan dari `pclexus392-coder/AMIGA` commit `a212da842f895a2fc6162fa6871f79265adc1e87`, di atas riwayat `Edythaf/amiga` yang sudah ada. File `sop.md` dan `AMIGA_Dummy_Invoice_Test.pdf` milik repo tim tetap dipertahankan.

Empat portal aktif: `/client`, `/uploader`, `/reviewer`, `/admin`. Entry point `backend.app:create_app`; gunakan `Start-AMIGA.cmd` untuk pengembangan lokal, bukan menjalankan backend dan antarmuka lama secara paralel. Frontend aktif berada pada `frontend/portal/`, sedangkan template lama tetap tersedia sebagai referensi.

Konfigurasi pengembangan dibuat sendiri dari `backend/.env.example`. Database SQLite pengembangan, akun/password, API key, bot Telegram dan dokumen pengguna tidak disertakan. PostgreSQL existing memerlukan peninjauan migrasi berurutan sesuai schema awal serta backup; PR ini tidak menjalankan migrasi, impor data, deploy atau pengiriman Telegram nyata. Struktur relasional ada pada `SCHEMA_3NF.md`; API/flow pada `API_TERBARU.md`; pemeriksaan source pada `SECURITY_REVIEW.md`.

Login: pemilik pertama menyiapkan password lewat launcher lokal. Email biasa mendaftarkan Klien perusahaan yang ditautkan admin; suffix `/uploader` (`/uploder`) memilih pendaftaran Uploader dan `/review` (`/view`) memilih Reviewer pada mode demo. Email bukan bukti kepemilikan Gmail. Review dan konfirmasi tetap dibatasi peran/membership pada backend. Gunakan akun/dokumen fiktif untuk demo; tinjau HTTPS dan onboarding internal sebelum produksi.
