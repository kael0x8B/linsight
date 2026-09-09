-- LInsight reverse preview channel: bind every saved video-wall layout to its execution node.
-- Preconditions: V202609031600__add_video_wall_layout.sql has completed.
-- Lock impact: one nullable column metadata change; schedule off peak for large installations.
-- Compatibility: existing layouts remain readable with node_id NULL and the UI selects a ready node.
-- Rollback: ALTER TABLE ai_video_wall_layout DROP COLUMN node_id;

ALTER TABLE `ai_video_wall_layout`
  ADD COLUMN `node_id` bigint NULL COMMENT '预览执行边缘节点编号' AFTER `split_count`;
