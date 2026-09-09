-- LInsight Story 11 forward-only parameter contract repair.
-- Makes Runtime-enforced PPE thresholds, behavior temporal confirmation and OCR voting
-- explicit in the control-plane schema/defaults. Published Pipeline rows remain immutable.
-- Rollback: restore algorithm parameter_schema/default_parameters from the previous release backup.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

UPDATE `ai_algorithm`
SET `parameter_schema` = JSON_OBJECT(
      'schemaVersion','1.0','type','object',
      'required',JSON_ARRAY('schemaVersion','confidence','personConfidence','ppeConfidence','unknownPolicy','sampleFps'),
      'properties',JSON_OBJECT(
        'confidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'personConfidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'ppeConfidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'unknownPolicy',JSON_OBJECT('type','string','const','NO_ALARM'),
        'sampleFps',JSON_OBJECT('type','number','minimum',0.1,'maximum',10)
      )
    ),
    `default_parameters` = JSON_OBJECT(
      'schemaVersion','1.0','confidence',0.5,'nmsThreshold',0.5,
      'inputWidth',640,'inputHeight',640,'sampleFps',5.0,
      'personConfidence',0.5,'ppeConfidence',0.5,'unknownPolicy','NO_ALARM'
    )
WHERE `id` IN (72001, 72002);

UPDATE `ai_algorithm`
SET `parameter_schema` = JSON_OBJECT(
      'schemaVersion','1.0','type','object',
      'required',JSON_ARRAY('schemaVersion','confidence','temporalN','temporalM','durationSeconds','sampleFps'),
      'properties',JSON_OBJECT(
        'confidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'temporalN',JSON_OBJECT('type','integer','minimum',2,'maximum',30),
        'temporalM',JSON_OBJECT('type','integer','minimum',2,'maximum',60),
        'durationSeconds',JSON_OBJECT('type','number','exclusiveMinimum',0,'maximum',300),
        'sampleFps',JSON_OBJECT('type','number','minimum',0.1,'maximum',10)
      )
    ),
    `default_parameters` = JSON_OBJECT(
      'schemaVersion','1.0','confidence',0.5,'nmsThreshold',0.5,
      'inputWidth',640,'inputHeight',640,'sampleFps',5.0,
      'temporalN',3,'temporalM',5,'durationSeconds',2.0
    )
WHERE `id` IN (72003, 72004, 72007);

UPDATE `ai_algorithm`
SET `parameter_schema` = JSON_OBJECT(
      'schemaVersion','1.0','type','object',
      'required',JSON_ARRAY('schemaVersion','confidence','ocrVoteFrames','ocrMinVotes','sampleFps'),
      'properties',JSON_OBJECT(
        'confidence',JSON_OBJECT('type','number','minimum',0.01,'maximum',1),
        'ocrVoteFrames',JSON_OBJECT('type','integer','minimum',2,'maximum',30),
        'ocrMinVotes',JSON_OBJECT('type','integer','minimum',2,'maximum',30),
        'sampleFps',JSON_OBJECT('type','number','minimum',0.1,'maximum',10)
      )
    ),
    `default_parameters` = JSON_OBJECT(
      'schemaVersion','1.0','confidence',0.5,'nmsThreshold',0.5,
      'inputWidth',640,'inputHeight',640,'sampleFps',5.0,
      'ocrVoteFrames',5,'ocrMinVotes',3
    )
WHERE `id` = 72010;

UPDATE `ai_algorithm`
SET `default_parameters` = JSON_SET(
      `default_parameters`,
      '$.nmsThreshold', 0.5,
      '$.inputWidth', 640,
      '$.inputHeight', 640,
      '$.sampleFps', 5.0
    )
WHERE `id` IN (72005, 72008, 72009, 72011);
