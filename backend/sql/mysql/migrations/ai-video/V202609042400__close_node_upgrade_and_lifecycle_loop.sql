-- LInsight: close the Edge Agent online redeployment and node lifecycle loop.
-- Preconditions: V202609042300 has added persisted deployment output.
-- Data/lock impact: one instant metadata column addition and two permission rows.
-- Forward repair: revoke the permissions to disable lifecycle actions; historical deployment
-- records remain readable. Drop operation_type only after exporting deployment audit history.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `ai_node_deployment`
  ADD COLUMN `operation_type` varchar(16) NOT NULL DEFAULT 'INITIAL'
  COMMENT '部署动作：INITIAL/REDEPLOY' AFTER `node_name`;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(70290, '节点启停', 'ai-video:node:operate', 3, 9, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(70291, '节点删除', 'ai-video:node:delete', 3, 10, 7020, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (SELECT 70290 AS menu_id UNION ALL SELECT 70291) permissions;
