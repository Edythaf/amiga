-- AMIGA v8: opt-in automatic official voucher delivery outbox.
BEGIN;
CREATE TABLE IF NOT EXISTS amiga_telegram_automatic_deliveries (
	delivery_id VARCHAR(80) NOT NULL,
	voucher_id VARCHAR(80) NOT NULL,
	recipient_id VARCHAR(80) NOT NULL,
	PRIMARY KEY (delivery_id),
	UNIQUE (voucher_id, recipient_id),
	FOREIGN KEY(delivery_id) REFERENCES amiga_telegram_deliveries (id),
	FOREIGN KEY(voucher_id) REFERENCES amiga_vouchers (id),
	FOREIGN KEY(recipient_id) REFERENCES amiga_users (id)
);
UPDATE amiga_settings SET value='8' WHERE key='schema_version' AND value='7';
COMMIT;
