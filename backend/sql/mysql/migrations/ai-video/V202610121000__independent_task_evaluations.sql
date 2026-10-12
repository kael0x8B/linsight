-- Prerequisites: current ai-video schema with ai_task; MySQL 8.4. Run before new API deployment.
-- Additive only: no existing acceptance DAG is migrated or reclassified as measured evidence.
-- DDL acquires a metadata lock for the new table only; no existing table rewrite/data loss.
-- Retry-safe. Rollback app first and retain this table to preserve recorded evaluations.
-- Destructive rollback (only if empty or separately backed up): DROP TABLE ai_task_evaluation;
-- Permissions reuse ai-video:task:query/update; no new menu permission grant is required.
CREATE TABLE IF NOT EXISTS ai_task_evaluation (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL DEFAULT 0,
    task_id BIGINT NOT NULL,
    task_name VARCHAR(100) NOT NULL,
    config_version INT NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    source VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    dataset_version VARCHAR(100) NOT NULL,
    dataset_sha256 CHAR(64) NOT NULL,
    measured_at_millis BIGINT NOT NULL,
    evidence_ref VARCHAR(512) NOT NULL,
    measurement JSON NOT NULL,
    configuration_snapshot JSON NOT NULL,
    failed_checks JSON NOT NULL,
    creator VARCHAR(64) DEFAULT '',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updater VARCHAR(64) DEFAULT '',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted BIT(1) NOT NULL DEFAULT b'0',
    PRIMARY KEY (id),
    UNIQUE KEY uk_evaluation_request (tenant_id, task_id, request_id),
    KEY idx_evaluation_task (tenant_id, task_id, id),
    KEY idx_evaluation_status (tenant_id, status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='不可修改的人工视频评测；结果不代表生产发布批准';
