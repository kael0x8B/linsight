-- LInsight Story 9: event evidence, disposition, false-positive feedback and durable WebSocket outbox.
-- Preconditions: V202609021500 has completed.
-- Data/lock impact: creates four tables; no existing business table is rewritten.
-- Rollback: remove menu 7090..7097, then drop ai_event_outbox, ai_event_action, ai_event_media, ai_event.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_event` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '事件编号',
  `event_no` varchar(40) NOT NULL COMMENT '租户内可展示稳定编号',
  `source_event_id` varchar(64) NOT NULL COMMENT 'Runtime 活动幂等编号',
  `activity_id` varchar(64) NOT NULL COMMENT '规则活动编号',
  `dedup_key` varchar(255) NOT NULL COMMENT '规则去重键',
  `active_dedup_key` varchar(255) NULL COMMENT '活动期唯一去重键，关闭后置空',
  `task_id` bigint NOT NULL COMMENT '任务编号',
  `task_run_id` varchar(36) NOT NULL COMMENT '任务 Run ID',
  `camera_id` bigint NOT NULL COMMENT '摄像头编号',
  `node_id` bigint NOT NULL COMMENT '上报节点编号',
  `algorithm_id` bigint NOT NULL COMMENT '算法编号',
  `pipeline_version_id` bigint NOT NULL COMMENT 'Pipeline 版本编号',
  `model_version_id` bigint NOT NULL COMMENT '模型版本编号',
  `rule_id` bigint NOT NULL COMMENT '规则编号',
  `rule_version_id` bigint NOT NULL COMMENT '规则版本编号',
  `event_type` varchar(64) NOT NULL COMMENT '事件类型',
  `severity` varchar(16) NOT NULL COMMENT 'INFO/MINOR/MAJOR/CRITICAL',
  `status` varchar(32) NOT NULL COMMENT 'ALARM/ASSIGNED/HANDLING/RESOLVED/CLOSED/FALSE_POSITIVE',
  `evidence_status` varchar(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/PARTIAL/READY/FAILED',
  `occurred_time` datetime(3) NOT NULL COMMENT '告警发生时间',
  `first_seen_time` datetime(3) NOT NULL COMMENT '首次检测时间',
  `last_seen_time` datetime(3) NOT NULL COMMENT '最后检测时间',
  `close_time` datetime(3) NULL COMMENT '关闭时间',
  `duration_ms` bigint NOT NULL DEFAULT 0 COMMENT '持续时长毫秒',
  `max_confidence` decimal(6,5) NULL COMMENT '最大置信度',
  `track_id` varchar(128) NULL COMMENT '跟踪编号',
  `assignee_id` bigint NULL COMMENT '处置人编号',
  `handling_result` varchar(1000) NULL COMMENT '处置结果',
  `false_positive_reason` varchar(500) NULL COMMENT '误报原因',
  `object_snapshot` json NOT NULL COMMENT '检测对象快照',
  `task_snapshot` json NOT NULL COMMENT '任务配置快照',
  `pipeline_snapshot` json NOT NULL COMMENT 'Pipeline 快照',
  `model_snapshot` json NOT NULL COMMENT '模型快照',
  `rule_snapshot` json NOT NULL COMMENT '规则快照',
  `version` int NOT NULL DEFAULT 0 COMMENT '乐观锁版本',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_event_tenant_no_deleted` (`tenant_id`, `event_no`, `deleted`),
  UNIQUE KEY `uk_ai_event_tenant_source_deleted` (`tenant_id`, `source_event_id`, `deleted`),
  UNIQUE KEY `uk_ai_event_tenant_active_dedup_deleted` (`tenant_id`, `active_dedup_key`, `deleted`),
  KEY `idx_ai_event_tenant_time` (`tenant_id`, `occurred_time` DESC),
  KEY `idx_ai_event_tenant_status_severity` (`tenant_id`, `status`, `severity`),
  KEY `idx_ai_event_tenant_camera_type` (`tenant_id`, `camera_id`, `event_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频事件事实与处置状态';

CREATE TABLE `ai_event_media` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '事件媒体编号',
  `event_id` bigint NOT NULL COMMENT '事件编号',
  `media_type` varchar(16) NOT NULL COMMENT 'SNAPSHOT/VIDEO',
  `object_ref` varchar(1024) NULL COMMENT '对象存储引用',
  `file_name` varchar(255) NOT NULL COMMENT '原始文件名',
  `mime_type` varchar(128) NOT NULL COMMENT 'MIME 类型',
  `file_size` bigint NOT NULL COMMENT '字节数',
  `sha256` char(64) NOT NULL COMMENT '内容摘要',
  `status` varchar(16) NOT NULL COMMENT 'READY/FAILED',
  `error_message` varchar(500) NULL COMMENT '上传错误',
  `capture_start_time` datetime(3) NULL COMMENT '取证起点',
  `capture_end_time` datetime(3) NULL COMMENT '取证终点',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_event_media_tenant_event_type_sha_deleted` (`tenant_id`, `event_id`, `media_type`, `sha256`, `deleted`),
  KEY `idx_ai_event_media_tenant_event` (`tenant_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 事件证据媒体';

CREATE TABLE `ai_event_action` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '事件动作编号',
  `event_id` bigint NOT NULL COMMENT '事件编号',
  `action_type` varchar(32) NOT NULL COMMENT 'CREATED/ASSIGNED/HANDLED/CLOSED/FALSE_POSITIVE/RECOVERED',
  `from_status` varchar(32) NULL COMMENT '原状态',
  `to_status` varchar(32) NOT NULL COMMENT '目标状态',
  `operator_id` bigint NULL COMMENT '操作人编号，节点动作为空',
  `assignee_id` bigint NULL COMMENT '处置人编号',
  `remark` varchar(1000) NULL COMMENT '处置说明',
  `reason_code` varchar(64) NULL COMMENT '结构化原因编码',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_event_action_tenant_event_time` (`tenant_id`, `event_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 事件不可变处置轨迹';

CREATE TABLE `ai_event_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Outbox 编号',
  `event_id` bigint NOT NULL COMMENT '事件编号',
  `message_type` varchar(64) NOT NULL COMMENT 'WebSocket 消息类型',
  `payload` json NOT NULL COMMENT '消息快照',
  `status` varchar(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/SENT',
  `attempts` int NOT NULL DEFAULT 0 COMMENT '投递次数',
  `next_attempt_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下次投递时间',
  `sent_time` datetime NULL COMMENT '投递成功时间',
  `last_error` varchar(500) NULL COMMENT '最近错误',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_event_outbox_status_next` (`status`, `next_attempt_time`),
  KEY `idx_ai_event_outbox_tenant_event` (`tenant_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 事件 WebSocket 耐久 Outbox';

START TRANSACTION;
INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7090, '事件中心', '', 2, 17, 7000, 'event', 'lucide:siren', 'ai-video/event/index', 'AiVideoEvent', 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7091, '事件查询', 'ai-video:event:query', 3, 1, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7092, '事件导出', 'ai-video:event:export', 3, 2, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7093, '事件指派', 'ai-video:event:assign', 3, 3, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7094, '事件处置', 'ai-video:event:handle', 3, 4, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7095, '事件关闭', 'ai-video:event:close', 3, 5, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7096, '标记误报', 'ai-video:event:false-positive', 3, 6, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7097, '证据查看', 'ai-video:event:evidence', 3, 7, 7090, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM `system_menu` WHERE id BETWEEN 7090 AND 7097;
COMMIT;
