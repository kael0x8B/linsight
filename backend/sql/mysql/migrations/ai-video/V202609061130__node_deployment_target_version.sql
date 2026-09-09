-- Explicit expected version in the durable operation; older packages already carry a source SHA.
ALTER TABLE ai_node_deployment ADD COLUMN target_version varchar(64) NULL;
UPDATE ai_node_deployment
SET target_version = CONCAT('source-', LEFT(runtime_package_sha256, 12))
WHERE runtime_package_sha256 IS NOT NULL;
