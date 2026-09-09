-- LInsight: bind every platform deployment to the exact Runtime archive sent to the node.
-- Preconditions: V202609030200 has created ai_node_deployment.
-- Security: the digest is non-secret and contains no SSH or Runtime credentials.
-- Rollback: ALTER TABLE ai_node_deployment DROP COLUMN runtime_package_sha256;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE `ai_node_deployment`
  ADD COLUMN `runtime_package_sha256` char(64) NULL COMMENT '平台上传 Runtime ZIP 的 SHA256'
  AFTER `python_version`;
