-- AMIGA workspace schema v1. Existing legacy tables are untouched.

BEGIN;

CREATE TABLE IF NOT EXISTS amiga_clients (
	id VARCHAR(80) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS amiga_settings (
	key VARCHAR(80) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS amiga_users (
	id VARCHAR(80) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	google_sub VARCHAR(255), 
	display_name VARCHAR(200) NOT NULL, 
	account_status VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	UNIQUE (google_sub)
);

CREATE TABLE IF NOT EXISTS amiga_auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(80) NOT NULL, 
	expires_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_auth_sessions_user_id ON amiga_auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS amiga_memberships (
	user_id VARCHAR(80) NOT NULL, 
	client_id VARCHAR(80) NOT NULL, 
	PRIMARY KEY (user_id, client_id), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id), 
	FOREIGN KEY(client_id) REFERENCES amiga_clients (id)
);

CREATE TABLE IF NOT EXISTS amiga_requests (
	id VARCHAR(80) NOT NULL, 
	client_id VARCHAR(80) NOT NULL, 
	uploaded_by VARCHAR(80) NOT NULL, 
	pic_id VARCHAR(80), 
	request_type VARCHAR(120) NOT NULL, 
	channel VARCHAR(50) NOT NULL, 
	request_date VARCHAR(10) NOT NULL, 
	deadline VARCHAR(10) NOT NULL, 
	updated_at VARCHAR(30) NOT NULL, 
	processing_status VARCHAR(30) NOT NULL, 
	stage VARCHAR(80) NOT NULL, 
	error_code VARCHAR(60), 
	job_token VARCHAR(80), 
	lease_until VARCHAR(30), 
	PRIMARY KEY (id), 
	FOREIGN KEY(client_id) REFERENCES amiga_clients (id), 
	FOREIGN KEY(uploaded_by) REFERENCES amiga_users (id), 
	FOREIGN KEY(pic_id) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_requests_client_id ON amiga_requests (client_id);

CREATE TABLE IF NOT EXISTS amiga_user_roles (
	user_id VARCHAR(80) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	PRIMARY KEY (user_id, role), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id)
);

CREATE TABLE IF NOT EXISTS amiga_documents (
	id VARCHAR(80) NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	mime_type VARCHAR(80) NOT NULL, 
	page_count INTEGER NOT NULL, 
	storage_key VARCHAR(100) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	uploaded_by VARCHAR(80) NOT NULL, 
	uploaded_at VARCHAR(30) NOT NULL, 
	description TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	UNIQUE (storage_key), 
	FOREIGN KEY(uploaded_by) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_documents_request_id ON amiga_documents (request_id);

CREATE INDEX IF NOT EXISTS ix_amiga_documents_sha256 ON amiga_documents (sha256);

CREATE TABLE IF NOT EXISTS amiga_extractions (
	id VARCHAR(80) NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	document_id VARCHAR(80) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	payload JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(document_id) REFERENCES amiga_documents (id)
);

CREATE TABLE IF NOT EXISTS amiga_invoices (
	id VARCHAR(80) NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	extraction_id VARCHAR(80) NOT NULL, 
	index INTEGER NOT NULL, 
	current_version INTEGER NOT NULL, 
	active INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (request_id, index), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(extraction_id) REFERENCES amiga_extractions (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_invoices_request_id ON amiga_invoices (request_id);

CREATE TABLE IF NOT EXISTS amiga_audit (
	id VARCHAR(80) NOT NULL, 
	request_id VARCHAR(80), 
	invoice_id VARCHAR(80), 
	actor_id VARCHAR(80), 
	action VARCHAR(80) NOT NULL, 
	at VARCHAR(30) NOT NULL, 
	reason TEXT, 
	changes JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(invoice_id) REFERENCES amiga_invoices (id), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_audit_request_id ON amiga_audit (request_id);

CREATE TABLE IF NOT EXISTS amiga_invoice_versions (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	created_by VARCHAR(80), 
	created_at VARCHAR(30) NOT NULL, 
	reason TEXT NOT NULL, 
	expected_item_count INTEGER, 
	vendor_name TEXT, 
	invoice_number TEXT, 
	invoice_date TEXT, 
	due_date TEXT, 
	currency TEXT, 
	subtotal TEXT, 
	invoice_discount_amount TEXT, 
	invoice_tax_amount TEXT, 
	total_amount TEXT, 
	bank_name TEXT, 
	account_number TEXT, 
	account_holder TEXT, 
	PRIMARY KEY (invoice_id, version), 
	FOREIGN KEY(invoice_id) REFERENCES amiga_invoices (id), 
	FOREIGN KEY(created_by) REFERENCES amiga_users (id)
);

CREATE TABLE IF NOT EXISTS amiga_field_sources (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	field VARCHAR(120) NOT NULL, 
	document_id VARCHAR(80) NOT NULL, 
	source_type VARCHAR(20) NOT NULL, 
	page INTEGER, 
	notes TEXT, 
	PRIMARY KEY (invoice_id, version, field), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version), 
	FOREIGN KEY(document_id) REFERENCES amiga_documents (id)
);

CREATE TABLE IF NOT EXISTS amiga_issue_resolutions (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	issue_code VARCHAR(80) NOT NULL, 
	actor_id VARCHAR(80) NOT NULL, 
	reason TEXT NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (invoice_id, version, issue_code), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version), 
	FOREIGN KEY(invoice_id) REFERENCES amiga_invoices (id), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);

CREATE TABLE IF NOT EXISTS amiga_line_items (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	index INTEGER NOT NULL, 
	description TEXT, 
	quantity TEXT, 
	unit_price TEXT, 
	discount_amount TEXT, 
	tax_amount TEXT, 
	line_total TEXT, 
	PRIMARY KEY (invoice_id, version, index), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version)
);

CREATE TABLE IF NOT EXISTS amiga_reviews (
	id VARCHAR(80) NOT NULL, 
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	decision VARCHAR(20) NOT NULL, 
	actor_id VARCHAR(80) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	reason TEXT, 
	validation_snapshot JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version), 
	FOREIGN KEY(invoice_id) REFERENCES amiga_invoices (id), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_reviews_invoice_id ON amiga_reviews (invoice_id);

CREATE TABLE IF NOT EXISTS amiga_vouchers (
	id VARCHAR(80) NOT NULL, 
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	review_id VARCHAR(80) NOT NULL, 
	pdf BYTEA NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (invoice_id, version), 
	FOREIGN KEY(invoice_id) REFERENCES amiga_invoices (id), 
	FOREIGN KEY(review_id) REFERENCES amiga_reviews (id)
);

CREATE TABLE IF NOT EXISTS amiga_handovers (
	id VARCHAR(80) NOT NULL, 
	voucher_id VARCHAR(80) NOT NULL, 
	actor_id VARCHAR(80) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(voucher_id) REFERENCES amiga_vouchers (id), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_handovers_voucher_id ON amiga_handovers (voucher_id);

INSERT INTO amiga_settings (key,value) VALUES ('schema_version','1'),('bootstrap_consumed','0') ON CONFLICT (key) DO NOTHING;

COMMIT;
