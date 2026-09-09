-- LInsight AI Video menu UTF-8 forward repair (MySQL 8.4)
-- Preconditions:
--   1. V202609011430, V202609011530 and V202609011700 have completed.
--   2. Menu IDs 7000-7031 retain their original LInsight meanings.
-- Data/lock impact: updates 19 fixed system_menu rows by primary key; no business table is locked.
-- Forward repair: rerun this idempotent statement with a utf8mb4 client connection.
-- Rollback: not applicable. The previous values were irreversibly mojibake-encoded names.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

START TRANSACTION;

UPDATE `system_menu`
SET `name` = CASE `id`
  WHEN 7000 THEN '视频分析'
  WHEN 7001 THEN '平台能力'
  WHEN 7002 THEN '平台能力查询'
  WHEN 7010 THEN '摄像头管理'
  WHEN 7011 THEN '摄像头查询'
  WHEN 7012 THEN '摄像头新增'
  WHEN 7013 THEN '摄像头修改'
  WHEN 7014 THEN '摄像头删除'
  WHEN 7015 THEN '摄像头导出'
  WHEN 7016 THEN '摄像头导入'
  WHEN 7017 THEN '连通检测'
  WHEN 7018 THEN '查看敏感配置'
  WHEN 7020 THEN '边缘节点'
  WHEN 7021 THEN '节点查询'
  WHEN 7022 THEN '节点注册'
  WHEN 7023 THEN '节点修改'
  WHEN 7024 THEN '节点升级'
  WHEN 7030 THEN '实时预览'
  WHEN 7031 THEN '摄像头预览'
  ELSE `name`
END,
`updater` = 'system',
`update_time` = CURRENT_TIMESTAMP
WHERE `id` IN (
  7000, 7001, 7002,
  7010, 7011, 7012, 7013, 7014, 7015, 7016, 7017, 7018,
  7020, 7021, 7022, 7023, 7024,
  7030, 7031
);

COMMIT;
