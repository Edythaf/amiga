-- AMIGA v4: versioned uploader confirmation, Luna agents and optional Telegram.

BEGIN;

CREATE TABLE IF NOT EXISTS amiga_telegram_challenges (
	user_id VARCHAR(80) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	expires_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id), 
	UNIQUE (token_hash)
);

CREATE TABLE IF NOT EXISTS amiga_telegram_links (
	user_id VARCHAR(80) NOT NULL, 
	chat_id VARCHAR(30) NOT NULL, 
	username VARCHAR(200), 
	verified_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id), 
	UNIQUE (chat_id)
);

CREATE TABLE IF NOT EXISTS amiga_agent_turns (
	id VARCHAR(80) NOT NULL, 
	user_id VARCHAR(80) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	request_id VARCHAR(80), 
	question TEXT NOT NULL, 
	result JSON, 
	input_hash VARCHAR(64) NOT NULL, 
	request_hash VARCHAR(64), 
	state VARCHAR(20) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	model VARCHAR(120), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id)
);

CREATE INDEX IF NOT EXISTS ix_amiga_agent_turns_user_id ON amiga_agent_turns (user_id);

CREATE TABLE IF NOT EXISTS amiga_request_sources (
	request_id VARCHAR(80) NOT NULL, 
	document_id VARCHAR(80) NOT NULL, 
	revision INTEGER NOT NULL, 
	PRIMARY KEY (request_id), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(document_id) REFERENCES amiga_documents (id)
);

CREATE TABLE IF NOT EXISTS amiga_invoice_assistance (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	input_hash VARCHAR(64), 
	result JSON, 
	model VARCHAR(120), 
	error_code VARCHAR(80), 
	attempts INTEGER NOT NULL, 
	job_token VARCHAR(80), 
	lease_until VARCHAR(30), 
	updated_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (invoice_id, version), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version)
);

CREATE TABLE IF NOT EXISTS amiga_uploader_confirmations (
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	input_hash VARCHAR(64) NOT NULL, 
	actor_id VARCHAR(80) NOT NULL, 
	item_count INTEGER NOT NULL, 
	confirmed_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (invoice_id, version, input_hash), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);

CREATE TABLE IF NOT EXISTS amiga_telegram_deliveries (
	id VARCHAR(80) NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	invoice_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	sender_id VARCHAR(80) NOT NULL, 
	recipient_id VARCHAR(80) NOT NULL, 
	chat_id VARCHAR(30) NOT NULL, 
	voucher_id VARCHAR(80), 
	body TEXT NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	created_at VARCHAR(30) NOT NULL, 
	expires_at VARCHAR(30) NOT NULL, 
	sent_at VARCHAR(30), 
	message_id VARCHAR(50), 
	error_code VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(invoice_id, version) REFERENCES amiga_invoice_versions (invoice_id, version), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(sender_id) REFERENCES amiga_users (id), 
	FOREIGN KEY(recipient_id) REFERENCES amiga_users (id), 
	FOREIGN KEY(voucher_id) REFERENCES amiga_vouchers (id)
);

UPDATE amiga_settings SET value='4' WHERE key='schema_version' AND value='3';

COMMIT;
