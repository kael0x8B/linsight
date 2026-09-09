-- Distinguish older streamed records from records that truly never collected SSH output.
-- Forward-only metadata correction; preserves every byte of existing output.
UPDATE ai_node_deployment
SET log_status = CASE WHEN status IN ('QUEUED', 'RUNNING') THEN 'COLLECTING' ELSE 'COMPLETE' END
WHERE log_status = 'LEGACY' AND output_log IS NOT NULL AND CHAR_LENGTH(output_log) > 0;
