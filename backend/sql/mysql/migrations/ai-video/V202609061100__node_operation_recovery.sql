-- Node operation coordination and observable deployment capture.
-- Preconditions: V202609042400. Additive migration; existing SSH content stays missing.
-- Impact: adds nullable metadata/indexes, one row per operation resource; brief metadata locks.
-- Forward repair: deploy compatible code; retain audit columns/table when reverting binaries.
ALTER TABLE ai_node_deployment
  ADD COLUMN resource_key varchar(160) NULL COMMENT 'Verified host/node operation key',
  ADD COLUMN request_id varchar(64) NULL,
  ADD COLUMN executor_owner varchar(64) NULL,
  ADD COLUMN log_status varchar(24) NOT NULL DEFAULT 'LEGACY',
  ADD COLUMN log_truncated bit(1) NOT NULL DEFAULT b'0',
  ADD COLUMN control_plane_url varchar(512) NULL,
  ADD COLUMN previous_version varchar(100) NULL,
  ADD UNIQUE KEY uk_deployment_request (tenant_id, request_id),
  ADD KEY idx_deployment_active_node (tenant_id, edge_node_id, status),
  ADD KEY idx_deployment_active_host (tenant_id, host, status);

CREATE TABLE ai_node_operation_mutex (
  tenant_id bigint NOT NULL,
  resource_key varchar(160) NOT NULL,
  PRIMARY KEY (tenant_id, resource_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE ai_node_upgrade
  MODIFY COLUMN status varchar(32) NOT NULL,
  ADD COLUMN activation_requested_at datetime NULL,
  ADD COLUMN previous_version varchar(100) NULL;
