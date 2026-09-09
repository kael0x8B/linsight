-- LInsight: persist sanitized SSH output for observable initial node deployment.
-- Preconditions: V202609031800 has added runtime_package_sha256 to ai_node_deployment.
-- Security: callers must redact credentials before appending; the column never stores SSH stdin.
-- Capacity: the application retains only the latest 256 KiB for each deployment.
-- Rollback: ALTER TABLE ai_node_deployment DROP COLUMN output_log;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `ai_node_deployment`
  ADD COLUMN `output_log` mediumtext NULL COMMENT '脱敏后的部署阶段与 SSH 输出'
  AFTER `message`;
