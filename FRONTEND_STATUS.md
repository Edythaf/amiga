# Status frontend AMIGA

15 Oktober 2026. Portal Klien, Reviewer dan Admin pada workspace tetap.

- Satu form masuk/daftar tanpa pilihan jenis akun. Email biasa otomatis klien; /review atau /view meminta reviewer; /atmin meminta admin. Reviewer disetujui admin sekali, tanpa assignment klien. Login berikutnya cukup email biasa; sidebar dan header menampilkan peran yang jelas.
- Reviewer: Tugas tersedia, Tugas saya, Voucher reviewer, panduan. Kartu tugas memuat klien, vendor, nominal, tenggat, kendala dan penanggung jawab. Filter pencarian/klien/tenggat/kendala, pembaruan delapan detik, klaim eksklusif dan pengembalian tersedia.
- Admin: ringkasan seluruh pekerjaan, Pantau penugasan, Reviewer & akun. Setujui reviewer dan Nonaktifkan reviewer berupa tombol langsung. Penonaktifan mencabut sesi dan melepas tugas belum selesai melalui backend.
- Editor: PDF kiri, empat kelompok data kanan, langkah kerja bernomor, catatan reviewer, konfirmasi seluruh item, simpan draft, batalkan perubahan, preview, validasi serta keputusan. Perubahan belum tersimpan ditandai dan mencegah navigasi, analisis, atau persetujuan. Lampiran bukti melalui portal klien membantu menjaga independensi reviewer.
- Asisten AI: pertanyaan fokus opsional, ringkasan/risiko/temuan/langkah berikutnya, versi dan waktu hasil. Membaca hasil tersimpan tidak memanggil API. Tidak ada saran yang diterapkan atau approval otomatis.
- Progres kerja dan PIC ditampilkan terpisah dari validasi; OPEN/CLOSED dapat difilter. Klien dapat menerima/tutup setelah seluruh voucher diunduh atau meminta revisi beralasan. Data CLOSED tampil terkunci. Pilihan invoice pada halaman voucher menangani PDF multi-invoice; voucher yang sudah terbit sebagian tetap muncul di daftar klien.
- Unduhan internal dibedakan dari unduhan klien yang mencatat penyerahan. Dark/light, animasi reduced motion dan layout mobile dipertahankan.
- 43 tes frontend dan build frontend/dist lulus. Chrome headless lulus pada alur login lokal bcrypt/JWT sebenarnya serta regresi Google fixture. Papan tugas, klaim, analisis fixture, dirty form, revisi/approval/voucher, aktivasi reviewer tanpa assignment, penerbitan melalui menu voucher, close/revisi klien, monitor admin dan viewport 390px berhasil tanpa pageerror/overflow.
- Tes browser memakai Flask/SQLite sementara melalui WSGI bridge stdio. Ekstraksi/analisis browser fixture; satu analisis Luna nyata diuji terpisah dengan PDF fiktif tiga barang dan berhasil menemukan selisih IDR10000. Tidak membuktikan semua SLA/akurasi PDF.
- Preview terpisah tetap simulasi lama. Alur tugas bersama dan analisis API dipakai pada Start-AMIGA.cmd dengan akun AMIGA. Pemeriksaan HTTP langsung host pada perubahan lifecycle dibatasi izin socket; verifikasi terbaru memakai aplikasi penuh terisolasi melalui WSGI bridge.

Panduan pengguna: CARA_KERJA_AMIGA.md. Kontrak API: AMIGA_KONTRAK_API.md. Batas layanan eksternal dan pengujian: INTEGRATION_STATUS.md.

## Tema perusahaan dan tipografi — 15 Oktober 2026

Identitas teal/pink serta logo mengacu pada amiga.id. Newsreader untuk judul utama dan Figtree untuk isi, form, judul panel dan angka. Dua font variable Latin disimpan lokal bersama OFL; tidak ada request font pihak ketiga saat login. Tiga weight 400/500/600, skala 1,25, base clamp 16–18px, line-height body 1,6, paragraf 70ch. Pengaturan tipografi sebelumnya dipindahkan dari tiga stylesheet layout ke typography.css. Token warna dan layout yang terdampak berada pada amiga-theme.css.

Mode terang menjadi default bagi pengunjung baru; pilihan tema tersimpan tetap berlaku. Mobile memakai tabel bergulir, kontrol berukuran sentuh dan kolom panel yang menumpuk. Salinan halaman selama mutation juga mempertahankan penanda busy untuk mencegah klik baru diabaikan ketika PDF masih dimuat.

Panduan lengkap: TIPOGRAFI_AMIGA.md. Contoh interaktif: frontend/portal/typography.html. Tidak ada perubahan kebijakan akses, finansial, atau lifecycle backend.


Verifikasi tema: 43 tes frontend dan build lulus. Alur browser login lokal, task/review/AI fixture, voucher, close dan revisi lulus pada aplikasi penuh dengan SQLite uji. Dua font benar-benar dimuat lokal; skala 1,25 dan line-height 1,6 diperiksa lewat computed style. Specimen diuji pada lebar 390/768/1440px dan teks 200% tanpa overflow dokumen. Pasangan warna teks utama, muted, tombol, pink, error dan warning melewati rasio 4,5:1 pada dua tema (pemeriksaan pasangan token, bukan audit aksesibilitas menyeluruh). Screenshot terang/gelap diperiksa secara visual.

Pratinjau HTTP lokal dari lingkungan ini mengalami timeout; server pratinjau sementara telah dihentikan. Browser QA memakai WSGI bridge terisolasi dan fixture, bukan transaksi pengguna. Untuk melihat pada aplikasi pengguna, jalankan Start-AMIGA.cmd lalu muat ulang; specimen tersedia pada /portal/typography.html.


## Integrasi backend utama 16 Oktober 2026

Portal kini tersambung ke controller utama auth/admin/upload pada backend ZIP yang diadaptasi. Halaman upload menerima PDF/foto (JPG/JPEG/PNG/WEBP), menampilkan foto sebelum upload, lalu PDF hasil konversi serta foto asli pada detail. Voucher resmi memakai renderer ZIP. Alur browser lokal dan Google fixture lulus kembali, termasuk foto→PDF→pratinjau asli. Tema, font lokal, papan tugas, handover, close/revisi dan pembatasan akses dipertahankan. Kontrak JSON tetap kompatibel.

Pembaruan 16 Oktober 2026: ekstraksi Bedrock Nova aktif; hitungan browser/server disamakan, JSON parsial ditolak, dan PDF teks/scan fiktif diuji pada AWS nyata. Lihat [PERBAIKAN_EKSTRAKSI_INVOICE.md](PERBAIKAN_EKSTRAKSI_INVOICE.md) untuk status terbaru; angka verifikasi pada bagian integrasi awal di atas merupakan catatan saat tahap tersebut.

Panel progres enam tahap hanya ditampilkan pada detail/voucher portal uploader/klien. Halaman reviewer tidak menampilkan panel tersebut; panduan pemeriksaan, data invoice, analisis dan penerbitan voucher tetap tersedia.

Progres uploader: saat panel penuh terlewati, bilah ringkas enam segmen menempel di tepi atas kolom konten (36px desktop, 40px mobile). Klik kembali ke panel lengkap; mengikuti reduced motion, dua tema, dan dibersihkan saat navigasi/logout. Uji Chrome membuktikan posisi, tinggi, batas sidebar/viewport, kembali ke panel, dan tidak terbawa ke reviewer. 45 tes frontend dan build lulus; tidak ada panggilan AI baru untuk perilaku scroll.

Verifikasi workflow v4 terbaru: **126 tes backend**, **45 tes frontend**, build, dan browser local_password lulus. Browser mencakup tiga asisten, konfirmasi awal/revisi uploader, arsip voucher, peran admin dan pratinjau/persetujuan Telegram dengan transport fiktif. Tidak ada panggilan AI berbayar atau Telegram nyata tambahan pada pengujian v4.


## Bubble asisten — 16 Oktober 2026

Tanya AMIGA tampil sebagai bubble kanan bawah untuk ketiga portal, membuka panel non-modal tanpa meninggalkan pekerjaan. agent-page.js sekarang mendukung root scoped dan tetap menjadi satu implementasi percakapan/Telegram. Halaman penuh tersedia lewat ↗. Konteks mengikuti dokumen, draf per Request ID tersimpan hanya dalam memori, Escape mengembalikan fokus ke launcher, dan logout menghapus widget/listener/draf. Tidak ada perubahan provider, endpoint, scope akses atau izin pengiriman.

45 tes frontend dan build lulus. Browser local_password lulus untuk bubble desktop/390px, kirim dengan Enter, tutup/buka kembali draf, Escape/fokus, perluasan halaman, serta pratinjau/edit/persetujuan Telegram dalam bubble dengan transport fiktif. Snapshot telah diperiksa; tidak ada API berbayar/Telegram nyata dari tes ini.
