-- LInsight Story 3: Edge Agent registration and heartbeat baseline (MySQL 8.4)
-- Preconditions: V202609011430__init_ai_video_module.sql has completed.
-- Data/lock impact: creates two empty tables and inserts disabled node menu metadata.
-- Rollback (only before node registration is used):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7020 AND 7024;
--   DELETE FROM system_menu WHERE id BETWEEN 7020 AND 7024;
--   DROP TABLE ai_camera_stream_check;
--   DROP TABLE ai_edge_node;
--   DROP TABLE ai_node_bootstrap_token;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_node_bootstrap_token` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '一次性注册令牌编号',
  `name` varchar(100) NOT NULL COMMENT '令牌用途说明',
  `token_digest` char(64) NOT NULL COMMENT '注册令牌 SHA-256 摘要',
  `expire_time` datetime NOT NULL COMMENT '过期时间',
  `used_time` datetime NULL COMMENT '使用时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_node_bootstrap_token_digest` (`token_digest`),
  KEY `idx_ai_node_bootstrap_tenant_expire` (`tenant_id`, `expire_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点一次性注册令牌';

CREATE TABLE `ai_edge_node` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '边缘节点编号',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定节点编码',
  `name` varchar(100) NOT NULL COMMENT '节点名称',
  `agent_version` varchar(64) NOT NULL COMMENT 'Agent 版本',
  `host_name` varchar(255) NOT NULL COMMENT '主机名',
  `ip_address` varchar(64) NULL COMMENT '最近来源 IP',
  `credential_digest` char(64) NOT NULL COMMENT '节点长期凭据 SHA-256 摘要',
  `online_status` tinyint NOT NULL DEFAULT 0 COMMENT '在线状态：0 未知，1 在线，2 离线',
  `last_heartbeat_time` datetime NULL COMMENT '最近心跳时间',
  `heartbeat_sequence` bigint NOT NULL DEFAULT 0 COMMENT '最近接收的单调心跳序号',
  `agent_time` datetime NULL COMMENT '最近 Agent 时间',
  `clock_offset_millis` bigint NULL COMMENT '中心与 Agent 时钟偏移毫秒',
  `resource_snapshot` json NULL COMMENT '最近 CPU/内存/磁盘/GPU 资源快照',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_edge_node_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_edge_node_tenant_online` (`tenant_id`, `online_status`, `last_heartbeat_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频边缘节点';

CREATE TABLE `ai_camera_stream_check` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '摄像头检测任务编号',
  `camera_id` bigint NOT NULL COMMENT '摄像头编号',
  `node_id` bigint NOT NULL COMMENT '执行节点编号',
  `status` varchar(16) NOT NULL COMMENT '状态：QUEUED/RUNNING/SUCCEEDED/FAILED',
  `diagnostic_id` varchar(36) NULL COMMENT 'Runtime 诊断编号',
  `stage_results` json NULL COMMENT 'DNS/TCP/AUTH/STREAM/KEYFRAME 分阶段结果',
  `stream_info` json NULL COMMENT '脱敏视频轨道信息',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `start_time` datetime NULL COMMENT '开始时间',
  `finish_time` datetime NULL COMMENT '完成时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_camera_check_node_status` (`tenant_id`, `node_id`, `status`, `id`),
  KEY `idx_ai_camera_check_camera_time` (`tenant_id`, `camera_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频摄像头异步连通检测';

START TRANSACTION;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7020, '边缘节点', '', 2, 20, 7000, 'node', 'lucide:server', 'ai-video/node/index', 'AiVideoNode',
 1, b'0', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7021, '节点查询', 'ai-video:node:query', 3, 1, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7022, '节点注册', 'ai-video:node:create', 3, 2, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7023, '节点修改', 'ai-video:node:update', 3, 3, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7024, '节点升级', 'ai-video:node:upgrade', 3, 4, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

COMMIT;
