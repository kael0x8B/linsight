-- LInsight Story 5: model assets, immutable versions and publication gates (MySQL 8.4)
-- Preconditions: V202609011430__init_ai_video_module.sql has completed.
-- Data/lock impact: creates two empty business tables, inserts 12 preset assets for the baseline tenant,
--   and inserts seven menu metadata rows. DDL takes brief metadata locks only.
-- Forward repair: correct conflicting menu IDs 7040-7046 or preset model codes, then rerun failed statements.
-- Rollback (only before model versions or task references exist):
--   DELETE FROM system_role_menu WHERE menu_id BETWEEN 7040 AND 7046;
--   DELETE FROM system_menu WHERE id BETWEEN 7040 AND 7046;
--   DROP TABLE ai_model_version;
--   DROP TABLE ai_model;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE `ai_model` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '模型资产编号',
  `name` varchar(100) NOT NULL COMMENT '模型名称',
  `code` varchar(64) NOT NULL COMMENT '租户内稳定模型编码',
  `source_type` varchar(32) NOT NULL COMMENT '来源类型：PRESET/CUSTOM',
  `description` varchar(500) NULL COMMENT '模型说明',
  `current_version_id` bigint NULL COMMENT '当前生产版本编号',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态：0 启用，1 停用',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_model_tenant_code_deleted` (`tenant_id`, `code`, `deleted`),
  KEY `idx_ai_model_tenant_source_status` (`tenant_id`, `source_type`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频模型资产';

CREATE TABLE `ai_model_version` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '模型版本编号',
  `model_id` bigint NOT NULL COMMENT '模型资产编号',
  `version` varchar(64) NOT NULL COMMENT '不可变版本标识',
  `source_repository` varchar(500) NULL COMMENT '来源仓库',
  `source_revision` varchar(128) NULL COMMENT '固定 commit 或 tag',
  `artifact_ref` varchar(1000) NOT NULL COMMENT '对象存储内部引用，不是永久公开地址',
  `artifact_name` varchar(255) NOT NULL COMMENT '原始文件名',
  `artifact_format` varchar(32) NOT NULL COMMENT '模型格式',
  `artifact_size` bigint NOT NULL COMMENT '文件字节数',
  `sha256` char(64) NOT NULL COMMENT '文件 SHA256',
  `license_spdx` varchar(128) NOT NULL COMMENT 'SPDX 许可证或明确的 PROPRIETARY',
  `commercial_approved` bit(1) NOT NULL DEFAULT b'0' COMMENT '商业使用审核是否通过',
  `validation_status` varchar(32) NOT NULL COMMENT '格式校验状态：VERIFIED/REJECTED',
  `publish_status` varchar(32) NOT NULL DEFAULT 'DRAFT' COMMENT '发布状态：DRAFT/PUBLISHED/SUPERSEDED',
  `published_time` datetime NULL COMMENT '发布时间',
  `creator` varchar(64) NOT NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) NOT NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ai_model_version_tenant_model_version_deleted` (`tenant_id`, `model_id`, `version`, `deleted`),
  UNIQUE KEY `uk_ai_model_version_tenant_sha_deleted` (`tenant_id`, `sha256`, `deleted`),
  KEY `idx_ai_model_version_tenant_model_time` (`tenant_id`, `model_id`, `create_time`),
  KEY `idx_ai_model_version_tenant_publish` (`tenant_id`, `publish_status`, `published_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI 视频不可变模型版本';

INSERT INTO `ai_model`
(`id`, `name`, `code`, `source_type`, `description`, `status`, `creator`, `updater`, `tenant_id`)
VALUES
(71001, 'Safety Helmet Model', 'safety-helmet', 'PRESET', '安全帽检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71002, 'Sleeping on Duty Model', 'sleeping-on-duty', 'PRESET', '睡岗检测预置扩展资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71003, 'Person Detection Model', 'person-detection', 'PRESET', '人员检测共享基础能力；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71004, 'License Plate Model', 'license-plate', 'PRESET', '车牌检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71005, 'Reflective Vest Model', 'reflective-vest', 'PRESET', '反光衣检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71006, 'Flame Model', 'flame', 'PRESET', '火焰检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71007, 'Smoking Detection Model', 'smoking-detection', 'PRESET', '吸烟检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71008, 'Phone Call Detection Model', 'phone-call-detection', 'PRESET', '打电话检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71009, 'Road Waterlogging Model', 'road-waterlogging', 'PRESET', '道路积水预置扩展资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71010, 'Face Mask Model', 'face-mask', 'PRESET', '口罩检测预置扩展资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71011, 'Fall Detection Model', 'fall-detection', 'PRESET', '跌倒检测预置资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1),
(71012, 'Face Detection Model', 'face-detection', 'PRESET', '人脸检测预置扩展资产；版本文件与许可证待供应链确认', 0, 'system', 'system', 1);

START TRANSACTION;

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`,
 `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
VALUES
(7040, '模型资产', '', 2, 12, 7000, 'model', 'lucide:brain-circuit', 'ai-video/model/index', 'AiVideoModel',
 0, b'1', b'1', b'1', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7041, '模型查询', 'ai-video:model:query', 3, 1, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7042, '模型新增', 'ai-video:model:create', 3, 2, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7043, '模型修改', 'ai-video:model:update', 3, 3, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7044, '模型删除', 'ai-video:model:delete', 3, 4, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7045, '版本上传', 'ai-video:model:upload', 3, 5, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0'),
(7046, '版本发布', 'ai-video:model:publish', 3, 6, 7040, '', '', '', NULL,
 0, b'0', b'0', b'0', 'system', CURRENT_TIMESTAMP, 'system', CURRENT_TIMESTAMP, b'0');

COMMIT;
