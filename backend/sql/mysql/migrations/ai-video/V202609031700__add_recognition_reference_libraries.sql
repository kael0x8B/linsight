-- Preconditions: V202609031600 has been applied; ai_algorithm and system_menu exist.
-- Data/lock impact: creates two empty tenant tables, inserts three empty starter libraries and five menu rows.
-- Forward repair: disable the menu and libraries if the feature must be rolled back; do not drop populated tables.

CREATE TABLE `ai_recognition_library` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '识别参考库编号',
  `name` varchar(100) NOT NULL COMMENT '参考库名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定编码',
  `library_type` varchar(16) NOT NULL COMMENT 'FACE/PLATE/POSE',
  `description` varchar(500) NULL COMMENT '说明',
  `engine_model_version_id` bigint NULL COMMENT '特征提取或识别模型版本',
  `feature_dimension` int NULL COMMENT '特征向量维度',
  `match_mode` varchar(32) NOT NULL COMMENT 'ONE_TO_N/EXACT/CLASSIFICATION',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '0启用 1停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_recognition_library_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_recognition_library_tenant_type_status` (`tenant_id`, `library_type`, `status`),
  KEY `idx_ai_recognition_library_tenant_model_version` (`tenant_id`, `engine_model_version_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人脸车牌场景姿态识别参考库';

CREATE TABLE `ai_recognition_library_entry` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '识别参考条目编号',
  `library_id` bigint NOT NULL COMMENT '参考库编号',
  `name` varchar(100) NOT NULL COMMENT '条目名称',
  `external_code` varchar(100) NULL COMMENT '人员工号、车牌号或姿态编码',
  `media_ref` varchar(1000) NULL COMMENT '受控文件引用，不保存公开签名地址',
  `feature_status` varchar(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/READY/FAILED',
  `attributes` json NOT NULL COMMENT '类型相关属性，schemaVersion=1.0',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '0启用 1停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  KEY `idx_ai_recognition_entry_tenant_library_status` (`tenant_id`, `library_id`, `status`),
  KEY `idx_ai_recognition_entry_tenant_external_code` (`tenant_id`, `external_code`),
  KEY `idx_ai_recognition_entry_tenant_feature_status` (`tenant_id`, `feature_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='识别参考库条目';

INSERT INTO `ai_recognition_library`
(`id`, `name`, `code`, `library_type`, `description`, `feature_dimension`, `match_mode`, `status`,
 `creator`, `updater`, `tenant_id`)
VALUES
(73001, '默认人脸库', 'default-face-library', 'FACE', '人员身份、重点人员与访客的人脸特征参考库', 512, 'ONE_TO_N', 0, 'system', 'system', 1),
(73002, '默认车牌库', 'default-plate-library', 'PLATE', '授权、重点关注和临时车辆的车牌参考库', NULL, 'EXACT', 0, 'system', 'system', 1),
(73003, '默认场景姿态库', 'default-pose-library', 'POSE', '场景动作、姿态与风险等级参考库', NULL, 'CLASSIFICATION', 0, 'system', 'system', 1);

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7130, '识别参考库', '', 2, 19, 7000, 'recognition-library', 'lucide:library-big',
 'ai-video/recognition-library/index', 'AiVideoRecognitionLibrary', 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7131, '参考库查询', 'ai-video:library:query', 3, 1, 7130, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7132, '参考库新增', 'ai-video:library:create', 3, 2, 7130, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7133, '参考库修改', 'ai-video:library:update', 3, 3, 7130, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7134, '参考库删除', 'ai-video:library:delete', 3, 4, 7130, '', '', '', NULL, 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');
