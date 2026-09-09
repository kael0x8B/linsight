-- LInsight P24: typed AI global settings, immutable versions and task delivery snapshots.
-- Data/lock impact: creates one version table and adds three nullable/defaulted task columns.
-- Existing rows receive version 0 defaults and are not restarted by this migration.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT IGNORE INTO `infra_config`
(`id`, `category`, `type`, `name`, `config_key`, `value`, `visible`, `remark`,
 `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(10001, 'ai-video', 1, 'AI 视频全局参数默认值', 'linsight.ai-video.settings.defaults',
 '{"schemaVersion":"1.0","recordBeforeSeconds":10,"recordAfterSeconds":20,"defaultConfidence":0.5,"defaultFps":1.0,"evidenceStorageMode":"OBJECT_STORAGE","evidenceRetentionDays":30,"notificationsEnabled":true,"nodeOfflineThresholdSeconds":60}',
 b'1', 'P24 强类型聚合接口的系统默认值；租户修改生成 ai_global_settings_version 快照',
 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

CREATE TABLE `ai_global_settings_version` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '配置版本记录编号',
  `version_no` int NOT NULL COMMENT '租户内递增版本号',
  `schema_version` varchar(16) NOT NULL DEFAULT '1.0' COMMENT '配置 Schema 版本',
  `settings_json` json NOT NULL COMMENT '完整强类型配置快照',
  `diff_json` json NOT NULL COMMENT '相对上一版本的字段级差异',
  `apply_scope` varchar(16) NOT NULL COMMENT 'NEW_TASKS/GRAY/ALL_RUNNING',
  `gray_task_ids_json` json NULL COMMENT '灰度任务编号',
  `status` varchar(16) NOT NULL COMMENT 'APPLIED/DISPATCHED/PARTIAL',
  `affected_task_count` int NOT NULL DEFAULT 0 COMMENT '纳入下发的运行任务数',
  `command_count` int NOT NULL DEFAULT 0 COMMENT '成功创建的节点命令数',
  `applied_at` datetime(3) NOT NULL COMMENT '保存时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_settings_tenant_version` (`tenant_id`, `version_no`, `deleted`),
  KEY `idx_ai_settings_tenant_time` (`tenant_id`, `create_time`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频全局参数版本';

ALTER TABLE `ai_task`
  ADD COLUMN `global_settings_version` int NOT NULL DEFAULT 0 COMMENT '期望全局参数版本' AFTER `config_version`,
  ADD COLUMN `applied_global_settings_version` int NOT NULL DEFAULT 0 COMMENT 'Runtime 已应用全局参数版本' AFTER `global_settings_version`,
  ADD COLUMN `global_settings_snapshot` json NULL COMMENT '任务绑定的全局参数完整快照' AFTER `applied_global_settings_version`;

UPDATE `ai_task`
SET `global_settings_snapshot` =
  '{"schemaVersion":"1.0","recordBeforeSeconds":10,"recordAfterSeconds":20,"defaultConfidence":0.5,"defaultFps":1.0,"evidenceStorageMode":"OBJECT_STORAGE","evidenceRetentionDays":30,"notificationsEnabled":true,"nodeOfflineThresholdSeconds":60}'
WHERE `global_settings_snapshot` IS NULL;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7110, 'AI 全局参数', '', 2, 31, 7000, 'settings', 'lucide:settings-2',
 'ai-video/settings/index', 'AiVideoSettings', 0, b'0', b'1', b'0',
 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7111, 'AI 参数查询', 'ai-video:settings:query', 3, 1, 7110, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7112, 'AI 参数保存', 'ai-video:settings:update', 3, 2, 7110, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7113, 'AI 参数批量下发', 'ai-video:settings:deploy', 3, 3, 7110, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (SELECT 7110 AS menu_id UNION ALL SELECT 7111 UNION ALL SELECT 7112 UNION ALL SELECT 7113) permissions;
