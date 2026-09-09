-- Declarative Runtime contract and recoverable catalog consolidation (ADR-0005).
ALTER TABLE `ai_model_version`
  ADD COLUMN `runtime_manifest` JSON NULL COMMENT '声明式模型执行契约' AFTER `artifact_format`;

SET @preprocess_rgb = JSON_OBJECT(
  'inputWidth', 640, 'inputHeight', 640, 'color', 'RGB', 'layout', 'NCHW',
  'dtype', 'FLOAT32', 'scale', 0.00392156862745098, 'mean', JSON_ARRAY(0,0,0),
  'std', JSON_ARRAY(1,1,1), 'resize', 'STRETCH');
SET @preprocess_bgr_raw = JSON_OBJECT(
  'inputWidth', 320, 'inputHeight', 240, 'color', 'BGR', 'layout', 'NCHW',
  'dtype', 'FLOAT32', 'scale', 1, 'mean', JSON_ARRAY(0,0,0),
  'std', JSON_ARRAY(1,1,1), 'resize', 'STRETCH');

SET @coco_labels = JSON_ARRAY(
  'person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic_light',
  'fire_hydrant','stop_sign','parking_meter','bench','bird','cat','dog','horse','sheep','cow',
  'elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee',
  'skis','snowboard','sports_ball','kite','baseball_bat','baseball_glove','skateboard','surfboard',
  'tennis_racket','bottle','wine_glass','cup','fork','knife','spoon','bowl','banana','apple',
  'sandwich','orange','broccoli','carrot','hot_dog','pizza','donut','cake','chair','couch',
  'potted_plant','bed','dining_table','toilet','tv','laptop','mouse','remote','keyboard','cell_phone',
  'microwave','oven','toaster','sink','refrigerator','book','clock','vase','scissors','teddy_bear',
  'hair_drier','toothbrush');

SET @manifest_coco = JSON_OBJECT(
  'schemaVersion','1.0','taskType','OBJECT_DETECTION','preprocess',@preprocess_rgb,
  'decoder',JSON_OBJECT('type','AUTO_DETECTION','labels',@coco_labels));
SET @manifest_ppe = JSON_OBJECT(
  'schemaVersion','1.0','taskType','OBJECT_DETECTION','preprocess',@preprocess_rgb,
  'decoder',JSON_OBJECT('type','AUTO_DETECTION',
    'labels',JSON_ARRAY('person','helmet','no_helmet','vest','no_vest','face_mask','no_face_mask','workwear','no_workwear','unknown')));
SET @manifest_fire = JSON_OBJECT(
  'schemaVersion','1.0','taskType','OBJECT_DETECTION','preprocess',@preprocess_rgb,
  'decoder',JSON_OBJECT('type','AUTO_DETECTION','labels',JSON_ARRAY('flame','smoke','dense_smoke')));
SET @manifest_plate_detector = JSON_OBJECT(
  'schemaVersion','1.0','taskType','OBJECT_DETECTION','preprocess',@preprocess_bgr_raw,
  'decoder',JSON_OBJECT('type','LPD_YUNET'));
SET @manifest_plate_ocr = JSON_OBJECT(
  'schemaVersion','1.0','taskType','OCR',
  'preprocess',JSON_OBJECT('inputWidth',94,'inputHeight',24,'color','BGR','layout','NCHW',
    'dtype','FLOAT32','scale',0.00784313725490196,'mean',JSON_ARRAY(1,1,1),
    'std',JSON_ARRAY(1,1,1),'resize','STRETCH'),
  'decoder',JSON_OBJECT('type','LPRNET'));

UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=@manifest_coco
WHERE m.code IN ('generic-coco-object-detection','person-detection','abandoned-removed-object')
  AND (v.artifact_name LIKE 'yolo11n%' OR v.artifact_name LIKE 'yolov8n.onnx');
UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=@manifest_ppe
WHERE m.code IN ('unified-ppe-detection','reflective-vest') AND v.artifact_name LIKE '%ppe%';
UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=@manifest_fire
WHERE m.code IN ('flame-smoke-detection','flame') AND v.artifact_name LIKE '%fire-smoke%';
UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=@manifest_plate_detector WHERE m.code='license-plate';
UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=@manifest_plate_ocr WHERE m.code='license-plate-ocr';

-- Select one executable, immutable artifact per consolidated capability. NOT_READY is retained
-- until the canonical logical version itself passes a node execution test.
UPDATE `ai_model_version` SET publish_status='SUPERSEDED'
WHERE model_id=71013 AND version<>'yolo11n-coco-rknn-zoo-bad6';
UPDATE `ai_model_version` SET publish_status='PUBLISHED', published_time=COALESCE(published_time,NOW())
WHERE model_id=71013 AND version='yolo11n-coco-rknn-zoo-bad6';
UPDATE `ai_model` SET current_version_id=(
  SELECT id FROM `ai_model_version` WHERE model_id=71013
    AND version='yolo11n-coco-rknn-zoo-bad6' AND deleted=b'0' LIMIT 1)
WHERE id=71013;

UPDATE `ai_model_version` SET publish_status='PUBLISHED', published_time=COALESCE(published_time,NOW())
WHERE (model_id=71014 AND version='yolov8n-ppe6-a2c1')
   OR (model_id=71019 AND version='yolov8s-fire-smoke-4adc');
UPDATE `ai_model` m SET current_version_id=(
  SELECT MIN(v.id) FROM `ai_model_version` v WHERE v.model_id=m.id AND v.publish_status='PUBLISHED'
) WHERE m.id IN (71014,71019);

-- Rebind only proven logical model aliases; preserve model/version rows for audit and rollback.
UPDATE `ai_algorithm` SET default_model_id=71013 WHERE default_model_id IN (71003,71021);
UPDATE `ai_algorithm` SET default_model_id=71014 WHERE default_model_id=71005;
UPDATE `ai_algorithm` SET default_model_id=71019 WHERE default_model_id=71006;
UPDATE `ai_model` SET status=1,
  description=CONCAT(description, ' [SUPERSEDED_BY_ADR_0005]')
WHERE id IN (71003,71005,71006,71021) AND status=0;

-- There are no fully equivalent algorithms after comparing event type + DAG + parameters.
-- Do not delete business-distinct compositions merely because they share a base detector.
