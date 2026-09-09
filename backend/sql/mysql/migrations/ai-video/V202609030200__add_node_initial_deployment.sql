-- LInsight: console-driven initial provisioning for Edge Agent and AI Runtime.
-- Preconditions: V202609030100 has completed; ai_edge_node and node menu 7020 exist.
-- Security: SSH credentials and generated runtime/bootstrap secrets are deliberately not persisted.
-- Rollback: revoke menu 7029, export required audit rows, then drop ai_node_deployment.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_node_deployment` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '初始部署任务编号',
  `host` varchar(255) NOT NULL COMMENT '目标主机（不含凭据）',
  `port` int NOT NULL DEFAULT 22 COMMENT 'SSH 端口',
  `username` varchar(32) NOT NULL COMMENT 'SSH 用户名（不含凭据）',
  `node_code` varchar(64) NOT NULL COMMENT '注册节点编码',
  `node_name` varchar(100) NOT NULL COMMENT '注册节点名称',
  `target_arch` varchar(32) NULL COMMENT '预检架构',
  `os_summary` varchar(255) NULL COMMENT '预检操作系统摘要',
  `python_version` varchar(64) NULL COMMENT '预检 Python 版本',
  `status` varchar(16) NOT NULL COMMENT 'QUEUED/RUNNING/SUCCEEDED/FAILED',
  `stage` varchar(32) NOT NULL COMMENT 'PACKAGING/CONNECTING/UPLOADING/INSTALLING/VERIFYING/COMPLETED/FAILED',
  `progress` int NOT NULL DEFAULT 0 COMMENT '进度百分比',
  `message` varchar(500) NULL COMMENT '脱敏状态摘要',
  `diagnostic_id` varchar(36) NULL COMMENT '失败诊断编号',
  `edge_node_id` bigint NULL COMMENT '成功注册后的节点编号',
  `finish_time` datetime NULL COMMENT '结束时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_node_deploy_tenant_status` (`tenant_id`, `status`, `id`),
  KEY `idx_ai_node_deploy_tenant_host_time` (`tenant_id`, `host`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频节点初始部署审计';

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7029, '部署节点', 'ai-video:node:deploy', 3, 8, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
VALUES (1, 7029, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1);
