# Pembaruan lokal v6 — 16 Oktober 2026

Hanya folder amiga-local-review. EC2 dan proyek asal tidak diperbarui. Tidak membuat akun/data uji pada database demo aktif dan tidak mengirim Telegram atau memanggil AI berbayar selama tes otomatis.

## Tata letak PDF voucher (v6.5)

Nominal pada PDF ditulis seperti Rp 1.850.000 atau Rp 297,20, termasuk rincian, diskon, pajak, penyesuaian negatif dan total. Mata uang lain memakai kode tersimpan, tanpa konversi. Formatter menggunakan Decimal, bukan float; harga/kuantitas mempertahankan hingga enam desimal bermakna dan nilai kosong tetap strip. Ini hanya format tampilan, bukan perubahan perhitungan/angka tersimpan.

Metadata dipadatkan di bagian atas; rekening tetap utuh termasuk nol awal. Tanggal dd/mm/yyyy dan waktu review WIB. Tabel berwarna teal, angka rata kanan, tanggal tidak diulang pada tiap baris, header berulang di halaman lanjutan. Ringkasan nominal menjadi dua kolom dengan total akhir tebal, catatan mendapat judul sendiri, dan tanda tangan memakai tinggi dinamis agar nama panjang tidak terpotong. Voucher pendek contoh tiga item/catatan menjadi satu halaman; banyak item dan catatan panjang dapat berlanjut ke halaman berikutnya tanpa memotong isi.

Format berlaku pada draft dan voucher otomatis yang baru dibuat. PDF resmi yang sudah diterbitkan tetap merupakan arsip saat penerbitan dan tidak ditimpa; versi revisi berikutnya memakai renderer terbaru. PDF final manual tetap berkas reviewer, bukan diubah renderer. Tidak ada perubahan endpoint, schema, hak akses atau nilai pajak. Tes integrasi PDF menyesuaikan ekspektasi teks desimal ke format Indonesia; ekspektasi nilai API tetap decimal kanonis.

Verifikasi: 182 tes backend lulus, termasuk angka presisi/negatif/unknown, semua nominal PDF, sumber tak berubah, rekening nol awal, pagination 65 item/catatan panjang dan header berulang. PDF contoh dan stres dirender ke PNG lalu diperiksa visual; tidak ada teks melewati margin. Contoh fiktif: .runtime-temp/voucher-format-contoh.pdf dan .runtime-temp/voucher-format-page-1.png. Frontend tidak berubah (70 tes dari v6.4 tetap berlaku).

## Kolom nominal utama mengikuti hasil pajak (v6.4)

Kolom PPN dan total utama serta kartu Total akhir voucher sekarang menampilkan hasil penyesuaian yang sama dengan ringkasan pajak. PPh tampil berdampingan. Angka sebelum penyesuaian tersedia dalam bagian tertutup, sehingga angka lama tidak lagi tampak sebagai total utama. Mengubah persentase/dasar langsung menghitung ulang semua tampilan akhir. Subtotal rincian tetap mengikuti item; pajak tidak mengubah nilai barang/jasa.

Reviewer dapat mengoreksi nominal PPN atau total akhir langsung. Koreksi PPN diperhitungkan terhadap pajak item dan memilih Pertahankan agar tidak diterapkan dua kali. Koreksi total mematikan otomatis secara terlihat; validasi aritmetika backend tetap berlaku. Penyimpanan tetap memakai basis kanonis bersama rencana pajak melalui review-draft; tidak mengganti data ekstraksi saat halaman dibuka.

Verifikasi v6.4: 70 tes frontend dan build lulus. Backend tidak berubah; hasil 179 tes v6.3 tetap berlaku. Portal reviewer yang sebenarnya diuji dengan API fixture terisolasi: contoh subtotal 10.760.000, pajak awal 1.165.000 termasuk item, PPN pengganti 0 dan PPh 7% menghasilkan kolom utama/kartu total 9.996.800. PPh 8% langsung mengubah keduanya menjadi 9.889.200. Koreksi total manual tetap tampil dan mematikan otomatis. Bukti .runtime-temp/primary-amounts-sync-preview.png; halaman QA sementara dihapus sebelum build. Tidak menyimpan perubahan ke database pengguna.

## Pajak sinkron langsung dan simpan gabungan (v6.3)

Mengubah tarif, mode atau dasar PPN/PPh langsung memperbarui ringkasan di panel pajak dan di Ringkasan nominal. Nilai akhir memakai draft invoice yang sedang diedit, bukan angka versi lama. Subtotal rincian tetap jumlah item; nominal pajak/potongan dan total akhir mengikuti persentase. Perubahan item memperbarui subtotal dan dasar pajak yang memilih **Ikuti subtotal rincian**. Dasar dari AI yang hanya mencakup jasa dipertahankan jika berbeda dari subtotal; koreksi dasar manual mematikan follow agar tidak ditimpa. Mengedit tarif/dasar saat mode Pertahankan otomatis memilih Tambah/Ganti atau Potong/Ganti sesuai pajak sumber; reviewer tetap bisa memilih Pertahankan kembali.

**Simpan hasil review & pajak** dan tombol simpan data pada portal reviewer memakai endpoint gabungan. Tidak perlu membatalkan salah satu draft. Catatan invoice menggunakan catatan pemeriksaan yang diisi atau alasan pajak sebagai alasan simpan; ack pajak tetap wajib. Kalau ada perubahan angka invoice, versi baru dan konfirmasi uploader tetap berlaku. Pajak saja tidak membuat versi invoice baru. Pratinjau PDF dan voucher resmi mengikuti angka yang sama sesudah disimpan; PDF sumber tetap dokumen asli.

API: PATCH /api/requests/{request}/invoices/{invoice}/review-draft menerima expected_version, expected_tax_revision, acknowledged:true, plan dan invoice opsional. invoice berisi fields, field_sources, item_count_confirmed, reason seperti PATCH invoice lama. Cek revisi pajak lama sebelum membuat versi baru; plan kemudian ditulis pada versi yang sesuai. Kegagalan satu bagian membatalkan seluruh transaksi. Respons: invoice, voucher_tax, revision_created. Endpoint terpisah lama tetap tersedia.

Verifikasi v6.3: 179 tes backend dan 68 tes frontend lulus. Kasus integrasi membuktikan penyimpanan gabungan, rollback versi/audit jika pajak salah, input usang, batas reviewer/tenant, tax-only tanpa versi baru, dan angka pratinjau PDF sama dengan voucher resmi. Browser berlabel fixture membuktikan rate mengubah total langsung, jumlah item mengubah subtotal/dasar, koreksi dasar manual tetap utuh, dan callback simpan gabungan tanpa akses database. Bukti .runtime-temp/tax-live-sync-preview.png. Tidak ada pajak pengguna, akun atau invoice demo aktif yang diubah oleh QA.

## Angka otomatis, format uang dan pilihan mata uang (v6.2)

Saat reviewer membuka draft, komponen angka hasil ekstraksi AI sudah terisi. **Hitung otomatis total baris, subtotal dan total akhir dari data AI** aktif bawaan. Perubahan jumlah, harga, diskon/pajak baris atau invoice langsung memperbarui nominal turunan. Total baris memakai jumlah × harga − diskon + pajak, subtotal menjumlah baris yang dibulatkan HALF_UP, total akhir memperhitungkan diskon/pajak invoice dan PPh sumber yang sudah dipotong. Tidak ada tambahan pajak yang dibuat hanya dari angka kosong.

Total otomatis hanya berubah pada buffer form; simpan untuk membuat versi koreksi. Dokumen dan hasil ekstraksi asli tetap utuh. Jika berbeda dari angka tersimpan, form menunjukkan perubahan belum disimpan dan meminta pemeriksaan ulang item. Untuk mengoreksi nominal total secara manual, matikan pilihan hitung otomatis. Validasi aritmetika backend tetap berlaku; tidak mengakali ketidaksesuaian dengan pajak negatif. Halaman voucher terbit/uploader tidak mengoreksi angka otomatis saat dibuka.

Nominal form ditampilkan seperti **Rp 1.000.000** atau **Rp 1.000.000,50**. Harga satuan, diskon, pajak, total serta dasar PPN/PPh memakai format ini; jumlah dan tarif persen tetap angka biasa. Koma untuk desimal, titik sebagai pemisah ribuan. API tetap menerima string decimal kanonis, misalnya 1000000.50. Nominal hingga enam desimal tetap presisi tanpa floating point.

Mata uang menjadi dropdown: IDR, USD, SGD, MYR, EUR, JPY, CNY, AUD, GBP dan THB. Kode lain yang sudah tersimpan tetap tersedia. Pilihan AI dipertahankan. Mengubah mata uang memperbarui simbol, tanpa mengubah nilai melalui kurs.

Verifikasi: 66 tes frontend lulus dan build berhasil; 176 tes backend dari verifikasi v6.1 masih berlaku (tidak ada perubahan backend pada v6.2). Browser dengan komponen/data fiktif membuktikan koreksi harga memperbarui total, pergantian IDR/USD mempertahankan nilai, serta mode koreksi manual dan kembali otomatis. Bukti .runtime-temp/automatic-money-currency-preview.png. Tidak menambah invoice/password pada database aktif atau memanggil AI berbayar selama QA.

## Tambahan hasil pemeriksaan tanpa PDF baru (v6.1)

Reviewer PIC dapat menambah/mengoreksi semua data voucher, termasuk item, identitas dan rekening, meski tidak tertulis atau tidak terlihat pada PDF sumber. Tulis catatan pemeriksaan, periksa jumlah item dan hitungannya, lalu simpan. Rekening dapat memilih **Hasil pemeriksaan reviewer (tanpa PDF tambahan)**; backend juga mengenali perubahan rekening reviewer secara otomatis. Tambahan tidak diklaim sebagai hasil ekstraksi PDF. Data asli dan perubahan sebelum/sesudah tetap ada dalam versi dan audit. Konfirmasi uploader versi baru tetap diperlukan; tidak perlu melampirkan PDF baru untuk tambahan reviewer tersebut.

Field header memakai source_type REVIEWER dengan catatan alasan dan page:null. document_id mengikat anotasi ke invoice sumber terkait sebagai konteks, bukan bukti bahwa nilainya tercantum di sana. Uploader hanya dapat mempertahankan anotasi reviewer yang nilainya tidak berubah; tidak dapat membuatnya sendiri. Reviewer lain/admin tidak mendapat izin edit baru.

Jika sudah ada PDF manual lalu pajak diperbarui, pilihan **Gunakan voucher otomatis dari data tersimpan** memungkinkan penerbitan tanpa unggah ulang. Pilihan ini eksplisit; PDF manual tetap tersimpan dan tanda tangannya tidak disalin. Voucher otomatis memakai data hasil koreksi dan pajak terbaru; snapshot review mencatat sumber PDF yang dipilih. Default tetap PDF manual bila ada. Tanpa PDF manual, sistem membuat voucher dari data tersimpan.

## Voucher final reviewer

Panel **Voucher final hasil revisi reviewer** menerima PDF hasil koreksi/catatan/tanda tangan. PDF boleh berbeda dari sumber; reviewer menyatakan bahwa berkas itu hasil akhir revisinya. Jika PDF manual dipilih saat persetujuan, bytes berkas tersebut menjadi PDF resmi yang diunduh Klien/dilampirkan Telegram. Data sumber, versi dan berkas lama tetap tersimpan. Tidak adanya tanda tangan tidak memblokir unggah/publikasi. Koreksi nominal harus konsisten dengan data dan pajak voucher yang diperiksa reviewer.

## Sandi tanpa Google

Login → **Lupa / ubah sandi**. Jika ingat sandi lama, isi sandi lama dan sandi baru dua kali. Jika lupa, admin membuka **Reviewer & akun → akun terkait → Buat kode reset sandi**. Pemilik akun memilih **Pakai kode dari admin** dan mengisi kode serta sandi baru. Kode berlaku 15 menit, sekali pakai; membuat kode baru membatalkan sebelumnya. Admin memastikan identitas penerima lalu menyerahkan kode langsung, tanpa pengiriman email/Telegram otomatis. Sandi lama tetap berlaku sampai perubahan/reset berhasil. Sesudahnya seluruh sesi akun dicabut dan pengguna login ulang. Role, perusahaan, approval dan status tidak berubah. Akun DISABLED tidak dapat diaktifkan melalui reset.

API:
- POST /api/auth/password/change: email_input, current_password, new_password, password_confirm.
- POST /api/admin/users/{user_id}/password-reset: System Admin, menghasilkan reset_code dan expires_at sekali.
- POST /api/auth/password/reset: email_input, reset_code, new_password, password_confirm.
Semua memerlukan CSRF; kode tidak dapat diganti dengan email saja. Bukti sandi lama berbagi pembatasan 5 percobaan/15 menit dengan login. Hash bcrypt saja yang disimpan. Kode reset disimpan sebagai SHA-256, bukan plaintext; tidak masuk audit/DTO biasa.

## Pajak & nilai akhir voucher

Reviewer membuka detail invoice; Luna otomatis mengusulkan pajak untuk versi tersimpan. Katalog terbatas memakai referensi DJP/JDIH, bukan asumsi bahwa setiap invoice wajib kena pajak. Model memilih jenis aturan dan dasar transaksi; server mengambil tarif katalog dan menghitung Decimal. Jenis khusus/di luar katalog atau status PKP/NPWP yang belum jelas ditandai perlu pemeriksaan. Usulan belum mengubah voucher sampai reviewer menyimpan dan mengonfirmasinya. Reviewer boleh mengubah jenis, dasar, tarif dan perlakuan, termasuk pajak yang sudah tertulis.

- PPN: Pertahankan, Tambahkan yang belum ada, atau Ganti nilai sumber. Pajak positif pada item/header mencegah mode tambah agar tidak ganda.
- PPh: Pertahankan, Potong yang belum ada, atau Ganti potongan. Isi sumber PPh hanya jika sudah dikurangkan dari total pada PDF; penambahan potongan kedua diblokir.
- Nilai akhir = total sumber + perubahan PPN − perubahan potongan PPh. Ganti memakai selisih terhadap pajak/potongan sumber, bukan menambahkan seluruhnya lagi.
- Angka asli tetap di InvoiceVersion. Rencana pajak berada di InvoiceTaxPlan untuk versi itu. Mengubah data invoice membuat versi dan rencana pajak baru. Pajak tersimpan tidak membatalkan konfirmasi dokumen uploader karena sumber tetap utuh.
- Approval memeriksa versi invoice dan expected_tax_revision; rencana dan hasil hitung disalin ke snapshot review. PDF otomatis, pratinjau, nilai akhir di portal Klien dan pengiriman resmi memakai hasil tersebut. Setelah terbit, pajak versi itu tidak dapat diubah.
- Jika pajak berubah setelah PDF manual diunggah, pilih voucher otomatis dari data terbaru atau unggah ulang PDF final yang sesuai. Berkas manual tidak diubah otomatis.
- Maksimal 2 percobaan AI per versi dan 10 per reviewer/hari; cache sesuai fingerprint dokumen. AI gagal tidak menghapus rencana manual dan tidak menciptakan tarif palsu.

API: PATCH /api/requests/{request}/invoices/{invoice}/voucher-tax dengan expected_version, expected_tax_revision, acknowledged:true, plan. POST pada path tersebut + /analyze memakai expected_version. DTO invoice menambahkan voucher_tax.

Referensi katalog, diperiksa 16 Oktober 2026: [PPN PMK 131/2024](https://www.jdih.kemenkeu.go.id/dok/pmk-131-tahun-2024/summary), [PPh 23](https://www.pajak.go.id/id/pph-pasal-23), [PPh final sewa tanah/bangunan](https://www.pajak.go.id/id/pemotongan-pajak-penghasilan-pasal-4-ayat-2-3), dan [PPh 22 untuk pemungut yang ditentukan](https://www.pajak.go.id/pph-pasal-22). PPN efektif nonmewah pada katalog 11% berasal dari 12% × DPP nilai lain 11/12. Konstruksi, fasilitas khusus dan kasus di luar katalog diarahkan ke pemeriksaan reviewer; jangan memakai tarif umum tanpa memeriksa fakta transaksi.

## Multiinvoice dan penugasan terpisah

Uploader → Unggah invoice, pilih sampai 10 PDF/foto dan bukti bersama. Satu unggahan untuk satu perusahaan yang ditugaskan. Batas berkas tetap 10 MB/5 halaman, total HTTP 32 MB; UI menyisakan ruang metadata.

POST /api/requests/batch menerima invoice_files[], evidence_files[], idempotency_key dan metadata request biasa. Seluruh berkas divalidasi sebelum request disimpan. Pengiriman ulang isi sama dengan kunci sama mengembalikan batch yang sama, isi berbeda ditolak. Setelah ekstraksi, tiap invoice mendapat Request ID dan PIC sendiri, termasuk beberapa invoice dalam satu PDF (maksimal 20 invoice/PDF pada batch baru). Uploader mengonfirmasi setiap tugas; Reviewer A mengambil satu tugas tidak mengunci tugas lain untuk Reviewer B.

Satu PDF multiinvoice tetap utuh sebagai dokumen sumber masing-masing tugas; data invoice dan keputusan terpisah. Sumber/bukti disalin ke dokumen privat masing-masing dengan kunci unik. Normalisasi satu PDF bersifat semua-atau-gagal, tidak menerbitkan hasil parsial. Kegagalan satu berkas terlihat pada requestnya sendiri. Deteksi duplikat tetap berlaku untuk unggahan lain; hanya task saudara dengan sumber yang sama dikecualikan dari duplikat berkas yang disengaja. Re-ekstraksi task terpisah tidak memperbanyak saudara; identitas yang ambigu gagal eksplisit. Request lama tidak diubah/dipisah.

## Migrasi dan verifikasi

Schema 6: tabel baru amiga_upload_batches, amiga_request_intakes, amiga_invoice_tax_plans. SQLite menambah tabel saat startup, tanpa reset; PostgreSQL memakai migrations/006_tax_batch.sql sesudah 005. Launcher dan aplikasi tetap port 5002 lokal.

176 tes backend dan 66 tes frontend lulus. Fixture bersama membuktikan hitung HALF_UP dan enam desimal, koreksi pajak, cegah pajak ganda, final PDF terbaru, input usang, batas tenant, reset sandi sekali pakai, serta klaim dua tugas hasil satu PDF oleh reviewer berbeda. Pengujian AI memakai transport fiktif; klasifikasi pajak lewat API Luna nyata belum diuji pada pembaruan ini.

Pemeriksaan browser setelah launcher pengguna berjalan: formulir ubah sandi dan kode reset tampil pada login lokal. Komponen multiinvoice, pajak dan PDF final diperiksa melalui pratinjau berlabel data fiktif; perubahan tarif contoh menghitung ulang nilai akhir langsung. Tidak ada password diubah, invoice dibuat, atau panggilan AI/Telegram nyata pada pemeriksaan tampilan ini. Halaman QA sementara sudah dihapus. Bukti tampilan berada di .runtime-temp/v6-multiinvoice-preview.png dan .runtime-temp/v6-tax-manual-preview.png, bukan dalam paket partner.

Tambahan verifikasi v6.1: tes integrasi menambah item/rekening tanpa PDF baru, mempertahankan sumber asli, menolak klaim asal reviewer dari uploader, dan menerbitkan voucher otomatis setelah pajak berubah tanpa menimpa PDF manual. Komponen pilihan asal data dan format voucher diperiksa pada browser dengan data fiktif; bukti .runtime-temp/reviewer-additions-preview.png. Schema tetap 6.
