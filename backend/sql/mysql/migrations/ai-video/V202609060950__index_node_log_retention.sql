-- Retention only: no business-data mutation. Index creation scans ai_node_log;
-- MySQL online DDL permits concurrent ingestion, but requires temporary disk space.
-- Forward repair/rollback: DROP INDEX idx_ai_node_log_retention ON ai_node_log.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE ai_node_log ADD INDEX idx_ai_node_log_retention (level, logged_at, id), ALGORITHM=INPLACE, LOCK=NONE;
