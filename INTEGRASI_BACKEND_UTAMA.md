# Backend utama AMIGA — integrasi 16 Oktober 2026

Sumber utama: `amiga-20261015T221710Z-1-001.zip` yang diberikan pengguna. Integrasi dikerjakan dalam folder proyek yang sama, bukan salinan aplikasi baru. Arsip ZIP asli tidak diubah. Hash arsip, hash source, daftar adaptasi, serta lokasi data tersimpan dalam `backend/source_manifest.json`.

## Bagian yang menjadi utama

| Bagian | Implementasi aktif |
|---|---|
| Titik masuk Flask | `backend/app.py:create_app`, mengikuti struktur backend ZIP |
| Login/pendaftaran/sesi | `backend/modules/auth/routes.py`, disesuaikan dengan satu login portal dan sesi yang bisa dicabut |
| Akun/perusahaan | `backend/modules/admin/routes.py`, memakai otorisasi System Admin |
| Request, task, review, voucher | `backend/modules/upload/routes.py`, menyajikan kontrak REST portal yang sudah ada |
| Pemeriksaan PDF/foto dan OCR Bedrock | `backend/modules/upload/service.py`, berasal dari ZIP dengan penambahan pembatasan input, precision Decimal, deteksi halaman scan campuran dan penolakan keluaran terpotong |
| Antrean | `backend/modules/upload/queue_store.py` dan `queue_worker.py`, disesuaikan untuk lease/fencing dan satu database bersama |
| Format PDF voucher | `backend/voucher_service.py`, berasal dari ZIP; kini mendukung stream, draft, versi, jejak reviewer dan disclaimer administrasi |
| Penghubung data portal | `backend/modules/upload/portal_adapter.py` dan `backend/api_common.py` |

`backend/api.py` dan `backend/processing.py` menjadi compatibility import. Keduanya tidak menjalankan backend atau renderer kedua. `backend/application.py` memasang konfigurasi, database, middleware dan aset pada aplikasi yang dibuat entry point utama.

Controller ZIP yang sebelumnya menggunakan HTML/session/PostgreSQL langsung telah diadaptasi menjadi controller REST di lokasi modul yang sama. Portal tetap menggunakan frontend yang telah dibuat, termasuk tema AMIGA, Newsreader/Figtree, mode terang/gelap, papan tugas, asisten analisis, voucher dan progres OPEN/CLOSED. Template HTML bawaan ZIP disimpan sebagai referensi; tidak ada halaman login kedua yang dapat melewati otorisasi portal.

## Penyesuaian yang diperlukan

- Satu skema relasional versioned dipakai bersama oleh backend dan portal. Data akun/request/invoice sebelumnya tetap berada di database yang sama; tidak ada dual-write ke `queue_items` JSON dan tabel invoice versi yang dapat saling berbeda.
- Startup tidak mereset seluruh pekerjaan PROCESSING. Antrean memakai claim atomik, lease dan token fencing untuk mencegah dua worker menerbitkan hasil berbeda.
- `supplier_name` dipetakan ke `vendor_name`; `supplier_bank_*` ke field rekening portal; `tax_amount` tingkat invoice ke `invoice_tax_amount`. Field asli dari ekstraksi Bedrock tetap tersimpan pada raw extraction.
- Nominal tetap string Decimal dan rekening tetap teks. Diskon/pajak yang tidak diketahui tidak diisi 0 tanpa dasar. Seluruh invoice/item harus valid strukturnya; keluaran tidak dipotong diam-diam.
- Persetujuan, versi, tenant, pengunggah, PIC tugas, CSRF, sesi, resolusi duplikasi dan CLOSED tetap diperiksa backend. Perubahan sesudah approval memerlukan review versi baru.
- Foto JPG/JPEG/PNG/WEBP dapat menjadi input invoice. Sistem menyiapkan PDF dan mempertahankan foto asli sebagai dokumen privat `SOURCE_IMAGE`. Reviewer dapat mengganti tampilan antara PDF dan foto asli. Bukti pendukung tetap PDF.
- Batas input portal dipertahankan: 10 MB per file, PDF maksimal 5 halaman; foto maksimal 20 megapiksel. Pemeriksaan format dilakukan ulang server. Tidak ada kewajiban S3 untuk pengembangan lokal.
- Renderer voucher utama mengikuti format ZIP dan menampilkan seluruh item, harga satuan, diskon/pajak, total, rekening, tujuan administratif, pengaju dan reviewer. PDF resmi menjadi snapshot tetap. Draft berwatermark dan tidak dapat diunduh sebagai voucher resmi.

## Data dan konfigurasi privat

1. **Data aplikasi sebelumnya:** kode dan konfigurasi dicadangkan secara privat di `.runtime-temp/pre-primary-backend-20261016/`; SQLite dicadangkan dengan backup API agar WAL ikut tercakup. Jumlah akun, request, dokumen dan voucher aktif dibandingkan dengan cadangan dan tetap sama setelah integrasi.
2. **Data bawaan ZIP:** 48 folder dokumen, 202 file, 19.301.794 byte disalin byte-identik ke `backend/storage/source-archive/`. Statusnya `PRESERVED_UNASSIGNED`. ID user/perusahaan di metadata mengacu pada PostgreSQL sumber; data tidak otomatis diberi pemilik atau dipublikasikan ke tenant lain. `queue.sqlite3` lama juga tetap tersimpan dalam arsip privat.
3. **Konfigurasi aktif:** `backend/.env` yang sudah bekerja dipertahankan. File privat ZIP disimpan sebagai `backend/.env.source` yang diabaikan Git. Tidak ada secret disalin ke frontend, log, atau dokumen ini. Konfigurasi PostgreSQL sumber belum diaktifkan pada runtime lokal.
4. **Koneksi PostgreSQL sumber:** pemeriksaan koneksi hanya-baca dengan timeout gagal/timeout. Tidak ada DDL atau perubahan data pada database tersebut. Jangan menyatakan akun/data PostgreSQL telah terintegrasi hanya karena file konfigurasi tersedia. Pemakaian database sumber memerlukan koneksi yang berfungsi, migrasi skema yang ditinjau, dan pemetaan kepemilikan yang benar.
5. Virtual environment, Git hooks, executable dan skrip pembuatan admin dari arsip tidak dijalankan. Dependensi digabung dengan versi kompatibel yang telah digunakan proyek, tanpa mengganti interpreter dari ZIP.

## Verifikasi

- **97 tes backend lulus**, termasuk 10 tes integrasi source utama: controller/worker aktif berasal dari modul utama, foto menjadi PDF, foto asli tetap privat, duplikasi foto deterministik, input rusak/mismatch ditolak, JPEG/WEBP, precision Decimal, OCR halaman campuran dan penolakan keluaran cloud terpotong.
- **43 tes frontend dan build lulus.**
- Alur browser login lokal bcrypt/JWT lulus: upload, claim, analisis fixture, koreksi, penerbitan dengan renderer ZIP, handover, close/revisi, admin, font lokal, tema, mobile dan foto→PDF→pratinjau foto asli.
- Browser memakai aplikasi Flask lengkap dengan SQLite sementara melalui WSGI bridge. Ekstraksi/analisis cloud memakai fixture. PDF draft dan voucher banyak item dirender dan diperiksa secara visual.
- Tidak ada panggilan AI berbayar, pengiriman ke S3/Telegram, pembayaran atau deploy publik untuk pengujian ini. Koneksi PostgreSQL, AWS/S3, OCR Bedrock nyata dan pengiriman eksternal belum diverifikasi pada integrasi ini.

## Menjalankan

Gunakan `Start-AMIGA.cmd` dari folder proyek ini. Launcher tetap membuka satu halaman login dan menjalankan `backend.manage`, yang memakai `backend.app:create_app`. Jika server versi sebelumnya masih hidup, hentikan terminalnya dengan Ctrl+C lalu jalankan kembali launcher. Preview tetap mode simulasi dan bukan pengganti backend utama.

## Ruang lingkup lanjutan

Chatbot, pengiriman Telegram, serta profil PIC QC yang berbeda dari Finance Reviewer masih merupakan rancangan yang dibahas pengguna. Ketiganya belum diaktifkan oleh integrasi backend ini. Tahap ini menyatukan backend ZIP dengan kemampuan portal yang sudah diimplementasikan; tidak menambahkan persetujuan QC atau pengiriman otomatis secara tersembunyi.

Pembaruan 16 Oktober 2026: ekstraksi Bedrock Nova aktif; hitungan browser/server disamakan, JSON parsial ditolak, dan PDF teks/scan fiktif diuji pada AWS nyata. Lihat [PERBAIKAN_EKSTRAKSI_INVOICE.md](PERBAIKAN_EKSTRAKSI_INVOICE.md) untuk status terbaru; angka verifikasi pada bagian integrasi awal di atas merupakan catatan saat tahap tersebut.
