-- LInsight AI Video module baseline (MySQL 8.4)
-- Preconditions:
--   1. The baseline schema and system_menu table already exist.
--   2. Menu IDs 7000-7018 are reserved for this migration.
-- Data/lock impact: creates two empty tables and inserts menu metadata; DDL takes brief metadata locks.
-- Forward repair: fix the failed statement and rerun only statements not recorded as successful by the release log.
-- Rollback (only before Camera/Group business data exists):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7000 AND 7018;
--   DELETE FROM system_menu WHERE id BETWEEN 7000 AND 7018;
--   DROP TABLE ai_camera;
--   DROP TABLE ai_camera_group;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_camera_group` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '摄像头分组编号',
  `name` varchar(100) NOT NULL COMMENT '分组名称',
  `parent_id` bigint NOT NULL DEFAULT 0 COMMENT '父分组编号，根节点为 0',
  `path` varchar(1000) NOT NULL DEFAULT '/' COMMENT '祖先路径，例如 /1/12/',
  `sort` int NOT NULL DEFAULT 0 COMMENT '同级显示顺序',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_camera_group_tenant_parent_name_deleted` (`tenant_id`, `parent_id`, `name`, `deleted`),
  KEY `idx_ai_camera_group_tenant_path` (`tenant_id`, `path`(191)),
  KEY `idx_ai_camera_group_tenant_parent_sort` (`tenant_id`, `parent_id`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频摄像头分组';

CREATE TABLE `ai_camera` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '摄像头编号',
  `name` varchar(100) NOT NULL COMMENT '摄像头名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定业务编码',
  `group_id` bigint NOT NULL DEFAULT 0 COMMENT '摄像头分组编号，未分组为 0',
  `protocol` varchar(16) NOT NULL COMMENT '接入协议：RTSP/ONVIF',
  `host` varchar(255) NOT NULL COMMENT '设备主机名或 IP，不含凭据',
  `port` int NOT NULL COMMENT '设备端口',
  `main_stream_uri_ciphertext` text NOT NULL COMMENT '主码流 URI 密文',
  `sub_stream_uri_ciphertext` text NULL COMMENT '子码流 URI 密文',
  `username_ciphertext` text NULL COMMENT '用户名密文',
  `password_ciphertext` text NULL COMMENT '密码密文',
  `credential_key_version` varchar(64) NOT NULL COMMENT '凭据加密密钥版本',
  `online_status` tinyint NOT NULL DEFAULT 0 COMMENT '在线状态：0 未知，1 在线，2 离线',
  `last_online_time` datetime NULL COMMENT '最近在线时间',
  `last_check_time` datetime NULL COMMENT '最近连通检测时间',
  `last_error_code` varchar(64) NULL COMMENT '最近一次脱敏错误码',
  `last_error_message` varchar(500) NULL COMMENT '最近一次脱敏错误摘要',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `version` int NOT NULL DEFAULT 1 COMMENT '乐观锁版本',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_camera_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_camera_tenant_group` (`tenant_id`, `group_id`),
  KEY `idx_ai_camera_tenant_online` (`tenant_id`, `online_status`, `last_online_time`),
  KEY `idx_ai_camera_tenant_name` (`tenant_id`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频摄像头';

START TRANSACTION;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7000, '视频分析', '', 1, 5, 0, '/ai-video', 'lucide:cctv', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7001, '平台能力', '', 2, 1, 7000, 'platform', 'lucide:blocks', 'ai-video/platform/index', 'AiVideoPlatform',
 1, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7002, '平台能力查询', 'ai-video:integration:query', 3, 1, 7001, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7010, '摄像头管理', '', 2, 10, 7000, 'camera', 'lucide:video', 'ai-video/camera/index', 'AiVideoCamera',
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7011, '摄像头查询', 'ai-video:camera:query', 3, 1, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7012, '摄像头新增', 'ai-video:camera:create', 3, 2, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7013, '摄像头修改', 'ai-video:camera:update', 3, 3, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7014, '摄像头删除', 'ai-video:camera:delete', 3, 4, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7015, '摄像头导出', 'ai-video:camera:export', 3, 5, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7016, '摄像头导入', 'ai-video:camera:import', 3, 6, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7017, '连通检测', 'ai-video:camera:check', 3, 7, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7018, '查看敏感配置', 'ai-video:camera:view-secret', 3, 8, 7010, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

COMMIT;
