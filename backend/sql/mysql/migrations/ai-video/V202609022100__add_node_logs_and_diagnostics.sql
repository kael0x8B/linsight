-- LInsight P22: bounded node/task logs and asynchronous diagnostic bundles.
-- Preconditions: V202609022000 has completed; ai_edge_node exists.
-- Data/lock impact: creates two empty tenant tables and adds two node permissions plus one hidden route.
-- Rollback: revoke menu ids 7026-7028, preserve/export required diagnostics, then drop
-- ai_node_diagnostic_bundle and ai_node_log. Object-storage files expire from access independently.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_node_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '节点日志编号',
  `node_id` bigint NOT NULL COMMENT '边缘节点编号',
  `entry_id` varchar(36) NOT NULL COMMENT '节点生成的幂等日志编号',
  `task_id` bigint NULL COMMENT '关联任务编号',
  `run_id` varchar(36) NULL COMMENT '关联任务运行编号',
  `component` varchar(32) NOT NULL COMMENT 'EDGE_AGENT/AI_RUNTIME/TASK 等组件',
  `level` varchar(8) NOT NULL COMMENT 'DEBUG/INFO/WARN/ERROR',
  `message` varchar(2000) NOT NULL COMMENT '服务端脱敏后的日志正文',
  `context_json` json NULL COMMENT '服务端脱敏后的结构化上下文',
  `diagnostic_id` varchar(36) NULL COMMENT '关联诊断编号',
  `logged_at` datetime(3) NOT NULL COMMENT '节点记录时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '接收时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_node_log_tenant_node_entry` (`tenant_id`, `node_id`, `entry_id`),
  KEY `idx_ai_node_log_tenant_node_time` (`tenant_id`, `node_id`, `logged_at`, `id`),
  KEY `idx_ai_node_log_tenant_task_time` (`tenant_id`, `task_id`, `logged_at`, `id`),
  KEY `idx_ai_node_log_tenant_level_time` (`tenant_id`, `level`, `logged_at`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点与任务结构化日志';

CREATE TABLE `ai_node_diagnostic_bundle` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '诊断包编号',
  `node_id` bigint NOT NULL COMMENT '边缘节点编号',
  `task_id` bigint NULL COMMENT '可选关联任务编号',
  `range_start` datetime(3) NOT NULL COMMENT '日志窗口开始时间',
  `range_end` datetime(3) NOT NULL COMMENT '日志窗口结束时间',
  `status` varchar(16) NOT NULL COMMENT 'QUEUED/RUNNING/READY/FAILED/EXPIRED',
  `file_ref` varchar(1024) NULL COMMENT '对象存储内部引用',
  `file_name` varchar(255) NULL COMMENT '下载文件名',
  `log_count` int NOT NULL DEFAULT 0 COMMENT '打包日志数量',
  `expires_at` datetime NOT NULL COMMENT '下载访问截止时间',
  `error_message` varchar(500) NULL COMMENT '脱敏失败摘要',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_node_diagnostic_tenant_node_time` (`tenant_id`, `node_id`, `create_time`),
  KEY `idx_ai_node_diagnostic_status` (`status`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点诊断包任务';

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7026, '节点日志', '', 2, 21, 7000, 'node/:id/logs', 'lucide:scroll-text',
 'ai-video/node-logs/index', 'AiVideoNodeLogs', 0, b'0', b'0', b'0',
 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7027, '节点日志查询', 'ai-video:node-log:query', 3, 6, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7028, '生成诊断包', 'ai-video:node-log:diagnostic', 3, 7, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (SELECT 7026 AS menu_id UNION ALL SELECT 7027 UNION ALL SELECT 7028) permissions;
