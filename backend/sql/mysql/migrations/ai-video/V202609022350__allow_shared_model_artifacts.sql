-- LInsight built-in model supply chain: allow one immutable artifact to back multiple logical models.
-- The original tenant-wide SHA uniqueness prevented person, vehicle and rule-based logical models
-- from sharing one general detector. Version identity remains unique inside each logical model.

ALTER TABLE `ai_model_version`
  DROP INDEX `uk_ai_model_version_tenant_sha_deleted`,
  ADD KEY `idx_ai_model_version_tenant_sha` (`tenant_id`, `sha256`);

