# Pembaruan workspace AMIGA v7

16 Oktober 2026. Hanya salinan amiga-local-review pada port 5002; tidak deploy, push, membuat ZIP, menghapus akun atau mengubah password.

## Kode request

Contoh: **REQ-20261016-0001-PT-MAJU-0001**.

- 20261016 adalah tanggal request.
- 0001 pertama adalah nomor perusahaan unik.
- PT-MAJU adalah nama perusahaan saat kode diterbitkan.
- 0001 terakhir adalah urutan request perusahaan, terus bertambah dan tidak direset per hari.

Nama perusahaan yang sama tetap aman karena nomor perusahaan berbeda. Mengedit nama tidak mengganti kode request lama. UUID lama tetap primary key internal agar foreign key, tautan, dokumen, voucher dan riwayat tidak rusak. Kode bisnis unik tersimpan pada tabel terpisah dan ditampilkan sebagai identitas utama pada daftar/detail/konteks asisten. Pencarian menerima kode; detail terotorisasi dan asisten dapat menerima kode atau UUID.

Alokasi nomor dikunci per transaksi dengan counter permanen, bukan jumlah baris atau angka acak pendek. Request single upload, batch dan pecahan multiinvoice masing-masing mendapat kode. Data lama di-backfill pada startup, diurutkan request_date lalu UUID; urutan backfill bukan klaim urutan upload historis bila waktu upload lama tidak tersedia. Tidak ada rename primary key atau penggabungan perusahaan berdasarkan nama.

## Buka pekerjaan tanpa geser ke ujung tabel

Baris daftar uploader/admin dan kartu pekerjaan reviewer/klien dapat dibuka dengan klik dua kali. Enter tersedia saat baris/kartu dipilih. Tombol Buka tetap tersedia dan dipindah ke kolom awal; teks tabel membungkus supaya seluruh kolom desktop terlihat. Pada layar sempit, baris berubah menjadi grid. Klik pada tombol, input, tautan atau kontrol lain tidak memicu pembukaan ganda. Dua klik pada kartu reviewer yang belum diambil menjalankan aksi Ambil tugas yang sama dan tetap memeriksa independensi/claim di backend.

## Koreksi potongan hasil AI

Nominal PPh pada Ringkasan nominal draft dapat diedit langsung. Rencana menyimpan `withholding_amount` opsional: null/kosong memakai persentase, nilai nonnegatif memakai koreksi exact dengan pembulatan HALF_UP. Mode DEDUCT/REPLACE tetap membedakan potongan baru dan penggantian potongan sumber agar tidak ganda. Mengedit tarif/dasar di panel pajak menghapus override nominal dan kembali menghitung dari persen. Informasi penggunaan nominal manual ditampilkan pada panel.

Simpan pajak tetap memerlukan konfirmasi reviewer dan revisi optimistik; koreksi pajak saja tidak membuat versi invoice baru. Perubahan isi invoice tetap mengikuti versi/konfirmasi uploader. AI tidak menimpa rencana reviewer yang sudah disimpan. Versi resmi yang sudah diterbitkan tetap terkunci; gunakan alur revisi untuk mengubahnya. PDF resmi dan pengiriman Telegram memakai nominal hasil koreksi tersimpan yang sama.

## Perbesar PDF dan baca alasan

Semua preview PDF menggunakan toolbar Perkecil, Perbesar, Pas lebar dan Perluas PDF. Dialog lebar menyediakan zoom hingga 300% relatif terhadap pas lebar; bitmap memiliki batas memori seluruh halaman. Berlaku untuk PDF sumber, draft/hasil voucher dan PDF reviewer yang sudah diunggah. Form unggah manual juga menyediakan preview lokal sebelum dikirim. Fitur ini tidak mengubah byte berkas atau mencatat handover saat hanya melihat preview.

Panel alasan pajak memiliki textarea lebih tinggi dan tombol Alasan lengkap. Popup dapat dibaca pada versi terkunci dan diedit pada draft; tombol Gunakan alasan ini hanya memindahkan teks ke draft, penyimpanan tetap eksplisit. Catatan koreksi invoice juga dapat diperluas. Escape/Tutup mengembalikan fokus ke pemicu; pergantian halaman menutup dialog.

## Database dan API

Schema 7 menambah `amiga_company_numbers`, `amiga_request_numbers` dan `amiga_invoice_tax_plans.withholding_amount`. SQLite bermigrasi additive saat startup; PostgreSQL perlu `migrations/007_request_codes_review.sql` sesudah006, lalu startup backfill kode. Cadangan SQLite privat sebelum perubahan ada di `.runtime-temp/private-backups/before-v7-*.db`; jangan dikemas.

DTO request menambah `request_code`, `company_number`, `request_sequence`. `id` tetap UUID lama. Endpoint review-draft/voucher-tax menerima plan lama tanpa withholding_amount maupun plan baru. Tabel dan kolom lama tidak dihapus, angka sumber/PDF resmi tidak ditimpa.

## Verifikasi

- 187 tes backend dan 73 tes frontend lulus. Pengujian mencakup kode dengan nama perusahaan sama, rename, backfill idempoten, alokasi bersamaan/rollback, isolasi akses, koreksi AI exact, stale revision dan PDF resmi memakai neto yang sama. Fixture matematika browser/backend mencakup potongan sumber agar tidak terpotong dua kali.
- Browser portal sesungguhnya dengan API fixture terisolasi: klik dua kali pada empat portal, PPh 753.200 dikoreksi ke500.000 langsung mengubah total menjadi10.250.000 dan dapat disimpan, popup alasan, preview manual dan dialog zoom125% berhasil. Fixture tidak membuat akun atau mengubah invoice pengguna. Bukti `.runtime-temp/v7-uploader-list.png`, `v7-pph-editable.png`, `v7-reason-dialog.png`, `v7-pdf-zoom.png`.
- Backend lokal `/health` merespons status ok/schema7. Pemeriksaan SQLite terhadap cadangan memastikan ID akun/request/dokumen/invoice/voucher lama tetap ada, hash voucher resmi tidak berubah, seluruh request memiliki kode dan foreign_key_check kosong.
- Telegram nyata: getMe berhasil untuk AMIGA_VoucherBot, getWebhookInfo berhasil tanpa webhook (verifikasi aplikasi memakai polling). Pengiriman PDF, penerima terverifikasi, preview/persetujuan, idempotensi dan status timeout diuji dengan transport fiktif dalam suite backend. Tidak ada pesan atau dokumen nyata dikirim oleh QA ini. Tidak mengklaim penerimaan pesan di ponsel klien sudah diuji.

## Perbaikan antrean v7.1

Request yang lolos validasi angka tetapi belum dikonfirmasi versi terbarunya kini berlabel **Belum dikirim ke reviewer**, dengan tombol **Periksa & konfirmasi** di daftar uploader dan pintasan pada progres. Panel konfirmasi menjelaskan versi saat ini dan tujuan Tugas tersedia. Tugas saya reviewer mendapat tombol Lihat Tugas tersedia; tidak mengambil tugas otomatis. Request baru tetap memerlukan konfirmasi seluruh invoice sebelum dapat diambil reviewer.

Verifikasi: 76 tes frontend, 21 tes backend workflow dan build lulus. Browser menguji daftar uploader dengan request menunggu konfirmasi vs sudah dikirim, serta perpindahan Tugas saya ke Tugas tersedia memakai portal asli dan API fixture terisolasi. Bukti `.runtime-temp/v71-uploader-status.png` berlabel simulasi fiktif. Pemeriksaan status database hanya read-only. Tidak ada perubahan schema/backend, konfirmasi atau pengambilan tugas pengguna oleh QA.
