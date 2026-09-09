-- Prerequisite: existing ai_task/node command schema; additive, no existing rows rewritten.
-- Developer-only active verification sessions. Images remain in private object storage.
-- Rollback: disable the new API/UI first; preserve this table for audit. No destructive rollback.
CREATE TABLE IF NOT EXISTS `ai_face_verification` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `camera_id` bigint NOT NULL,
  `node_id` bigint NOT NULL,
  `model_version_id` bigint NOT NULL,
  `command_id` varchar(36) NOT NULL,
  `reference_ref` varchar(1000) NOT NULL,
  `reference_sha256` varchar(64) NOT NULL,
  `parameters` json NOT NULL,
  `status` varchar(24) NOT NULL,
  `result` json DEFAULT NULL,
  `expires_time` datetime NOT NULL,
  `creator` varchar(64) DEFAULT '',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updater` varchar(64) DEFAULT '',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` bit(1) NOT NULL DEFAULT b'0',
  `tenant_id` bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_tenant_face_command` (`tenant_id`,`command_id`),
  KEY `idx_tenant_face_camera_time` (`tenant_id`,`camera_id`,`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='主动入口核验开发会话';
