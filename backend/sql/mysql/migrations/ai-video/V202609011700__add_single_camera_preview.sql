-- LInsight Story 4: single-camera browser preview menu and permission (MySQL 8.4)
-- Preconditions: V202609011430__init_ai_video_module.sql has completed.
-- Data/lock impact: inserts two menu metadata rows; no business table or long-running lock is involved.
-- Forward repair: correct conflicting menu IDs 7030-7031, then rerun this transaction.
-- Rollback:
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7030 AND 7031;
--   DELETE FROM system_menu WHERE id BETWEEN 7030 AND 7031;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

START TRANSACTION;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7030, '实时预览', '', 2, 11, 7000, 'live', 'lucide:monitor-play', 'ai-video/live/index', 'AiVideoLive',
 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7031, '摄像头预览', 'ai-video:camera:preview', 3, 1, 7030, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

COMMIT;
