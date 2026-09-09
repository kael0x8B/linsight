-- LInsight Story 11: controlled Pipeline contracts for the remaining ten core algorithms.
-- These immutable Pipeline definitions do not bypass model version publish, license, deployment,
-- single-image execution, or field-accuracy gates. Missing external assets remain NOT_READY.
-- Rollback: clear current_pipeline_version_id for algorithms 72001..72005 and 72007..72011,
-- then delete pipeline versions 72103..72112.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO `ai_pipeline_version`
(`id`, `algorithm_id`, `version`, `dag`, `validation_status`, `published_time`, `creator`, `updater`, `tenant_id`)
VALUES
(72103, 72001, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person'),
  JSON_OBJECT('id','helmet-classifier','type','CLASSIFIER','capabilityKey','ppe.helmet'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','person-detector','to','helmet-classifier'),JSON_OBJECT('from','helmet-classifier','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','unknownPolicy','NO_ALARM')), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72104, 72002, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person'),
  JSON_OBJECT('id','vest-classifier','type','CLASSIFIER','capabilityKey','ppe.reflective-vest'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','person-detector','to','vest-classifier'),JSON_OBJECT('from','vest-classifier','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','unknownPolicy','NO_ALARM')), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72105, 72003, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','smoking-classifier','type','CLASSIFIER','capabilityKey','behavior.smoking'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','smoking-classifier','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','singleFrameAlarm',FALSE)), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72106, 72004, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','phone-classifier','type','CLASSIFIER','capabilityKey','behavior.phone-call'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','phone-classifier','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','singleFrameAlarm',FALSE)), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72107, 72005, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou'),
  JSON_OBJECT('id','intrusion-rule','type','RULE','capabilityKey','rule.person-intrusion')
),'edges',JSON_ARRAY(JSON_OBJECT('from','person-detector','to','iou-tracker'),JSON_OBJECT('from','iou-tracker','to','intrusion-rule'))),
 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72108, 72007, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','fall-classifier','type','CLASSIFIER','capabilityKey','behavior.fall'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','fall-classifier','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','temporalConfirmation',TRUE)), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72109, 72008, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','flame-detector','type','DETECTOR','capabilityKey','detector.flame')
),'edges',JSON_ARRAY(),'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','dedupScope','CAMERA_TASK_TYPE')), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72110, 72009, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','vehicle-detector','type','DETECTOR','capabilityKey','detector.vehicle'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','vehicle-detector','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_MODEL_IMPLEMENTATION')), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72111, 72010, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','plate-detector','type','DETECTOR','capabilityKey','detector.license-plate'),
  JSON_OBJECT('id','plate-ocr','type','OCR','capabilityKey','ocr.license-plate'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou')
),'edges',JSON_ARRAY(JSON_OBJECT('from','plate-detector','to','plate-ocr'),JSON_OBJECT('from','plate-ocr','to','iou-tracker')),
  'acceptance',JSON_OBJECT('status','BLOCKED_EXTERNAL_ASSETS','ocrVotingRequired',TRUE)), 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1),
(72112, 72011, 1, JSON_OBJECT('schemaVersion','1.0','nodes',JSON_ARRAY(
  JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person'),
  JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou'),
  JSON_OBJECT('id','absence-rule','type','RULE','capabilityKey','rule.person-absence')
),'edges',JSON_ARRAY(JSON_OBJECT('from','person-detector','to','iou-tracker'),JSON_OBJECT('from','iou-tracker','to','absence-rule'))),
 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1);

UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72103 WHERE `id` = 72001;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72104 WHERE `id` = 72002;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72105 WHERE `id` = 72003;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72106 WHERE `id` = 72004;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72107 WHERE `id` = 72005;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72108 WHERE `id` = 72007;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72109 WHERE `id` = 72008;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72110 WHERE `id` = 72009;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72111 WHERE `id` = 72010;
UPDATE `ai_algorithm` SET `current_pipeline_version_id` = 72112 WHERE `id` = 72011;
