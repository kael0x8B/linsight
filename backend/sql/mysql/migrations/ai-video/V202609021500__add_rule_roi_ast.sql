-- LInsight Story 8: ROI / Rule AST, immutable versions and task binding (MySQL 8.4)
-- Preconditions: V202609021430 has completed.
-- Data/lock impact: creates two rule tables and adds two nullable columns plus indexes to ai_task.
--   The ALTER may rebuild ai_task on older MySQL variants; schedule outside peak writes in production.
-- Forward repair: resolve conflicting IDs/codes, then rerun only statements not recorded by the migration log.
-- Rollback (only before tasks reference rules): remove menu 7080..7085, drop ai_task rule indexes/columns,
--   then drop ai_rule_version and ai_rule.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_rule` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '规则编号',
  `name` varchar(100) NOT NULL COMMENT '规则名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定规则编码',
  `description` varchar(500) NULL COMMENT '规则说明',
  `event_type` varchar(64) NOT NULL COMMENT '确认后的事件类型',
  `current_version_id` bigint NULL COMMENT '当前发布规则版本编号',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_rule_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_rule_tenant_event_status` (`tenant_id`, `event_type`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频规则定义';

CREATE TABLE `ai_rule_version` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '规则版本编号',
  `rule_id` bigint NOT NULL COMMENT '规则编号',
  `version` int NOT NULL COMMENT '不可变版本号',
  `ast` json NOT NULL COMMENT 'ROI、时序、组合和冷却 AST，schemaVersion=1.0',
  `natural_summary` varchar(1000) NOT NULL COMMENT '规则自然语言摘要',
  `validation_status` varchar(32) NOT NULL COMMENT 'DRAFT/VALID/PUBLISHED',
  `validation_errors` json NULL COMMENT '结构化校验错误',
  `published_time` datetime NULL COMMENT '发布时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_rule_version_tenant_rule_version_deleted` (`tenant_id`, `rule_id`, `version`, `deleted`),
  KEY `idx_ai_rule_version_tenant_rule_status` (`tenant_id`, `rule_id`, `validation_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频不可变规则版本';

ALTER TABLE `ai_task`
  ADD COLUMN `rule_id` bigint NULL COMMENT '规则编号' AFTER `node_id`,
  ADD COLUMN `rule_version_id` bigint NULL COMMENT '已发布规则版本编号' AFTER `rule_id`,
  ADD KEY `idx_ai_task_tenant_rule` (`tenant_id`, `rule_id`),
  ADD KEY `idx_ai_task_tenant_rule_version` (`tenant_id`, `rule_version_id`);

INSERT INTO `ai_rule`
(`id`, `name`, `code`, `description`, `event_type`, `current_version_id`, `status`, `creator`, `updater`, `tenant_id`)
VALUES
(73001, '区域入侵默认规则', 'area-intrusion-default', 'Person 足点进入多边形，3/5 帧且持续 2 秒后确认，30 秒冷却',
 'AREA_INTRUSION', 73101, 0, 'system', 'system', 1);

INSERT INTO `ai_rule_version`
(`id`, `rule_id`, `version`, `ast`, `natural_summary`, `validation_status`, `published_time`, `creator`, `updater`, `tenant_id`)
VALUES
(73101, 73001, 1,
 JSON_OBJECT(
   'schemaVersion', '1.0',
   'eventType', 'AREA_INTRUSION',
   'severity', 'MAJOR',
   'regions', JSON_ARRAY(JSON_OBJECT(
     'id', 'work-zone', 'name', '默认警戒区', 'type', 'POLYGON',
     'sourceWidth', 1920, 'sourceHeight', 1080,
     'pointMode', 'FOOT', 'overlapThreshold', 0.0,
     'points', JSON_ARRAY(
       JSON_OBJECT('x', 0.15, 'y', 0.15), JSON_OBJECT('x', 0.85, 'y', 0.15),
       JSON_OBJECT('x', 0.85, 'y', 0.85), JSON_OBJECT('x', 0.15, 'y', 0.85)
     )
   )),
   'schedule', JSON_OBJECT('timezone', 'Asia/Shanghai', 'weekly', JSON_ARRAY(
     JSON_OBJECT('days', JSON_ARRAY(1,2,3,4,5,6,7), 'start', '00:00', 'end', '23:59')
   )),
   'condition', JSON_OBJECT('type', 'AND', 'children', JSON_ARRAY(
     JSON_OBJECT('type', 'ROI_ENTER', 'regionId', 'work-zone', 'objectClasses', JSON_ARRAY('person')),
     JSON_OBJECT('type', 'N_OF_M', 'n', 3, 'm', 5),
     JSON_OBJECT('type', 'DURATION', 'seconds', 2.0)
   )),
   'cooldownSeconds', 30,
   'recoverySeconds', 5,
   'dedup', JSON_OBJECT('scope', 'TRACK', 'windowSeconds', 30)
 ),
 '每天 00:00-23:59，人员足点进入默认警戒区，5 帧中至少 3 帧且持续 2 秒后告警；同一目标冷却 30 秒。',
 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1);

START TRANSACTION;
INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7080, '规则中心', '', 2, 16, 7000, 'rule', 'lucide:scan-line', 'ai-video/rule/index', 'AiVideoRule', 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7081, '规则查询', 'ai-video:rule:query', 3, 1, 7080, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7082, '规则新增', 'ai-video:rule:create', 3, 2, 7080, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7083, '规则修改', 'ai-video:rule:update', 3, 3, 7080, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7084, '规则发布', 'ai-video:rule:publish', 3, 4, 7080, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7085, '规则试跑', 'ai-video:rule:dry-run', 3, 5, 7080, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

INSERT IGNORE INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, id, 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0', 1
FROM `system_menu` WHERE id BETWEEN 7080 AND 7085;
COMMIT;
