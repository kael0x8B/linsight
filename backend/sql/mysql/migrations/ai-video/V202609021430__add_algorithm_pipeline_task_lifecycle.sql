-- LInsight Story 7: Algorithm/Pipeline and Task lifecycle (MySQL 8.4)
-- Preconditions: V202609021000 has completed; camera, model, node and durable command tables exist.
-- Data/lock impact: creates four business tables, registers 12 algorithm assets, one published controlled
--   Person pipeline, and 13 menu rows. Existing business rows are not rewritten.
-- Forward repair: resolve conflicting IDs/codes, then rerun only statements not recorded by the migration log.
-- Rollback (only before task data or external command references exist):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7060 AND 7076;
--   DELETE FROM system_menu WHERE id BETWEEN 7060 AND 7076;
--   DROP TABLE ai_task_run; DROP TABLE ai_task; DROP TABLE ai_pipeline_version; DROP TABLE ai_algorithm;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_algorithm` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '算法编号',
  `name` varchar(100) NOT NULL COMMENT '算法名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定算法编码，使用后不可修改',
  `category` varchar(32) NOT NULL COMMENT '类别：CORE/EXTENSION/CUSTOM',
  `description` varchar(500) NULL COMMENT '算法说明',
  `capability_key` varchar(64) NOT NULL COMMENT '运行时能力键',
  `event_type` varchar(64) NULL COMMENT '默认事件类型',
  `default_model_id` bigint NULL COMMENT '默认模型资产编号',
  `current_pipeline_version_id` bigint NULL COMMENT '当前发布 Pipeline 版本编号',
  `parameter_schema` json NOT NULL COMMENT '带 schemaVersion 的参数 Schema',
  `default_parameters` json NOT NULL COMMENT '带 schemaVersion 的默认参数',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_algorithm_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_algorithm_tenant_category_status` (`tenant_id`, `category`, `status`),
  KEY `idx_ai_algorithm_tenant_model` (`tenant_id`, `default_model_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频算法定义';

CREATE TABLE `ai_pipeline_version` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Pipeline 版本编号',
  `algorithm_id` bigint NOT NULL COMMENT '算法编号',
  `version` int NOT NULL COMMENT '不可变版本号',
  `dag` json NOT NULL COMMENT '受控节点 DAG，schemaVersion=1.0',
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
  UNIQUE KEY `uk_ai_pipeline_tenant_algorithm_version_deleted` (`tenant_id`, `algorithm_id`, `version`, `deleted`),
  KEY `idx_ai_pipeline_tenant_algorithm_status` (`tenant_id`, `algorithm_id`, `validation_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频不可变 Pipeline 版本';

CREATE TABLE `ai_task` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'AI 任务编号',
  `name` varchar(100) NOT NULL COMMENT '任务名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定任务编码',
  `camera_id` bigint NOT NULL COMMENT '摄像头编号',
  `algorithm_id` bigint NOT NULL COMMENT '算法编号',
  `pipeline_version_id` bigint NOT NULL COMMENT 'Pipeline 版本编号',
  `model_version_id` bigint NOT NULL COMMENT '模型版本编号',
  `node_id` bigint NOT NULL COMMENT '执行节点编号',
  `parameters` json NOT NULL COMMENT '带 schemaVersion 的推理参数',
  `desired_status` varchar(32) NOT NULL DEFAULT 'STOPPED' COMMENT '期望状态：STOPPED/RUNNING',
  `actual_status` varchar(32) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT/STOPPED/STARTING/RUNNING/STOPPING/FAILED/OFFLINE',
  `config_version` int NOT NULL DEFAULT 1 COMMENT '配置版本',
  `active_run_id` char(36) NULL COMMENT '当前运行编号',
  `last_command_id` char(36) NULL COMMENT '最近生命周期命令编号',
  `last_heartbeat_time` datetime NULL COMMENT '最近运行状态上报时间',
  `metrics_snapshot` json NULL COMMENT '最近带 schemaVersion 的运行指标',
  `diagnostic_id` char(36) NULL COMMENT '最近诊断编号',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `version` int NOT NULL DEFAULT 1 COMMENT '乐观锁版本',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_task_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_task_tenant_status` (`tenant_id`, `actual_status`, `update_time`),
  KEY `idx_ai_task_tenant_camera` (`tenant_id`, `camera_id`),
  KEY `idx_ai_task_tenant_algorithm` (`tenant_id`, `algorithm_id`),
  KEY `idx_ai_task_tenant_node` (`tenant_id`, `node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频任务';

CREATE TABLE `ai_task_run` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务运行记录编号',
  `task_id` bigint NOT NULL COMMENT '任务编号',
  `run_id` char(36) NOT NULL COMMENT '跨进程稳定运行编号',
  `config_version` int NOT NULL COMMENT '运行采用的配置版本',
  `command_id` char(36) NOT NULL COMMENT '启动命令编号',
  `status` varchar(32) NOT NULL COMMENT 'STARTING/RUNNING/STOPPED/FAILED/OFFLINE',
  `start_time` datetime NULL COMMENT '实际启动时间',
  `finish_time` datetime NULL COMMENT '结束时间',
  `metrics_snapshot` json NULL COMMENT '结束前最近运行指标',
  `diagnostic_id` char(36) NULL COMMENT '诊断编号',
  `error_code` varchar(64) NULL COMMENT '脱敏错误码',
  `error_message` varchar(500) NULL COMMENT '脱敏错误摘要',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_task_run_tenant_run` (`tenant_id`, `run_id`),
  UNIQUE KEY `uk_ai_task_run_tenant_command` (`tenant_id`, `command_id`),
  KEY `idx_ai_task_run_tenant_task_time` (`tenant_id`, `task_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频任务运行记录';

INSERT INTO `ai_algorithm`
(`id`, `name`, `code`, `category`, `description`, `capability_key`, `event_type`, `default_model_id`,
 `parameter_schema`, `default_parameters`, `status`, `creator`, `updater`, `tenant_id`)
VALUES
(72001, '安全帽检测', 'safety-helmet', 'CORE', '人员检测后判定安全帽属性，unknown 不强判违规', 'ppe.helmet', 'SAFETY_HELMET', 71001, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72002, '反光衣检测', 'reflective-vest', 'CORE', '人员检测后判定反光衣属性，unknown 不强判违规', 'ppe.reflective-vest', 'REFLECTIVE_VEST', 71005, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72003, '吸烟检测', 'smoking-detection', 'CORE', '行为结果必须经过连续帧或持续时间确认', 'behavior.smoking', 'SMOKING', 71007, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72004, '打电话检测', 'phone-call-detection', 'CORE', '行为结果必须经过连续帧或持续时间确认', 'behavior.phone-call', 'PHONE_CALL', 71008, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72005, '人员闯入', 'person-intrusion', 'CORE', '复用 Person 与 Tracker，时间规则由 Rule 领域确认', 'rule.person-intrusion', 'PERSON_INTRUSION', 71003, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72006, '区域入侵', 'area-intrusion', 'CORE', '复用 Person/Vehicle、Tracker 与 Polygon ROI', 'rule.area-intrusion', 'AREA_INTRUSION', 71003, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72007, '跌倒检测', 'fall-detection', 'CORE', '跌倒行为必须经过时序确认', 'behavior.fall', 'FALL', 71011, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72008, '火焰检测', 'flame-detection', 'CORE', '无稳定 trackId 时按摄像头、任务、事件类型和时间窗口聚合', 'detector.flame', 'FLAME', 71006, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72009, '车辆检测', 'vehicle-detection', 'CORE', '自研共享 VehicleDetector/Tracker 能力', 'detector.vehicle', 'VEHICLE', NULL, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72010, '车牌识别', 'license-plate', 'CORE', 'Vehicle/Plate/OCR 多帧投票并按车辆短时去重', 'ocr.license-plate', 'LICENSE_PLATE', 71004, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72011, '人员离岗', 'person-absence', 'CORE', '复用 Person 与 Tracker，由人数缺失规则确认', 'rule.person-absence', 'PERSON_ABSENCE', 71003, JSON_OBJECT('schemaVersion','1.0','type','object'), JSON_OBJECT('schemaVersion','1.0','confidence',0.5), 0, 'system', 'system', 1),
(72012, '人员检测基础能力', 'person-detection-base', 'EXTENSION', 'Story 7 首个可运行受控 Pipeline，供后续规则与算法复用', 'detector.person', NULL, 71003,
 JSON_OBJECT('schemaVersion','1.0','type','object','required',JSON_ARRAY('schemaVersion','confidence','sampleFps')),
 JSON_OBJECT('schemaVersion','1.0','confidence',0.5,'nmsThreshold',0.5,'inputWidth',640,'inputHeight',640,'sampleFps',1.0), 0, 'system', 'system', 1);

INSERT INTO `ai_pipeline_version`
(`id`, `algorithm_id`, `version`, `dag`, `validation_status`, `published_time`, `creator`, `updater`, `tenant_id`)
VALUES
(72101, 72012, 1,
 JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
   JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person','input','VIDEO_FRAME','output','DETECTIONS')
 ),'edges',JSON_ARRAY()),
 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1);

UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72101 WHERE `id` = 72012;

START TRANSACTION;
INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7060, '算法中心', '', 2, 14, 7000, 'algorithm', 'lucide:workflow', 'ai-video/algorithm/index', 'AiVideoAlgorithm', 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7061, '算法查询', 'ai-video:algorithm:query', 3, 1, 7060, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7062, '算法新增', 'ai-video:algorithm:create', 3, 2, 7060, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7063, '算法修改', 'ai-video:algorithm:update', 3, 3, 7060, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7064, 'Pipeline 发布', 'ai-video:algorithm:publish', 3, 4, 7060, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7070, 'AI 任务中心', '', 2, 15, 7000, 'task', 'lucide:play-circle', 'ai-video/task/index', 'AiVideoTask', 0, b'1', b'0', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7071, '任务查询', 'ai-video:task:query', 3, 1, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7072, '任务新增', 'ai-video:task:create', 3, 2, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7073, '任务修改', 'ai-video:task:update', 3, 3, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7074, '任务启动', 'ai-video:task:start', 3, 4, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7075, '任务停止', 'ai-video:task:stop', 3, 5, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7076, '任务删除', 'ai-video:task:delete', 3, 6, 7070, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');
COMMIT;
