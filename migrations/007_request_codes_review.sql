-- AMIGA v7: human request codes; exact reviewer withholding correction.

BEGIN;

CREATE TABLE IF NOT EXISTS amiga_company_numbers (
	client_id VARCHAR(80) NOT NULL,
	number INTEGER NOT NULL,
	next_request INTEGER NOT NULL,
	PRIMARY KEY (client_id),
	FOREIGN KEY(client_id) REFERENCES amiga_clients (id),
	UNIQUE (number)
);

CREATE TABLE IF NOT EXISTS amiga_request_numbers (
	request_id VARCHAR(80) NOT NULL,
	client_id VARCHAR(80) NOT NULL,
	sequence INTEGER NOT NULL,
	code VARCHAR(160) NOT NULL,
	PRIMARY KEY (request_id),
	UNIQUE (client_id, sequence),
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id),
	FOREIGN KEY(client_id) REFERENCES amiga_clients (id),
	UNIQUE (code)
);

ALTER TABLE amiga_invoice_tax_plans ADD COLUMN IF NOT EXISTS withholding_amount TEXT;

UPDATE amiga_settings SET value='7' WHERE key='schema_version' AND value='6';

COMMIT;
