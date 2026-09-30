-- Apply with a migration runner in production. SQLAlchemy creates the equivalent
-- local SQLite schema for development and integration tests.
CREATE TABLE accounts (
  id VARCHAR(36) PRIMARY KEY,
  email VARCHAR(320) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  quota_bytes BIGINT NOT NULL
);
CREATE TABLE api_keys (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  key_hash VARCHAR(128) UNIQUE NOT NULL,
  prefix VARCHAR(32) NOT NULL,
  environment VARCHAR(8) NOT NULL,
  status VARCHAR(16) NOT NULL,
  scopes_json TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  last_used_at TIMESTAMP NULL
);
CREATE TABLE sessions (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  token_hash VARCHAR(128) UNIQUE NOT NULL,
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  revoked_at TIMESTAMP NULL
);
CREATE TABLE files (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  storage_key VARCHAR(512) UNIQUE NOT NULL,
  filename VARCHAR(512) NOT NULL,
  content_type VARCHAR(128) NOT NULL,
  size_bytes BIGINT NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  status VARCHAR(16) NOT NULL,
  error TEXT NULL,
  summary_json TEXT NULL,
  parts_json TEXT NULL,
  idempotency_key VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE TABLE jobs (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  file_id VARCHAR(36) NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  kind VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,
  idempotency_key VARCHAR(255) NULL,
  payload_json TEXT NULL,
  result_file_id VARCHAR(36) NULL,
  error TEXT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE TABLE request_logs (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NULL,
  api_key_id VARCHAR(36) NULL,
  request_id VARCHAR(64) NOT NULL,
  method VARCHAR(12) NOT NULL,
  path VARCHAR(512) NOT NULL,
  status_code INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE audit_logs (
  id VARCHAR(36) PRIMARY KEY,
  owner_id VARCHAR(36) NOT NULL,
  action VARCHAR(80) NOT NULL,
  target_type VARCHAR(40) NOT NULL,
  target_id VARCHAR(36) NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE INDEX files_owner_id_idx ON files(owner_id);
CREATE INDEX jobs_status_idx ON jobs(status, created_at);
CREATE INDEX request_logs_key_time_idx ON request_logs(api_key_id, created_at);
