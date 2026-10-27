"""Relational workspace schema. Legacy queue_items/invoice_records are untouched.

Amounts are canonical decimal text, never binary floating point (including SQLite).
JSON is limited to raw extraction, validation snapshots, and audit payloads.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, Text, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, JSON, LargeBinary
from sqlalchemy.orm import DeclarativeBase


def uid(prefix):
    return prefix + '_' + uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = 'amiga_settings'
    key = Column(String(80), primary_key=True)
    value = Column(Text, nullable=False)


class User(Base):
    __tablename__ = 'amiga_users'
    id = Column(String(80), primary_key=True)
    email = Column(String(254), nullable=False, unique=True)
    google_sub = Column(String(255), unique=True)
    display_name = Column(String(200), nullable=False)
    account_status = Column(String(30), nullable=False)


class Role(Base):
    __tablename__ = 'amiga_user_roles'
    user_id = Column(ForeignKey('amiga_users.id'), primary_key=True)
    role = Column(String(40), primary_key=True)


class LocalCredential(Base):
    __tablename__ = 'amiga_local_credentials'
    user_id = Column(ForeignKey('amiga_users.id'), primary_key=True)
    password_hash = Column(Text, nullable=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(String(30))
    admin_bootstrap_allowed = Column(Integer, nullable=False, default=0)
    updated_at = Column(String(30), nullable=False, default=now)


class Client(Base):
    __tablename__ = 'amiga_clients'
    id = Column(String(80), primary_key=True)
    name = Column(String(200), nullable=False)


class Membership(Base):
    __tablename__ = 'amiga_memberships'
    user_id = Column(ForeignKey('amiga_users.id'), primary_key=True)
    client_id = Column(ForeignKey('amiga_clients.id'), primary_key=True)


class AuthSession(Base):
    __tablename__ = 'amiga_auth_sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey('amiga_users.id'), nullable=False, index=True)
    expires_at = Column(String(30), nullable=False)


class WorkRequest(Base):
    __tablename__ = 'amiga_requests'
    id = Column(String(80), primary_key=True)
    client_id = Column(ForeignKey('amiga_clients.id'), nullable=False, index=True)
    uploaded_by = Column(ForeignKey('amiga_users.id'), nullable=False)
    pic_id = Column(ForeignKey('amiga_users.id'))
    request_type = Column(String(120), nullable=False)
    channel = Column(String(50), nullable=False)
    request_date = Column(String(10), nullable=False)
    deadline = Column(String(10), nullable=False)
    updated_at = Column(String(30), nullable=False)
    processing_status = Column(String(30), nullable=False, default='QUEUED')
    stage = Column(String(80), nullable=False, default='Menunggu ekstraksi')
    error_code = Column(String(60))
    job_token = Column(String(80))
    lease_until = Column(String(30))


class RequestLifecycle(Base):
    """Administrative closure, separate from extraction/review/payment status.

    Absence means OPEN at revision 0, including requests predating schema v3.
    Writers must lock the parent WorkRequest before creating/updating this row.
    """
    __tablename__ = 'amiga_request_lifecycle'
    __table_args__ = (CheckConstraint("state IN ('OPEN', 'CLOSED')"),
                     CheckConstraint('revision >= 1'))
    request_id = Column(ForeignKey('amiga_requests.id'), primary_key=True)
    state = Column(String(10), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(String(30), nullable=False)
    actor_id = Column(ForeignKey('amiga_users.id'), nullable=False)


class Document(Base):
    __tablename__ = 'amiga_documents'
    id = Column(String(80), primary_key=True)
    request_id = Column(ForeignKey('amiga_requests.id'), nullable=False, index=True)
    type = Column(String(20), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(80), nullable=False)
    page_count = Column(Integer, nullable=False)
    storage_key = Column(String(100), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False, index=True)
    uploaded_by = Column(ForeignKey('amiga_users.id'), nullable=False)
    uploaded_at = Column(String(30), nullable=False)
    description = Column(Text)


class Extraction(Base):
    __tablename__ = 'amiga_extractions'
    id = Column(String(80), primary_key=True)
    request_id = Column(ForeignKey('amiga_requests.id'), nullable=False)
    document_id = Column(ForeignKey('amiga_documents.id'), nullable=False)
    created_at = Column(String(30), nullable=False)
    payload = Column(JSON, nullable=False)  # immutable source, including OCR text


class Invoice(Base):
    __tablename__ = 'amiga_invoices'
    __table_args__ = (UniqueConstraint('request_id', 'index'),)
    id = Column(String(80), primary_key=True)
    request_id = Column(ForeignKey('amiga_requests.id'), nullable=False, index=True)
    extraction_id = Column(ForeignKey('amiga_extractions.id'), nullable=False)
    index = Column(Integer, nullable=False)
    current_version = Column(Integer, nullable=False)
    active = Column(Integer, nullable=False, default=1)


HEADER_FIELDS = ('vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'currency',
                 'subtotal', 'invoice_discount_amount', 'invoice_tax_amount', 'total_amount',
                 'bank_name', 'account_number', 'account_holder')
ITEM_FIELDS = ('description', 'quantity', 'unit_price', 'discount_amount', 'tax_amount', 'line_total')
MONEY_FIELDS = ('subtotal', 'invoice_discount_amount', 'invoice_tax_amount', 'total_amount')


class InvoiceVersion(Base):
    __tablename__ = 'amiga_invoice_versions'
    invoice_id = Column(ForeignKey('amiga_invoices.id'), primary_key=True)
    version = Column(Integer, primary_key=True)
    created_by = Column(ForeignKey('amiga_users.id'))
    created_at = Column(String(30), nullable=False)
    reason = Column(Text, nullable=False)
    expected_item_count = Column(Integer)
    for _field in HEADER_FIELDS:
        locals()[_field] = Column(Text)


class LineItem(Base):
    __tablename__ = 'amiga_line_items'
    # Version FK is composite: prevent lines attaching to an unrelated revision.
    __table_args__ = (ForeignKeyConstraint(['invoice_id', 'version'],
                                         ['amiga_invoice_versions.invoice_id', 'amiga_invoice_versions.version']),)
    invoice_id = Column(String(80), primary_key=True)
    version = Column(Integer, primary_key=True)
    index = Column(Integer, primary_key=True)
    for _field in ITEM_FIELDS:
        locals()[_field] = Column(Text)


class FieldSource(Base):
    __tablename__ = 'amiga_field_sources'
    __table_args__ = (ForeignKeyConstraint(['invoice_id', 'version'],
                                         ['amiga_invoice_versions.invoice_id', 'amiga_invoice_versions.version']),)
    invoice_id = Column(String(80), primary_key=True)
    version = Column(Integer, primary_key=True)
    field = Column(String(120), primary_key=True)
    document_id = Column(ForeignKey('amiga_documents.id'), nullable=False)
    source_type = Column(String(20), nullable=False)
    page = Column(Integer)
    notes = Column(Text)


class Resolution(Base):
    __tablename__ = 'amiga_issue_resolutions'
    __table_args__ = (ForeignKeyConstraint(['invoice_id', 'version'],
                                         ['amiga_invoice_versions.invoice_id', 'amiga_invoice_versions.version']),)
    invoice_id = Column(ForeignKey('amiga_invoices.id'), primary_key=True)
    version = Column(Integer, primary_key=True)
    issue_code = Column(String(80), primary_key=True)
    actor_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(String(30), nullable=False)


class Review(Base):
    __tablename__ = 'amiga_reviews'
    __table_args__ = (ForeignKeyConstraint(['invoice_id', 'version'],
                                         ['amiga_invoice_versions.invoice_id', 'amiga_invoice_versions.version']),)
    id = Column(String(80), primary_key=True)
    invoice_id = Column(ForeignKey('amiga_invoices.id'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    decision = Column(String(20), nullable=False)
    actor_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    created_at = Column(String(30), nullable=False)
    reason = Column(Text)
    validation_snapshot = Column(JSON, nullable=False)


class Voucher(Base):
    __tablename__ = 'amiga_vouchers'
    __table_args__ = (UniqueConstraint('invoice_id', 'version'),)
    id = Column(String(80), primary_key=True)
    invoice_id = Column(ForeignKey('amiga_invoices.id'), nullable=False)
    version = Column(Integer, nullable=False)
    review_id = Column(ForeignKey('amiga_reviews.id'), nullable=False)
    pdf = Column(LargeBinary, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(String(30), nullable=False)


class ManualReviewPDF(Base):
    __tablename__ = 'amiga_manual_review_pdfs'
    __table_args__ = (ForeignKeyConstraint(['invoice_id','version'],['amiga_invoice_versions.invoice_id','amiga_invoice_versions.version']),)
    id = Column(String(80), primary_key=True)
    invoice_id = Column(String(80), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    uploaded_by = Column(ForeignKey('amiga_users.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    pdf = Column(LargeBinary, nullable=False)
    sha256 = Column(String(64), nullable=False)
    page_count = Column(Integer, nullable=False)
    created_at = Column(String(30), nullable=False, default=now)
    signature_state = Column(String(30), nullable=False, default='PENDING')
    signature_result = Column(JSON)
    analysis_attempts = Column(Integer, nullable=False, default=0)
    analysis_started_at = Column(String(30))


class Handover(Base):
    __tablename__ = 'amiga_handovers'
    id = Column(String(80), primary_key=True)
    voucher_id = Column(ForeignKey('amiga_vouchers.id'), nullable=False, index=True)
    actor_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    created_at = Column(String(30), nullable=False)


class Audit(Base):
    __tablename__ = 'amiga_audit'
    id = Column(String(80), primary_key=True)
    request_id = Column(ForeignKey('amiga_requests.id'), index=True)
    invoice_id = Column(ForeignKey('amiga_invoices.id'))
    actor_id = Column(ForeignKey('amiga_users.id'))
    action = Column(String(80), nullable=False)
    at = Column(String(30), nullable=False)
    reason = Column(Text)
    changes = Column(JSON, nullable=False)


class RequestSource(Base):
    __tablename__ = 'amiga_request_sources'
    request_id = Column(ForeignKey('amiga_requests.id'), primary_key=True)
    document_id = Column(ForeignKey('amiga_documents.id'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)


class InvoiceAssistance(Base):
    __tablename__ = 'amiga_invoice_assistance'
    __table_args__ = (ForeignKeyConstraint(['invoice_id','version'],['amiga_invoice_versions.invoice_id','amiga_invoice_versions.version']),)
    invoice_id = Column(String(80), primary_key=True)
    version = Column(Integer, primary_key=True)
    state = Column(String(20), nullable=False, default='PENDING')
    input_hash = Column(String(64))
    result = Column(JSON)
    model = Column(String(120))
    error_code = Column(String(80))
    attempts = Column(Integer, nullable=False, default=0)
    job_token = Column(String(80))
    lease_until = Column(String(30))
    updated_at = Column(String(30), nullable=False, default=now)


class UploaderConfirmation(Base):
    __tablename__ = 'amiga_uploader_confirmations'
    __table_args__ = (ForeignKeyConstraint(['invoice_id','version'],['amiga_invoice_versions.invoice_id','amiga_invoice_versions.version']),)
    invoice_id = Column(String(80), primary_key=True)
    version = Column(Integer, primary_key=True)
    input_hash = Column(String(64), primary_key=True)
    actor_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    item_count = Column(Integer, nullable=False)
    confirmed_at = Column(String(30), nullable=False, default=now)


class AgentTurn(Base):
    __tablename__ = 'amiga_agent_turns'
    id = Column(String(80), primary_key=True)
    user_id = Column(ForeignKey('amiga_users.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    request_id = Column(ForeignKey('amiga_requests.id'))
    question = Column(Text, nullable=False)
    result = Column(JSON)
    input_hash = Column(String(64), nullable=False)
    request_hash = Column(String(64))
    state = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(String(30), nullable=False, default=now)
    model = Column(String(120))


class TelegramLink(Base):
    __tablename__ = 'amiga_telegram_links'
    user_id = Column(ForeignKey('amiga_users.id'), primary_key=True)
    chat_id = Column(String(30), nullable=False, unique=True)
    username = Column(String(200))
    verified_at = Column(String(30), nullable=False, default=now)


class TelegramChallenge(Base):
    __tablename__ = 'amiga_telegram_challenges'
    user_id = Column(ForeignKey('amiga_users.id'), primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(String(30), nullable=False)


class TelegramDelivery(Base):
    __tablename__ = 'amiga_telegram_deliveries'
    __table_args__ = (ForeignKeyConstraint(['invoice_id','version'],['amiga_invoice_versions.invoice_id','amiga_invoice_versions.version']),)
    id = Column(String(80), primary_key=True)
    request_id = Column(ForeignKey('amiga_requests.id'), nullable=False)
    invoice_id = Column(String(80), nullable=False)
    version = Column(Integer, nullable=False)
    sender_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    recipient_id = Column(ForeignKey('amiga_users.id'), nullable=False)
    chat_id = Column(String(30), nullable=False)
    voucher_id = Column(ForeignKey('amiga_vouchers.id'))
    body = Column(Text, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    state = Column(String(20), nullable=False, default='DRAFT')
    created_at = Column(String(30), nullable=False, default=now)
    expires_at = Column(String(30), nullable=False)
    sent_at = Column(String(30))
    message_id = Column(String(50))
    error_code = Column(String(80))


class TelegramAutomaticDelivery(Base):
    __tablename__ = 'amiga_telegram_automatic_deliveries'
    __table_args__ = (UniqueConstraint('voucher_id','recipient_id'),)
    delivery_id = Column(ForeignKey('amiga_telegram_deliveries.id'), primary_key=True)
    voucher_id = Column(ForeignKey('amiga_vouchers.id'), nullable=False)
    recipient_id = Column(ForeignKey('amiga_users.id'), nullable=False)


class UploadBatch(Base):
    __tablename__ = 'amiga_upload_batches'
    __table_args__ = (UniqueConstraint('uploaded_by','idempotency_key'),)
    id = Column(String(80), primary_key=True)
    client_id = Column(ForeignKey('amiga_clients.id'), nullable=False)
    uploaded_by = Column(ForeignKey('amiga_users.id'), nullable=False)
    idempotency_key = Column(String(80), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    created_at = Column(String(30), nullable=False, default=now)


class RequestIntake(Base):
    __tablename__ = 'amiga_request_intakes'
    request_id = Column(ForeignKey('amiga_requests.id'), primary_key=True)
    batch_id = Column(ForeignKey('amiga_upload_batches.id'), nullable=False, index=True)
    source_group = Column(String(80), nullable=False, index=True)
    invoice_number = Column(String(2000))
    vendor_name = Column(String(2000))
    selected = Column(Integer, nullable=False, default=0)


class InvoiceTaxPlan(Base):
    __tablename__ = 'amiga_invoice_tax_plans'
    __table_args__ = (ForeignKeyConstraint(['invoice_id','version'],['amiga_invoice_versions.invoice_id','amiga_invoice_versions.version']),)
    invoice_id = Column(String(80), primary_key=True)
    version = Column(Integer, primary_key=True)
    revision = Column(Integer, nullable=False, default=0)
    vat_mode = Column(String(20), nullable=False, default='KEEP')
    vat_rate = Column(Text, nullable=False, default='0')
    vat_base = Column(Text, nullable=False, default='0')
    withholding_mode = Column(String(20), nullable=False, default='KEEP')
    withholding_kind = Column(String(80), nullable=False, default='PPh')
    withholding_rate = Column(Text, nullable=False, default='0')
    withholding_base = Column(Text, nullable=False, default='0')
    source_withholding = Column(Text, nullable=False, default='0')
    withholding_amount = Column(Text)  # Optional exact reviewer correction, not an AI lock.
    note = Column(Text, nullable=False, default='')
    edited_by = Column(ForeignKey('amiga_users.id'))
    edited_at = Column(String(30))
    ai_state = Column(String(20), nullable=False, default='PENDING')
    ai_result = Column(JSON)
    ai_attempts = Column(Integer, nullable=False, default=0)
    ai_started_at = Column(String(30))
    ai_input_hash = Column(String(64))


class CompanyNumber(Base):
    __tablename__ = 'amiga_company_numbers'
    client_id = Column(ForeignKey('amiga_clients.id'), primary_key=True)
    number = Column(Integer, nullable=False, unique=True)
    next_request = Column(Integer, nullable=False, default=1)


class RequestNumber(Base):
    __tablename__ = 'amiga_request_numbers'
    __table_args__ = (UniqueConstraint('client_id', 'sequence'),)
    request_id = Column(ForeignKey('amiga_requests.id'), primary_key=True)
    client_id = Column(ForeignKey('amiga_clients.id'), nullable=False)
    sequence = Column(Integer, nullable=False)
    code = Column(String(160), nullable=False, unique=True)


WORKFLOW_TABLES = {'amiga_request_sources','amiga_invoice_assistance','amiga_uploader_confirmations',
                   'amiga_agent_turns','amiga_telegram_links','amiga_telegram_challenges','amiga_telegram_deliveries'}
