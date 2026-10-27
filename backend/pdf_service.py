"""Portal DTO adapter; the supplied voucher_service is the sole PDF renderer."""
from io import BytesIO
from .voucher_service import generate_voucher_pdf
from .modules.upload.portal_adapter import to_source_invoice

DISCLAIMER = ('Voucher ini telah ditinjau oleh AMIGA. Persetujuan pembayaran dan '
              'pelaksanaan pembayaran merupakan kewenangan klien.')


def render_voucher(fields, voucher_id, version, reviewer_name=None, reviewed_at=None, *, requester_name=None, purpose=None,tax=None):
    output = BytesIO()
    source_fields = to_source_invoice(fields)
    source_fields['purpose'] = purpose
    if tax:
        source_fields['voucher_tax']=tax
        source_fields['total_amount']=tax['calculated']['net_payable']
    generate_voucher_pdf(source_fields, output, voucher_id, requester_name=requester_name,
                         approver_name=reviewer_name, draft=not reviewer_name,
                         version=version, reviewed_at=reviewed_at)
    return output.getvalue()
