-- Remove model families that do not have a verified Runtime execution contract.
-- The platform uses logical deletion so historical task/event/test/deployment evidence remains auditable.
-- Active catalog after this migration contains only models that can be loaded by the current Runtime.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

START TRANSACTION;

-- A task configured with a removed algorithm must never be restarted accidentally. Historical task-run
-- and event rows are retained, while the task itself is removed from active configuration screens.
UPDATE `ai_task`
SET `desired_status` = 'STOPPED',
    `actual_status` = 'FAILED',
    `active_run_id` = NULL,
    `error_code` = 'MODEL_CATALOG_REMOVED',
    `error_message` = '模型及算法因缺少可验证 Runtime 执行协议已从生产目录移除',
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `algorithm_id` IN (
    SELECT `id`
    FROM `ai_algorithm`
    WHERE `deleted` = b'0'
      AND `default_model_id` IN (71010, 71012, 71015, 71017, 71022, 71024, 71025, 71026, 71027, 71028, 71029)
  );

UPDATE `ai_pipeline_version`
SET `validation_status` = 'DRAFT',
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `algorithm_id` IN (
    SELECT `id`
    FROM `ai_algorithm`
    WHERE `deleted` = b'0'
      AND `default_model_id` IN (71010, 71012, 71015, 71017, 71022, 71024, 71025, 71026, 71027, 71028, 71029)
  );

UPDATE `ai_algorithm`
SET `current_pipeline_version_id` = NULL,
    `status` = 1,
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `default_model_id` IN (71010, 71012, 71015, 71017, 71022, 71024, 71025, 71026, 71027, 71028, 71029);

UPDATE `ai_model_version`
SET `publish_status` = 'SUPERSEDED',
    `execution_status` = 'NOT_READY',
    `execution_ready_time` = NULL,
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `model_id` IN (71010, 71012, 71015, 71017, 71022, 71024, 71025, 71026, 71027, 71028, 71029);

UPDATE `ai_model`
SET `current_version_id` = NULL,
    `status` = 1,
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `id` IN (71010, 71012, 71015, 71017, 71022, 71024, 71025, 71026, 71027, 71028, 71029);

COMMIT;
