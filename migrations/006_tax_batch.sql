-- AMIGA v6: separate invoice intake tasks and versioned voucher tax adjustments.

BEGIN;

CREATE TABLE IF NOT EXISTS amiga_upload_batches (
	id VARCHAR(80) NOT NULL,
	client_id VARCHAR(80) NOT NULL,
	uploaded_by VARCHAR(80) NOT NULL,
	idempotency_key VARCHAR(80) NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	created_at VARCHAR(30) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (uploaded_by, idempotency_key),
	FOREIGN KEY(client_id) REFERENCES amiga_clients (id),
	FOREIGN KEY(uploaded_by) REFERENCES amiga_users (id)
);

CREATE TABLE IF NOT EXISTS amiga_request_intakes (
	request_id VARCHAR(80) NOT NULL,
	batch_id VARCHAR(80) NOT NULL,
	source_group VARCHAR(80) NOT NULL,
	invoice_number VARCHAR(2000),
	vendor_name VARCHAR(2000),
	selected INTEGER NOT NULL,
	PRIMARY KEY (request_id),
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id),
	FOREIGN KEY(batch_id) REFERENCES amiga_upload_batches (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_request_intakes_source_group ON amiga_request_intakes (source_group);

CREATE INDEX IF NOT EXISTS ix_amiga_request_intakes_batch_id ON amiga_request_intakes (batch_id);

CREATE TABLE IF NOT EXISTS amiga_invoice_tax_plans (
	invoice_id VARCHAR(80) NOT NULL,
	version INTEGER NOT NULL,
	revision INTEGER NOT NULL,
	vat_mode VARCHAR(20) NOT NULL,
	vat_rate TEXT NOT NULL,
	vat_base TEXT NOT NULL,
	withholding_mode VARCHAR(20) NOT NULL,
	withholding_kind VARCHAR(80) NOT NULL,
	withholding_rate TEXT NOT NULL,
	withholding_base TEXT NOT NULL,
	source_withholding TEXT NOT NULL,
	note TEXT NOT NULL,
	edited_by VARCHAR(80),
	edited_at VARCHAR(30),
	ai_state VARCHAR(20) NOT NULL,
	ai_result JSON,
	ai_attempts INTEGER NOT NULL,
	ai_started_at VARCHAR(30),
	ai_input_hash VARCHAR(64),
	PRIMARY KEY (invoice_id, version),
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version),
	FOREIGN KEY(edited_by) REFERENCES amiga_users (id)
);

UPDATE amiga_settings SET value='6' WHERE key='schema_version' AND value='5';

COMMIT;
