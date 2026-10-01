-- Phone-only accounts retain the existing account/key/session ownership model.
ALTER TABLE accounts ALTER COLUMN email DROP NOT NULL;
ALTER TABLE accounts ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE accounts ADD COLUMN phone_e164 VARCHAR(16) UNIQUE;
CREATE INDEX IF NOT EXISTS ix_accounts_phone_e164 ON accounts (phone_e164);

CREATE TABLE phone_start_attempts (
  id VARCHAR(36) PRIMARY KEY,
  phone_hash VARCHAR(128) NOT NULL,
  ip_hash VARCHAR(128) NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_phone_start_attempts_phone_hash ON phone_start_attempts (phone_hash);
CREATE INDEX IF NOT EXISTS ix_phone_start_attempts_ip_hash ON phone_start_attempts (ip_hash);
CREATE INDEX IF NOT EXISTS ix_phone_start_attempts_created_at ON phone_start_attempts (created_at);
