-- One physical action-classification contract is shared by sleeping/calling/action algorithms.
SET @action_manifest = JSON_OBJECT(
  'schemaVersion','1.0','taskType','CLASSIFICATION',
  'preprocess',JSON_OBJECT(
    'inputWidth',224,'inputHeight',224,'color','RGB','layout','NCHW','dtype','FLOAT32',
    'scale',0.00392156862745098,'mean',JSON_ARRAY(0.5,0.5,0.5),
    'std',JSON_ARRAY(0.5,0.5,0.5),'resize','STRETCH'),
  'decoder',JSON_OBJECT(
    'type','CLASSIFICATION','labels',JSON_ARRAY(
      'calling','clapping','cycling','dancing','drinking','eating','fighting','hugging',
      'laughing','listening_music','running','sitting','sleeping','texting','using_laptop')));

UPDATE `ai_model_version`
SET runtime_manifest=@action_manifest, updater='system'
WHERE artifact_name='human-action-vit-int8.onnx' AND deleted=b'0';

-- A pose tensor is not an AUTO_DETECTION tensor. A previous model-level manifest assignment
-- is intentionally cleared; it will become deployable only after the pose protocol decoder exists.
UPDATE `ai_model_version` v JOIN `ai_model` m ON m.id=v.model_id
SET v.runtime_manifest=NULL, v.updater='system'
WHERE m.code='fall-detection' AND v.artifact_name='yolov8n-pose.onnx' AND v.deleted=b'0';
