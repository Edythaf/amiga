"""One source of truth for administrative state and human work progress."""
from .application import ApiFault
from .models import RequestLifecycle


def lifecycle(db, req):
    row = db.get(RequestLifecycle, req.id)
    return {'state': row.state if row else 'OPEN', 'revision': row.revision if row else 0,
            'updated_at': row.updated_at if row else None,
            'actor_id': row.actor_id if row else None}


def require_open(db, req):
    if lifecycle(db, req)['state'] == 'CLOSED':
        raise ApiFault(409, 'REQUEST_CLOSED', 'Pekerjaan sudah ditutup. Klien perlu meminta revisi untuk membukanya kembali.')


def progress(req, status, invoice_rows, state):
    if state == 'CLOSED':
        return 'CLOSED'
    if status in ('AMIGA_REVIEWED', 'SENT_TO_CLIENT'):
        return 'AWAITING_CLIENT_CLOSE' if status == 'SENT_TO_CLIENT' else 'VOUCHER_READY'
    if req.processing_status in ('QUEUED', 'PROCESSING'):
        return 'PROCESSING'
    if req.processing_status == 'FAILED':
        return 'EXTRACTION_FAILED'
    if any(row['review_status'] == 'REJECTED' for row in invoice_rows):
        return 'WAITING_CLIENT'
    if any(row['review_status']!='APPROVED' and not row.get('uploader_confirmation',{}).get('confirmed') for row in invoice_rows):
        return 'WAITING_UPLOADER'
    return 'IN_REVIEW' if req.pic_id else 'UNCLAIMED'


def client_actions(is_client, status, state):
    if not is_client:
        return []
    if state == 'CLOSED':
        return ['REQUEST_REVISION']
    actions = ['CLOSE'] if status == 'SENT_TO_CLIENT' else []
    if status in ('AMIGA_REVIEWED', 'SENT_TO_CLIENT'):
        actions.append('REQUEST_REVISION')
    return actions
