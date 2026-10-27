# Status integrasi AMIGA

16 Oktober 2026. Workspace tetap, diperbarui di tempat. Backend ZIP amiga-20261015T221710Z-1-001 menjadi sumber utama; lihat INTEGRASI_BACKEND_UTAMA.md.

Ekstraksi aktif: AWS Bedrock Nova Lite; PDF teks dan scan fiktif telah diuji nyata. Perbaikan angka/JSON dan rincian pengujian: [PERBAIKAN_EKSTRAKSI_INVOICE.md](PERBAIKAN_EKSTRAKSI_INVOICE.md).

## Alur aktif

- Satu login email/password dengan portal Klien (/client), Reviewer (/reviewer), Admin/Service Lead (/admin), dan status pending (/pending). Password dibuat pemilik akun; bcrypt/JWT cookie HttpOnly, CSRF, lockout dan sesi revocable dipertahankan. Google opsional.
- Klien biasa mendapat tenant baru yang privat. /review atau /view meminta PENDING_REVIEWER, admin menyetujui sekali melalui Setujui reviewer tanpa client_ids. /atmin tetap permintaan admin dengan bootstrap pemilik melalui capability launcher sekali pakai. Setelah aktif cukup login email biasa.
- Papan bersama menampilkan ringkasan tugas terbuka lintas klien untuk reviewer aktif. Klaim atomik mengisi pic_id. Tugas pindah ke Tugas saya dan hilang dari daftar tersedia. Halaman aktif memperbarui daftar setiap delapan detik. Hanya pemilik tugas yang mendapat akses reviewer ke detail, dokumen, editing dan analisis; Klien/Backup tetap dibatasi membership tenant. Admin/Service Lead memantau seluruh pekerjaan.
- Admin dapat menonaktifkan reviewer: sesi dicabut dan tugas belum selesai kembali ke antrean. Tugas/voucher selesai dan audit tetap disimpan. Revisi baru dengan PIC nonaktif kembali ke antrean. Admin tidak approve voucher; reviewer independen dari pengunggah invoice dan bukti.
- Editor menjelaskan tiga langkah: periksa sumber, simpan data, terbitkan voucher. Empat kelompok field, konfirmasi seluruh item, preview voucher, catatan reviewer, penanda perubahan belum tersimpan dan pembatalan tersedia. Keputusan dan analisis diblokir saat perubahan belum disimpan.
- Analisis Luna dipicu reviewer pada draft tersimpan, membandingkan PDF dan data/validasi. Hasil berupa ringkasan, risiko, temuan dan langkah pemeriksaan. Tidak mengedit, meresolusi flag, atau approve. API key hanya server. Hasil disimpan di audit, input identik memakai cache, dan akses/PIC/versi/fingerprint diperiksa lagi setelah panggilan API. Database lock dilepas selama panggilan.
- PDF input, antrean durable lease/fencing, raw extraction, versi, Decimal validation, duplikasi, SoD, resolusi beralasan dan snapshot voucher tetap aktif. MISSING_EVIDENCE dipicu rekening/sumber tidak lengkap; invoice lengkap tidak selalu perlu bukti terpisah. Perubahan rekening tetap memerlukan EVIDENCE.
- Hanya unduhan Klien/Backup pada tenant berwenang mencatat handover. Unduhan reviewer/admin untuk pemeriksaan tidak membuat SENT_TO_CLIENT. Multi-invoice menunggu handover seluruh voucher aktif.
- Skema versi 3: 20 tabel, satu tabel tambahan amiga_request_lifecycle. Migrasi additive 003; SQLite menaikkan versi 1/2 ke 3 otomatis saat startup, PostgreSQL eksplisit. Data legacy tidak diimpor otomatis, DB eksternal HOBBY tidak diubah.
- Menu Voucher reviewer menampilkan draft dan voucher tugas sendiri, selector multi-invoice, validasi, konfirmasi pemeriksaan, serta penerbitan. Klien melihat progres/PIC/OPEN-CLOSED, menerima hasil setelah semua voucher terbaru diunduh, atau meminta revisi beralasan. CLOSED mengunci mutation konten; PDF dan audit tetap tersedia. Revisi membuka request dan menambah versi seluruh invoice untuk review ulang.
- Kebijakan lifecycle dipusatkan di backend/request_lifecycle.py; endpoint transition mengunci parent request dan memeriksa revision lifecycle serta seluruh versi invoice. Label/komponen progres frontend dibagi melalui work-progress.js. Status kanonik BRD tetap terpisah dari penutupan administratif.

## Verifikasi terakhir

- 107 tes backend lulus. Sepuluh tes tambahan memverifikasi controller/worker ZIP aktif, foto→PDF dan sumber asli, duplikasi konversi, format gambar, precision Decimal, OCR campuran dan respons terpotong. Sembilan tes lifecycle mencakup progres tanggung jawab, penutupan hanya oleh klien, semua voucher/handover terbaru, akses lintas tenant, perubahan setelah CLOSED, revisi/PIC nonaktif/arsip, versi stale, close bersamaan, close beradu edit, dan upgrade SQLite v2. Tambahan mencakup klaim bersamaan satu pemenang, ringkasan lintas-klien tanpa membership reviewer, PDF/detail eksklusif setelah klaim, release, aktivasi sekali, pencabutan sesi, pelepasan tugas belum selesai, revisi setelah reviewer nonaktif, tenant membership yang dicabut, internal vs client download, analisis berizin/cache/audit/failure, perubahan konteks serta penonaktifan saat analisis berjalan.
- 45 tes frontend lulus dan frontend/dist berhasil dibangun.
- Chrome headless terbaru lulus pada jalur bcrypt/JWT sebenarnya tanpa Google; regresi Google fixture lulus saat integrasi backend utama sebelumnya. Alur mencakup pendaftaran reviewer melalui /review tanpa pemilih peran, alias /view, penghapusan suffix kembali menjadi klien, persetujuan sekali tanpa assignment klien, portal terpisah, papan tugas, klaim, analisis fixture, dirty form, revisi/approval/voucher, unduhan klien, penerbitan melalui menu Voucher reviewer, penutupan dan permintaan revisi klien, monitor admin, renderer voucher ZIP, foto→PDF→pratinjau foto asli, dark/light dan viewport 390px tanpa overflow.
- Browser memakai Flask/SQLite sementara melalui WSGI stdio bridge; ekstraksi dan analisis dalam tes browser memakai fixture, bukan panggilan berbayar.
- Satu panggilan analisis Luna nyata berhasil dengan PDF fiktif tiga jenis barang. PDF total IDR118000 vs draft IDR128000; AI menunjukkan selisih IDR10000 dan langkah koreksi. Lama sampel 10,53 detik, 751 input / 610 output token. Ini uji fungsi terbatas, bukan pembuktian SLA atau akurasi umum.
- Uji ekstraksi Luna nyata sebelumnya memakai satu invoice/satu item dan berhasil. Analisis tiga item di atas bukan pengganti pengujian ekstraksi seluruh baris pada ragam PDF lima halaman.
- Pemeriksaan host sebelum perubahan lifecycle: localhost:5000 health 200 dengan local_password/openai/gpt-6-luna; route /reviewer 200. Aplikasi mengirim review_workflow:task_pool_v1 untuk membedakan versi alur. Pengujian tidak membuat akun/password/transaksi nyata pengguna. Pada perubahan lifecycle, pemeriksaan HTTP langsung localhost dibatasi izin socket sandbox; versi server yang sedang berjalan belum diverifikasi ulang. Pengujian browser memakai aplikasi penuh yang baru melalui WSGI bridge terisolasi. Muat ulang aplikasi; bila masih lama, restart Start-AMIGA.cmd.

## Batas dan cara pakai

Baca CARA_KERJA_AMIGA.md untuk langkah pengguna, AMIGA_KONTRAK_API.md untuk API. Jalankan Start-AMIGA.cmd; bila server lama belum memuat perubahan, Ctrl+C pada terminalnya lalu jalankan kembali. Tidak ada proses lain yang dihentikan.

Start-AMIGA.cmd preview tetap simulasi lama, bukan papan tugas/API aktif. Produksi publik belum dipasang. PostgreSQL eksternal dan Google nyata belum diverifikasi; AWS Bedrock telah diuji terbatas pada PDF teks dan scan fiktif. HTTPS/WSGI produksi, backup operasional, S3/antivirus, pemantauan dan optimasi volume besar belum disiapkan. Target ekstraksi <=15 detik, UI <=2 detik dan PDF <=3 detik belum diuji secara representatif. Tidak ada deploy publik, email keluar, atau pembayaran.

Kunci dibaca dari file privat yang ditunjukkan backend/.env dan tidak dicetak/disalin ke frontend. Penyimpanan dokumen tetap disk privat, snapshot PDF dan audit di database. Tidak ada fallback provider atau data demo diam-diam ketika API gagal.

## Kesesuaian dengan PDF dan batas perubahan

PDF AMIGA Robot Admin — MAIN Hackathon 2026, halaman 5/7/8, menetapkan review independen → voucher resmi → unduh klien dan pembayaran di luar sistem. Implementasi mempertahankan alur itu. OPEN/CLOSED dan penerimaan hasil oleh klien merupakan tambahan operasional dari permintaan pengguna, bukan ketentuan pembayaran pada PDF. Target SLA belum dibuktikan dengan uji beban produksi. Tidak ada panggilan AI berbayar tambahan dalam perubahan lifecycle ini.


## Integrasi backend utama 16 Oktober 2026

Aplikasi Flask dibuat oleh backend/app.py. Controller auth/admin/upload memakai modul utama ZIP yang diadaptasi ke kontrak portal. OCR/inspeksi memakai service ZIP, antrean pada queue_store/queue_worker utama, dan PDF pada voucher_service utama melalui adapter DTO. Pada integrasi awal skema bersama v3/20 tabel; workflow terbaru v4/27 tabel tanpa menggandakan data invoice ke dua store. File backend/api.py serta processing.py hanya compatibility import.

Foto JPG/JPEG/PNG/WEBP diterima sebagai input invoice dan dikonversi menjadi PDF; foto asli tetap privat. Format voucher utama menampilkan harga, diskon, pajak dan total baris, draft berwatermark, nomor versi, reviewer dan disclaimer. Berkas kode/konfigurasi/database sebelumnya dicadangkan privat. Jumlah akun, request, dokumen dan voucher aktif tetap sama.

48 folder dokumen sumber (202 file, 19.301.794 byte) disimpan byte-identik di backend/storage/source-archive tanpa tenant hasil tebakan. Konfigurasi ZIP disimpan privat sebagai backend/.env.source, konfigurasi aktif lama tetap dipertahankan. Pemeriksaan PostgreSQL sumber hanya-baca timeout; tidak ada DDL atau import ke PostgreSQL. Tidak ada panggilan AI berbayar/S3/Telegram baru. Tiga chatbot Luna dan Telegram opsional kini diimplementasikan pada workflow v4; PIC QC terpisah belum ditambahkan.

## Pembaruan workflow v4

Implementasi terbaru dan review partner: [API_TERBARU.md](API_TERBARU.md), [PARTNER_REVIEW.md](PARTNER_REVIEW.md). Analisis awal Luna dan konfirmasi uploader mendahului papan tugas. Tiga asisten mengikuti peran dan Request ID; admin mendapat metrik reviewer yang dihitung server. Revisi sumber mempertahankan riwayat/arsip. Telegram opsional memerlukan link private-chat dan persetujuan reviewer atas pratinjau; transport nyata belum diuji dan bot lokal belum diisi.

Tes otomatis menggunakan data/transport fiktif. Tidak ada pengiriman Telegram nyata atau deployment pada perubahan ini. Source/contoh API config siap dikemas dengan Prepare-PartnerReview.ps1; ZIP belum dibuat dan kredensial/database/data klien dikecualikan.

Verifikasi workflow v4 terbaru: **126 tes backend**, **45 tes frontend**, build, dan browser local_password lulus. Browser mencakup tiga asisten, konfirmasi awal/revisi uploader, arsip voucher, peran admin dan pratinjau/persetujuan Telegram dengan transport fiktif. Tidak ada panggilan AI berbayar atau Telegram nyata tambahan pada pengujian v4.
