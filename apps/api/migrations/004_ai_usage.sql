-- Atomic per-account UTC-day AI request reservations and coarse usage metrics.
-- This limits request count; provider-billed token/currency accounting must
-- be added after live provider response schemas and prices are validated.
CREATE TABLE ai_daily_usage (
  owner_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  day VARCHAR(10) NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 0,
  prompt_chars INTEGER NOT NULL DEFAULT 0,
  image_bytes INTEGER NOT NULL DEFAULT 0,
  output_chars INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (owner_id, day)
);
