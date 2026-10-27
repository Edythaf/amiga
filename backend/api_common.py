"""Same-origin API. Every document and invoice is scoped on the server."""
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import secrets
import json
import jwt
from flask import Blueprint, current_app, g, request, session, jsonify, send_file
from sqlalchemy import select, delete, func, update, or_, true, false, and_
from pypdf import PdfReader
from .application import ApiFault
from .models import (User, Role, Client, Membership, AuthSession, LocalCredential, Setting, WorkRequest,
                     Document, Invoice, InvoiceVersion, Resolution, Review,
                     Voucher, Handover, Audit, RequestLifecycle, HEADER_FIELDS, now, uid)
from .repository import roles, client_ids, fields_for, sources_for, write_version, latest_review, audit
from .validation import normalize, validate, InvalidDraft
from .pdf_service import render_voucher
from .auth_tokens import issue_token, verify_token
from .local_auth import parse_identity, hash_password, verify_password, owner_setup_record
from .request_lifecycle import lifecycle, require_open, progress, client_actions
from .workflow import source_document,assistance_dto,confirmation_dto,ready_for_review

api = Blueprint('api', __name__, url_prefix='/api')
ALL_ROLES = {'SYSTEM_ADMIN', 'FINANCE_REVIEWER', 'SERVICE_LEAD', 'CLIENT_OWNER', 'CLIENT_BACKUP', 'COMPANY_CLIENT'}
CLIENT_ROLES = {'CLIENT_OWNER', 'CLIENT_BACKUP'}
COMPANY_ROLES = {'COMPANY_CLIENT'}
RESOLVABLE = {'DUPLICATE_FILE', 'POSSIBLE_DUPLICATE', 'SUSPICIOUS_DATE'}


def ok(data, status=200):
    return jsonify(data=data), status


def fail(status, code, message):
    raise ApiFault(status, code, message)


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        fail(422, 'INVALID_JSON', 'Body harus objek JSON.')
    return value


def reason(data):
    value = data.get('reason')
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 2000:
        fail(422, 'REASON_REQUIRED', 'Isi alasan 3–2000 karakter.')
    return value.strip()


def authenticate():
    token = session.get('auth', '')
    try:
        claims = verify_token(token, current_app.config) if token else None
    except jwt.InvalidTokenError:
        claims = None
    record = g.db.get(AuthSession, sha256(token.encode()).hexdigest()) if claims else None
    if not record or record.expires_at <= now() or record.user_id != claims['sub']:
        session.pop('auth', None)
        fail(401, 'UNAUTHENTICATED', 'Silakan masuk kembali ke AMIGA.')
    g.actor = g.db.get(User, record.user_id)
    g.auth_session = record
    if not g.actor or g.actor.account_status == 'DISABLED':
        fail(403, 'ACCOUNT_DISABLED', 'Akun telah dinonaktifkan.')


def require_role(role):
    if role not in roles(g.db, g.actor):
        fail(403, 'FORBIDDEN', 'Peran akun tidak berwenang melakukan aksi ini.')


def user_dto(user):
    memberships = client_ids(g.db, user)
    return {'id': user.id, 'email': user.email, 'display_name': user.display_name,
            'account_status': user.account_status, 'roles': sorted(roles(g.db, user)),
            'requested_role': {'PENDING_ADMIN': 'SYSTEM_ADMIN', 'PENDING_REVIEWER': 'FINANCE_REVIEWER', 'PENDING_COMPANY': 'COMPANY_CLIENT'}.get(user.account_status),
            'requested_company_name': (record.value if (record := g.db.get(Setting, 'company_request:'+user.id)) else None),
            'clients': [{'id': c.id, 'name': c.name} for c in g.db.scalars(select(Client).where(Client.id.in_(memberships)).order_by(Client.name))]}


def session_dto(user, expires_at):
    data = user_dto(user)
    portal = 'pending' if user.account_status != 'ACTIVE' else (
        'admin' if set(data['roles']) & {'SYSTEM_ADMIN', 'SERVICE_LEAD'} else
        'reviewer' if 'FINANCE_REVIEWER' in data['roles'] else
        'client' if 'COMPANY_CLIENT' in data['roles'] else 'uploader' if set(data['roles']) & CLIENT_ROLES else 'pending')
    return {'user': data, 'portal': portal, 'csrf_token': session['csrf'], 'expires_at': expires_at}


def start_session(user, status=200):
    old = session.get('auth')
    if old:
        g.db.execute(delete(AuthSession).where(AuthSession.token_hash == sha256(old.encode()).hexdigest()))
    session.clear()
    token, expiry = issue_token(user.id, current_app.config)
    # HttpOnly, SameSite cookie carries the JWT. JavaScript never persists it.
    session.update(auth=token, csrf=secrets.token_urlsafe(32))
    session.permanent = True
    g.db.add(AuthSession(token_hash=sha256(token.encode()).hexdigest(), user_id=user.id, expires_at=expiry))
    audit(g.db, 'LOGIN', actor_id=user.id)
    g.db.flush()
    return ok(session_dto(user, expiry), status)


def local_input(data):
    if current_app.config['AUTH_METHOD'] != 'local_password':
        fail(503, 'AUTH_METHOD_DISABLED', 'Metode masuk ini belum diaktifkan.')
    try:
        return parse_identity(data.get('email_input'))
    except ValueError as exc:
        fail(422, 'INVALID_EMAIL', str(exc))


def pending_status(requested_role):
    return {'SYSTEM_ADMIN': 'PENDING_ADMIN', 'FINANCE_REVIEWER': 'PENDING_REVIEWER'}.get(requested_role, 'PENDING_CLIENT')


def create_client_workspace(user):
    """New ordinary accounts own a fresh tenant, never a pre-existing client's records."""
    client = Client(id=uid('cli'), name=('Workspace ' + user.display_name)[:200])
    g.db.add(client)
    g.db.flush()
    g.db.add(Membership(user_id=user.id, client_id=client.id))
    g.db.add(Role(user_id=user.id, role='CLIENT_OWNER'))
    user.account_status = 'ACTIVE'
    audit(g.db, 'CLIENT_WORKSPACE_CREATED', actor_id=user.id,
          changes=[{'field': 'client_id', 'before': None, 'after': client.id}])


def request_role(user, requested_role):
    # Registration/login can activate a reviewer request, but never undo a
    # suspension or add the role to an existing client/admin account.
    if user.account_status == 'PENDING_REVIEWER' and requested_role in (None, 'FINANCE_REVIEWER'):
        assigned = roles(g.db, user)
        if assigned - {'FINANCE_REVIEWER'}:
            fail(403, 'ROLE_CONFLICT', 'Peran akun perlu diperiksa pengelola.')
        if 'FINANCE_REVIEWER' not in assigned:
            g.db.add(Role(user_id=user.id, role='FINANCE_REVIEWER'))
        user.account_status = 'ACTIVE'
        audit(g.db, 'REVIEWER_SELF_REGISTERED', actor_id=user.id,
              reason='Reviewer registration activates without admin approval')
        return
    if not requested_role:
        return
    if user.account_status == 'PENDING_COMPANY':
        fail(403, 'ROLE_NOT_GRANTED', 'Akun Klien perusahaan menunggu pengaitan perusahaan oleh admin. Masuk dengan email biasa.')
    if user.account_status != 'ACTIVE':
        if requested_role == 'CLIENT_OWNER':
            fail(403, 'ROLE_NOT_GRANTED', 'Peran Uploader belum diberikan pada akun ini.')
        user.account_status = pending_status(requested_role)
        return
    assigned = roles(g.db, user)
    permitted = {'FINANCE_REVIEWER': {'FINANCE_REVIEWER', 'SERVICE_LEAD'},
                 'CLIENT_OWNER': CLIENT_ROLES, 'SYSTEM_ADMIN': {'SYSTEM_ADMIN'}}[requested_role]
    if not assigned & permitted:
        fail(403, 'ROLE_NOT_GRANTED', 'Akses yang diminta belum diberikan. Masuk dengan email biasa dan hubungi pengelola untuk perubahan peran.')


def request_access():
    actor_roles = roles(g.db, g.actor)
    if actor_roles & {'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        return true()
    permitted = [false()]
    if actor_roles & (CLIENT_ROLES | COMPANY_ROLES):
        permitted.append(WorkRequest.client_id.in_(client_ids(g.db, g.actor)))
    if 'FINANCE_REVIEWER' in actor_roles:
        permitted.append(WorkRequest.pic_id == g.actor.id)
        permitted.append(and_(WorkRequest.uploaded_by == g.actor.id, WorkRequest.client_id.in_(client_ids(g.db, g.actor))))
    return or_(*permitted)


def scoped_request(request_id, lock=False):
    from .models import RequestNumber
    if isinstance(request_id,str) and request_id.upper().startswith('REQ-'):
        alias=g.db.scalar(select(RequestNumber.request_id).where(RequestNumber.code==request_id.upper()))
        request_id=alias or request_id
    query = select(WorkRequest).where(WorkRequest.id == request_id, request_access())
    if lock:
        query = query.with_for_update()
    req = g.db.scalar(query)
    if not req:
        fail(404, 'NOT_FOUND', 'Request tidak ditemukan.')
    return req


def scoped_invoice(req, invoice_id, expected=None):
    if not isinstance(invoice_id, str):
        fail(422, 'INVALID_INVOICE_ID', 'invoice_id harus string.')
    inv = g.db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.request_id == req.id, Invoice.active == 1))
    if not inv:
        fail(404, 'NOT_FOUND', 'Invoice tidak ditemukan atau telah diganti ekstraksi baru.')
    if expected is not None and (type(expected) is not int or expected != inv.current_version):
        fail(409, 'STALE_VERSION', 'Versi invoice berubah. Muat ulang sebelum melanjutkan.')
    return inv


def mutation_invoice(request_id, invoice_id, data, *, allow_closed=False):
    if 'expected_version' not in data or data['expected_version'] is None:
        fail(422, 'VERSION_REQUIRED', 'expected_version wajib diisi.')
    req = scoped_request(request_id, True)
    if not allow_closed:
        require_open(g.db, req)
    if req.processing_status in ('QUEUED', 'PROCESSING'):
        fail(409, 'PROCESSING', 'Tunggu proses ekstraksi selesai.')
    return req, scoped_invoice(req, invoice_id, data['expected_version'])


def independent(req):
    return req.uploaded_by != g.actor.id and not g.db.scalar(select(Document.id).where(
        Document.request_id == req.id, Document.uploaded_by == g.actor.id).limit(1))


def reviewer(req):
    actor_roles = roles(g.db, g.actor)
    return ('FINANCE_REVIEWER' in actor_roles and 'SYSTEM_ADMIN' not in actor_roles
            and independent(req) and req.pic_id == g.actor.id)


def editable(req):
    actor_roles = roles(g.db, g.actor)
    return 'SYSTEM_ADMIN' not in actor_roles and (
        bool(actor_roles & CLIENT_ROLES) and req.client_id in client_ids(g.db, g.actor)
        or 'FINANCE_REVIEWER' in actor_roles and req.pic_id == g.actor.id)


def require_review(req):
    if not reviewer(req):
        fail(403, 'INDEPENDENT_REVIEWER_REQUIRED', 'Reviewer harus ditugaskan, berbeda dari pengunggah, dan bukan System Admin.')


def invoices(req):
    return list(g.db.scalars(select(Invoice).where(Invoice.request_id == req.id, Invoice.active == 1).order_by(Invoice.index)))


def validation_for(req, inv):
    fields = fields_for(g.db, inv)
    extra = []
    def flag(code, message):
        extra.append({'code': code, 'severity': 'BLOCK', 'message': message, 'resolved': False})
    doc = source_document(g.db,req)
    from .models import RequestIntake
    intake=g.db.get(RequestIntake,req.id)
    same_source=select(RequestIntake.request_id).where(RequestIntake.source_group==intake.source_group) if intake else select(RequestIntake.request_id).where(false())
    duplicate = g.db.scalar(select(Document.id).join(WorkRequest, Document.request_id == WorkRequest.id).where(
        WorkRequest.client_id == req.client_id, Document.type == 'INVOICE', Document.sha256 == doc.sha256,
        Document.request_id != req.id,Document.request_id.not_in(same_source)).limit(1))
    if duplicate:
        flag('DUPLICATE_FILE', 'Berkas identik sudah ada di klien ini; reviewer wajib memeriksa alasan pengulangan.')
    if fields['vendor_name'] and fields['invoice_number']:
        peers = g.db.execute(select(InvoiceVersion.vendor_name, InvoiceVersion.invoice_number)
            .join(Invoice, (Invoice.id == InvoiceVersion.invoice_id) & (Invoice.current_version == InvoiceVersion.version))
            .join(WorkRequest, WorkRequest.id == Invoice.request_id).where(
                WorkRequest.client_id == req.client_id, Invoice.active == 1, Invoice.id != inv.id))
        key = lambda value: re.sub(r'\s+', ' ', value or '').strip().casefold()
        if any(key(vendor) == key(fields['vendor_name']) and key(number) == key(fields['invoice_number']) for vendor, number in peers):
            flag('POSSIBLE_DUPLICATE', 'Vendor dan nomor invoice yang sama sudah tercatat pada klien ini.')
    documents = {d.id: d for d in g.db.scalars(select(Document).where(Document.request_id == req.id))}
    source = sources_for(g.db, inv).get('account_number')
    if not fields['account_number'] or not source or source['document_id'] not in documents:
        flag('MISSING_EVIDENCE', 'Rekening belum lengkap atau belum memiliki catatan asal. Lengkapi dari dokumen atau hasil pemeriksaan reviewer.')
    if not source or source['document_id'] not in documents:
        flag('ACCOUNT_SOURCE_REQUIRED', 'Catat asal rekening dari dokumen atau hasil pemeriksaan reviewer.')
    head = g.db.get(InvoiceVersion, (inv.id, inv.current_version))
    resolutions = {r.issue_code: {'actor_id': r.actor_id, 'reason': r.reason, 'at': r.created_at}
                   for r in g.db.scalars(select(Resolution).where(Resolution.invoice_id == inv.id, Resolution.version == inv.current_version))}
    confirmed=confirmation_dto(g.db,req,inv)
    from .models import InvoiceTaxPlan
    tax_plan=g.db.get(InvoiceTaxPlan,(inv.id,inv.current_version))
    source_pph=tax_plan.source_withholding if tax_plan and tax_plan.revision>0 else '0'
    return validate(fields, inv.current_version, confirmed['item_count'] if confirmed['confirmed'] else head.expected_item_count, extra, resolutions,
                    current_app.config['IDR_TOLERANCE'] if fields['currency'] == 'IDR' else current_app.config['DEFAULT_TOLERANCE'],source_withholding=source_pph)


def invoice_dto(req, inv, *, request_state=None,review_ready=None):
    from .manual_pdf import latest_manual,manual_dto
    from .voucher_tax import plan_dto
    manual=latest_manual(g.db,inv)
    rev = latest_review(g.db, inv)
    approved = bool(rev and rev.decision == 'APPROVED')
    confirmation=confirmation_dto(g.db,req,inv)
    actions = []
    idle = req.processing_status not in ('QUEUED', 'PROCESSING')
    open_request = (request_state or lifecycle(g.db, req)['state']) == 'OPEN'
    if editable(req) and idle and open_request:
        actions.append('EDIT')
        if not approved:
            actions.append('VALIDATE')
    if reviewer(req) and idle and open_request and not approved and not (rev and rev.decision == 'REJECTED'):
        actions += ['REJECT', 'RESOLVE']
        if (ready_for_review(g.db,req) if review_ready is None else review_ready):actions.append('APPROVE')
    if approved and idle:
        actions.append('DOWNLOAD_VOUCHER')
    return {'id': inv.id, 'index': inv.index, 'current_version': inv.current_version,
            'fields': fields_for(g.db, inv), 'field_sources': sources_for(g.db, inv),
            'expected_item_count':confirmation['item_count'] if confirmation['confirmed'] else g.db.get(InvoiceVersion, (inv.id, inv.current_version)).expected_item_count,
            'validation': validation_for(req, inv), 'review_status': rev.decision if rev else 'PENDING',
            'review_note': rev.reason if rev else None,
            'reviewer_id': rev.actor_id if rev else None, 'reviewed_at': rev.created_at if rev else None,
            'initial_analysis':assistance_dto(g.db,req,inv),
            'uploader_confirmation':confirmation, 'manual_review_pdf':manual_dto(manual),
            'voucher_pdf_source':rev.validation_snapshot.get('voucher_pdf_source') if approved else None,
            'voucher_tax':plan_dto(g.db,inv,fields_for(g.db,inv)),
            'allowed_actions': actions}


def request_dto(req, detail=False):
    state = lifecycle(g.db, req)
    invs = invoices(req)
    review_ready=ready_for_review(g.db,req)
    invoice_rows = [invoice_dto(req, inv, request_state=state['state'],review_ready=review_ready) for inv in invs]
    if req.processing_status in ('QUEUED', 'PROCESSING'):
        status = req.processing_status
    elif req.processing_status == 'FAILED' or not invs:
        status = 'EXCEPTION'
    elif all(row['review_status'] == 'APPROVED' for row in invoice_rows):
        handed_over = True
        for inv in invs:
            voucher = g.db.scalar(select(Voucher).where(Voucher.invoice_id == inv.id, Voucher.version == inv.current_version))
            if not voucher or not g.db.scalar(select(Handover.id).where(Handover.voucher_id == voucher.id).limit(1)):
                handed_over = False
        status = 'SENT_TO_CLIENT' if handed_over else 'AMIGA_REVIEWED'
    elif any(row['review_status'] == 'REJECTED' or not row['validation']['valid'] for row in invoice_rows):
        status = 'EXCEPTION'
    else:
        status = 'READY_FOR_REVIEW'
    totals = {}
    for row in invoice_rows:
        f = row['fields']
        if f['currency'] and f['total_amount'] is not None:
            totals[f['currency']] = totals.get(f['currency'], Decimal(0)) + Decimal(f['total_amount'])
    pic = g.db.get(User, req.pic_id) if req.pic_id else None
    data = {'id': req.id, 'client_id': req.client_id, 'client_name': g.db.get(Client, req.client_id).name,
            'pic_name': pic.display_name if pic else None, 'uploader_name': g.db.get(User,req.uploaded_by).display_name,
            'uploaded_by': req.uploaded_by, 'pic_id': req.pic_id, 'request_type': req.request_type,
            'status': status, 'request_date': req.request_date, 'deadline': req.deadline,
            'channel': req.channel, 'updated_at': req.updated_at, 'invoice_count': len(invs),
            'vendor_names': list(dict.fromkeys(row['fields']['vendor_name'] for row in invoice_rows if row['fields']['vendor_name'])),
            'invoice_numbers': [row['fields']['invoice_number'] for row in invoice_rows if row['fields']['invoice_number']],
            'totals_by_currency': [{'currency': currency, 'amount': format(total, 'f')} for currency, total in sorted(totals.items())],
            'issues': [issue for row in invoice_rows for issue in row['validation']['issues']]}
    from .models import RequestNumber,CompanyNumber
    number=g.db.get(RequestNumber,req.id)
    company_number=g.db.get(CompanyNumber,req.client_id)
    data['request_code']=number.code if number else req.id
    data['company_number']=company_number.number if company_number else None
    data['request_sequence']=number.sequence if number else None
    data['lifecycle'] = state
    data['work_status'] = progress(req, status, invoice_rows, state['state'])
    data['voucher_count'] = sum(row['review_status'] == 'APPROVED' for row in invoice_rows)
    data['ready_for_review']=review_ready
    if detail:
        current_source=source_document(g.db,req)
        documents=list(g.db.scalars(select(Document).where(Document.request_id==req.id).order_by(Document.uploaded_at.desc(),Document.id)))
        if current_source:documents.sort(key=lambda d:d.id!=current_source.id)
        data['documents']=[{**document_dto(d),'current_source':bool(current_source and d.id==current_source.id)} for d in documents]
        data['invoices'] = invoice_rows
        approved_any = any(row['review_status'] == 'APPROVED' for row in invoice_rows)
        idle = req.processing_status not in ('QUEUED', 'PROCESSING') and state['state'] == 'OPEN'
        data['allowed_actions'] = (['ADD_EVIDENCE'] if editable(req) and idle and not approved_any else []) + (
            ['REEXTRACT'] if editable(req) and idle and not approved_any else [])
        actor_roles = roles(g.db, g.actor)
        is_client = bool(actor_roles & COMPANY_ROLES) and req.client_id in client_ids(g.db, g.actor) and 'SYSTEM_ADMIN' not in actor_roles
        data['allowed_actions'] += client_actions(is_client, status, state['state'])
        if req.uploaded_by==g.actor.id and bool(actor_roles & CLIENT_ROLES) and idle:data['allowed_actions'].append('UPLOAD_REVISION')
        event = g.db.scalar(select(Audit).where(Audit.request_id == req.id,
            Audit.action == 'CLIENT_REVISION_REQUESTED').order_by(Audit.at.desc(), Audit.id.desc()).limit(1))
        data['client_revision_note'] = event.reason if event else None
        data['processing'] = {'status': req.processing_status, 'stage': req.stage,
                              'stage_step': 3 if req.processing_status == 'COMPLETE' else 1 if req.processing_status == 'PROCESSING' else 0,
                              'stage_total': 3, 'error_code': req.error_code,
                              'error_message': req.stage if req.error_code else None}
        from .telegram_config import company_recipients,bot_dto
        recipients=company_recipients(g.db,req.client_id,current_app.config)
        data['telegram']={'available':bool(any(r['connected'] for r in recipients) and bot_dto(current_app.config)['configured']),
                          'recipient_name':recipients[0]['name'] if len(recipients)==1 else None,'recipients':recipients}
        if is_client:
            from .telegram_automatic import automatic_receipts
            data['telegram']['automatic']=automatic_receipts(g.db,req,g.actor.id,current_app.config)
    return data


def document_dto(doc):
    return {'id': doc.id, 'type': doc.type, 'original_filename': doc.original_filename,
            'mime_type': doc.mime_type, 'page_count': doc.page_count, 'uploaded_by': doc.uploaded_by,
            'uploaded_at': doc.uploaded_at,
            'download_url': f'/api/requests/{doc.request_id}/documents/{doc.id}'}


def read_upload(file, *, allow_images=False):
    from .modules.upload.portal_adapter import prepare_document
    from .modules.upload.service import UploadError
    if not file or not file.filename:
        fail(422, 'FILE_REQUIRED', 'Dokumen diperlukan.')
    content = file.read(current_app.config['FILE_LIMIT'] + 1)
    if len(content) > current_app.config['FILE_LIMIT']:
        fail(422, 'FILE_TOO_LARGE', 'Maksimal 10 MB per berkas.')
    name = Path(file.filename.replace('\\', '/')).name[:255]
    try:
        return prepare_document(content, name, current_app.config, allow_images=allow_images)
    except UploadError as exc:
        fail(422, 'INVALID_DOCUMENT', str(exc))
    except OSError:
        fail(503, 'STORAGE_UNAVAILABLE', 'Penyimpanan dokumen belum tersedia.')
    except Exception:
        fail(422, 'INVALID_DOCUMENT', 'Dokumen tidak dapat dibaca. Unggah PDF atau foto yang valid.')


def save_upload(req, checked, kind, description=None):
    def persist(content, name, mime, suffix, document_kind, pages):
        doc_id = uid('doc')
        storage_key = doc_id + suffix
        path = Path(current_app.config['UPLOAD_DIR']) / storage_key
        if 'new_files' not in g:
            g.new_files = []
        with path.open('xb') as handle:
            g.new_files.append(path)
            handle.write(content)
        doc = Document(id=doc_id, request_id=req.id, type=document_kind, original_filename=name,
                       mime_type=mime, page_count=pages, storage_key=storage_key,
                       sha256=sha256(content).hexdigest(), uploaded_by=g.actor.id,
                       uploaded_at=now(), description=description)
        g.db.add(doc)
        g.db.flush()
        return doc
    doc = persist(checked.content, checked.filename, 'application/pdf', '.pdf', kind, checked.pages)
    if checked.original_content is not None:
        persist(checked.original_content, checked.original_filename, checked.original_mime,
                Path(checked.original_filename).suffix.lower(), 'SOURCE_IMAGE', 1)
        audit(g.db, 'IMAGE_CONVERTED_TO_PDF', g.actor.id, req.id,
              reason='Foto asli dipertahankan; PDF hasil konversi dipakai untuk ekstraksi dan review.')
    return doc


def task_complete(req):
    rows = invoices(req)
    return bool(rows) and all((review := latest_review(g.db, inv)) and review.decision == 'APPROVED' for inv in rows)


def require_task_staff():
    if not roles(g.db, g.actor) & {'FINANCE_REVIEWER', 'SYSTEM_ADMIN', 'SERVICE_LEAD'}:
        fail(403, 'REVIEWER_REQUIRED', 'Papan tugas hanya tersedia untuk tim AMIGA yang sudah aktif.')


def analysis_context(req, inv, question):
    validation = validation_for(req, inv)
    validation.pop('executed_at', None)  # A read timestamp must not invalidate an unchanged draft.
    return {'invoice_version': inv.current_version, 'fields': fields_for(g.db, inv),
            'validation': validation, 'field_sources': sources_for(g.db, inv),
            'documents': [{'id': d.id, 'type': d.type, 'sha256': d.sha256}
                          for d in g.db.scalars(select(Document).where(Document.request_id == req.id).order_by(Document.id))],
            'question': question}


def analysis_fingerprint(context):
    return sha256(json.dumps(context, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def previous_analysis(inv, fingerprint=None):
    rows = g.db.scalars(select(Audit).where(Audit.invoice_id == inv.id, Audit.action == 'REVIEW_AI_ANALYSIS')
                       .order_by(Audit.at.desc(), Audit.id.desc()))
    for row in rows:
        result = row.changes[0]['after']
        if result['version'] == inv.current_version and (fingerprint is None or result['fingerprint'] == fingerprint):
            return result
    return None


def release_inactive_pic(req):
    pic = g.db.get(User, req.pic_id) if req.pic_id else None
    if pic and (pic.account_status != 'ACTIVE' or 'FINANCE_REVIEWER' not in roles(g.db, pic)):
        previous_pic = req.pic_id
        req.pic_id = None
        audit(g.db, 'TASK_RELEASED_AFTER_REVISION', g.actor.id, req.id,
              reason='Revisi baru membutuhkan reviewer aktif',
              changes=[{'field': 'pic_id', 'before': previous_pic, 'after': None}])


def decide(request_id, invoice_id, decision):
    data = body()
    req, inv = mutation_invoice(request_id, invoice_id, data)
    require_review(req)
    if decision=='APPROVED' and not ready_for_review(g.db,req):
        fail(409,'UPLOADER_CONFIRMATION_REQUIRED','Uploader perlu mengonfirmasi seluruh versi invoice terbaru setelah analisis awal.')
    previous = latest_review(g.db, inv)
    if previous and previous.decision == 'APPROVED':
        fail(409, 'ALREADY_APPROVED', 'Versi ini telah disetujui. Buat revisi jika ada perubahan.')
    if previous and previous.decision == 'REJECTED':
        fail(409, 'REVISION_REQUIRED', 'Versi ini telah ditolak. Simpan revisi sebelum review berikutnya.')
    validation = validation_for(req, inv)
    why = reason(data) if decision == 'REJECTED' else None
    if decision == 'APPROVED' and not validation['valid']:
        fail(422, 'VALIDATION_BLOCKED', 'Selesaikan seluruh validasi BLOCK sebelum approval.')
    from .voucher_tax import applied_tax
    from .manual_pdf import latest_manual
    tax=applied_tax(g.db,inv,fields_for(g.db,inv))
    manual=latest_manual(g.db,inv)
    pdf_source=data.get('voucher_pdf_source','MANUAL' if manual else 'GENERATED')
    if decision=='APPROVED':
        if pdf_source not in ('MANUAL','GENERATED'):
            fail(422,'INVALID_VOUCHER_SOURCE','Pilih PDF manual atau voucher otomatis dari data tersimpan.')
        if pdf_source=='MANUAL' and not manual:
            fail(409,'MANUAL_PDF_CHANGED','PDF manual belum tersedia pada versi ini. Muat ulang.')
    if decision=='APPROVED' and tax:
        if type(data.get('expected_tax_revision')) is not int or data['expected_tax_revision']!=tax['revision']:
            fail(409,'TAX_CHANGED','Pajak voucher berubah. Muat ulang dan periksa nilai akhir sebelum menyetujui.')
        if pdf_source=='MANUAL' and manual and tax['edited_at'] and manual.created_at<tax['edited_at']:
            fail(409,'MANUAL_TAX_STALE','Pajak berubah setelah PDF final diunggah. Pilih voucher otomatis dari data terbaru atau unggah PDF final yang disesuaikan.')
        validation={**validation,'voucher_tax':tax}
    if decision=='APPROVED':
        validation={**validation,'voucher_pdf_source':pdf_source,'manual_pdf_id':manual.id if pdf_source=='MANUAL' else None}
    review = Review(id=uid('rev'), invoice_id=inv.id, version=inv.current_version, decision=decision,
                    actor_id=g.actor.id, created_at=now(), reason=why, validation_snapshot=validation)
    g.db.add(review)
    g.db.flush()
    if decision == 'APPROVED':
        voucher_id = uid('vch')
        pdf = render_voucher(fields_for(g.db, inv), voucher_id, inv.current_version,
                             g.actor.display_name, review.created_at,
                             requester_name=g.db.get(User, req.uploaded_by).display_name, purpose=req.request_type,tax=tax)
        if pdf_source=='MANUAL':pdf=bytes(manual.pdf)
        voucher=Voucher(id=voucher_id, invoice_id=inv.id, version=inv.current_version, review_id=review.id,
                         pdf=pdf, sha256=sha256(pdf).hexdigest(), created_at=now())
        g.db.add(voucher)
        from .telegram_automatic import enqueue_automatic
        enqueue_automatic(g.db,req,inv,voucher,g.actor.id,current_app.config)
    req.updated_at = now()
    audit(g.db, 'INVOICE_' + decision, g.actor.id, req.id, inv.id, why)
    g.db.flush()
    return ok(invoice_dto(req, inv))


