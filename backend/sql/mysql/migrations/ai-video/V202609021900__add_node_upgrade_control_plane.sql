-- LInsight Story 12: node upgrade/rollback control-plane state and visible P20/P21 entry.
-- Preconditions: V202609021800 has completed; ai_edge_node and ai_node_command exist.
-- Data/lock impact: creates one empty tenant table and updates six menu/role rows only.
-- Rollback: disable menu 7020, delete role/menu row 7025, then drop ai_node_upgrade after
-- preserving its audit history. Existing Edge release files are not deleted by DB rollback.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_node_upgrade` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '节点升级操作编号',
  `node_id` bigint NOT NULL COMMENT '边缘节点编号',
  `action` varchar(16) NOT NULL COMMENT '动作：UPGRADE/ROLLBACK',
  `target_version` varchar(64) NULL COMMENT '目标 Agent 版本',
  `package_ref` varchar(1024) NULL COMMENT '升级包对象存储内部引用',
  `package_name` varchar(255) NULL COMMENT '原始升级包名称',
  `sha256` char(64) NULL COMMENT '升级包 SHA-256',
  `signature` char(64) NULL COMMENT 'version:sha256 的 HMAC-SHA256 签名',
  `command_id` varchar(36) NOT NULL COMMENT '耐久命令编号',
  `config_version` int NOT NULL COMMENT '节点升级配置版本',
  `status` varchar(16) NOT NULL COMMENT 'QUEUED/RUNNING/SUCCEEDED/FAILED',
  `stage` varchar(32) NULL COMMENT '执行阶段',
  `diagnostic_id` varchar(36) NULL COMMENT 'Agent 诊断编号',
  `result_summary` json NULL COMMENT '脱敏执行结果',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `finish_time` datetime NULL COMMENT '完成时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_node_upgrade_command` (`command_id`),
  KEY `idx_ai_node_upgrade_tenant_node_time` (`tenant_id`, `node_id`, `create_time`),
  KEY `idx_ai_node_upgrade_tenant_status` (`tenant_id`, `status`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点升级与回滚操作';

UPDATE `system_menu`
SET `status` = 0, `visible` = b'1', `updater` = 'system', `update_time` = CURRENT_TIMESTAMP
WHERE `id` = 7020;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7025, '节点回滚', 'ai-video:node:rollback', 3, 5, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (
  SELECT 7020 AS menu_id UNION ALL SELECT 7021 UNION ALL SELECT 7022
  UNION ALL SELECT 7023 UNION ALL SELECT 7024 UNION ALL SELECT 7025
) permissions;
