-- LInsight P07 video wall and per-user layout plans (MySQL 8.4)
-- Preconditions: V202609011700__add_single_camera_preview.sql has completed.
-- Data/lock impact: creates one empty tenant table and inserts two menu rows; metadata locks are brief.
-- Forward repair: resolve conflicting menu IDs 7120-7121, then rerun statements not recorded by the release log.
-- Rollback (only after confirming saved layouts can be discarded):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7120 AND 7121;
--   DELETE FROM system_menu WHERE id BETWEEN 7120 AND 7121;
--   DROP TABLE ai_video_wall_layout;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_video_wall_layout` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '布局方案编号',
  `user_id` bigint NOT NULL COMMENT '布局所属用户编号',
  `slot_index` tinyint NOT NULL COMMENT '方案位置：1-15',
  `name` varchar(50) NOT NULL COMMENT '方案名称',
  `split_count` tinyint NOT NULL COMMENT '分屏数量：1/4/9/16',
  `schema_version` varchar(16) NOT NULL DEFAULT '1.0' COMMENT '摄像头位置 JSON Schema 版本',
  `camera_ids_json` json NOT NULL COMMENT '按格子顺序保存的摄像头编号，可含 null',
  `active` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否为当前激活方案',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_video_wall_layout_owner_slot_deleted` (`tenant_id`, `user_id`, `slot_index`, `deleted`),
  KEY `idx_ai_video_wall_layout_owner_active` (`tenant_id`, `user_id`, `active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频墙用户布局方案';

START TRANSACTION;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7120, '分屏监控', '', 2, 12, 7000, 'wall', 'lucide:layout-grid', 'ai-video/wall/index', 'AiVideoWall',
 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7121, '分屏预览', 'ai-video:camera:preview', 3, 1, 7120, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu`
(`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM (SELECT 7120 AS menu_id UNION ALL SELECT 7121) permissions;

COMMIT;
