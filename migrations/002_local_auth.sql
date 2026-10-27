-- AMIGA v2: local bcrypt credentials. Existing users/documents are preserved.
BEGIN;
CREATE TABLE IF NOT EXISTS amiga_local_credentials (
	user_id VARCHAR(80) NOT NULL, 
	password_hash TEXT NOT NULL, 
	failed_attempts INTEGER NOT NULL, 
	locked_until VARCHAR(30), 
	admin_bootstrap_allowed INTEGER NOT NULL, 
	updated_at VARCHAR(30) NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES amiga_users (id)
);
UPDATE amiga_settings SET value='2' WHERE key='schema_version' AND value='1';
COMMIT;
