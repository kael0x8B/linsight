-- LInsight P23: signed Webhook endpoints and reliable delivery records.
-- Data/lock impact: creates two empty tenant tables and adds one route plus seven permissions.
-- Rollback: disable menu 7100, revoke menu ids 7100-7107, export required delivery audit rows,
-- then drop ai_webhook_delivery and ai_webhook_endpoint.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_webhook_endpoint` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Webhook 端点编号',
  `name` varchar(100) NOT NULL COMMENT '端点名称',
  `url` varchar(2048) NOT NULL COMMENT 'HTTPS 目标地址',
  `secret_ciphertext` varchar(1024) NOT NULL COMMENT 'HMAC 密钥密文',
  `event_types_json` json NULL COMMENT '订阅事件类型；空数组表示全部',
  `severities_json` json NULL COMMENT '订阅等级；空数组表示全部',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '0 启用 1 停用',
  `max_attempts` tinyint NOT NULL DEFAULT 5 COMMENT '最大投递次数',
  `timeout_ms` int NOT NULL DEFAULT 5000 COMMENT '单次请求超时毫秒',
  `success_count` bigint NOT NULL DEFAULT 0 COMMENT '累计成功次数',
  `failure_count` bigint NOT NULL DEFAULT 0 COMMENT '累计死信次数',
  `last_success_time` datetime(3) NULL COMMENT '最近成功时间',
  `last_failure_time` datetime(3) NULL COMMENT '最近失败时间',
  `last_error` varchar(500) NULL COMMENT '最近脱敏错误摘要',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_webhook_tenant_name` (`tenant_id`, `name`, `deleted`),
  KEY `idx_ai_webhook_tenant_status` (`tenant_id`, `status`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频 Webhook 端点';

CREATE TABLE `ai_webhook_delivery` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '投递编号',
  `endpoint_id` bigint NOT NULL COMMENT 'Webhook 端点编号',
  `event_id` bigint NULL COMMENT '关联事件编号；模拟测试为空',
  `message_id` varchar(64) NOT NULL COMMENT '消息编号',
  `idempotency_key` varchar(128) NOT NULL COMMENT '接收方幂等键',
  `event_type` varchar(64) NOT NULL COMMENT '事件类型',
  `severity` varchar(16) NULL COMMENT '事件等级',
  `payload` json NOT NULL COMMENT '版本化业务事件正文，重试期间保持不变',
  `status` varchar(16) NOT NULL COMMENT 'PENDING/RETRY/SUCCEEDED/DEAD',
  `attempts` tinyint NOT NULL DEFAULT 0 COMMENT '已尝试次数',
  `next_attempt_time` datetime(3) NOT NULL COMMENT '下次尝试时间',
  `last_attempt_time` datetime(3) NULL COMMENT '最近尝试时间',
  `response_status` int NULL COMMENT '最近 HTTP 状态码',
  `response_body` varchar(2000) NULL COMMENT '最近脱敏响应摘要',
  `duration_ms` int NULL COMMENT '最近请求耗时毫秒',
  `last_error` varchar(500) NULL COMMENT '最近脱敏错误摘要',
  `is_test` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否模拟测试事件',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_webhook_delivery_message` (`tenant_id`, `endpoint_id`, `message_id`),
  KEY `idx_ai_webhook_delivery_ready` (`status`, `next_attempt_time`, `id`),
  KEY `idx_ai_webhook_delivery_endpoint_time` (`tenant_id`, `endpoint_id`, `create_time`, `id`),
  KEY `idx_ai_webhook_delivery_event` (`tenant_id`, `event_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频 Webhook 可靠投递记录';

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7100, 'Webhook 集成', '', 2, 30, 7000, 'integration/webhook', 'lucide:webhook',
 'ai-video/webhook/index', 'AiVideoWebhook', 0, b'0', b'1', b'0',
 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7101, 'Webhook 查询', 'ai-video:webhook:query', 3, 1, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7102, 'Webhook 新增', 'ai-video:webhook:create', 3, 2, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7103, 'Webhook 修改', 'ai-video:webhook:update', 3, 3, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7104, 'Webhook 删除', 'ai-video:webhook:delete', 3, 4, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7105, 'Webhook 启停', 'ai-video:webhook:update-status', 3, 5, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7106, 'Webhook 模拟测试', 'ai-video:webhook:test', 3, 6, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7107, 'Webhook 死信重放', 'ai-video:webhook:replay', 3, 7, 7100, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (SELECT 7100 AS menu_id UNION ALL SELECT 7101 UNION ALL SELECT 7102 UNION ALL SELECT 7103
      UNION ALL SELECT 7104 UNION ALL SELECT 7105 UNION ALL SELECT 7106 UNION ALL SELECT 7107) permissions;
