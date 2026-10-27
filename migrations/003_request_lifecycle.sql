-- AMIGA v3: administrative closure. Existing requests default to OPEN.
BEGIN;
CREATE TABLE IF NOT EXISTS amiga_request_lifecycle (
	request_id VARCHAR(80) NOT NULL, 
	state VARCHAR(10) NOT NULL, 
	revision INTEGER NOT NULL, 
	updated_at VARCHAR(30) NOT NULL, 
	actor_id VARCHAR(80) NOT NULL, 
	PRIMARY KEY (request_id), 
	CHECK (state IN ('OPEN', 'CLOSED')), 
	CHECK (revision >= 1), 
	FOREIGN KEY(request_id) REFERENCES amiga_requests (id), 
	FOREIGN KEY(actor_id) REFERENCES amiga_users (id)
);
UPDATE amiga_settings SET value='3' WHERE key='schema_version' AND value='2';
COMMIT;
