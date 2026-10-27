-- AMIGA v5: company accounts (role + membership), immutable manual review PDFs.

BEGIN;

CREATE TABLE IF NOT EXISTS amiga_manual_review_pdfs (
	id VARCHAR(80) NOT NULL,
	invoice_id VARCHAR(80) NOT NULL,
	version INTEGER NOT NULL,
	uploaded_by VARCHAR(80) NOT NULL,
	filename VARCHAR(255) NOT NULL,
	pdf BYTEA NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	page_count INTEGER NOT NULL,
	created_at VARCHAR(30) NOT NULL,
	signature_state VARCHAR(30) NOT NULL,
	signature_result JSON,
	analysis_attempts INTEGER NOT NULL,
	analysis_started_at VARCHAR(30),
	PRIMARY KEY (id),
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version),
	FOREIGN KEY(uploaded_by) REFERENCES amiga_users (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_manual_review_pdfs_invoice_id ON amiga_manual_review_pdfs (invoice_id);

UPDATE amiga_settings SET value='5' WHERE key='schema_version' AND value='4';

COMMIT;
