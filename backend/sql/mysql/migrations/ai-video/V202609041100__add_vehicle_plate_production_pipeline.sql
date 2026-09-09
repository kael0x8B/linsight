-- Forward-only production acceptance repair for vehicle/plate recognition.
-- Existing immutable pipeline rows are retained for audit. The new rows deliberately remain
-- blocked until the exact detector weights, hashes and real field benchmark are accepted.
-- Rollback: restore the previous current_pipeline_version_id values, then delete these rows.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO ai_pipeline_version
(id, algorithm_id, version, dag, validation_status, published_time, creator, updater, tenant_id)
VALUES
(82610, 72010, 2, JSON_OBJECT(
  'schemaVersion','1.0',
  'nodes',JSON_ARRAY(
    JSON_OBJECT('id','vehicle-detector','type','DETECTOR','capabilityKey','detector.vehicle','modelId',71013),
    JSON_OBJECT('id','plate-detector','type','DETECTOR','capabilityKey','detector.license-plate','modelId',71004),
    JSON_OBJECT('id','plate-ocr','type','OCR','capabilityKey','ocr.license-plate','modelId',71018),
    JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
  ),
  'edges',JSON_ARRAY(
    JSON_OBJECT('from','vehicle-detector','to','iou-tracker'),
    JSON_OBJECT('from','plate-detector','to','plate-ocr'),
    JSON_OBJECT('from','plate-ocr','to','iou-tracker')
  ),
  'acceptance',JSON_OBJECT(
    'status','BLOCKED_EXTERNAL_ASSETS',
    'reason','WAITING_FOR_REAL_DATA_AND_VERIFIED_VEHICLE_PLATE_DETECTOR_WEIGHTS',
    'ocrVotingRequired',TRUE,
    'minimumOcrVotes',2
  )
), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1);

INSERT INTO ai_pipeline_version
(id, algorithm_id, version, dag, validation_status, published_time, creator, updater, tenant_id)
SELECT 82615 + (id - 72315), id, 3, JSON_OBJECT(
  'schemaVersion','1.0',
  'nodes',JSON_ARRAY(
    JSON_OBJECT('id','vehicle-detector','type','DETECTOR','capabilityKey','detector.vehicle','modelId',71013),
    JSON_OBJECT('id','plate-detector','type','DETECTOR','capabilityKey','detector.license-plate','modelId',71004),
    JSON_OBJECT('id','plate-ocr','type','OCR','capabilityKey','ocr.license-plate','modelId',71018),
    JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
  ),
  'edges',JSON_ARRAY(
    JSON_OBJECT('from','vehicle-detector','to','iou-tracker'),
    JSON_OBJECT('from','plate-detector','to','plate-ocr'),
    JSON_OBJECT('from','plate-ocr','to','iou-tracker')
  ),
  'acceptance',JSON_OBJECT(
    'status','BLOCKED_EXTERNAL_ASSETS',
    'reason','WAITING_FOR_REAL_DATA_AND_VERIFIED_VEHICLE_PLATE_DETECTOR_WEIGHTS',
    'ocrVotingRequired',TRUE,
    'minimumOcrVotes',2
  )
), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', tenant_id
FROM ai_algorithm
WHERE id BETWEEN 72315 AND 72319 AND deleted = b'0';

UPDATE ai_algorithm
SET current_pipeline_version_id = 82610,
    implementation_type = 'COMPOSITE',
    required_capabilities = JSON_ARRAY(
      'detector.vehicle','detector.license-plate','ocr.license-plate','tracker.iou'
    )
WHERE id = 72010 AND deleted = b'0';

UPDATE ai_algorithm
SET current_pipeline_version_id = 82615 + (id - 72315),
    implementation_type = 'COMPOSITE',
    required_capabilities = JSON_ARRAY(
      'detector.vehicle','detector.license-plate','ocr.license-plate','tracker.iou'
    )
WHERE id BETWEEN 72315 AND 72319 AND deleted = b'0';
