-- Preconditions: V202609031900 has been applied; system_menu 7000 and AI page menus 7001-7141 exist.
-- Data/lock impact: inserts five directory menus, updates sixteen menu metadata rows, and adds role-menu parent links.
-- No camera, task, event, model, node, or other business data is rewritten.
-- Forward repair: restore the moved page parent_id to 7000 and relative paths shown at the end of this file,
-- then disable directory menus 7150-7154. Do not delete role-menu history during an incident rollback.

START TRANSACTION;

UPDATE `system_menu`
SET `name` = '视频监控', `sort` = 4, `icon` = 'lucide:cctv',
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP
WHERE `id` = 7000 AND `deleted` = b'0';

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7150, 'AI 能力', '', 1, 5, 0, '/ai-center', 'lucide:brain-circuit', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7151, '任务编排', '', 1, 6, 0, '/task-center', 'lucide:workflow', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7152, '事件中心', '', 1, 7, 0, '/event-center', 'lucide:siren', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7153, '边缘计算', '', 1, 8, 0, '/edge-computing', 'lucide:server-cog', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7154, '平台配置', '', 1, 9, 0, '/platform-config', 'lucide:settings-2', NULL, NULL,
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

-- 视频监控：原根路径 /ai-video 保持不变，子页仍使用相对路径。
UPDATE `system_menu` SET `sort` = 1, `updater` = 'system', `update_time` = CURRENT_TIMESTAMP
WHERE `id` = 7010 AND `deleted` = b'0';
UPDATE `system_menu` SET `sort` = 2, `updater` = 'system', `update_time` = CURRENT_TIMESTAMP
WHERE `id` = 7030 AND `deleted` = b'0';
UPDATE `system_menu` SET `sort` = 3, `updater` = 'system', `update_time` = CURRENT_TIMESTAMP
WHERE `id` = 7120 AND `deleted` = b'0';

-- AI 能力：菜单归属调整，但页面绝对路由保持兼容。
UPDATE `system_menu` SET `name` = '模型中心', `parent_id` = 7150, `path` = '/ai-video/model', `sort` = 1,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7040 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7150, `path` = '/ai-video/algorithm', `sort` = 2,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7060 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7150, `path` = '/ai-video/model-test', `sort` = 3,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7050 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7150, `path` = '/ai-video/recognition-library', `sort` = 4,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7130 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7150, `path` = '/ai-video/algorithm-validation', `sort` = 5,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7140 AND `deleted` = b'0';

-- 任务编排。
UPDATE `system_menu` SET `name` = 'AI 任务', `parent_id` = 7151, `path` = '/ai-video/task', `sort` = 1,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7070 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7151, `path` = '/ai-video/rule', `sort` = 2,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7080 AND `deleted` = b'0';

-- 事件中心。
UPDATE `system_menu` SET `name` = '事件列表', `parent_id` = 7152, `path` = '/ai-video/event', `sort` = 1,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7090 AND `deleted` = b'0';

-- 边缘计算；节点日志是隐藏路由，与节点列表保持同一业务域。
UPDATE `system_menu` SET `parent_id` = 7153, `path` = '/ai-video/node', `sort` = 1,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7020 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7153, `path` = '/ai-video/node/:id/logs', `sort` = 2,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7026 AND `deleted` = b'0';

-- 平台配置：已完成的 Webhook 与全局参数页面恢复可见；未完成的平台能力路由继续禁用隐藏。
UPDATE `system_menu` SET `parent_id` = 7154, `path` = '/ai-video/platform', `sort` = 1,
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7001 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7154, `path` = '/ai-video/integration/webhook', `sort` = 2, `visible` = b'1',
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7100 AND `deleted` = b'0';
UPDATE `system_menu` SET `parent_id` = 7154, `path` = '/ai-video/settings', `sort` = 3, `visible` = b'1',
    `updater` = 'system', `update_time` = CURRENT_TIMESTAMP WHERE `id` = 7110 AND `deleted` = b'0';

-- 超级管理员显式持有新目录，避免角色编辑时目录状态不完整。
INSERT INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT r.`id`, roots.`menu_id`, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', r.`tenant_id`
FROM `system_role` r
CROSS JOIN (
  SELECT 7150 AS `menu_id` UNION ALL SELECT 7151 UNION ALL SELECT 7152 UNION ALL SELECT 7153 UNION ALL SELECT 7154
) roots
WHERE r.`id` = 1 AND r.`deleted` = b'0'
  AND NOT EXISTS (
    SELECT 1 FROM `system_role_menu` rm
    WHERE rm.`role_id` = r.`id` AND rm.`tenant_id` = r.`tenant_id`
      AND rm.`menu_id` = roots.`menu_id` AND rm.`deleted` = b'0'
  );

-- 其他角色按已拥有的页面/按钮权限继承新的一级目录，不扩大业务权限。
INSERT INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT DISTINCT rm.`role_id`, menu_groups.`root_id`, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', rm.`tenant_id`
FROM `system_role_menu` rm
JOIN (
  SELECT 7150 AS `root_id`, 7040 AS `from_id`, 7064 AS `to_id`
  UNION ALL SELECT 7150, 7130, 7141
  UNION ALL SELECT 7151, 7070, 7085
  UNION ALL SELECT 7152, 7090, 7097
  UNION ALL SELECT 7153, 7020, 7029
  UNION ALL SELECT 7154, 7001, 7002
  UNION ALL SELECT 7154, 7100, 7113
) menu_groups ON rm.`menu_id` BETWEEN menu_groups.`from_id` AND menu_groups.`to_id`
WHERE rm.`deleted` = b'0'
  AND NOT EXISTS (
    SELECT 1 FROM `system_role_menu` existing
    WHERE existing.`role_id` = rm.`role_id` AND existing.`tenant_id` = rm.`tenant_id`
      AND existing.`menu_id` = menu_groups.`root_id` AND existing.`deleted` = b'0'
  );

COMMIT;

-- Forward rollback reference (execute as a new repair migration, never edit an applied migration):
-- UPDATE system_menu SET name='视频分析', sort=5, icon='lucide:cctv' WHERE id=7000;
-- UPDATE system_menu SET parent_id=7000, path='model', name='模型资产', sort=12 WHERE id=7040;
-- UPDATE system_menu SET parent_id=7000, path='model-test', sort=13 WHERE id=7050;
-- UPDATE system_menu SET parent_id=7000, path='algorithm', sort=14 WHERE id=7060;
-- UPDATE system_menu SET parent_id=7000, path='task', name='AI 任务中心', sort=15 WHERE id=7070;
-- UPDATE system_menu SET parent_id=7000, path='rule', sort=16 WHERE id=7080;
-- UPDATE system_menu SET parent_id=7000, path='event', name='事件中心', sort=17 WHERE id=7090;
-- UPDATE system_menu SET parent_id=7000, path='recognition-library', sort=19 WHERE id=7130;
-- UPDATE system_menu SET parent_id=7000, path='algorithm-validation', sort=20 WHERE id=7140;
-- UPDATE system_menu SET parent_id=7000, path='node', sort=20 WHERE id=7020;
-- UPDATE system_menu SET parent_id=7000, path='node/:id/logs', sort=21 WHERE id=7026;
-- UPDATE system_menu SET parent_id=7000, path='platform', sort=1 WHERE id=7001;
-- UPDATE system_menu SET parent_id=7000, path='integration/webhook', sort=30, visible=b'0' WHERE id=7100;
-- UPDATE system_menu SET parent_id=7000, path='settings', sort=31, visible=b'0' WHERE id=7110;
-- UPDATE system_menu SET status=1, visible=b'0' WHERE id BETWEEN 7150 AND 7154;
