-- Keep static inventory generation aligned with the model/algorithm rows retired by V202609041800.
-- inventory-retired-algorithm-ids: 72003,72256,72257,72258,72259,72260,72261,72262,72263,72264,72265,72266,72267,72268,72269,72270,72271,72272,72273,72274,72275,72276,72277,72303,72304,72305,72306,72307,72308,72309,72310,72344,72345,72346,72347,72348,72349,72350,72351,72352,72353,72354,72358,72359,72360,72361,72362,72363,72364,72365,72366,72367,72368,72369,72370,72371,72372,72373,72374,72375,72376,72377,72378,72379,72380,72381,72382,72383,72384,72385,72386,72387,72388,72389,72390,72391,72392,72393,72394,72395,72396,72397,72398,72399,72400,72401,72402

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Defensive forward repair for databases where custom data was inserted while the earlier migration ran.
UPDATE `ai_pipeline_version` p
JOIN `ai_algorithm` a ON a.id = p.algorithm_id
JOIN `ai_model` m ON m.id = a.default_model_id
SET p.validation_status = 'DRAFT', p.deleted = b'1', p.updater = 'system'
WHERE p.deleted = b'0' AND m.deleted = b'1';

UPDATE `ai_algorithm` a
JOIN `ai_model` m ON m.id = a.default_model_id
SET a.current_pipeline_version_id = NULL, a.status = 1, a.deleted = b'1', a.updater = 'system'
WHERE a.deleted = b'0' AND m.deleted = b'1';
