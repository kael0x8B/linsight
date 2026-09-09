-- Prerequisite: V202609081100 and reference library/event schemas.
-- Additive entrance configuration, consent references and audit sessions. No data deletion.
-- Event task/pipeline/rule IDs become nullable for explicit entrance sessions (not fake task IDs).
-- MODIFY may acquire a metadata lock; run during a quiet deployment window.
-- Rollback: disable entrance APIs/UI; retain audit/reference rows. Do not drop populated tables.
CREATE TABLE IF NOT EXISTS ai_face_reference (
 id bigint NOT NULL AUTO_INCREMENT, entry_id bigint NOT NULL, library_id bigint NOT NULL,
 model_version_id bigint NOT NULL, object_ref varchar(1000) NOT NULL, sha256 char(64) NOT NULL,
 validation_status varchar(24) NOT NULL, validation_command_id varchar(36) NOT NULL,
 valid_until datetime NOT NULL, creator varchar(64) DEFAULT '', create_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updater varchar(64) DEFAULT '', update_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 deleted bit(1) NOT NULL DEFAULT b'0', tenant_id bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(id), UNIQUE KEY uk_face_reference_entry(tenant_id,entry_id), KEY idx_face_reference_library(tenant_id,library_id,validation_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_entry_access (
 id bigint NOT NULL AUTO_INCREMENT, name varchar(100) NOT NULL, camera_id bigint NOT NULL,
 node_id bigint NOT NULL, library_id bigint NOT NULL, model_version_id bigint NOT NULL,
 parameters json NOT NULL, enabled bit(1) NOT NULL DEFAULT b'0', version int NOT NULL DEFAULT 1,
 creator varchar(64) DEFAULT '', create_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updater varchar(64) DEFAULT '', update_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 deleted bit(1) NOT NULL DEFAULT b'0', tenant_id bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(id), KEY idx_entry_camera(tenant_id,camera_id), KEY idx_entry_library(tenant_id,library_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ai_entry_scan (
 id bigint NOT NULL AUTO_INCREMENT, entry_access_id bigint NULL, reference_id bigint NULL,
 camera_id bigint NOT NULL, node_id bigint NOT NULL, model_version_id bigint NOT NULL,
 command_id varchar(36) NOT NULL, mode varchar(16) NOT NULL, status varchar(24) NOT NULL,
 snapshot json NOT NULL, result json NULL, event_id bigint NULL, expires_time datetime NOT NULL,
 creator varchar(64) DEFAULT '', create_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updater varchar(64) DEFAULT '', update_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 deleted bit(1) NOT NULL DEFAULT b'0', tenant_id bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(id), UNIQUE KEY uk_entry_scan_command(tenant_id,command_id), KEY idx_entry_scan_time(tenant_id,entry_access_id,create_time),
 KEY idx_entry_scan_reference(tenant_id,reference_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE ai_event MODIFY task_id bigint NULL COMMENT '普通任务编号；主动入口会话使用task_snapshot中的入口编号',
 MODIFY algorithm_id bigint NULL, MODIFY pipeline_version_id bigint NULL,
 MODIFY rule_id bigint NULL, MODIFY rule_version_id bigint NULL;
