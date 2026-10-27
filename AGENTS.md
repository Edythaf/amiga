# AMIGA contributor instructions

Use backend/app.py and backend/modules/{auth,admin,upload} as the active application; backend/api.py and processing.py are compatibility imports. Four portals: /client for company clients, /uploader, /reviewer, /admin. Company clients are separate COMPANY_CLIENT accounts linked to company IDs by admin.

Preserve bcrypt/JWT/session revocation, CSRF, server tenant boundaries and independent reviewer/PIC checks. SYSTEM_ADMIN cannot approve vouchers. Uploader must explicitly confirm each current invoice fingerprint after initial AI analysis. Preserve all source files, extraction output, invoice versions, issued PDF blobs and audit history. Never auto-approve, silently confirm uploads, reset accounts, or publish source documents/secrets.

Use exact Decimal/HALF_UP math with tests/fixtures contracts. Reviewer additions may differ from the source PDF with explicit provenance/reason. Tax plans remain separate and editable; no doubled withholding/VAT. Official PDFs are immutable. Signature analysis is advisory. Human request codes supplement stable UUID primary keys; never replace foreign keys with human labels.

Telegram automatic delivery is opt-in per verified company recipient. Queue approval and outbox atomically; send official immutable bytes after commit. UNKNOWN is terminal, never auto-retry. Sending does not accept/close the service or create a client handover. Preserve manual preview/consent and duplicate prevention.

Keep API credentials, .env, databases, storage, backups, runtime logs and generated personal test artifacts outside Git. Do not import local accounts/documents into server deployments. PostgreSQL requires reviewed sequential migrations; back up before deployment. Existing source publication does not authorize future deployments or visibility changes.

Maintain light/dark themes and reduced motion. Fonts/type scale belong in typography.css; theme colors in amiga-theme.css. Vendor PDF.js main/worker and LICENSE must ship together. Run backend unittest suite, frontend Node tests and build for related changes; real paid AI or Telegram tests require explicit user instruction and authorized recipients.
