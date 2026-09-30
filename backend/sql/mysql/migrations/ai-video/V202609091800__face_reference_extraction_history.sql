-- Re-extraction appends a new reference and revokes the preceding one under the person row lock.
-- The original (tenant_id, entry_id) unique index prevented any retry/renewal after first enrollment.
-- Keep historical IDs intact for ai_entry_scan.reference_id and immutable scan snapshots.
-- Preconditions: ai_face_reference exists. No data deletion or status changes.
-- Forward-compatible rollback: retain these indexes; do not restore entry uniqueness once history exists.

SET @face_command_index_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_face_reference' AND INDEX_NAME = 'uk_face_reference_command');
SET @face_index_sql = IF(@face_command_index_exists = 0, 'ALTER TABLE ai_face_reference ADD UNIQUE INDEX uk_face_reference_command (tenant_id, validation_command_id)', 'SELECT 1');
PREPARE face_index_stmt FROM @face_index_sql;
EXECUTE face_index_stmt;
DEALLOCATE PREPARE face_index_stmt;

SET @face_entry_index_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_face_reference' AND INDEX_NAME = 'idx_face_reference_entry');
SET @face_index_sql = IF(@face_entry_index_exists = 0, 'ALTER TABLE ai_face_reference ADD INDEX idx_face_reference_entry (tenant_id, entry_id)', 'SELECT 1');
PREPARE face_index_stmt FROM @face_index_sql;
EXECUTE face_index_stmt;
DEALLOCATE PREPARE face_index_stmt;

SET @face_entry_unique_exists = (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_face_reference' AND INDEX_NAME = 'uk_face_reference_entry');
SET @face_index_sql = IF(@face_entry_unique_exists > 0, 'ALTER TABLE ai_face_reference DROP INDEX uk_face_reference_entry', 'SELECT 1');
PREPARE face_index_stmt FROM @face_index_sql;
EXECUTE face_index_stmt;
DEALLOCATE PREPARE face_index_stmt;
