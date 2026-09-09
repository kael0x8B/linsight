-- Runtime owns rule-window and track deduplication. The control plane keeps active_dedup_key
-- searchable, but source_event_id is the only idempotency key so sequential offline activities
-- are not collapsed before their close transitions replay.
-- Rollback: drop idx_ai_event_tenant_active_dedup and recreate
-- uk_ai_event_tenant_active_dedup_deleted(tenant_id, active_dedup_key, deleted) only after
-- proving no duplicate non-null active keys exist.
SET NAMES utf8mb4;

ALTER TABLE `ai_event`
  DROP INDEX `uk_ai_event_tenant_active_dedup_deleted`,
  ADD INDEX `idx_ai_event_tenant_active_dedup`
    (`tenant_id`, `active_dedup_key`, `deleted`);
