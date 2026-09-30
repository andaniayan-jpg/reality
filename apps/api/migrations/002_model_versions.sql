-- Immutable source/derived model lineage used by API and MCP edit undo.
ALTER TABLE files ADD COLUMN parent_file_id VARCHAR(36);
CREATE INDEX IF NOT EXISTS ix_files_parent_file_id ON files (parent_file_id);
