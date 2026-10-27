# Telegram voucher otomatis v8

16 Oktober 2026. Perubahan hanya di salinan lokal amiga-local-review, port 5002.

Klien membuka **Telegram penerima**, memastikan penerima terverifikasi, mencentang **Terima voucher otomatis setelah reviewer menerbitkan hasil final**, lalu menekan **Simpan pilihan otomatis**. Pengaturan ini sekali per koneksi penerima, dapat dimatikan kapan saja, dan berlaku untuk penerbitan berikutnya dari perusahaan yang terhubung. Voucher lama tidak dikirim ulang ketika opsi diaktifkan. Beberapa akun klien dalam perusahaan hanya menerima bila masing-masing opt-in.

Saat reviewer menyetujui dan menerbitkan voucher final, backend menyimpan pekerjaan pengiriman bersama transaksi penerbitan. Worker mengirim pemberitahuan tetap dan PDF resmi tersimpan, termasuk PDF final yang diunggah reviewer. Tidak perlu percakapan AI/pratinjau/kirim manual lagi untuk jalur ini. Telegram API sendDocument mengunggah PDF multipart sesuai [dokumentasi resmi](https://core.telegram.org/bots/api#senddocument); lampiran tidak diambil dari URL localhost.

Status otomatis terlihat pada detail progres perusahaan dan riwayat reviewer/admin: QUEUED, SENDING, SENT, FAILED, UNKNOWN, CANCELLED. Tidak mencatat handover atau menerima/menutup layanan otomatis. Klien tetap memeriksa hasil di AMIGA. Status SENT berarti Telegram mengembalikan message_id, bukan bukti pesan dibaca.

Penerima dan izin dicek lagi ketika worker mengambil antrean. Perubahan versi, bot, chat, verifikasi, opt-in atau membership membatalkan pekerjaan lama. Akun nonaktif atau PIC yang tidak lagi berwenang juga membatalkan. Unik per voucher+penerima; lock transaksi mencegah dua worker mengirim pekerjaan yang sama. PDF ke chat yang sama diberi jeda. Timeout/crash setelah mulai kirim menjadi UNKNOWN dan tidak diulang otomatis. Kegagalan definitif tetap tercatat; voucher resmi tersedia di web. Jalur manual lama tetap memerlukan pratinjau dan persetujuan, serta menolak duplikasi ketika ada pengiriman otomatis aktif/berhasil/UNKNOWN.

Schema 8 menambah amiga_telegram_automatic_deliveries tanpa mengubah ID atau isi tabel/dokumen lama. SQLite migrasi additive saat startup; PostgreSQL memerlukan migrations/008_automatic_telegram.sql sesudah007. Worker existing harus aktif (START_QUEUE_WORKER=1). Tidak membuat worker/proses paralel baru atau mengubah deployment publik. Cadangan privat sebelum migrasi ada pada .runtime-temp/private-backups/before-v8-*.db, jangan dikemas.

Verifikasi: 203 tes backend, 78 tes frontend dan build lulus. Suite mencakup opt-in/izin, tanpa backfill, pengiriman byte PDF resmi/manual, rollback approval+outbox, isolasi perusahaan/riwayat per penerima, nonce verifikasi/bot baru, pencabutan akses, revisi baru, dua worker, jeda per chat, gagal/timeout/crash, anti-duplikasi manual dan tanpa handover. Semua transport Telegram pada tes fiktif. QA browser memakai portal asli dengan stub API per halaman, mengaktifkan opsi simulasi dan memeriksa status; fixture dihapus sebelum build. Bukti .runtime-temp/v8-telegram-automatic.png adalah data simulasi.

Backend lokal merespons health schema8/status ok. Database aktif: foreign_key_check kosong, seluruh hash voucher resmi dari cadangan tetap sama; automatic_jobs=0 ketika verifikasi. Tidak mengaktifkan opt-in akun pengguna dan tidak mengirim Telegram nyata selama QA.


Uji lokal fiktif terotorisasi berikutnya berhasil sampai status Telegram SENT. Identitas penerima, akun dan bukti pengiriman disimpan privat; bukan bukti alur EC2.
