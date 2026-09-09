-- LInsight Story 6: model test, deployment and durable node commands (MySQL 8.4)
-- Preconditions: V202609011530 and V202609011900 have completed.
-- Data/lock impact: adds two nullable/defaulted columns, creates three empty tables and inserts four menu metadata rows.
-- Forward repair: correct conflicting menu IDs 7050-7053, then rerun failed statements.
-- Rollback (only before commands, tests or deployments are used):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7050 AND 7053;
--   DELETE FROM system_menu WHERE id BETWEEN 7050 AND 7053;
--   DROP TABLE ai_model_test;
--   DROP TABLE ai_model_deployment;
--   DROP TABLE ai_node_command;
--   ALTER TABLE ai_model_version DROP COLUMN execution_ready_time, DROP COLUMN execution_status;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `ai_model_version`
  ADD COLUMN `execution_status` varchar(32) NOT NULL DEFAULT 'NOT_READY'
    COMMENT '技术执行门槛：NOT_READY/READY' AFTER `publish_status`,
  ADD COLUMN `execution_ready_time` datetime NULL COMMENT '节点部署与单图测试均成功时间'
    AFTER `execution_status`;

CREATE TABLE `ai_node_command` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '节点命令记录编号',
  `command_id` char(36) NOT NULL COMMENT '跨进程稳定命令编号',
  `node_id` bigint NOT NULL COMMENT '目标节点编号',
  `command_type` varchar(32) NOT NULL COMMENT '命令类型：DEPLOY_MODEL/RUN_MODEL_TEST',
  `aggregate_id` bigint NOT NULL COMMENT '命令所属部署或测试记录编号',
  `config_version` int NOT NULL COMMENT '配置版本',
  `idempotency_key` varchar(128) NOT NULL COMMENT '租户内幂等键',
  `status` varchar(32) NOT NULL COMMENT 'QUEUED/SENT/RUNNING/SUCCEEDED/FAILED/EXPIRED',
  `attempt_count` int NOT NULL DEFAULT 0 COMMENT '拉取尝试次数',
  `result_summary` json NULL COMMENT '节点返回的版本化结果摘要',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `expire_time` datetime NOT NULL COMMENT '命令过期时间',
  `sent_time` datetime NULL COMMENT '最近下发时间',
  `finish_time` datetime NULL COMMENT '完成时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_node_command_tenant_command` (`tenant_id`, `command_id`),
  UNIQUE KEY `uk_ai_node_command_tenant_idempotency` (`tenant_id`, `idempotency_key`),
  KEY `idx_ai_node_command_tenant_node_status` (`tenant_id`, `node_id`, `status`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点耐久命令';

CREATE TABLE `ai_model_deployment` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '模型部署记录编号',
  `model_version_id` bigint NOT NULL COMMENT '模型版本编号',
  `node_id` bigint NOT NULL COMMENT '目标节点编号',
  `config_version` int NOT NULL COMMENT '部署配置版本',
  `desired_status` varchar(32) NOT NULL COMMENT '期望状态：READY/ROLLED_BACK',
  `actual_status` varchar(32) NOT NULL COMMENT 'QUEUED/DOWNLOADING/VERIFYING/LOADING/READY/FAILED/ROLLED_BACK',
  `command_id` char(36) NOT NULL COMMENT '当前节点命令编号',
  `diagnostic_id` char(36) NULL COMMENT '诊断编号',
  `backend` varchar(64) NULL COMMENT '实际推理后端',
  `device` varchar(64) NULL COMMENT '实际加载设备',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `ready_time` datetime NULL COMMENT '进入 ready 时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_model_deployment_tenant_version_node_config` (`tenant_id`, `model_version_id`, `node_id`, `config_version`, `deleted`),
  UNIQUE KEY `uk_ai_model_deployment_tenant_command` (`tenant_id`, `command_id`),
  KEY `idx_ai_model_deployment_tenant_node_status` (`tenant_id`, `node_id`, `actual_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频模型节点部署';

CREATE TABLE `ai_model_test` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '单图测试编号',
  `model_version_id` bigint NOT NULL COMMENT '模型版本编号',
  `node_id` bigint NOT NULL COMMENT '执行节点编号',
  `image_ref` varchar(1000) NOT NULL COMMENT '测试图片对象存储内部引用',
  `image_name` varchar(255) NOT NULL COMMENT '测试图片名',
  `parameters` json NOT NULL COMMENT '带 schemaVersion 的推理参数',
  `status` varchar(32) NOT NULL COMMENT 'QUEUED/RUNNING/SUCCEEDED/FAILED',
  `command_id` char(36) NOT NULL COMMENT '节点命令编号',
  `diagnostic_id` char(36) NULL COMMENT '诊断编号',
  `backend` varchar(64) NULL COMMENT '实际推理后端',
  `preprocess_millis` int NULL COMMENT '预处理耗时',
  `inference_millis` int NULL COMMENT '推理耗时',
  `postprocess_millis` int NULL COMMENT '后处理耗时',
  `result` json NULL COMMENT 'V1 标准化检测结果',
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
  UNIQUE KEY `uk_ai_model_test_tenant_command` (`tenant_id`, `command_id`),
  KEY `idx_ai_model_test_tenant_version_time` (`tenant_id`, `model_version_id`, `create_time`),
  KEY `idx_ai_model_test_tenant_node_status` (`tenant_id`, `node_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频模型单图测试';

START TRANSACTION;
INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7050, '单图模型测试', '', 2, 13, 7000, 'model-test', 'lucide:scan-search', 'ai-video/model-test/index', 'AiVideoModelTest',
 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7051, '测试记录查询', 'ai-video:model:query', 3, 1, 7050, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7052, '执行单图测试', 'ai-video:model:test', 3, 2, 7050, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7053, '部署模型版本', 'ai-video:model:deploy', 3, 7, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');
COMMIT;
