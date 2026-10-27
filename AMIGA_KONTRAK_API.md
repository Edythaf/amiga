# Kontrak portal Klien, Reviewer dan Admin AMIGA — v0.5

Tanggal: 15 Oktober 2026. Status: diimplementasikan Codex di workspace tetap dan diuji lokal; AWS Nova PDF teks/scan fiktif sudah diverifikasi; Google/PostgreSQL nyata belum diverifikasi. Pengguna menyerahkan pekerjaan backend Argon kepada Codex. Jika kode lama tidak mendukung suatu field/aksi, laporkan gap dan tambahkan secara eksplisit; jangan mengembalikan nilai palsu.

## Konvensi

- Satu origin: Flask menyajikan `/login`, `/admin`, `/reviewer`, `/client`, `/pending` dan aset `/portal/*` dari `frontend/portal/`. Gunakan base URL `/portal/` di HTML supaya aset tetap benar pada seluruh route.
- API prefix `/api`; cookie session memakai `credentials: same-origin`. JSON envelope sukses `{ "data": ... }`; gagal `{ "error": { "code": "...", "message": "...", "fields": {} } }`.
- GET `/api/auth/csrf` memberi `{data:{csrf_token:"...",auth_method:"local_password",auth_configured:true,google_client_id:""}}`. Seluruh POST/PATCH termasuk login/daftar memakai header `X-CSRF-Token`. Google hanya opsional saat AUTH_METHOD=google.
- 401: sesi tidak ada/expired. 403: tidak berwenang/pending/disabled/CSRF. 404: objek tidak ditemukan. 409: versi berubah/konflik state. 422: validasi input. 503: konfigurasi/dependency belum tersedia. Endpoint API tidak redirect ke HTML login.
- ID berupa string opaque; timestamp ISO-8601 UTC. Email/rekening berupa string. Nominal berupa string decimal; jangan memakai float untuk uang. Tenant ditentukan/diperiksa backend.
- Client tidak mengirim role sebagai sumber kewenangan. Seluruh endpoint data, termasuk route HTML lama dan akses PDF/S3, melewati guard actor/tenant.

## Session dan akun

| Method / path | Input | Output data |
|---|---|---|
| GET `/api/auth/csrf` | — | csrf_token, auth_method, google_client_id, auth_configured |
| POST `/api/auth/register` | email_input, password, display_name opsional | UserSession pending, 201 |
| POST `/api/auth/owner-setup` | setup_token dari launcher + CSRF | email_input pemilik + /admin; capability cookie HttpOnly |
| POST `/api/auth/login` | email_input (boleh `/admin` atau `/review`), password | UserSession |
| POST `/api/auth/google` | credential, email_input (boleh `/admin`); AUTH_METHOD=google saja | UserSession |
| GET `/api/auth/me` | cookie sesi | UserSession |
| POST `/api/auth/logout` | CSRF | `{logged_out:true}` |

UserSession:

```json
{
  "user": {
    "id": "usr_opaque",
    "email": "contoh@gmail.com",
    "display_name": "Nama Pengguna",
    "roles": ["SYSTEM_ADMIN"],
    "account_status": "ACTIVE",
    "clients": [{"id": "cli_opaque", "name": "Klien Demo"}]
  },
  "portal": "admin",
  "csrf_token": "opaque_csrf",
  "expires_at": "2026-10-15T12:00:00Z"
}
```

portal: `admin` (System Admin/Service Lead), `reviewer` (Finance Reviewer), `client`, atau `pending`. Account status: ACTIVE/PENDING_ADMIN/PENDING_REVIEWER/PENDING_CLIENT/DISABLED. Akun pending hanya boleh membaca status dirinya dan logout; dokumen tidak dapat diakses. Google sub disimpan server dan tidak perlu dikirim ke frontend. Email contoh adalah ilustrasi, bukan bootstrap admin sebenarnya.

Suffix `/admin` dibuang sebelum menyimpan email; berfungsi sebagai permintaan aktivasi, bukan bukti otorisasi. FIRST ADMIN memerlukan provisioning/allowlist server. Admin terdaftar tidak perlu suffix pada login berikutnya. Kebijakan masa sesi configurable dan terdokumentasi, tidak login abadi.

Default lokal: password bcrypt cost 12, minimal 10 karakter dan maksimal 72 byte UTF-8. JWT HS256 dengan sub/iat/exp/jti/iss/aud berada dalam cookie HttpOnly (SameSite Lax, Secure pada produksi); frontend tidak menyimpan token/password di localStorage dan tidak perlu mengirim Bearer header. AuthSession menyimpan hash token untuk pencabutan segera pada logout/perubahan akses. Role dan tenant dibaca server pada setiap request, tidak dipercaya dari token atau formulir. Lima password salah mengunci akun 15 menit (429 LOGIN_LOCKED); pesan password salah generik 401 INVALID_CREDENTIALS.

Pendaftaran biasa membuat CLIENT_OWNER aktif pada tenant baru yang privat; tidak pernah memberi akses ke tenant existing atau peran internal. /review membuat PENDING_REVIEWER tanpa role dan /admin membuat PENDING_ADMIN tanpa role. DTO user menyertakan requested_role (FINANCE_REVIEWER/SYSTEM_ADMIN/null) agar pengelola melihat permintaan. Launcher lokal membuat capability acak sekali pakai (30 menit) untuk pemilik allowlist dan membuka /login#owner-setup=KODE. Frontend menghapus fragmen dari address bar dan memverifikasi lewat POST owner-setup. Capability tersimpan pada cookie HttpOnly bertanda tangan; GET csrf hanya memberi owner_setup_email_input ketika capability masih sah, tanpa mengembalikan kodenya. Pemilik membuat password sendiri pada formulir daftar. POST register dengan email pemilik/admin dan capability sah membuat kredensial dan SYSTEM_ADMIN, lalu menghabiskan capability/setting bootstrap secara atomik. Payload setup_token juga dapat diterima untuk registrasi pertama, tetapi frontend default memakai cookie setelah verifikasi.

Pendaftaran email pemilik tanpa capability ditolak OWNER_SETUP_REQUIRED. Capability salah, expired, email lain, tanpa /admin atau dipakai ulang ditolak; validasi password gagal tidak menghabiskannya. Tidak ada verifikasi kepemilikan Gmail/email atau pengiriman OTP. Pendaftaran publik tidak dapat memasang password pada akun existing. CLI setup-admin dengan input tersembunyi tetap tersedia sebagai jalur operator alternatif. Tidak ada password yang dibuat oleh admin untuk pengguna lain.

## Request dan dokumen

| Method / path | Input | Output data |
|---|---|---|
| GET `/api/requests` | optional search, status, client_id, pic_id, scope=mine, deadline (sampai), issues=1 | `{items:[RequestSummary], page, page_size, total}`; pagination wajib jelas |
| POST `/api/requests` | multipart client_id, request_type, channel, request_date, deadline, invoice_file, evidence_files[] | RequestDetail; proses async dapat berstatus QUEUED |
| GET `/api/requests/<id>` | — | RequestDetail |
| GET `/api/requests/<id>/documents/<document_id>` | — | Bytes PDF/image dengan Content-Type benar; selalu periksa ownership |
| POST `/api/requests/<id>/evidence` | multipart evidence_file, description | Document |
| POST `/api/requests/<id>/process` | mode REVALIDATE/REEXTRACT, invoice_id jika relevan, expected_version, reason; force optional reviewer | RequestDetail atau job yang dapat dipoll |
| GET `/api/requests/<id>/audit` | pagination optional | `{items:[AuditEvent], total}` |

RequestSummary minimal:

```json
{
  "id":"req_opaque", "client_id":"cli_opaque", "client_name":"Klien Demo",
  "uploaded_by":"usr_opaque", "pic_id":"usr_reviewer",
  "status":"READY_FOR_REVIEW", "request_date":"2026-10-15", "deadline":"2026-10-20",
  "channel":"Portal", "updated_at":"2026-10-15T05:00:00Z",
  "invoice_count":1, "vendor_names":["Vendor Demo"], "invoice_numbers":["INV-001"],
  "totals_by_currency":[{"currency":"IDR","amount":"650000.00"}],
  "issues":[{"code":"MISSING_EVIDENCE","severity":"BLOCK","resolved":false}]
}
```

Jangan menjumlahkan currency berbeda menjadi satu nilai tanpa kurs yang disepakati. pic_id dapat null jika belum ditugaskan. List hanya metadata yang diperlukan, bukan token/konfigurasi/internal storage path/rekening lengkap.

RequestDetail menambahkan:

- documents: array `{id,type,original_filename,mime_type,page_count,uploaded_by,uploaded_at,download_url}`. type INVOICE/EVIDENCE; URL dikontrol otorisasi.
- invoices: array InvoiceDetail; dokumen multi-invoice tetap lengkap dan frontend dapat memilih invoice.
- allowed_actions: array aksi yang dihitung backend untuk membantu UI, **bukan pengganti guard server**.
- processing: `{status,stage,stage_step,stage_total,error_code?,error_message?}`.

Request status canonical untuk UI: QUEUED, PROCESSING, READY_FOR_REVIEW, EXCEPTION, AMIGA_REVIEWED, SENT_TO_CLIENT. APPROVED legacy dipetakan ke AMIGA_REVIEWED setelah semua invoice terkait direview; NEEDS_REVIEW legacy dipetakan EXCEPTION. Argon mendokumentasikan mapping/error teknis; jangan mengubah status pembayaran menjadi PAID.

## Invoice, review dan voucher

| Method / path | Input | Output data |
|---|---|---|
| PATCH `/api/requests/<id>/invoices/<invoice_id>` | expected_version, fields InvoiceDraft, field_sources, reason | InvoiceDetail dengan version baru; validasi ulang tanpa ekstraksi |
| POST `/api/requests/<id>/invoices/<invoice_id>/validate` | expected_version | InvoiceDetail |
| POST `/api/requests/<id>/invoices/<invoice_id>/resolve` | expected_version, issue_code, reason | InvoiceDetail; hanya issue yang boleh di-resolve |
| POST `/api/requests/<id>/invoices/<invoice_id>/approve` | expected_version | Review record; hanya Finance Reviewer independen |
| POST `/api/requests/<id>/invoices/<invoice_id>/reject` | expected_version, reason | Review record dan status baru |
| GET `/api/requests/<id>/invoices/<invoice_id>/voucher/preview.pdf` | version optional | PDF draft berwatermark atau approved PDF; belum mencatat handover |
| POST `/api/requests/<id>/invoices/<invoice_id>/voucher/download` | expected_version, CSRF | PDF resmi, X-Voucher-ID, X-Handover-Recorded true/false; hanya unduhan Klien/Backup pada tenantnya mencatat handover. Unduhan internal tidak mengubah status penyerahan. |

InvoiceDetail: `{id,index,current_version,fields:InvoiceDraft,field_sources,validation,review_status,reviewer_id?,reviewed_at?,allowed_actions}`. Review status PENDING/APPROVED/REJECTED terpisah dari request status. Dengan multi-invoice, request baru SENT_TO_CLIENT setelah seluruh voucher invoice aktif telah dihandover; handover per invoice tetap tercatat.

InvoiceDraft target:

```json
{
  "vendor_name":"Vendor Demo", "invoice_number":"INV-001", "invoice_date":"2026-10-15",
  "due_date":null, "currency":"IDR",
  "line_items":[{"description":"Barang", "quantity":"1", "unit_price":"1000.00", "discount_amount":"0.00", "tax_amount":"0.00", "line_total":"1000.00"}],
  "subtotal":"1000.00", "invoice_discount_amount":"0.00", "invoice_tax_amount":"0.00", "total_amount":"1000.00",
  "bank_name":null, "account_number":null, "account_holder":null
}
```

Nilai unknown adalah null. Mapping `supplier_name`/`total`/`tax` legacy ke schema ini eksplisit. Jangan menambah pajak dua kali ketika tax_amount legacy sudah mencakup pajak item. Jika suatu nominal discount/tax memang tidak diketahui, jangan mengisinya 0 tanpa aturan bisnis.

Validation: `{valid,version,executed_at,tolerance,currency,calculated:{subtotal,total,delta},issues:[{code,severity,message,field?,resolved,resolution?}]}`. Semua kalkulasi server decimal. Toleransi per currency/config; IDR demo Rp1 masih asumsi. Revisi akun/sumber rekening perlu bukti; revalidate tidak menjalankan ekstraksi.

FieldSource: map field/path → `{document_id,page?,source_type,notes?}`. source_type EXTRACTED/MANUAL/EVIDENCE. AuditEvent: `{id,request_id,invoice_id?,actor_id,actor_name,action,at,reason?,changes:[{field,before,after}]}`.

## Pengelolaan internal

| Method / path | Akses | Fungsi |
|---|---|---|
| GET `/api/admin/users` | SYSTEM_ADMIN | Akun dan status/role |
| PATCH `/api/admin/users/<id>` | SYSTEM_ADMIN | Aktivasi, penetapan role dan assignment klien dengan audit; larangan self-escalation |
| GET `/api/admin/clients` | SYSTEM_ADMIN / scoped internal sesuai policy | Master klien |
| POST `/api/admin/clients` | SYSTEM_ADMIN | Membuat klien |
| PATCH `/api/requests/<id>/assignment` | SYSTEM_ADMIN / SERVICE_LEAD | pic_id reviewer aktif, independen; tidak memerlukan assignment klien. Review selesai tidak dialokasikan ulang. |

## Integrasi bertahap

Prioritas 1: auth/me/logout, provisioning aman, tenant migration, guard semua route lama, request list/detail/original. Prioritas 2: upload/process/review/version/voucher/audit API. Prioritas 3: pengelolaan akun/assignment lengkap. Laporkan endpoint yang belum tersedia; frontend tidak menggantinya diam-diam dengan data simulasi ketika mode live dipilih.

Mode demo lama tetap boleh berdiri terpisah dengan penanda yang jelas. Produksi tidak boleh menerima selector user demo, email-only login, ID token tanpa verifikasi, atau suffix `/admin` sebagai satu-satunya sumber kewenangan.

## Tambahan implementasi Codex (15 Oktober 2026)

- PATCH invoice menerima `item_count_confirmed` boolean; respons `expected_item_count` null sampai seluruh item dikonfirmasi manusia. Konfirmasi disimpan per versi.
- REEXTRACT dengan beberapa invoice wajib mengirim `expected_versions: {invoice_id: version}` untuk seluruh invoice aktif. Invoice tunggal juga boleh memakai `expected_version`. Tidak ada cache ekstraksi lintas tenant. Semua percobaan/generasi disimpan, termasuk output terstruktur yang gagal normalisasi.
- GET `/api/requests/<id>/reviewers` khusus Admin/Service Lead memberi kandidat reviewer aktif dan independen. PATCH assignment menegakkan aturan yang sama. Reviewer harus mengambil/ditugaskan request sebelum membaca detail atau mereview; membership klien saja tidak memberikan akses reviewer ke dokumen.
- Finance Reviewer juga dapat mengunggah invoice, tetapi tidak dapat menyetujui request yang ia unggah atau beri bukti.
- Rejection bersifat final untuk versi tersebut; simpan revisi baru sebelum approval berikutnya.
- Preview versi historis mempertahankan PDF snapshot; unduhan/handover resmi hanya untuk versi aktif yang disetujui. Revisi tidak menghapus voucher atau audit lama.
- Semua endpoint tabel kontrak tersedia. Audit global untuk pengelolaan akun disimpan di database; API audit pada kontrak hanya menampilkan per request.
- Pagination list dilakukan setelah penghitungan status/validasi sesuai tenant. Untuk volume besar, tambahkan query/agregat/index terukur sebelum produksi; implementasi saat ini ditujukan pengembangan lokal.
- SQLite pengembangan dan PostgreSQL memakai tabel `amiga_*`. Tidak ada impor otomatis data legacy tanpa pemilik. Server biasa tidak menjalankan CREATE TABLE pada PostgreSQL; gunakan migrasi/init-db eksplisit.
- Batas upload awal PDF 10 MB/5 halaman, maksimal 10 bukti, request 32 MB. Image upload legacy tidak tersedia pada API baru.

## Provider ekstraksi sementara

AI_PROVIDER=openai memakai OPENAI_MODEL=gpt-6-luna dengan kunci server dari OPENAI_API_KEY_FILE/OPENAI_API_KEY/GPT_LUNA_API. PDF input_file, schema strict, store=false, endpoint tetap OpenAI Responses API, tanpa redirect/retry/fallback provider. Raw model_response/ocr_text/provider/model/usage disimpan bersama extraction immutable; kontrak fields invoice dan validasi Decimal tidak berubah. Error provider disanitasi menjadi OPENAI_AUTH_FAILED, OPENAI_ACCESS_DENIED, OPENAI_MODEL_UNAVAILABLE, OPENAI_QUOTA_LIMIT atau OPENAI_UNAVAILABLE; output terpotong/refusal/invalid tidak menjadi hasil parsial. Bedrock tetap dapat dipilih eksplisit. Uji satu PDF fiktif melalui API Luna nyata sudah berhasil.

## Papan tugas bersama dan analisis reviewer (v0.3)

Perubahan kebijakan disetujui pengguna 15 Oktober 2026: /review tetap menunggu persetujuan admin satu kali, lalu reviewer bebas mengambil tugas lintas klien tanpa membership. Privasi antar-klien tetap berlaku pada akun Klien/Backup. Admin/Service Lead dapat memantau seluruh request. Daftar tugas terbuka hanya berisi ringkasan tanpa rekening, lampiran, atau data ekstraksi lengkap. Nama PIC tersedia sebagai pic_name pada RequestSummary.

| Method / path | Akses / input | Hasil |
|---|---|---|
| GET /api/tasks?scope=available | reviewer aktif / pengelola | Ringkasan tugas belum diambil, belum selesai, dan bukan kontribusi peminta. items, total. |
| GET /api/tasks?scope=all | Admin/Service Lead | Semua tugas, termasuk pemilik dan status selesai. |
| POST /api/tasks/<id>/claim | reviewer aktif independen, CSRF | Mengisi pic_id secara atomik. Dua klaim bersamaan hanya satu berhasil; lainnya 409 TASK_UNAVAILABLE. |
| GET /api/requests?scope=mine | reviewer | Request yang sedang/pernah diambil reviewer tersebut; pagination normal. |
| POST /api/tasks/<id>/release | pemilik tugas / pengelola, reason | Tugas belum selesai kembali ke antrean; reviewer lama kehilangan akses detail/PDF. |
| GET /api/requests/<id>/invoices/<invoice_id>/analysis | pembaca detail berwenang | result: analisis terakhir versi aktif atau null, stale bila bukti/validasi berubah. Tidak memanggil provider. |
| POST /api/requests/<id>/invoices/<invoice_id>/analysis | reviewer pemilik independen, expected_version, question opsional <=1000 karakter | Analisis advisory terstruktur, model, version, actor_name, created_at, cached, stale, included_documents, omitted_documents. |

Aktivasi reviewer: PATCH admin/users dengan roles:[FINANCE_REVIEWER], account_status:ACTIVE, client_ids:[] diterima. Menonaktifkan akun/menghapus role reviewer mencabut semua AuthSession dan melepas PIC tugas yang belum selesai, dengan audit TASK_RELEASED_BY_ADMIN. Voucher dan pemilik tugas selesai dipertahankan. Jika klien merevisi tugas selesai yang PIC-nya sudah tidak aktif, tugas kembali ke antrean dengan TASK_RELEASED_AFTER_REVISION.

Analisis: OpenAI Responses API memakai model Luna dari konfigurasi server, store=false dan strict JSON Schema. Maksimal lima PDF atau 15 MB; daftar berkas terlewat dikembalikan. Database lock dilepas selama panggilan model; sesi, PIC, versi dan fingerprint data/bukti diperiksa lagi sebelum menyimpan hasil. Input identik menggunakan hasil tersimpan; analisis baru dibatasi 20 detik per reviewer setelah hasil sukses. Tidak ada retry/provider fallback otomatis. Provider gagal: 502 ANALYSIS_UNAVAILABLE tanpa mengubah invoice. Draft/bukti berubah: 409; akses dicabut: 401/403/404 sesuai kondisi. Hasil dicatat sebagai event REVIEW_AI_ANALYSIS pada tabel audit yang sudah ada, tanpa migrasi skema baru.

Analisis tidak mengedit draft, menyelesaikan flag, atau approve. Revisi harus disimpan lewat PATCH invoice dan approval tetap endpoint reviewer. MISSING_EVIDENCE muncul bila nomor rekening/sumbernya kurang; invoice lengkap tidak selalu memerlukan PDF bukti terpisah. Perubahan rekening tetap wajib memakai sumber EVIDENCE.

GET health dan auth/csrf menyertakan review_workflow:task_pool_v1. Mode preview lama tetap berlabel simulasi dan tidak menyamar sebagai API/analisis nyata.


## v0.4 — lifecycle layanan dan workspace voucher (15 Oktober 2026)

Skema database v3 menambah `amiga_request_lifecycle` (migrasi 003). Request lama tanpa row berarti OPEN pada revision 0. Status BRD `QUEUED/PROCESSING/EXCEPTION/READY_FOR_REVIEW/AMIGA_REVIEWED/SENT_TO_CLIENT` dipertahankan.

Ringkasan/detail request kini menambah:
- `lifecycle: {state: OPEN|CLOSED, revision: integer, updated_at, actor_id}`.
- `work_status`: PROCESSING, UNCLAIMED, IN_REVIEW, WAITING_CLIENT (review ditolak), VOUCHER_READY, AWAITING_CLIENT_CLOSE, CLOSED.
- `voucher_count`: jumlah invoice aktif yang versinya disetujui.
- Detail juga berisi `client_revision_note` dan allowed_actions CLOSE/REQUEST_REVISION hanya untuk Klien/Backup tenant terkait, bukan System Admin.

GET `/api/requests` menerima filter `lifecycle=OPEN|CLOSED` dan `has_voucher=1` sebelum pagination. Voucher parsial dalam request multi-invoice tetap dapat ditemukan. `scope=mine` dipakai menu Voucher reviewer.

POST `/api/requests/{id}/lifecycle` memerlukan CSRF dan payload:
```json
{"action":"CLOSE","reason":"Klien menerima hasil layanan administrasi.","expected_lifecycle_revision":0,"expected_versions":{"invoice_id":2}}
```

- CLOSE: hanya Klien/Backup terkait, seluruh invoice aktif sudah disetujui dan setiap voucher versi terbaru memiliki unduhan klien. State menjadi CLOSED; ini bukan otorisasi pembayaran.
- REQUEST_REVISION: hanya klien terkait pada request seluruh voucher sudah terbit atau CLOSED, alasan 3–2000 karakter. State menjadi OPEN, seluruh invoice mendapat versi baru dengan konfirmasi item kosong, tanpa review/resolusi lama. Reviewer aktif dipertahankan; PIC nonaktif dilepas. PDF, review, handover dan audit lama tidak ditimpa.
- Parent request dikunci; revision lifecycle dan peta versi seluruh invoice harus sama. Tab lama atau klik bersamaan ditolak 409 STALE_VERSION; versi hilang/salah tipe 422 VERSION_REQUIRED. Transisi di luar aturan 409 LIFECYCLE_BLOCKED; peran salah 403 CLIENT_REQUIRED; tenant lain 404.
- CLOSED memblokir edit/validasi/keputusan/resolusi/analisis baru, lampiran, re-extraction, klaim, release dan assignment. Pembacaan, audit, preview dan unduhan resmi tetap tersedia. Setiap transisi tercatat sebagai REQUEST_CLOSED atau CLIENT_REVISION_REQUESTED, serta INVOICE_REVISED untuk setiap revisi.
- UI memakai allowed_actions untuk menampilkan kontrol; server selalu memvalidasi ulang otorisasi, state dan versi. Endpoint approve lama tetap sumber tunggal penerbitan resmi dari detail review maupun workspace voucher.


## v0.5 — backend ZIP utama, 16 Oktober 2026

- Entry point backend.app:create_app dan controller backend/modules/{auth,admin,upload}/routes.py menjadi utama. Kontrak /api dan otorisasi portal tetap dipakai; tidak ada login session-only atau antrean tanpa scope kedua. /health menambah backend_source=amiga-20261015T221710Z-1-001.
- POST /api/requests pada invoice_file menerima PDF/JPG/JPEG/PNG/WEBP. Batas 10 MB, PDF 1–5 halaman, foto 20 megapiksel. Server memakai inspector source ZIP, menyiapkan PDF dan menyimpan foto asli privat. Format gambar palsu/mismatch ditolak 422 INVALID_DOCUMENT, kegagalan storage 503 STORAGE_UNAVAILABLE. Bukti tetap PDF.
- documents[].type dapat SOURCE_IMAGE, mime_type image/jpeg|png|webp, selain INVOICE/EVIDENCE. Dokumen foto dan PDF mempunyai id/hash masing-masing, akses tenant dan kontribusi uploader tetap berlaku. IMAGE_CONVERTED_TO_PDF dicatat pada audit. Sumber rekening hasil ekstraksi menunjuk PDF, sedangkan foto asli tersedia sebagai referensi.
- Pemanggilan analisis memakai PDF konversi dan bukti; foto asli tidak dikirim ulang dengan nama PDF. Ekstraksi Bedrock memetakan supplier_* ke field portal dan mempertahankan raw source. Provider eksplisit, tidak ada fallback otomatis.
- Voucher resmi/draft memakai backend/voucher_service.py dari ZIP yang diadaptasi ke snapshot versi portal. Nomor/versi, seluruh baris, harga, diskon, pajak, rekening dan disclaimer tetap ada; snapshot resmi lama tidak dibuat ulang setelah perubahan renderer.
- Tidak ada perubahan skema DB baru. Data native PostgreSQL/arsip ZIP bukan tenant portal sampai pemetaan resmi dilakukan. Metadata controller native disatukan ke shared schema, bukan disalin melalui dual-write ke invoice_records.

Penanda reviewer `/view` adalah alias `/review`, tanpa membedakan huruf besar/kecil. Keduanya meminta FINANCE_REVIEWER dan memakai akun email dasar yang sama. Form pendaftaran tidak memiliki pemilih jenis akun; email_input yang diketik diteruskan utuh ke backend.

Pembaruan 16 Oktober 2026: ekstraksi Bedrock Nova aktif; hitungan browser/server disamakan, JSON parsial ditolak, dan PDF teks/scan fiktif diuji pada AWS nyata. Lihat [PERBAIKAN_EKSTRAKSI_INVOICE.md](PERBAIKAN_EKSTRAKSI_INVOICE.md) untuk status terbaru; angka verifikasi pada bagian integrasi awal di atas merupakan catatan saat tahap tersebut.

## Workflow v4 — menggantikan alur antrean langsung setelah ekstraksi

Kontrak endpoint dan aturan baru lengkap pada [API_TERBARU.md](API_TERBARU.md). Ekstraksi AWS Nova tetap utama. Worker menyiapkan analisis awal Luna, kemudian uploader mengonfirmasi versi/fingerprint/seluruh item. Claim, assignment dan approval menunggu seluruh konfirmasi aktif. Revisi data/bukti membatalkan konfirmasi. Tiga asisten Luna, penggantian dokumen sumber pada Request ID tetap, arsip voucher, dan Telegram dengan pratinjau/persetujuan ditambahkan melalui tujuh tabel additive pada migrasi 004. Kontrak v1–v3 tetap berlaku kecuali aturan antrean dan syarat konfirmasi yang diperketat di atas.
