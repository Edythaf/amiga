# Pemeriksaan source AMIGA — 16 Oktober 2026

Cakupan: autentikasi lokal, pembatasan perusahaan dan peran, independensi reviewer, konfirmasi uploader, versi invoice/voucher, perhitungan Decimal, unggahan, pengiriman Telegram otomatis, dependency dan isi rilis. Pemeriksaan ini bukan sertifikasi keamanan atau penetration test menyeluruh.

Temuan yang diperbaiki:

- PDF.js 5.6.205 termasuk rentang terdampak [GHSA-hq66-cqwq-w95j](https://github.com/advisories/GHSA-hq66-cqwq-w95j). Library dan worker diperbarui ke 6.2.108 dari registry npm, dengan verifikasi SHA-512 terhadap metadata paket resmi. Pratinjau memakai canvas dan `isEvalSupported:false`. Penghancuran worker kini menggunakan LoadingTask sesuai API versi 6.
- Paket deployment sebelumnya mengabaikan ekstensi `.mjs`, sehingga renderer/worker PDF dapat hilang dari rilis. Filter paket sekarang menyertakan modul tersebut beserta LICENSE. Tes memeriksa seluruh import relatif statis modul portal dan kehadiran renderer/worker/license.
- Ignore Git diperluas untuk PDF hasil kerja lokal, database SQLite, kunci privat dan laporan pengujian penerima nyata. Rahasia server, `.env`, storage, runtime, backup dan virtualenv tidak termasuk source yang dipublikasikan.
- Pip lokal diperbarui dari 25.0.1 ke 26.2.1. Pip bukan dependency runtime aplikasi dalam requirements.

Validasi: 205 tes backend dan 78 tes frontend lulus, build berhasil, serta uji browser render/zoom/tampilan besar PDF berhasil. Audit versi dependency memakai OSV untuk paket Python terpasang, pin Gunicorn dan dua library PDF JavaScript. Audit 40 paket setelah pembaruan tidak menemukan advisori yang berlaku pada versi yang diperiksa. Hasil audit dan bukti browser disimpan privat dalam `.runtime-temp`, bukan bagian source publikasi. Alur invoice fiktif sampai penerimaan Telegram nyata sebelumnya lulus melalui HTTP API lokal; itu tidak menyatakan alur EC2 telah diuji.

Kontrol yang dipertahankan: bcrypt, JWT HttpOnly dan pencabutan sesi, CSRF pada mutasi, lockout sandi, verifikasi membership di backend, reviewer independen, expected_version/tax_revision, PDF resmi immutable, opt-in Telegram terverifikasi, dan tidak mencoba ulang pengiriman UNKNOWN.

Batas penggunaan: konfigurasi demo HTTP hanya untuk akun/password uji dan dokumen fiktif. Reviewer/uploader langsung aktif merupakan perilaku demo yang diminta pemilik; ini bukan verifikasi identitas email atau onboarding produksi. Produksi memerlukan HTTPS dan peninjauan onboarding internal, pembatasan trafik, backup serta pemantauan operasional. Pengguna menunda pembaruan EC2; publikasi GitHub tidak mengubah database atau layanan server.
