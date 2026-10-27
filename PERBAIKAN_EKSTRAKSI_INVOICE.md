# Perbaikan ekstraksi dan invoice — 16 Oktober 2026

Backend utama tetap ZIP amiga-20261015T221710Z-1-001, diperbarui di workspace yang sama.

## Ekstraksi aktif

- AI_PROVIDER=bedrock, BEDROCK_MODEL_ID=apac.amazon.nova-lite-v1:0, region ap-southeast-1. Hanya pengaturan AWS dipindahkan secara selektif dari konfigurasi asal ZIP; database, autentikasi, dan pengaturan OpenAI tidak diganti. Kredensial hanya pada konfigurasi privat server.
- PDF teks memakai pembacaan lokal lalu Nova untuk ekstraksi struktur. PDF scan/foto memakai OCR Bedrock per halaman, lalu ekstraksi struktur. PDF campuran tetap memeriksa seluruh halaman.
- Nova Lite memakai batas keluaran 5.000 token, bukan 8.192. OCR satu halaman per panggilan mengurangi risiko keluaran panjang terpotong. Tidak ada retry lintas provider atau fallback diam-diam.
- Hanya respons selesai end_turn dengan konten teks yang diterima. Truncation, filter, tool output dan respons tidak lengkap ditolak. JSON harus satu objek lengkap; fragmen invoice dari JSON luar yang rusak tidak boleh diselamatkan. Kunci JSON duplikat, NaN/Infinity, container/item rusak juga ditolak.
- Publikasi invoice tetap atomik dan versioned: semua invoice harus dapat dinormalisasi sebelum diterbitkan. Field sumber/raw model tetap dipertahankan. Nilai hilang tetap null dan memblokir persetujuan, tidak diisi nilai buatan.
- Error AWS menjadi kode stabil tanpa kredensial/detail respons privat. Progres ekstraksi FAILED dibedakan dari antrean review.
- Analisis reviewer yang sudah tersedia tetap OpenAI Luna, terpisah dari pilihan ekstraksi AWS. Tiga agent GPT Sol, Telegram, konfirmasi uploader baru dan upload revisi masih pekerjaan tahap berikutnya.

## Angka invoice

- Aturan perhitungan browser/server sama: jumlah × harga − diskon + pajak; setiap hasil baris dibulatkan HALF_UP ke dua desimal, lalu dijumlahkan. Diskon/pajak tambahan invoice diterapkan setelah subtotal, dan hasil akhir dibulatkan dengan aturan yang sama.
- Input jumlah/harga/nominal sampai enam desimal tetap dipertahankan. Hitungan server menggunakan Decimal; browser menggunakan BigInt untuk operasi finansial. Nilai melebihi batas presisi browser tidak diperkirakan.
- Selisih selalu hasil hitung dikurangi total pada PDF. Angka sumber tidak ditimpa otomatis untuk membuat selisih hilang. Toleransi IDR/default yang sudah ada tetap berlaku.
- Pratinjau menampilkan hasil hitung per baris, subtotal, total dan selisih saat diedit. Input kosong membersihkan ringkasan sebelumnya. Mengubah/menambah/menghapus item membatalkan konfirmasi item sebelumnya.
- Nilai sumber belum lengkap tetap memblokir approval walaupun subtotal/total sudah dapat dihitung dari komponen yang tersedia. Riwayat persetujuan dan voucher lama tetap dipertahankan.

## Bukti verifikasi

- Tes otomatis memakai SQLite/transport fiktif dan tidak memanggil API berbayar. Kontrak angka browser/server berbagi kasus pembulatan, quantity/harga enam desimal dan arah selisih.
- Browser Chrome dengan bcrypt/JWT asli dan ekstraksi fixture memeriksa upload, edit, hitungan langsung, sumber yang tidak berubah, reset konfirmasi, angka kosong, reviewer, voucher, penutupan/revisi, foto, dua tema dan mobile.
- Dua uji manual AWS nyata memakai dokumen fiktif saja: PDF teks satu invoice/satu item serta PDF image-only satu invoice/tiga item. Keduanya lolos validasi; nomor rekening 0000123 tetap utuh. Scan menghasilkan total 50000.00. Total tiga panggilan model: satu struktur PDF teks, satu OCR scan, satu struktur hasil OCR.
- Uji terbatas tersebut membuktikan sambungan dan dua jalur fungsi, bukan jaminan akurasi seluruh invoice atau SLA. Tidak ada dokumen klien yang dikirim dalam pengujian, tidak ada S3/Telegram/pembayaran/deploy publik.

## Menjalankan hasil

Hentikan server AMIGA lama dengan Ctrl+C, lalu jalankan Start-AMIGA.cmd dari folder proyek ini dan muat ulang halaman. Konfigurasi provider dibaca saat startup. Dokumen lama tidak diekstrak ulang otomatis; data dan voucher lama tetap tersimpan.

Rujukan AWS: https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html dan https://docs.aws.amazon.com/nova/latest/userguide/complete-request-schema-response.html.
