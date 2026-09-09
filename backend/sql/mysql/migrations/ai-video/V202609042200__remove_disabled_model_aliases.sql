-- Remove superseded model aliases from the active model catalog.
-- Model versions and their task/deployment/test evidence remain immutable for audit and
-- for the currently running task that still references the old person-detection version.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

START TRANSACTION;

UPDATE `ai_model`
SET `current_version_id` = NULL,
    `deleted` = b'1',
    `updater` = 'system'
WHERE `deleted` = b'0'
  AND `source_type` = 'PRESET'
  AND `status` = 1
  AND `code` IN (
    'safety-helmet',
    'sleeping-on-duty',
    'person-detection',
    'reflective-vest',
    'flame',
    'smoking-detection',
    'phone-call-detection',
    'abandoned-removed-object'
  );

COMMIT;
