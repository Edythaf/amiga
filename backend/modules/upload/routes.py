"""ZIP primary controller, adapted to the existing portal API and revocable access.

The native HTML/session/SQL controller is rebased onto the shared integration
schema so there is one login, one policy, one set of immutable invoice versions.
"""
from ...api_common import (
    Audit, BytesIO, CLIENT_ROLES, Document, HEADER_FIELDS, Handover,
    InvalidDraft, InvoiceVersion, Path, RESOLVABLE, RequestLifecycle, Resolution,
    User, Voucher, WorkRequest, analysis_context, analysis_fingerprint, api,
    audit, authenticate, body, client_ids, current_app, date,
    datetime, decide, document_dto, editable, fail, fields_for,
    g, independent, invoice_dto, invoices, latest_review, lifecycle,
    mutation_invoice, normalize, now, ok, previous_analysis, read_upload,
    reason, release_inactive_pic, render_voucher, request, request_access, request_dto, reviewer,
    require_open, require_review, require_role, require_task_staff, roles, save_upload,
    scoped_invoice, scoped_request, select, send_file, sources_for, task_complete,
    timedelta, timezone, uid, update, validation_for, write_version
)
from ...workflow import ready_for_review,invalidate_assistance,source_document,input_hash,assistance_dto,confirmation_dto
from ...models import UploaderConfirmation,InvoiceAssistance,RequestSource,Invoice


@api.get('/requests')
def list_requests():
    try:
        page, size = int(request.args.get('page', 1)), int(request.args.get('page_size', 50))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        fail(422, 'PAGINATION', 'page >= 1 dan page_size antara 1–100.')
    query = select(WorkRequest).where(request_access())
    if request.args.get('scope') == 'mine':
        query = query.where(WorkRequest.pic_id == g.actor.id)
    for key in ('client_id', 'pic_id'):
        if request.args.get(key):
            query = query.where(getattr(WorkRequest, key) == request.args[key])
    rows = [request_dto(req) for req in g.db.scalars(query.order_by(WorkRequest.updated_at.desc(), WorkRequest.id))]
    search = request.args.get('search', '').strip().casefold()
    statuses = set(filter(None, request.args.get('status', '').split(',')))
    if search:
        rows = [r for r in rows if search in ' '.join([r['id'], r.get('request_code',''), r['client_name']] + r['vendor_names'] + r['invoice_numbers']).casefold()]
    if statuses:
        rows = [r for r in rows if r['status'] in statuses]
    if request.args.get('lifecycle'):
        rows = [r for r in rows if r['lifecycle']['state'] == request.args['lifecycle']]
    if request.args.get('has_voucher') == '1':
        rows = [r for r in rows if r['voucher_count'] > 0]
    if request.args.get('deadline'):
        rows = [r for r in rows if r['deadline'] <= request.args['deadline']]
    if request.args.get('issues') == '1':
        rows = [r for r in rows if any(not i['resolved'] for i in r['issues'])]
    return ok({'items': rows[(page - 1) * size:page * size], 'page': page, 'page_size': size, 'total': len(rows)})



@api.get('/tasks')
def task_board():
    require_task_staff()
    monitor = request.args.get('scope') == 'all'
    if monitor and not roles(g.db, g.actor) & {'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        fail(403, 'FORBIDDEN', 'Pemantauan seluruh penugasan hanya untuk pengelola.')
    query = select(WorkRequest)
    if not monitor:
        query = query.where(WorkRequest.pic_id.is_(None), WorkRequest.uploaded_by != g.actor.id,
            ~select(Document.id).where(Document.request_id == WorkRequest.id, Document.uploaded_by == g.actor.id).exists())
    # The board exposes summaries. PDF, bank details, edits and AI remain protected by request_access.
    rows = [request_dto(req) for req in g.db.scalars(query.order_by(WorkRequest.deadline, WorkRequest.id))
            if monitor or (lifecycle(g.db, req)['state'] == 'OPEN' and not task_complete(req) and ready_for_review(g.db,req))]
    return ok({'items': rows, 'total': len(rows)})



@api.post('/tasks/<request_id>/claim')
def claim_task(request_id):
    g.db.refresh(g.actor, with_for_update=True)
    if g.actor.account_status != 'ACTIVE':
        fail(403, 'ACCOUNT_INACTIVE', 'Reviewer tidak aktif.')
    require_role('FINANCE_REVIEWER')
    if 'SYSTEM_ADMIN' in roles(g.db, g.actor):
        fail(403, 'FORBIDDEN', 'Admin memantau tugas dan tidak mengambil review.')
    req = g.db.scalar(select(WorkRequest).where(WorkRequest.id == request_id).with_for_update())
    if not req or req.pic_id is not None:
        fail(409, 'TASK_UNAVAILABLE', 'Tugas sudah diambil reviewer lain. Muat ulang papan tugas.')
    require_open(g.db, req)
    if not independent(req):
        fail(403, 'INDEPENDENT_REVIEWER_REQUIRED', 'Pengunggah dokumen tidak boleh mengambil review sendiri.')
    if task_complete(req):
        fail(409, 'TASK_COMPLETED', 'Review tugas ini sudah selesai.')
    if not ready_for_review(g.db,req):
        fail(409,'UPLOADER_CONFIRMATION_REQUIRED','Tugas belum dikonfirmasi uploader setelah analisis awal.')
    result = g.db.execute(update(WorkRequest).where(WorkRequest.id == req.id, WorkRequest.pic_id.is_(None))
                          .values(pic_id=g.actor.id, updated_at=now()))
    if result.rowcount != 1:
        fail(409, 'TASK_UNAVAILABLE', 'Tugas sudah diambil reviewer lain.')
    g.db.refresh(req)
    audit(g.db, 'TASK_CLAIMED', g.actor.id, req.id,
          changes=[{'field': 'pic_id', 'before': None, 'after': g.actor.id}])
    return ok(request_dto(req, True))



@api.post('/tasks/<request_id>/release')
def release_task(request_id):
    req = scoped_request(request_id, True)
    require_open(g.db, req)
    if req.pic_id != g.actor.id and not roles(g.db, g.actor) & {'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        fail(403, 'FORBIDDEN', 'Hanya pemilik tugas atau pengelola yang dapat mengembalikan tugas.')
    if not req.pic_id or task_complete(req):
        fail(409, 'TASK_COMPLETED', 'Tugas tidak sedang dikerjakan atau review sudah selesai.')
    before = req.pic_id
    req.pic_id, req.updated_at = None, now()
    audit(g.db, 'TASK_RELEASED', g.actor.id, req.id, reason=reason(body()),
          changes=[{'field': 'pic_id', 'before': before, 'after': None}])
    return ok({'id': req.id, 'released': True})



@api.get('/requests/<request_id>/invoices/<invoice_id>/analysis')
def get_review_analysis(request_id, invoice_id):
    req = scoped_request(request_id)
    inv = scoped_invoice(req, invoice_id)
    record = previous_analysis(inv)
    if record:
        record = {**record, 'stale': record['fingerprint'] != analysis_fingerprint(analysis_context(req, inv, record['question']))}
    return ok({'result': record})



@api.post('/requests/<request_id>/invoices/<invoice_id>/analysis')
def review_analysis(request_id, invoice_id):
    data = body()
    req, inv = mutation_invoice(request_id, invoice_id, data)
    require_review(req)
    question = data.get('question', '')
    if not isinstance(question, str) or len(question) > 1000:
        fail(422, 'INVALID_QUESTION', 'Pertanyaan analisis maksimal 1000 karakter.')
    question = question.strip()
    context = analysis_context(req, inv, question)
    fingerprint = analysis_fingerprint(context)
    cached = previous_analysis(inv, fingerprint)
    if cached:
        return ok({**cached, 'cached': True, 'stale': False})
    recent = g.db.scalar(select(Audit.at).where(Audit.actor_id == g.actor.id, Audit.action == 'REVIEW_AI_ANALYSIS')
                         .order_by(Audit.at.desc()).limit(1))
    if recent and datetime.fromisoformat(recent.replace('Z', '+00:00')) > datetime.now(timezone.utc) - timedelta(seconds=20):
        fail(429, 'ANALYSIS_RATE_LIMIT', 'Tunggu 20 detik sebelum meminta analisis baru. Hasil terakhir tetap tersimpan.')
    source = source_document(g.db,req)
    docs = ([source] if source else []) + list(g.db.scalars(select(Document).where(Document.request_id == req.id,Document.type == 'EVIDENCE').order_by(Document.uploaded_at.desc())))
    attachments, total = [], 0
    context['included_documents'], context['omitted_documents'] = [], []
    for doc in docs:
        if doc.type == 'SOURCE_IMAGE':
            continue  # Its normalized PDF is already included; do not mislabel an image as PDF.
        path = Path(current_app.config['UPLOAD_DIR']) / doc.storage_key
        if path.stat().st_size + total > 15 * 1024 * 1024 or len(attachments) >= 5:
            context['omitted_documents'].append(doc.id)
            continue
        value = path.read_bytes()
        total += len(value)
        name = f'{doc.type.lower()}-{len(attachments) + 1}.pdf'
        attachments.append((name, value))
        context['included_documents'].append({'id': doc.id, 'file': name})
    # Release the database write lock while waiting for the external API.
    g.db.commit()
    try:
        from ...review_analysis import analyze, validate_analysis
        analyzer = current_app.config.get('REVIEW_ANALYZER') if current_app.testing else None
        result = (analyzer or analyze)(context, attachments, current_app.config)
        validate_analysis(result['analysis'])
    except (RuntimeError, KeyError, TypeError, ValueError):
        fail(502, 'ANALYSIS_UNAVAILABLE', 'Analisis AI belum berhasil. Data dan keputusan review belum berubah. Periksa konfigurasi atau coba kembali.')
    if current_app.extensions['amiga_engine'].dialect.name == 'sqlite':
        from sqlalchemy import text
        g.db.execute(text('BEGIN IMMEDIATE'))
    g.db.expire_all()
    authenticate()  # Admin may have disabled the reviewer while the API was running.
    if g.actor.account_status != 'ACTIVE':
        fail(403, 'ACCOUNT_INACTIVE', 'Akses reviewer sudah dihentikan.')
    req, inv = mutation_invoice(request_id, invoice_id, data)
    require_review(req)
    if fingerprint != analysis_fingerprint(analysis_context(req, inv, question)):
        fail(409, 'ANALYSIS_CONTEXT_CHANGED', 'Data atau bukti berubah saat AI menganalisis. Muat ulang dan analisis versi terbaru.')
    record = {'id': uid('analysis'), 'version': inv.current_version, 'fingerprint': fingerprint,
              'question': question, 'created_at': now(), 'actor_name': g.actor.display_name,
              'model': result.get('model', current_app.config['OPENAI_MODEL']), 'analysis': result['analysis'],
              'included_documents': context['included_documents'], 'omitted_documents': context['omitted_documents']}
    audit(g.db, 'REVIEW_AI_ANALYSIS', g.actor.id, req.id, inv.id,
          reason='Analisis pendamping; tidak mengubah data atau memberi persetujuan',
          changes=[{'field': 'ai_analysis', 'before': None, 'after': record}])
    return ok({**record, 'cached': False, 'stale': False})



def upload_metadata():
    if not roles(g.db, g.actor) & (CLIENT_ROLES | {'FINANCE_REVIEWER'}) or 'SYSTEM_ADMIN' in roles(g.db, g.actor):
        fail(403, 'FORBIDDEN', 'Akun tidak berwenang mengunggah invoice.')
    values = {key: request.form.get(key, '').strip() for key in ('client_id', 'request_type', 'channel', 'request_date', 'deadline')}
    if values['client_id'] not in client_ids(g.db, g.actor):
        fail(403, 'TENANT_FORBIDDEN', 'Klien tidak ditugaskan ke akun ini.')
    if any(not v or len(v) > 200 for v in values.values()):
        fail(422, 'METADATA_REQUIRED', 'Lengkapi metadata request.')
    try:
        if any(date.fromisoformat(values[k]).isoformat() != values[k] for k in ('request_date', 'deadline')) or values['deadline'] < values['request_date']:
            raise ValueError()
    except ValueError:
        fail(422, 'INVALID_DATE', 'Tanggal harus YYYY-MM-DD dan tenggat tidak boleh mendahului tanggal request.')
    return values


@api.post('/requests')
def upload():
    values = upload_metadata()
    evidence = [f for f in request.files.getlist('evidence_files[]') if f.filename]
    if len(evidence) > 10:
        fail(422, 'FILE_LIMIT', 'Maksimal 10 berkas bukti.')
    invoice_checked = read_upload(request.files.get('invoice_file'), allow_images=True)
    evidence_checked = [read_upload(f) for f in evidence]
    req = WorkRequest(id=uid('req'), uploaded_by=g.actor.id, updated_at=now(),
                      processing_status='QUEUED', stage='Menunggu ekstraksi', **values)
    g.db.add(req)
    g.db.flush()
    from ...request_numbers import assign_request_number
    assign_request_number(g.db,req)
    source=save_upload(req, invoice_checked, 'INVOICE')
    g.db.add(RequestSource(request_id=req.id,document_id=source.id,revision=1))
    for checked in evidence_checked:
        save_upload(req, checked, 'EVIDENCE')
    audit(g.db, 'REQUEST_UPLOADED', g.actor.id, req.id)
    return ok(request_dto(req, True), 201)


@api.post('/requests/<request_id>/invoices/<invoice_id>/confirm-uploader')
def confirm_uploader(request_id,invoice_id):
    data=body();req,inv=mutation_invoice(request_id,invoice_id,data)
    if g.actor.id!=req.uploaded_by or not roles(g.db,g.actor)&(CLIENT_ROLES|{'FINANCE_REVIEWER'}) or 'SYSTEM_ADMIN' in roles(g.db,g.actor):
        fail(403,'UPLOADER_REQUIRED','Konfirmasi dilakukan oleh uploader request ini.')
    if req.processing_status!='COMPLETE':fail(409,'PROCESSING','Tunggu ekstraksi selesai.')
    if data.get('acknowledged') is not True:fail(422,'CONFIRMATION_REQUIRED','Konfirmasikan pemeriksaan data dan hasil AI terhadap dokumen.')
    head=g.db.get(InvoiceVersion,(inv.id,inv.current_version))
    count=len(fields_for(g.db,inv)['line_items'])
    if not count or data.get('item_count_confirmed') is not True:
        fail(422,'ITEM_CONFIRMATION_REQUIRED','Konfirmasikan seluruh baris item yang dibandingkan dengan PDF.')
    initial=assistance_dto(g.db,req,inv)
    if initial['state']!='READY':fail(409,'INITIAL_ANALYSIS_REQUIRED','Tunggu analisis awal atau coba ulang jika gagal.')
    fingerprint=input_hash(g.db,req,inv)
    key=(inv.id,inv.current_version,fingerprint)
    if not g.db.get(UploaderConfirmation,key):
        g.db.add(UploaderConfirmation(invoice_id=inv.id,version=inv.current_version,input_hash=fingerprint,actor_id=g.actor.id,item_count=count))
        audit(g.db,'UPLOADER_CONFIRMED',g.actor.id,req.id,inv.id,
              changes=[{'field':'version','before':None,'after':inv.current_version}])
    g.db.flush();req.updated_at=now()
    return ok(request_dto(req,True))


@api.post('/requests/<request_id>/invoices/<invoice_id>/initial-analysis/retry')
def retry_initial(request_id,invoice_id):
    req,inv=mutation_invoice(request_id,invoice_id,body())
    if g.actor.id!=req.uploaded_by:fail(403,'UPLOADER_REQUIRED','Analisis awal diulang oleh uploader.')
    row=g.db.get(InvoiceAssistance,(inv.id,inv.current_version))
    if row and (row.state!='FAILED' or row.attempts>=3):
        fail(409,'INITIAL_RETRY_BLOCKED','Analisis masih berjalan, sudah tersedia, atau batas percobaan versi ini tercapai.')
    if row:row.state,row.error_code,row.updated_at='PENDING',None,now()
    else:g.db.add(InvoiceAssistance(invoice_id=inv.id,version=inv.current_version,state='PENDING'))
    return ok({'queued':True})


@api.post('/requests/<request_id>/document-revision')
def upload_document_revision(request_id):
    import json
    req=scoped_request(request_id,True);require_open(g.db,req)
    if req.uploaded_by!=g.actor.id or not roles(g.db,g.actor)&CLIENT_ROLES or 'SYSTEM_ADMIN' in roles(g.db,g.actor):
        fail(403,'UPLOADER_REQUIRED','Dokumen revisi diunggah oleh uploader request ini.')
    if req.processing_status in ('QUEUED','PROCESSING'):fail(409,'PROCESSING','Tunggu ekstraksi yang sedang berjalan.')
    current=invoices(req)
    published=any((rev:=latest_review(g.db,inv)) and rev.decision=='APPROVED' for inv in current)
    if published and request.form.get('supersede_published')!='true':
        fail(422,'SUPERSEDE_CONFIRMATION_REQUIRED','Setujui bahwa voucher yang sudah terbit akan menjadi arsip dan hasil baru memerlukan review ulang.')
    try:expected=json.loads(request.form.get('expected_versions',''))
    except ValueError:fail(422,'VERSION_REQUIRED','Kirim versi seluruh invoice yang ditampilkan.')
    if not isinstance(expected,dict) or any(type(v) is not int for v in expected.values()) or expected!={i.id:i.current_version for i in current}:
        fail(409,'STALE_VERSION','Data berubah. Muat ulang sebelum mengunggah revisi.')
    why=reason({'reason':request.form.get('reason')})
    category=request.form.get('category','UNSPECIFIED')
    if category not in ('SOURCE_ERROR','REVIEW_CORRECTION','UNSPECIFIED'):fail(422,'INVALID_CATEGORY','Kategori revisi tidak dikenal.')
    checked=read_upload(request.files.get('invoice_file'),allow_images=True)
    document=save_upload(req,checked,'INVOICE')
    pointer=g.db.get(RequestSource,req.id)
    if pointer:pointer.document_id,pointer.revision=document.id,pointer.revision+1
    else:g.db.add(RequestSource(request_id=req.id,document_id=document.id,revision=2))
    for inv in current:inv.active=0
    req.processing_status,req.stage,req.error_code='QUEUED','Membaca dokumen revisi',None
    req.updated_at,req.job_token,req.lease_until=now(),None,None
    release_inactive_pic(req)
    audit(g.db,'DOCUMENT_REVISION_UPLOADED',g.actor.id,req.id,reason=why,
          changes=[{'field':'document_id','before':None,'after':document.id},{'field':'revision_category','before':None,'after':category}])
    if published:audit(g.db,'CLIENT_REVISION_REQUESTED',g.actor.id,req.id,reason=why)
    return ok(request_dto(req,True),201)


@api.get('/requests/<request_id>/voucher-history')
def voucher_history(request_id):
    req=scoped_request(request_id)
    rows=g.db.execute(select(Voucher,Invoice).join(Invoice,Invoice.id==Voucher.invoice_id).where(Invoice.request_id==req.id).order_by(Voucher.created_at.desc()))
    return ok({'items':[{'id':v.id,'invoice_id':inv.id,'version':v.version,'created_at':v.created_at,'sha256':v.sha256}
                        for v,inv in rows if not inv.active or v.version!=inv.current_version]})


@api.post('/requests/<request_id>/vouchers/<voucher_id>/archive-download')
def archive_voucher(request_id,voucher_id):
    req=scoped_request(request_id)
    from ...models import Invoice
    row=g.db.execute(select(Voucher,Invoice).join(Invoice,Invoice.id==Voucher.invoice_id).where(Invoice.request_id==req.id,Voucher.id==voucher_id)).first()
    if not row:fail(404,'NOT_FOUND','Arsip voucher tidak ditemukan.')
    voucher,inv=row
    if inv.active and voucher.version==inv.current_version:fail(409,'CURRENT_VOUCHER','Gunakan unduhan voucher aktif untuk hasil terbaru.')
    audit(g.db,'ARCHIVED_VOUCHER_DOWNLOADED',g.actor.id,req.id,inv.id)
    return send_file(BytesIO(voucher.pdf),mimetype='application/pdf',as_attachment=True,download_name=f'AMIGA-arsip-{voucher.id}.pdf',conditional=False)



@api.get('/requests/<request_id>')
def detail(request_id):
    return ok(request_dto(scoped_request(request_id), True))



@api.get('/requests/<request_id>/documents/<document_id>')
def original(request_id, document_id):
    req = scoped_request(request_id)
    doc = g.db.scalar(select(Document).where(Document.id == document_id, Document.request_id == req.id))
    if not doc:
        fail(404, 'NOT_FOUND', 'Dokumen tidak ditemukan.')
    path = Path(current_app.config['UPLOAD_DIR']) / doc.storage_key
    if not path.is_file():
        fail(503, 'STORAGE_UNAVAILABLE', 'Dokumen sumber tidak tersedia di penyimpanan.')
    return send_file(path, mimetype=doc.mime_type, as_attachment=False, download_name=doc.original_filename, conditional=False)



@api.post('/requests/<request_id>/evidence')
def add_evidence(request_id):
    req = scoped_request(request_id, True)
    require_open(g.db, req)
    if 'ADD_EVIDENCE' not in request_dto(req, True)['allowed_actions']:
        fail(403, 'EVIDENCE_FORBIDDEN', 'Bukti tidak dapat ditambahkan pada status atau peran ini.')
    description = request.form.get('description', '')[:2000]
    doc = save_upload(req, read_upload(request.files.get('evidence_file')), 'EVIDENCE', description)
    invalidate_assistance(g.db,req)
    req.updated_at = now()
    audit(g.db, 'EVIDENCE_ADDED', g.actor.id, req.id, reason=description)
    return ok(document_dto(doc), 201)



@api.post('/requests/<request_id>/process')
def process(request_id):
    data = body()
    req = scoped_request(request_id, True)
    require_open(g.db, req)
    if not editable(req):
        fail(403, 'FORBIDDEN', 'Aksi tidak diizinkan untuk akun ini.')
    if req.processing_status in ('QUEUED', 'PROCESSING'):
        fail(409, 'PROCESSING', 'Proses sudah berada dalam antrean.')
    if data.get('mode') == 'REVALIDATE':
        if type(data.get('expected_version')) is not int or data['expected_version'] < 1:
            fail(422, 'VERSION_REQUIRED', 'expected_version harus integer positif.')
        inv = scoped_invoice(req, data.get('invoice_id'), data.get('expected_version', -1))
        audit(g.db, 'REVALIDATED', g.actor.id, req.id, inv.id)
    elif data.get('mode') == 'REEXTRACT':
        current = invoices(req)
        if any((rev := latest_review(g.db, inv)) and rev.decision == 'APPROVED' for inv in current):
            fail(409, 'APPROVED_INVOICE', 'Buat revisi invoice sebelum ekstraksi ulang.')
        expected = data.get('expected_versions')
        if current:
            if isinstance(expected, dict):
                if any(type(v) is not int or v < 1 for v in expected.values()):
                    fail(422, 'INVALID_VERSION', 'Setiap expected_versions harus integer positif.')
                if expected != {inv.id: inv.current_version for inv in current}:
                    fail(409, 'STALE_VERSION', 'Versi invoice dalam request berubah.')
            elif len(current) != 1 or type(data.get('expected_version')) is not int or data['expected_version'] != current[0].current_version:
                fail(409, 'STALE_VERSION', 'Kirim expected_versions untuk seluruh invoice dalam request.')
        audit(g.db, 'REEXTRACT_REQUESTED', g.actor.id, req.id, reason=reason(data))
        req.processing_status, req.stage, req.error_code, req.updated_at = 'QUEUED', 'Menunggu ekstraksi ulang', None, now()
    else:
        fail(422, 'INVALID_MODE', 'Mode harus REVALIDATE atau REEXTRACT.')
    return ok(request_dto(req, True))



@api.patch('/requests/<request_id>/invoices/<invoice_id>')
def edit_invoice(request_id, invoice_id):
    data = body()
    req, inv = mutation_invoice(request_id, invoice_id, data)
    return ok(save_invoice_draft(req,inv,data))


def save_invoice_draft(req,inv,data):
    if not editable(req):
        fail(403, 'FORBIDDEN', 'Akun tidak dapat mengubah invoice.')
    why = reason(data)
    previous = fields_for(g.db, inv)
    try:
        fields = normalize(data.get('fields'))
    except InvalidDraft as exc:
        fail(422, 'INVALID_DRAFT', str(exc))
    sources = data.get('field_sources', {})
    if not isinstance(sources, dict) or len(sources) > 100:
        fail(422, 'INVALID_SOURCE', 'Sumber field harus objek.')
    previous_sources = sources_for(g.db, inv)
    review_edit = reviewer(req)
    invoice_doc = source_document(g.db,req)
    # document_id scopes this annotation to the invoice being reviewed; REVIEWER
    # expressly means a human addition, not evidence extracted from that PDF.
    review_source = {'document_id': invoice_doc.id, 'source_type': 'REVIEWER', 'page': None, 'notes': why}
    docs = {d.id: d for d in g.db.scalars(select(Document).where(Document.request_id == req.id))}
    cleaned = {}
    for field, source in sources.items():
        if field not in HEADER_FIELDS:
            continue
        if source is None:
            cleaned[field] = None
            continue
        if not isinstance(source, dict) or set(source) - {'document_id', 'source_type', 'page', 'notes'}:
            fail(422, 'INVALID_SOURCE', 'Format sumber field tidak valid.')
        source_id = source.get('document_id')
        if not isinstance(source_id, str):
            fail(422, 'INVALID_SOURCE', 'document_id sumber harus string.')
        doc = docs.get(source_id)
        kind, page, notes = source.get('source_type'), source.get('page'), source.get('notes')
        if not doc or kind not in ('EXTRACTED', 'MANUAL', 'EVIDENCE', 'REVIEWER') or (kind == 'EVIDENCE' and doc.type != 'EVIDENCE'):
            fail(422, 'INVALID_SOURCE', 'Sumber harus dokumen milik request ini.')
        if page is not None and (type(page) is not int or not 1 <= page <= doc.page_count):
            fail(422, 'INVALID_SOURCE', 'Nomor halaman sumber tidak valid.')
        if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
            fail(422, 'INVALID_SOURCE', 'Catatan sumber tidak valid.')
        canonical_source = {'document_id': doc.id, 'source_type': kind, 'page': page, 'notes': notes}
        if kind == 'REVIEWER':
            if review_edit:
                if doc.id != invoice_doc.id:
                    fail(422, 'INVALID_SOURCE', 'Tambahan reviewer harus terkait invoice yang sedang diperiksa.')
                # Preserve unchanged provenance on a no-op save.
                if canonical_source != previous_sources.get(field) or fields[field] != previous[field]:
                    canonical_source = dict(review_source)
            elif canonical_source != previous_sources.get(field) or fields[field] != previous[field]:
                fail(403, 'REVIEWER_SOURCE_REQUIRED', 'Tambahan hasil review hanya dapat dicatat reviewer yang menangani tugas.')
        if kind == 'EXTRACTED':
            if canonical_source != previous_sources.get(field):
                fail(422, 'INVALID_SOURCE', 'Sumber EXTRACTED hanya dapat dipertahankan dari hasil sebelumnya.')
            if fields[field] != previous[field]:
                canonical_source = dict(review_source) if review_edit else {**canonical_source, 'source_type': 'MANUAL', 'notes': why}
        cleaned[field] = canonical_source
    for field in HEADER_FIELDS:
        if review_edit and fields[field] != previous[field] and (not cleaned.get(field) or cleaned[field]['source_type'] != 'EVIDENCE'):
            cleaned[field] = dict(review_source)
        elif fields[field] != previous[field] and field not in cleaned:
            cleaned[field] = {'document_id': invoice_doc.id, 'source_type': 'MANUAL', 'page': None, 'notes': why}
        elif field not in cleaned and field in previous_sources:
            cleaned[field] = previous_sources[field]
    bank_changed = any(fields[k] != previous[k] for k in ('account_number', 'bank_name', 'account_holder'))
    if review_edit and fields['account_number'] and (bank_changed or not cleaned.get('account_number')):
        if not cleaned.get('account_number') or cleaned['account_number']['source_type'] != 'EVIDENCE':
            cleaned['account_number'] = dict(review_source)
    if bank_changed and not review_edit and (not cleaned.get('account_number') or cleaned['account_number']['source_type'] != 'EVIDENCE'):
        fail(422, 'BANK_EVIDENCE_REQUIRED', 'Perubahan rekening harus merujuk bukti pendukung.')
    if type(data.get('item_count_confirmed', False)) is not bool:
        fail(422, 'INVALID_CONFIRMATION', 'Konfirmasi item harus boolean.')
    previous_version = inv.current_version
    previous_count = g.db.get(InvoiceVersion, (inv.id, previous_version)).expected_item_count
    confirmed_count = len(fields['line_items']) if data.get('item_count_confirmed') else None
    confirmation = confirmation_dto(g.db, req, inv)
    effective_count = confirmation['item_count'] if confirmation['confirmed'] else previous_count
    # A save of identical persisted content is not a revision. In particular,
    # retaining the uploader's already-verified item count must not revoke it.
    if (fields == previous and {k: v for k, v in cleaned.items() if v} == previous_sources
            and confirmed_count == effective_count):
        return {**invoice_dto(req, inv), 'revision_created': False}
    inv.current_version += 1
    write_version(g.db, inv, fields, cleaned, g.actor.id, why,
                  len(fields['line_items']) if data.get('item_count_confirmed') else None)
    req.updated_at = now()
    release_inactive_pic(req)
    changes = [{'field': key, 'before': previous[key], 'after': fields[key]} for key in fields if previous[key] != fields[key]]
    changes += [{'field': 'version', 'before': previous_version, 'after': inv.current_version}]
    if previous_sources != sources_for(g.db, inv):
        changes.append({'field': 'field_sources', 'before': previous_sources, 'after': sources_for(g.db, inv)})
    if previous_count != confirmed_count:
        changes.append({'field': 'expected_item_count', 'before': previous_count, 'after': confirmed_count})
    audit(g.db, 'INVOICE_REVISED', g.actor.id, req.id, inv.id, why, changes)
    return {**invoice_dto(req, inv), 'revision_created': True}



@api.post('/requests/<request_id>/invoices/<invoice_id>/validate')
def revalidate(request_id, invoice_id):
    req, inv = mutation_invoice(request_id, invoice_id, body())
    if not editable(req):
        fail(403, 'FORBIDDEN', 'Akun tidak dapat memvalidasi invoice.')
    audit(g.db, 'REVALIDATED', g.actor.id, req.id, inv.id)
    return ok(invoice_dto(req, inv))



@api.post('/requests/<request_id>/invoices/<invoice_id>/resolve')
def resolve(request_id, invoice_id):
    data = body()
    req, inv = mutation_invoice(request_id, invoice_id, data)
    require_review(req)
    rev = latest_review(g.db, inv)
    if rev and rev.decision == 'APPROVED':
        fail(409, 'ALREADY_APPROVED', 'Invoice telah disetujui.')
    code = data.get('issue_code')
    if not isinstance(code, str) or code not in RESOLVABLE or code not in {i['code'] for i in validation_for(req, inv)['issues']}:
        fail(422, 'ISSUE_NOT_RESOLVABLE', 'Issue ini harus diperbaiki datanya, tidak dapat diabaikan.')
    why = reason(data)
    if g.db.get(Resolution, (inv.id, inv.current_version, code)):
        fail(409, 'ALREADY_RESOLVED', 'Issue telah diselesaikan pada versi ini.')
    g.db.add(Resolution(invoice_id=inv.id, version=inv.current_version, issue_code=code,
                        actor_id=g.actor.id, reason=why, created_at=now()))
    audit(g.db, 'ISSUE_RESOLVED', g.actor.id, req.id, inv.id, why,
          [{'field': code, 'before': 'BLOCK', 'after': 'RESOLVED'}])
    g.db.flush()
    return ok(invoice_dto(req, inv))



@api.post('/requests/<request_id>/invoices/<invoice_id>/approve')
def approve(request_id, invoice_id):
    return decide(request_id, invoice_id, 'APPROVED')



@api.post('/requests/<request_id>/invoices/<invoice_id>/reject')
def reject(request_id, invoice_id):
    return decide(request_id, invoice_id, 'REJECTED')



@api.get('/requests/<request_id>/invoices/<invoice_id>/voucher/preview.pdf')
def voucher_preview(request_id, invoice_id):
    req = scoped_request(request_id)
    inv = scoped_invoice(req, invoice_id)
    try:
        version = int(request.args.get('version', inv.current_version))
    except ValueError:
        fail(422, 'INVALID_VERSION', 'Versi tidak valid.')
    fields = fields_for(g.db, inv, version)
    if not fields:
        fail(404, 'NOT_FOUND', 'Versi invoice tidak ditemukan.')
    voucher = g.db.scalar(select(Voucher).where(Voucher.invoice_id == inv.id, Voucher.version == version))
    from ...voucher_tax import applied_tax
    pdf = voucher.pdf if voucher else render_voucher(fields, 'DRAFT-' + inv.id, version,
        requester_name=g.db.get(User, req.uploaded_by).display_name, purpose=req.request_type,tax=applied_tax(g.db,inv,fields,version))
    return send_file(BytesIO(pdf), mimetype='application/pdf', download_name='voucher-preview.pdf', conditional=False)



@api.post('/requests/<request_id>/invoices/<invoice_id>/voucher/download')
def voucher_download(request_id, invoice_id):
    req, inv = mutation_invoice(request_id, invoice_id, body(), allow_closed=True)
    review = latest_review(g.db, inv)
    voucher = g.db.scalar(select(Voucher).where(Voucher.invoice_id == inv.id, Voucher.version == inv.current_version))
    if not review or review.decision != 'APPROVED' or not voucher:
        fail(403, 'APPROVAL_REQUIRED', 'Voucher resmi hanya tersedia setelah approval independen.')
    client_download = 'COMPANY_CLIENT' in roles(g.db, g.actor) and req.client_id in client_ids(g.db, g.actor)
    if client_download:
        g.db.add(Handover(id=uid('hnd'), voucher_id=voucher.id, actor_id=g.actor.id, created_at=now()))
    audit(g.db, 'VOUCHER_DOWNLOAD_PROVIDED', g.actor.id, req.id, inv.id,
          'Unduhan disediakan; bukan bukti penerimaan klien atau pelaksanaan pembayaran.')
    req.updated_at = now()
    response = send_file(BytesIO(voucher.pdf), mimetype='application/pdf', as_attachment=True,
                         download_name=voucher.id + '.pdf', conditional=False)
    response.headers['X-Voucher-ID'] = voucher.id
    response.headers['X-Handover-Recorded'] = 'true' if client_download else 'false'
    return response



@api.post('/requests/<request_id>/lifecycle')
def change_lifecycle(request_id):
    """Client acceptance or revision of the entire request, atomically.

    Lock order matches invoice mutations: parent request, then its revisions.
    Both lifecycle and invoice versions prevent stale tabs from closing new work.
    Historical approvals, handovers and PDF snapshots are never overwritten.
    """
    data = body()
    req = scoped_request(request_id, True)
    actor_roles = roles(g.db, g.actor)
    if ('SYSTEM_ADMIN' in actor_roles or 'COMPANY_CLIENT' not in actor_roles
            or req.client_id not in client_ids(g.db, g.actor)):
        fail(403, 'CLIENT_REQUIRED', 'Penerimaan layanan dan permintaan revisi dilakukan klien terkait.')
    current = request_dto(req, True)
    state = current['lifecycle']
    expected = data.get('expected_versions')
    if (type(data.get('expected_lifecycle_revision')) is not int or not isinstance(expected, dict)
            or any(type(v) is not int for v in expected.values())):
        fail(422, 'VERSION_REQUIRED', 'Kirim versi lifecycle dan seluruh invoice yang ditampilkan.')
    if (data['expected_lifecycle_revision'] != state['revision']
            or expected != {i['id']: i['current_version'] for i in current['invoices']}):
        fail(409, 'STALE_VERSION', 'Pekerjaan telah berubah. Muat ulang sebelum melanjutkan.')
    action = data.get('action')
    if action not in ('CLOSE', 'REQUEST_REVISION'):
        fail(422, 'INVALID_ACTION', 'Aksi lifecycle tidak dikenal.')
    if action not in current['allowed_actions']:
        fail(409, 'LIFECYCLE_BLOCKED', 'Penutupan memerlukan semua voucher terbaru sudah diunduh klien. Revisi melalui aksi ini tersedia setelah seluruh voucher terbit.')
    why = reason(data)
    changes = []
    if action == 'REQUEST_REVISION':
        for inv in invoices(req):
            fields, sources = fields_for(g.db, inv), sources_for(g.db, inv)
            before = inv.current_version
            inv.current_version += 1
            # Fresh human review is mandatory, including checking all line items.
            write_version(g.db, inv, fields, sources, g.actor.id, why, None)
            audit(g.db, 'INVOICE_REVISED', g.actor.id, req.id, inv.id, why,
                  [{'field': 'version', 'before': before, 'after': inv.current_version}])
        release_inactive_pic(req)
    row = g.db.get(RequestLifecycle, req.id)
    if row is None:
        row = RequestLifecycle(request_id=req.id)
        g.db.add(row)
    row.state = 'CLOSED' if action == 'CLOSE' else 'OPEN'
    row.revision, row.updated_at, row.actor_id = state['revision'] + 1, now(), g.actor.id
    req.updated_at = row.updated_at
    changes.append({'field': 'lifecycle', 'before': state['state'], 'after': row.state})
    audit(g.db, 'REQUEST_CLOSED' if action == 'CLOSE' else 'CLIENT_REVISION_REQUESTED',
          g.actor.id, req.id, reason=why, changes=changes)
    g.db.flush()
    return ok(request_dto(req, True))



@api.get('/requests/<request_id>/audit')
def history(request_id):
    req = scoped_request(request_id)
    rows = list(g.db.scalars(select(Audit).where(Audit.request_id == req.id).order_by(Audit.at, Audit.id)))
    return ok({'items': [{'id': e.id, 'request_id': e.request_id, 'invoice_id': e.invoice_id,
                         'actor_id': e.actor_id, 'actor_name': g.db.get(User, e.actor_id).display_name if e.actor_id else 'Sistem',
                         'action': e.action, 'at': e.at, 'reason': e.reason, 'changes': e.changes} for e in rows], 'total': len(rows)})



@api.patch('/requests/<request_id>/assignment')
def assign(request_id):
    if not roles(g.db, g.actor) & {'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        fail(403, 'FORBIDDEN', 'Penugasan ulang hanya untuk pengelola.')
    req = scoped_request(request_id, True)
    require_open(g.db, req)
    pic_id = body().get('pic_id')
    pic = g.db.get(User, pic_id) if isinstance(pic_id, str) else None
    if (not pic or pic.account_status != 'ACTIVE' or 'FINANCE_REVIEWER' not in roles(g.db, pic)
        or 'SYSTEM_ADMIN' in roles(g.db, pic)
        or req.uploaded_by == pic.id or g.db.scalar(select(Document.id).where(Document.request_id == req.id, Document.uploaded_by == pic.id).limit(1))):
        fail(422, 'INVALID_REVIEWER', 'PIC harus reviewer aktif dan independen dari pengunggah.')
    if task_complete(req):
        fail(409, 'TASK_COMPLETED', 'Review sudah selesai; penugasan historis dipertahankan.')
    if not ready_for_review(g.db,req):
        fail(409,'UPLOADER_CONFIRMATION_REQUIRED','Penugasan menunggu konfirmasi uploader atas versi terbaru.')
    before = req.pic_id
    req.pic_id, req.updated_at = pic.id, now()
    audit(g.db, 'REVIEWER_ASSIGNED', g.actor.id, req.id, changes=[{'field': 'pic_id', 'before': before, 'after': pic.id}])
    return ok(request_dto(req, True))



@api.get('/requests/<request_id>/reviewers')
def reviewer_candidates(request_id):
    if not roles(g.db, g.actor) & {'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        fail(403, 'FORBIDDEN', 'Daftar reviewer hanya untuk pengelola.')
    req = scoped_request(request_id)
    candidates = g.db.scalars(select(User).where(User.account_status == 'ACTIVE').order_by(User.display_name))
    contributors = set(g.db.scalars(select(Document.uploaded_by).where(Document.request_id == req.id))) | {req.uploaded_by}
    return ok({'items': [{'id': u.id, 'display_name': u.display_name, 'email': u.email} for u in candidates
                        if u.id not in contributors and 'FINANCE_REVIEWER' in roles(g.db, u) and 'SYSTEM_ADMIN' not in roles(g.db, u)]})

