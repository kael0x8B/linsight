-- Forward repair for five license-plate OCR catalog Pipelines created by V202609022330.
-- The v1 rows remain immutable for audit. This migration creates structurally complete v2 rows
-- and switches only the current Pipeline pointer. Production remains blocked until the OCR Adapter exists.
-- Rollback: point algorithms 72315..72319 back to pipeline ids 82315..82319, then delete 82515..82519.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO ai_pipeline_version
(id, algorithm_id, version, dag, validation_status, published_time, creator, updater, tenant_id)
SELECT 82515 + (id - 72315), id, 2,
       JSON_OBJECT(
         'schemaVersion', '1.0',
         'nodes', JSON_ARRAY(
           JSON_OBJECT('id','plate-detector','type','DETECTOR','capabilityKey','detector.license-plate'),
           JSON_OBJECT('id','plate-ocr','type','OCR','capabilityKey','ocr.license-plate'),
           JSON_OBJECT('id','tracker','type','TRACKER','capabilityKey','tracker.iou')
         ),
         'edges', JSON_ARRAY(
           JSON_OBJECT('from','plate-detector','to','plate-ocr'),
           JSON_OBJECT('from','plate-ocr','to','tracker')
         ),
         'acceptance', JSON_OBJECT('status','BLOCKED_RUNTIME_ADAPTER')
       ),
       'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', tenant_id
FROM ai_algorithm
WHERE id BETWEEN 72315 AND 72319 AND deleted = b'0';

UPDATE ai_algorithm
SET current_pipeline_version_id = 82515 + (id - 72315),
    required_capabilities = JSON_ARRAY('detector.license-plate','ocr.license-plate','tracker.iou')
WHERE id BETWEEN 72315 AND 72319 AND deleted = b'0';
