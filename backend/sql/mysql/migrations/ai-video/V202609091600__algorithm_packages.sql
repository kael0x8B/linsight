-- Additive package object reference; old pipeline rows stay NULL and execute unchanged.
-- Preconditions: ai_pipeline_version exists. Metadata-only nullable-column addition.
-- Rollback: stop package tasks and roll back application; retain column and package objects.
SET @package_column_present = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_pipeline_version' AND COLUMN_NAME = 'package_artifact_ref');
SET @package_column_sql = IF(@package_column_present = 0, 'ALTER TABLE ai_pipeline_version ADD COLUMN package_artifact_ref VARCHAR(1024) NULL', 'SELECT 1');
PREPARE package_column_stmt FROM @package_column_sql;
EXECUTE package_column_stmt;
DEALLOCATE PREPARE package_column_stmt;
