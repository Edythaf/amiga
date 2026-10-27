# Deployment AMIGA ke EC2 — Kelompok 10

Status 16 Oktober 2026: aplikasi demo HTTP berjalan di **http://54.163.22.36/login**, port publik **80**, pada instance **i-0d180ffec44dcbe91** di **us-east-1**. Nginx, Gunicorn AMIGA dan PostgreSQL aktif. Pemeriksaan dari laptop setelah restart: /health 200, /login 200, /api/auth/me anonim 401, login tanpa CSRF 403. Port 3000 dan 5432 tidak terjangkau dari luar pada pemeriksaan ini. Ini bukan verifikasi seluruh alur pengguna.

Uji manual provider dari EC2 berhasil memakai dokumen/konteks fiktif: AWS Bedrock us.amazon.nova-lite-v1:0 mengekstrak satu invoice dengan perhitungan valid dan nol awal rekening terjaga; agent gpt-6-luna memberi jawaban. Sebelumnya Nova mengembalikan pajak nol sebagai null; instruksi ekstraksi diperjelas tanpa mengisi nilai hilang secara otomatis atau melonggarkan validasi. Kunci Luna sempat tertempel empat kali identik; salinan server dibetulkan dengan mencocokkan fingerprint sumber, tanpa menampilkan nilainya. Tes backend offline 134 lulus. Tidak ada pesan Telegram nyata dikirim.

Source dasar commit de41e587e8d0f8f585ac9b4087b1105562f05141 ada di /opt/amiga. Dua patch runtime diverifikasi terhadap source lokal: backend/deployment.py SHA256 4906a63e3509778de7647267341b7883ed01e6f026014162e8a5be0c5313051c dan backend/modules/upload/service.py SHA256 UTF-8/LF 1175ed46895485d3db9b140ba25601d694c31649ff05043f33d52d6cdada452e. Perubahan lokal terbaru belum dipush ke GitHub. PostgreSQL memakai peer lokal sebagai user OS amiga; AWS memakai iam-role. Konfigurasi dan key privat ada di /etc/amiga, tidak masuk source/paket.

Batas verifikasi: password pemilik belum dibuat; login akun, unggah–konfirmasi uploader–claim reviewer–voucher di server belum diuji. Browser Chrome otomatis menolak halaman publik dengan BLOCKED_BY_CLIENT, sehingga visual publik belum terverifikasi; permintaan HTTP dari laptop berhasil. Telegram opsional belum dikonfigurasi. HTTPS belum disiapkan karena pengguna memilih demo HTTP sesuai tutorial; gunakan akun/password uji dan invoice fiktif. IP dapat berubah setelah stop/start.

Percobaan sebelumnya di ap-southeast-1 gagal karena batas vCPU 16; itu bukan bukti bahwa kuota us-east-1 habis. Pembuatan security group khusus di Singapore juga ditolak IAM. Tidak ada server Singapore yang dibuat dan tidak ada resource kelompok lain yang diubah. Template bersama tetap dipakai tanpa mengubah aturannya; target aplikasi publik 80 dan backend localhost:3000. CloudShell pada akun lab tidak dapat membuat environment, sehingga jalur upload source melalui CloudShell belum tersedia. Source repo privat telah diambil melalui GitHub CLI yang diotorisasi pengguna.

Runtime server: Python 3.12/pip, Nginx, PostgreSQL 15 server/client dipasang dari repository Amazon Linux. GitHub CLI 2.102.0 dipasang dari repository RPM resmi GitHub dengan signature vendor. Pengguna sudah menyetujui device authorization GitHub CLI; konfigurasi autentikasi sementara di /dev/shm telah dibersihkan setelah pengunduhan source. Credential helper Git global tidak diubah. Tidak ada token GitHub dalam URL git, log source, atau file deployment.

## Hasil cek ulang tutorial

- Halaman 5: region mengikuti mentor, gunakan launch template dan ukuran bawaan, satu instance saja, tanpa key pair, Owner harus username IAM persis. Langkah tersebut diterapkan.
- Halaman 7 dan pemecahan masalah halaman 13 mencantumkan us-east-1; template region itu ada dan peluncuran berhasil. Kesimpulan bahwa harus menunggu kenaikan kuota berdasarkan error Singapore saja sudah dikoreksi.
- Halaman 2/3/9/11 memakai port publik 3000 dan HTTP. Permintaan pengguna memilih port publik 80, sehingga Nginx menjadi listener publik dan meneruskan ke backend localhost:3000. Ini penyesuaian yang disengaja, bukan kesalahan bind.
- Halaman 8 menyatakan repo privat membutuhkan otorisasi. Repo AMIGA tetap privat; jangan mengganti visibilitas sebagai jalan pintas.
- Halaman 10 menempatkan PostgreSQL pada localhost. Tidak ada kebutuhan membuka port 5432.
- Halaman 15 meminta IP EC2 dan port aplikasi, bukan Instance ID. IP aplikasi adalah 54.163.22.36 dan port 80; HTTP serta provider AI lulus smoke check. Login akun dan seluruh alur pengguna masih menunggu uji.

## Sesuai panduan mentor

PDF `Deploy aplikasi ke EC2.pdf` menetapkan satu instance dari `main-ec2-templates`, tanpa mengganti ukuran instance/disk/key pair. Owner harus username IAM persis, bukan otomatis nama kelompok. Akses melalui Session Manager, kemudian `sudo su - ec2-user` dan `cloud-init status --wait`. Tidak ada SSH key atau access key baru yang diperlukan. Jangan hentikan instance/server milik kelompok lain.

Konfigurasi EC2 mengikuti halaman 7 tutorial dan instance yang berhasil dibuat: `us-east-1` (N. Virginia), port publik **80 melalui Nginx**, backend internal `127.0.0.1:3000`, PostgreSQL lokal dan kredensial AWS melalui instance role `MainEC2Role`. Template versi 2 memakai Amazon Linux 2023, t3.micro dan disk gp3 20 GiB. Tag Owner=student_10 diterapkan pada instance dan volume. Jangan salin `backend/.env`, `.env.source`, `C:\API`, database laptop atau dokumen pengguna ke repo/server.

Nova Lite tetap diperlukan untuk PDF scan/foto. Contoh Nova Micro dalam PDF mentor hanya mendukung teks; jangan mengganti model OCR ke Micro. Profil yang disiapkan adalah `us.amazon.nova-lite-v1:0`; akses role lab ke profil dan model tujuannya lulus uji manual PDF teks fiktif dari EC2. Scan/foto belum diuji ulang di server ini. Jika role hanya mengizinkan Micro, minta mentor memeriksa akses Lite, bukan memasukkan access key lokal sebagai jalan pintas. Konfigurasi AWS laptop untuk pengujian lokal tidak diubah.

## Port publik 80 dan login produksi

Permintaan terbaru pengguna mengganti alamat publik menjadi `http://IP` (port 80). Nginx meneruskan trafik ke backend localhost:3000; port 3000 tidak perlu dibuka di security group. PDF mentor sebelumnya memakai port 3000. Login produksi AMIGA memakai cookie Secure dan membutuhkan endpoint HTTPS. Produksi tetap mempertahankan ketentuan tersebut. Server saat ini memakai mode demo HTTP eksplisit seperti dijelaskan di bawah; login akun belum diuji.

Untuk produksi, gunakan ingress/reverse proxy HTTPS yang disediakan mentor, atau domain dan sertifikat valid pada konfigurasi yang disepakati. Untuk ingress HTTPS yang meneruskan ke Nginx port 80, batasi origin sesuai jalur ingress yang benar. Tidak ada penambahan port, DNS, load balancer, sertifikat atau biaya AWS yang dilakukan otomatis oleh file ini.

Pengguna telah memilih mengikuti HTTP tutorial setelah perbedaan dengan produksi dijelaskan. Konfigurasi server disetel AMIGA_ENV=lab_demo, AMIGA_LAB_HTTP_ACK=1, PUBLIC_BASE_URL=http://54.163.22.36. Mode ini tetap mewajibkan PostgreSQL, secret server, instance role dan otorisasi akun; cookie tidak memakai Secure agar berfungsi melalui HTTP. Respons diberi header X-AMIGA-Environment: lab_demo. Gunakan dokumen fiktif dan password uji yang unik. Mode produksi tetap menolak HTTP meskipun flag lab diisi. Untuk beralih ke produksi: sediakan endpoint HTTPS, ubah AMIGA_ENV=production dan PUBLIC_BASE_URL, hapus ACK lab, verifikasi proxy/cookie/login, lalu restart service. Jangan mengubah database atau membuat ulang skema saat beralih mode.

## Berkas deployment

- `backend/deployment.py`: wrapper factory utama, memeriksa konfigurasi produksi dan membatasi Host yang diterima.
- `deploy/ec2/gunicorn.conf.py`: satu worker, empat thread, localhost:3000, tanpa reloader/preload; satu background worker antrean.
- `deploy/ec2/nginx-amiga.conf`: listener publik port 80; isi server_name dengan hostname/IP tujuan, cek konflik konfigurasi Nginx existing sebelum dipasang.
- `deploy/ec2/amiga.service`: unit systemd non-root; source di `/opt/amiga`, dokumen di `/var/lib/amiga/documents`, runtime di `/run/amiga`.
- `deploy/ec2/.env.example`: konfigurasi server tanpa nilai rahasia.
- `deploy/ec2/preflight.py`: pemeriksaan offline yang hanya mencetak kode kesalahan, tanpa koneksi database/cloud atau nilai rahasia.
- `deploy/ec2/package_release.py`: paket source saja, tanpa akun, database, dokumen klien, kredensial atau backup.

Konfigurasi laptop tetap terpisah. `UPLOAD_DIR` sekarang dapat ditentukan lewat environment agar dokumen server tetap tersimpan di luar folder source saat update.

## Persiapan di EC2 setelah akses tersedia

1. Verifikasi instance milik kelompok, cloud-init selesai, OS/arsitektur, Python 3.12+, RAM/disk, port publik 80 dan port internal 3000 tidak dipakai aplikasi lain, instance role dan endpoint HTTPS.
2. Clone repo privat melalui metode akses yang disetujui pemilik/mentor. Token tidak boleh dimasukkan ke URL git, script, shell history, screenshot atau source. Jika memakai arsip source terfilter, verifikasi SHA256 lalu ekstrak di `/opt/amiga` yang baru/kosong; jangan menimpa deployment lain.
3. Buat user service `amiga`, folder konfigurasi `/etc/amiga` dan state `/var/lib/amiga`. Source dibaca service; kredensial hanya dapat dibaca root/group service.
4. Pada Amazon Linux, periksa paket PostgreSQL yang cocok dengan AMI. Jangan jalankan initdb bila cluster lama sudah ada. Buat database dan user aplikasi tersendiri; PostgreSQL hanya listen localhost. Jangan membuka port 5432 di security group.
5. Salin contoh konfigurasi ke `/etc/amiga/amiga.env`, isi database, SECRET_KEY acak, email pemilik dan endpoint HTTPS yang benar. Simpan API key Luna privat di `/etc/amiga/openai.key` (root:amiga, mode 0640); jangan commit nilainya. Telegram boleh kosong. Tanpa key Luna, tahap analisis awal tidak siap.
6. Instal dependency di virtualenv Linux:

```bash
cd /opt/amiga
python3.12 -m venv .venv
.venv/bin/python -m pip install -r deploy/ec2/requirements.txt
.venv/bin/python deploy/ec2/preflight.py --env-file /etc/amiga/amiga.env
```

7. Tinjau migrasi `001`–`004`. Untuk database AMIGA baru yang telah disiapkan, jalankan inisialisasi eksplisit sebagai user service, dengan direktori dokumen sudah dimiliki `amiga`:

```bash
sudo -u amiga /opt/amiga/.venv/bin/python -m backend.manage --env-file /etc/amiga/amiga.env init-db
```

8. Setelah preflight lulus dan database siap, pasang unit systemd lalu jalankan service:

```bash
sudo install -m 0644 deploy/ec2/amiga.service /etc/systemd/system/amiga.service
sudo systemctl daemon-reload
sudo systemctl enable --now amiga
sudo systemctl status amiga --no-pager
curl --fail http://127.0.0.1:3000/health
# Setelah server_name Nginx diisi dan konfigurasi existing diperiksa:
sudo nginx -t
# Terapkan/reload Nginx hanya setelah validasi dan tujuan instance terverifikasi.
```

Port yang dilaporkan kepada mentor adalah **80**, bukan port backend 3000. Pemeriksaan publik memakai `http://IP/health` atau endpoint HTTPS yang disediakan, tanpa `:3000`.

9. Pemilik membuat password sendiri. Gunakan `backend.manage setup-admin` secara interaktif pada server, atau capability aktivasi sekali pakai dari operator tepercaya. Jangan mengirim password ke Codex atau repo. Login pertama pada endpoint mode yang dipilih dengan email `/admin`; berikutnya email biasa. Pendaftaran reviewer `/review` atau `/view` dan izin admin tetap berlaku.
10. Uji HTTPS dari luar: login/logout, cookie Secure/HttpOnly, isolasi tenant, unggah invoice fiktif, ekstraksi Nova, analisis Luna, konfirmasi uploader, klaim reviewer, voucher dan arsip. Telegram tidak diuji dengan mengirim ke klien nyata tanpa instruksi terpisah.

## Update dan pemulihan

Backup PostgreSQL dan direktori dokumen secara privat sebelum migrasi/update. Hentikan hanya `amiga.service`, terapkan source/migrasi yang ditinjau dan restart service itu. Jangan memakai `pkill node`, `pkill python`, atau menghapus database untuk menyelesaikan konflik port. Source versi sebelumnya dapat dikembalikan, tetapi rollback database harus mengikuti migrasi dan backup yang sesuai.

```bash
sudo journalctl -u amiga -n 80 --no-pager
sudo systemctl restart amiga
```

URL demo HTTP dapat dilaporkan sebagai halaman hidup setelah pemeriksaan di atas. Jangan menyebut siap produksi atau seluruh alur lulus: HTTPS, login akun dan unggah sampai voucher belum diverifikasi. Form pelaporan pada PDF belum diisi otomatis.

Rujukan: [Flask/Gunicorn](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/), [kredensial Boto3 melalui instance role](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html), [kemampuan Nova Lite dan Micro](https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html).
