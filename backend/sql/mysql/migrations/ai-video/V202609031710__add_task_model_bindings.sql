-- Preconditions: V202609031700 has been applied and ai_task contains the legacy model_version_id column.
-- Data/lock impact: adds one nullable JSON column, backfills one binding per existing task, then makes it required.
-- Forward repair: keep model_version_id as the primary compatibility binding; do not drop model_bindings after tasks use multiple models.

ALTER TABLE `ai_task`
  ADD COLUMN `model_bindings` json NULL COMMENT 'Pipeline 节点 ID 到模型版本 ID 的动态绑定' AFTER `model_version_id`;

UPDATE `ai_task`
SET `model_bindings` = JSON_OBJECT('primary', `model_version_id`)
WHERE `model_bindings` IS NULL;

ALTER TABLE `ai_task`
  MODIFY COLUMN `model_bindings` json NOT NULL COMMENT 'Pipeline 节点 ID 到模型版本 ID 的动态绑定';
