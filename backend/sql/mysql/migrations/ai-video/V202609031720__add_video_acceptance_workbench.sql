-- Preconditions: V202609031710 has been applied; system_menu parent 7000 exists.
-- Data/lock impact: inserts one page menu and query permission only; no business rows are rewritten.
-- Forward repair: disable menu 7140 if the workbench must be withdrawn.

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7140, '视频识别验收', '', 2, 20, 7000, 'algorithm-validation', 'lucide:clipboard-check',
 'ai-video/algorithm-validation/index', 'AiVideoAlgorithmValidation', 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7141, '视频验收查询', 'ai-video:algorithm:query', 3, 1, 7140, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');
