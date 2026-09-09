-- LInsight Story 10: first complete Area Intrusion vertical sample.
-- Preconditions: V202609021600 has completed and algorithm 72006/model asset 71003 exist.
-- Data/lock impact: inserts one immutable Pipeline version and updates one algorithm pointer/schema.
-- Rollback: set ai_algorithm.current_pipeline_version_id NULL for id 72006, then delete pipeline 72102.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO `ai_pipeline_version`
(`id`, `algorithm_id`, `version`, `dag`, `validation_status`, `published_time`, `creator`, `updater`, `tenant_id`)
VALUES
(72102, 72006, 1,
 JSON_OBJECT(
   'schemaVersion', '1.0',
   'nodes', JSON_ARRAY(
     JSON_OBJECT('id','person-detector','type','DETECTOR','capabilityKey','detector.person','input','VIDEO_FRAME','output','DETECTIONS'),
     JSON_OBJECT('id','iou-tracker','type','TRACKER','capabilityKey','tracker.iou','input','DETECTIONS','output','TRACKS'),
     JSON_OBJECT('id','area-rule','type','RULE','capabilityKey','rule.area-intrusion','input','TRACKS','output','EVENT_TRANSITIONS')
   ),
   'edges', JSON_ARRAY(
     JSON_OBJECT('from','person-detector','to','iou-tracker'),
     JSON_OBJECT('from','iou-tracker','to','area-rule')
   )
 ),
 'PUBLISHED', CURRENT_TIMESTAMP, 'system', 'system', 1);

UPDATE `ai_algorithm`
SET `current_pipeline_version_id` = 72102,
    `parameter_schema` = JSON_OBJECT(
      'schemaVersion','1.0','type','object',
      'required',JSON_ARRAY('schemaVersion','confidence','nmsThreshold','sampleFps'),
      'properties',JSON_OBJECT(
        'confidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'nmsThreshold',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'sampleFps',JSON_OBJECT('type','number','minimum',0.1,'maximum',10)
      )
    ),
    `default_parameters` = JSON_OBJECT(
      'schemaVersion','1.0','confidence',0.5,'nmsThreshold',0.5,
      'inputWidth',640,'inputHeight',640,'sampleFps',5.0
    ),
    `description` = 'Person Detection → IoU Tracker → Polygon ROI Rule；3/5 帧且持续 2 秒确认，输出事件证据与处置闭环'
WHERE `id` = 72006;
