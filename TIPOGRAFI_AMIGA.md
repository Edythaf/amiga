# Sistem tipografi AMIGA

Diterapkan pada portal yang sama, 15 Oktober 2026. Jenis website: workspace administrasi invoice. Audiens: PIC klien, reviewer keuangan, Service Lead, dan administrator. Nuansa: profesional, tenang, hangat, dengan hierarki editorial yang jelas.

## 1. Pairing dan arah visual

| Peran | Font dan sumber | Alasan |
|---|---|---|
| Judul utama, judul editorial, kutipan | [Newsreader — Google Fonts](https://fonts.google.com/specimen/Newsreader) | Bentuk serif memberi karakter pada pembuka halaman tanpa memerlukan dekorasi atau huruf kapital berlebihan. |
| Isi, navigasi, formulir, judul panel, tabel, angka | [Figtree — Google Fonts](https://fonts.google.com/specimen/Figtree) | Sans yang terbuka dan bersahabat untuk pekerjaan administratif. Figtree juga teridentifikasi pada judul situs referensi AMIGA. |

Identitas logo serta arah teal–pink mengacu pada [amiga.id](https://www.amiga.id/). Newsreader merupakan pilihan baru untuk portal ini, bukan klaim font situs aslinya. Warna fungsional disesuaikan agar teks tetap terbaca: aksen teal `#286e76` di mode terang, `#8dcdd0` di mode gelap; pink menjadi penanda navigasi aktif dan detail, bukan warna body.

Hanya dua keluarga font yang dimuat. Weight yang dipakai: **400** untuk isi, **500** untuk judul utama/tombol, **600** untuk judul panel dan penegasan singkat. Logo tetap aset gambar merek.

## 2. CSS lengkap dan pemuatan font

- `frontend/portal/src/css/typography.css`: @font-face lokal, semua token tipografi, h1–h6, p, small, blockquote, link, button, caption, formulir, angka, dan pemetaan komponen portal.
- `frontend/portal/src/css/amiga-theme.css`: token warna terang/gelap dan penyesuaian layout responsif.
- `frontend/portal/public/fonts/`: dua WOFF2 Latin (sekitar 152 KB total), beserta lisensi SIL OFL. Tidak ada permintaan Google Fonts dari browser portal.

Urutan stylesheet pada portal: layout lama → layout portal → `amiga-theme.css` → `typography.css`. Deklarasi font, ukuran, weight, line-height, dan tracking yang tersebar pada tiga stylesheet lama telah dipindahkan ke file tipografi; jangan menambah aturan tipografi kembali di sana.

Untuk website lain yang memilih hosting font Google, alternatif `<link>` berikut setara. Gunakan salah satu metode, jangan muat lokal dan Google sekaligus:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
```

Jika memakai alternatif Google, hapus dua blok @font-face lokal dari salinan CSS. Proyek AMIGA tetap memakai font lokal agar login tidak bergantung pada layanan font eksternal.

## 3. Responsivitas dan hierarki

Satu base: `clamp(1rem, .95rem + .25vw, 1.125rem)`. Rasio **1,25** dipertahankan di seluruh ukuran viewport melalui perkalian token, bukan breakpoint dengan ukuran huruf acak. Root mengikuti ukuran teks browser (`100%`), sehingga zoom tetap dihormati.

| Token / penggunaan | Pada base 16 px | Pada base 18 px |
|---|---:|---:|
| small, caption, metadata | 12,80 | 14,40 |
| body, h6 | 16,00 | 18,00 |
| langkah 1 / h5 / judul panel | 20,00 | 22,50 |
| langkah 2 / h4 / kutipan | 25,00 | 28,13 |
| langkah 3 / h3 | 31,25 | 35,16 |
| langkah 4 / h2 | 39,06 | 43,95 |
| langkah 5 / h1 | 48,83 | 54,93 |
| langkah 6 / pembuka login | 61,04 | 68,66 |

Body memakai line-height **1,6**, paragraf maksimal **70ch**, serta `hyphens: auto` dengan bahasa halaman `id`. Pada layar sempit, lebar mengikuti ruang yang tersedia. Heading memakai line-height **1,15–1,25**, tracking negatif ringan, dan `text-wrap: balance`. Label kecil memakai tracking positif ringan tanpa otomatis mengubah tulisan menjadi kapital.

Newsreader menjadi fokus pada judul halaman; judul panel memakai Figtree agar satu layar tidak dipenuhi judul serif besar. Uang, nomor invoice, dan angka tabel memakai `lining-nums tabular-nums`. Kutipan memakai `oldstyle-nums`. Tabel panjang dapat digulir secara horizontal, bukan dipaksa muat dengan mengecilkan huruf. Tema tersimpan pengguna tetap dihormati; pengunjung baru mendapat mode terang.

## 4. Contoh HTML pendek

```html
<html lang="id" data-theme="light">
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="src/css/amiga-theme.css">
  <link rel="stylesheet" href="src/css/typography.css">
</head>
<body>
  <main class="prose">
    <p class="eyebrow">AMIGA / Pemeriksaan invoice</p>
    <h1>Periksa sebelum diterbitkan.</h1>
    <p>Invoice PT Sinar Pagi sedang diperiksa Rani. Cocokkan rincian
      barang dan rekening dengan PDF sebelum menerbitkan voucher.</p>
    <h2>Catatan pemeriksaan</h2>
    <blockquote>“Mohon periksa diskon pada baris kedua.”</blockquote>
    <p>Total invoice: <strong class="amount">Rp 12.450.000</strong></p>
    <button type="button">Pratinjau voucher</button>
    <small>Data fiktif untuk contoh tipografi.</small>
  </main>
</body>
</html>
```

Contoh lengkap yang dapat dibuka melalui aplikasi: `/portal/typography.html`. File ini memperlihatkan h1–h6, paragraf, link, tombol, kutipan, caption, tabel angka, mode terang/gelap, serta aturan tim. Tombol contoh tidak menerbitkan transaksi.

## 5. Lima aturan tim

1. **Gunakan token skala.** Jangan membuat ukuran font atau tracking bebas per komponen.
2. **Satu judul yang memimpin tiap section.** Newsreader untuk pembuka/editorial; Figtree untuk panel, data, dan kontrol.
3. **Batasi penekanan.** Gunakan 400/500/600; hindari paragraf penuh bold, seluruh heading kapital, gradient text, dan emoji judul.
4. **Jaga keterbacaan.** Body 16–18 px, line-height 1,6, paragraf maksimal 70ch, angka tabel tabular. Jangan mengecilkan teks agar tabel muat.
5. **Tulis tindakan yang spesifik.** “Minta bukti rekening” lebih berguna daripada slogan. Gunakan tanda kutip “ ”, em dash bila diperlukan, dan periksa terang, gelap, ponsel serta pembesaran teks.

## Batas perubahan

Pembaruan ini mengubah tema, aset merek, tipografi, layout yang terdampak, dan copy pembuka. Hak akses, validasi finansial, lifecycle, dan penerbitan voucher tetap memakai backend yang sama. Tidak ada publikasi atau panggilan AI berbayar untuk pekerjaan desain ini.


Verifikasi tema: 43 tes frontend dan build lulus. Alur browser login lokal, task/review/AI fixture, voucher, close dan revisi lulus pada aplikasi penuh dengan SQLite uji. Dua font benar-benar dimuat lokal; skala 1,25 dan line-height 1,6 diperiksa lewat computed style. Specimen diuji pada lebar 390/768/1440px dan teks 200% tanpa overflow dokumen. Pasangan warna teks utama, muted, tombol, pink, error dan warning melewati rasio 4,5:1 pada dua tema (pemeriksaan pasangan token, bukan audit aksesibilitas menyeluruh). Screenshot terang/gelap diperiksa secara visual.

Pratinjau HTTP lokal dari lingkungan ini mengalami timeout; server pratinjau sementara telah dihentikan. Browser QA memakai WSGI bridge terisolasi dan fixture, bukan transaksi pengguna. Untuk melihat pada aplikasi pengguna, jalankan Start-AMIGA.cmd lalu muat ulang; specimen tersedia pada /portal/typography.html.
