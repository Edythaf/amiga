# Cara kerja AMIGA

Satu halaman masuk: http://127.0.0.1:5000/login. Setelah akun aktif, gunakan email biasa dan password yang kamu buat sendiri. Nama portal di sidebar menunjukkan peran aktif.

## Klien

1. Pilih **Daftar**, lalu masukkan email tanpa akhiran. Akun mendapat workspace klien pribadi.
2. Buka **Unggah invoice**, pilih PDF atau foto JPG/JPEG/PNG/WEBP dan isi tanggal/tenggat. Foto disiapkan menjadi PDF; foto asli tetap tersedia pada Dokumen sumber. Bukti tambahan diperlukan bila informasi rekening kurang atau rekening dikoreksi.
3. Tunggu ekstraksi Nova dan analisis awal Luna pada detail. Bandingkan seluruh item, nominal dan rekening dengan PDF, simpan koreksi bila perlu, lalu centang pemeriksaan dan klik **Konfirmasi & kirim ke reviewer**. Setelah seluruh invoice aktif dikonfirmasi, tugas muncul di papan reviewer. Perubahan data/bukti meminta konfirmasi ulang. **Dokumen saya** menunjukkan status dan PIC.
4. Buka detail untuk melengkapi data atau membaca catatan reviewer. Simpan koreksi sebelum berpindah halaman.
5. Setelah reviewer menyetujui, buka **Voucher saya → Unduh voucher resmi**. Unduhan klien mencatat penyerahan; pembayaran tetap di luar AMIGA.

6. Status pekerjaan membedakan **belum diambil**, **sedang dikerjakan reviewer**, **menunggu perbaikan klien**, **voucher siap**, dan **ditutup**. Nama penanggung jawab serta waktu pembaruan terlihat pada detail; gunakan **Muat ulang status** untuk perkembangan terbaru.
7. Setelah **semua voucher terbaru** diunduh, centang penerimaan hasil lalu klik **Terima hasil & tutup pekerjaan**. Status menjadi CLOSED dan data terkunci. Voucher tetap dapat diunduh. Ini penerimaan layanan administrasi, bukan persetujuan pembayaran.
8. Jika voucher perlu koreksi, pilih **Minta revisi**; jika sudah CLOSED, pilih **Minta revisi & buka kembali**. Tulis alasan. Seluruh invoice pada request mendapat versi baru dan wajib diperiksa/disetujui ulang. Voucher lama dan audit tetap disimpan. Reviewer lama tetap menangani jika aktif; jika tidak aktif tugas kembali ke antrean.

Klien tidak dapat melihat data klien lain. Filter OPEN/CLOSED tersedia di daftar dokumen. Penutupan tidak otomatis terjadi saat reviewer menerbitkan voucher atau klien mengunduhnya.

## Reviewer / viewer

1. Pilih **Daftar**, lalu tambahkan `/review` atau `/view` pada email, misalnya `nama@gmail.com/review`. Kedua penanda meminta peran reviewer yang sama.
2. Admin memeriksa identitas dan menyetujui satu kali. Setelah itu login ulang dengan email biasa. Tidak perlu assignment atau izin untuk setiap klien.
3. **Tugas tersedia** menampilkan ringkasan tugas semua klien yang belum diambil. Gunakan filter klien, tenggat, pencarian, atau kendala. Daftar diperbarui otomatis setiap delapan detik saat halaman terlihat.
4. Klik **Ambil tugas**. Tugas pindah ke **Tugas saya** dan hilang dari papan reviewer lain. Detail dan PDF tersedia bagi reviewer yang mengambilnya.
5. Bandingkan PDF dengan empat kelompok data: identitas, barang/jasa, nominal, rekening. Periksa seluruh baris dan centang konfirmasi item.
6. Gunakan **Analisis dengan AI** untuk mendapat ringkasan, risiko, temuan, dan urutan pemeriksaan. Pertanyaan fokus opsional. AI membaca data yang sudah disimpan; simpan koreksi dahulu. Hasil AI tidak menggantikan validasi atau keputusan manusia.
7. Klik **Simpan data & perbarui draft voucher**. **Tinjau & terbitkan voucher** menunjukkan PDF hasil data tersebut. Gunakan **Batalkan perubahan belum tersimpan** untuk kembali ke data terakhir.
8. Buka menu **Voucher reviewer → Periksa draft & terbitkan**. Pilih invoice jika PDF berisi beberapa invoice. Setelah kendala selesai, periksa draft dan centang konfirmasi pemeriksaan, lalu klik **Setujui & terbitkan voucher**. Tombol yang sama tetap tersedia pada bagian keputusan di detail review. Jika perlu koreksi klien, gunakan **Minta perbaikan ke klien** dan isi catatan. Penolakan memerlukan versi revisi baru sebelum persetujuan berikutnya.
9. Jika tidak bisa melanjutkan, buka **Tugas saya → Kembalikan ke antrean**. Reviewer lain bisa mengambilnya. Riwayat tetap ada.

Pengunggah invoice atau bukti tidak boleh menyetujui request itu sendiri. Unduhan internal reviewer tidak mengubah status menjadi diserahkan ke klien.

## Admin

Untuk meminta akun admin, daftar dengan `nama@gmail.com/admin`. Setelah aktif, cukup masuk dengan email biasa.

1. Buka **Reviewer & akun → Permintaan reviewer → Setujui reviewer**. Persetujuan ini berlaku untuk akses papan tugas bersama.
2. Buka **Pantau penugasan** untuk melihat pemilik, tenggat, status, serta kendala setiap tugas. Detail tugas menyediakan **Riwayat** dan penugasan ulang selama review belum selesai.
3. Gunakan **Nonaktifkan reviewer** untuk menghentikan akses. Semua sesi akun dicabut. Tugas yang belum selesai kembali ke antrean; penugasan historis dan voucher selesai tetap tersimpan.
4. Pengaturan klien dan akun lain tersedia di bagian lanjutan halaman akun. Assignment klien hanya wajib untuk peran Klien/Backup.

Admin mengelola akses dan pekerjaan. Persetujuan review tetap dilakukan reviewer independen.

## Bantuan AI

API key tetap dibaca backend dari konfigurasi privat. Tidak ada key di browser. Setiap analisis baru menggunakan API; menampilkan hasil tersimpan tidak memanggil model lagi. Input mencakup versi draft, validasi, pertanyaan, dan PDF sumber/bukti hingga lima berkas atau 15 MB. Berkas yang tidak disertakan diberitahukan agar diperiksa manual. Hasil dicatat pada audit dan ditolak bila data, penugasan, atau akses berubah selama proses.

Satu uji nyata dengan PDF fiktif tiga barang berhasil menemukan selisih total Rp10.000. Ini uji fungsi terbatas, bukan jaminan akurasi semua invoice atau target waktu seluruh dokumen.

## Jika tampilan masih lama

Muat ulang halaman. Bila route reviewer/papan tugas belum tersedia, tutup terminal AMIGA lama dengan Ctrl+C dan jalankan **Start-AMIGA.cmd** dari folder proyek tetap. Data dan akun tetap tersimpan.

Mode `Start-AMIGA.cmd preview` merupakan simulasi lama; alur papan tugas dan analisis API digunakan pada aplikasi lokal dengan akun AMIGA.


Backend utama memakai ZIP yang diberikan pada 16 Oktober 2026 dan frontend tetap proyek ini. Jalankan launcher yang sama. Data bawaan ZIP disimpan sebagai arsip privat sampai pemilik/kliennya dipetakan secara benar; tidak otomatis muncul di akun klien. Rincian integrasi: INTEGRASI_BACKEND_UTAMA.md.

## Asisten dan revisi dokumen (v4)

Menu **Asisten AI** tersedia untuk setiap peran. Gunakan Request ID dari detail atau tombol **Asisten uploader/reviewer/admin** untuk membuka konteks dokumen. Uploader dapat menanyakan progres dan temuan, reviewer membahas pemeriksaan/prioritas, admin melihat urgensi dan tabel hasil reviewer. Kuota default 60 panggilan per akun per hari termasuk analisis awal; jawaban identik dengan data yang sama dapat memakai cache.

Uploader dapat membuka **Dokumen sumber salah? Unggah revisi**, memilih PDF/foto baru dan menulis alasan. Request ID tetap sama; sumber lama, review dan voucher tetap disimpan. Jika ada voucher terbit, setujui bahwa hasil sebelumnya menjadi arsip. Pekerjaan CLOSED harus dibuka melalui permintaan revisi dahulu. Analisis dan konfirmasi diperlukan kembali. Arsip voucher dapat diunduh dari **Riwayat**, dan tidak menggantikan hasil aktif.

Telegram tidak wajib. Pada Asisten uploader, pilih **Hubungkan Telegram**, buka bot, tekan Start lalu **periksa koneksi**. Bila bot belum dikonfigurasi atau uploader belum terhubung, reviewer mendapat catatan bahwa pesan belum dapat dikirim; website tetap berfungsi.

Reviewer membuka Asisten reviewer untuk Request ID miliknya, membahas hasil, lalu memilih invoice dan opsional voucher resmi. Klik **Buat pratinjau pesan**, baca percakapan, penerima, versi, isi dan lampiran. Mengedit isi memerlukan **Perbarui pratinjau setelah edit** sebelum persetujuan. Pengiriman hanya berlangsung setelah reviewer mencentang persetujuan dan menekan **Setujui & kirim ke Telegram**. Status tidak pasti tidak dikirim ulang otomatis; periksa Telegram dahulu.

Admin melihat jumlah tugas diambil, seluruh invoice selesai, pekerjaan diterima klien dan diterima tanpa revisi dalam periode laporan. Nilai tanpa revisi memakai jumlah pekerjaan yang sudah diterima sebagai denominator, bukan semua tugas masuk. Ini informasi operasional, bukan keputusan AI tentang kualitas individu.

## Asisten berbentuk bubble

Tombol **Tanya AMIGA** berada di kanan bawah portal klien, reviewer dan admin. Klik untuk membuka chat tanpa meninggalkan invoice. Konteks mengikuti Request ID pada detail; **Request ID & konteks** dapat dipakai untuk mengganti fokus. Bagian prioritas, kinerja admin dan Telegram dapat dibuka-tutup; tutup bagian tersebut untuk kembali ke percakapan. Tombol ↗ membuka halaman asisten lengkap.

Bubble dapat ditutup dengan × atau Escape. Draf pertanyaan dipertahankan dalam memori selama sesi, terpisah per konteks; logout membersihkannya. Enter mengirim pesan dan Shift+Enter membuat baris baru. Mode terang/gelap, layar HP dan reduced motion tetap didukung. Model, scope akses dan persetujuan Telegram memakai API yang sama; menutup atau membuka bubble tidak memanggil model berbayar.
