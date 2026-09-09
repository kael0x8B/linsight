-- Continue ADR-0005 consolidation: algorithms own semantics; models own reusable tensors.
UPDATE `ai_algorithm` SET default_model_id=71014 WHERE default_model_id=71001;
UPDATE `ai_algorithm` SET default_model_id=71016 WHERE default_model_id IN (71002,71008);
UPDATE `ai_algorithm` SET default_model_id=71029 WHERE default_model_id=71007;

UPDATE `ai_model` SET status=1,
  description=CONCAT(description, ' [SUPERSEDED_BY_ADR_0005]')
WHERE id IN (71001,71002,71007,71008) AND status=0;

UPDATE `ai_model_version` SET publish_status='PUBLISHED',
  published_time=COALESCE(published_time,NOW()), updater='system'
WHERE model_id=71016 AND version='human-action-vit-int8-43fb' AND deleted=b'0';
UPDATE `ai_model` SET current_version_id=(
  SELECT id FROM `ai_model_version` WHERE model_id=71016
    AND version='human-action-vit-int8-43fb' AND deleted=b'0' LIMIT 1)
WHERE id=71016;

-- Old alias versions remain immutable evidence but are not selectable as production heads.
UPDATE `ai_model_version` SET publish_status='SUPERSEDED', updater='system'
WHERE model_id IN (71001,71002,71007,71008) AND publish_status='PUBLISHED' AND deleted=b'0';
