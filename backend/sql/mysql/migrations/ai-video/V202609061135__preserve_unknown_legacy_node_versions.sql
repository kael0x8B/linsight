-- Old source hashes identify artifacts, not necessarily the version that an old installer expected.
-- Do not retroactively claim those historical operations performed target-version validation.
UPDATE ai_node_deployment SET target_version = NULL WHERE executor_owner IS NULL;
