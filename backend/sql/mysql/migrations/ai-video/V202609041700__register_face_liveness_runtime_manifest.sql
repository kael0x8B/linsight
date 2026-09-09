SET @liveness_manifest = JSON_OBJECT(
  'schemaVersion','1.0','taskType','CLASSIFICATION',
  'preprocess',JSON_OBJECT(
    'inputWidth',128,'inputHeight',128,'color','RGB','layout','NCHW','dtype','FLOAT32',
    'scale',0.00392156862745098,'mean',JSON_ARRAY(0,0,0),
    'std',JSON_ARRAY(1,1,1),'resize','STRETCH'),
  'decoder',JSON_OBJECT('type','CLASSIFICATION','labels',JSON_ARRAY('real','spoof')));
UPDATE `ai_model_version`
SET runtime_manifest=@liveness_manifest, updater='system'
WHERE artifact_name='face-antispoof-int8.onnx' AND deleted=b'0';
