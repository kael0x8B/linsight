-- Additive per-tenant/user camera display preferences. No task/rule settings change.
-- Forward repair: CREATE IF NOT EXISTS is replay safe. Rollback: stop writes and archive this table first.
CREATE TABLE IF NOT EXISTS ai_camera_display_preference (
 id bigint NOT NULL AUTO_INCREMENT, user_id bigint NOT NULL, camera_id bigint NOT NULL,
 hidden_layers_json json NOT NULL,
 creator varchar(64) NOT NULL DEFAULT '', create_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updater varchar(64) NOT NULL DEFAULT '', update_time datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 deleted bit(1) NOT NULL DEFAULT b'0', tenant_id bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(id), UNIQUE KEY uk_camera_display_owner(tenant_id,user_id,camera_id,deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='摄像头用户图层显示偏好';
